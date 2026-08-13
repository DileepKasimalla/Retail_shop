import { ApiError, getToken } from "../api/client";

/**
 * Images need an auth header, so they can't go straight into <img src>.
 * We fetch them once, keep the object URL for the life of the page, and hand
 * the same URL back on later renders — so scrolling and navigating never
 * re-download a photo. The `version` in the key means a replaced photo still
 * gets picked up straight away.
 */
const urls = new Map<string, string>();
const inflight = new Map<string, Promise<string>>();

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function download(path: string, key: string): Promise<string> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { headers });
  if (!res.ok) throw new ApiError(res.status, "Could not load image");
  const url = URL.createObjectURL(await res.blob());
  urls.set(key, url);
  inflight.delete(key);
  return url;
}

function load(path: string, key: string): string | Promise<string> {
  const cached = urls.get(key);
  if (cached) return cached;
  let pending = inflight.get(key);
  if (!pending) {
    // Dedupe: a grid of cards asking for the same photo makes one request.
    pending = download(path, key).catch((e) => {
      inflight.delete(key);
      throw e;
    });
    inflight.set(key, pending);
  }
  return pending;
}

export function loadProductImage(id: number, version: string) {
  const key = `p:${id}:${version}`;
  return load(`/api/products/${id}/image?v=${encodeURIComponent(version)}`, key);
}

export function loadCategoryImage(name: string, version: string) {
  const key = `c:${name}:${version}`;
  return load(
    `/api/categories/image?name=${encodeURIComponent(name)}&v=${encodeURIComponent(version)}`,
    key,
  );
}

/** Drop everything (used on logout so images aren't left in memory). */
export function clearImageCache(): void {
  for (const url of urls.values()) URL.revokeObjectURL(url);
  urls.clear();
  inflight.clear();
}
