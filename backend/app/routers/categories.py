"""Category tile images.

Categories are just a name on each product, so their pictures live in their own
small table keyed by that name. The name is passed as a query parameter (not a
path segment) so names containing spaces or slashes work without escaping.
"""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..imaging import UnsafeUrlError, fetch_image_bytes, image_response, process_image
from ..models import CategoryImage
from ..schemas import CategoryImageInfo, ImageUrlIn

router = APIRouter(
    prefix="/api/categories",
    tags=["categories"],
    dependencies=[Depends(get_current_user)],
)


def _clean(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is required")
    return name[:60]


def _get(db: Session, name: str) -> CategoryImage | None:
    return db.execute(
        select(CategoryImage).where(CategoryImage.name == name)
    ).scalar_one_or_none()


def _save(db: Session, name: str, raw: bytes) -> None:
    data, ctype = process_image(raw)
    row = _get(db, name)
    if row is None:
        row = CategoryImage(name=name, image_data=data, image_type=ctype)
    else:
        row.image_data, row.image_type = data, ctype
    db.add(row)
    db.commit()


@router.get("/images", response_model=list[CategoryImageInfo])
def list_categories_with_images(db: Session = Depends(get_db)) -> list[CategoryImageInfo]:
    """Categories that have a picture, with a version for cache-busting.

    Selects only the name/timestamp columns — never the image bytes.
    """
    rows = db.execute(select(CategoryImage.name, CategoryImage.updated_at)).all()
    return [
        CategoryImageInfo(name=n, version=str(int(t.timestamp())) if t else "0")
        for n, t in rows
    ]


@router.get("/image")
def get_category_image(
    request: Request,
    name: str = Query(..., max_length=60),
    v: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    row = _get(db, _clean(name))
    if row is None:
        raise HTTPException(status_code=404, detail="No image for this category")
    return image_response(row.image_data, row.image_type, request, versioned=v is not None)


@router.post("/image", status_code=status.HTTP_204_NO_CONTENT)
async def upload_category_image(
    name: str = Query(..., max_length=60),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> None:
    _save(db, _clean(name), await file.read())


@router.post("/image/from-url", status_code=status.HTTP_204_NO_CONTENT)
def set_category_image_from_url(
    payload: ImageUrlIn,
    name: str = Query(..., max_length=60),
    db: Session = Depends(get_db),
) -> None:
    try:
        raw = fetch_image_bytes(payload.url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    _save(db, _clean(name), raw)


@router.delete("/image", status_code=status.HTTP_204_NO_CONTENT)
def delete_category_image(
    name: str = Query(..., max_length=60), db: Session = Depends(get_db)
) -> None:
    row = _get(db, _clean(name))
    if row is not None:
        db.delete(row)
        db.commit()
