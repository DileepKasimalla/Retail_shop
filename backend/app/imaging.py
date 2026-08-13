"""Image processing and safe fetching of images from user-supplied URLs."""
from __future__ import annotations

import hashlib
import io
import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

from fastapi import HTTPException, status

MAX_IMAGE_BYTES = 6 * 1024 * 1024   # accept up to 6 MB from a camera/phone
THUMB_SIZE = (512, 512)             # stored size after resizing
FETCH_TIMEOUT = 8                   # seconds per request
MAX_REDIRECTS = 3


def image_response(data: bytes, content_type: str, request, versioned: bool = False) -> "Response":
    """Serve image bytes with an ETag so browsers pick up replacements at once.

    When the caller passes a `?v=` version in the URL the content can never
    change behind that URL, so we let the browser keep it for a year — a page
    refresh then paints from disk with no network call at all. Without a
    version we fall back to `no-cache` (cache, but revalidate every time), which
    still shows re-imported photos immediately at the cost of a small 304.
    """
    from fastapi import Response

    etag = '"' + hashlib.md5(data).hexdigest() + '"'
    cache = (
        "private, max-age=31536000, immutable" if versioned else "private, no-cache"
    )
    headers = {"ETag": etag, "Cache-Control": cache}
    if request is not None and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=content_type, headers=headers)


def process_image(raw: bytes) -> tuple[bytes, str]:
    """Validate and re-encode an image to a small JPEG thumbnail.

    Re-encoding is the security boundary: anything that isn't a real, decodable
    image is rejected, and any embedded metadata/payload is discarded.
    """
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large (max 6 MB).",
        )

    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()                       # reject anything that isn't a real image
        img = Image.open(io.BytesIO(raw))  # verify() exhausts the file, so reopen
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file isn't a readable image. Use a JPG, PNG or WEBP.",
        )

    img.thumbnail(THUMB_SIZE)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue(), "image/jpeg"


class UnsafeUrlError(ValueError):
    """Raised when a URL is not allowed to be fetched server-side."""


def _assert_public_host(hostname: str | None) -> None:
    """Block SSRF: refuse loopback / private / link-local / reserved addresses."""
    if not hostname:
        raise UnsafeUrlError("URL has no host")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise UnsafeUrlError("Could not resolve that address")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeUrlError("That address is not allowed")


def validate_image_url(url: str) -> str:
    """Check the scheme and that the host resolves to a public address."""
    url = (url or "").strip()
    if not url:
        raise UnsafeUrlError("Enter an image URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http:// and https:// links are supported")
    _assert_public_host(parsed.hostname)
    return url


def fetch_image_bytes(url: str) -> bytes:
    """Download an image from a public URL, with redirect and size limits."""
    current = validate_image_url(url)

    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(
            current,
            headers={"User-Agent": "RetailShopManager/1.0", "Accept": "image/*"},
        )
        # Handle redirects ourselves so every hop is re-validated against SSRF.
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            resp = opener.open(req, timeout=FETCH_TIMEOUT)
        except _Redirect as redirect:
            current = validate_image_url(redirect.location)
            continue
        except Exception:
            raise UnsafeUrlError("Could not download the image from that link")

        with resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype and not ctype.startswith("image/"):
                raise UnsafeUrlError(f"That link is not an image ({ctype or 'unknown type'})")
            data = resp.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise UnsafeUrlError("Image too large (max 6 MB)")
            return data

    raise UnsafeUrlError("Too many redirects")


class _Redirect(Exception):
    def __init__(self, location: str):
        self.location = location


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn redirects into an exception so the caller can re-validate the target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise _Redirect(newurl)
