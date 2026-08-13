"""Product / item catalog: CRUD + images + bulk upload."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..bulk import parse_upload, pick
from ..database import get_db
from ..deps import get_current_user
from ..imaging import UnsafeUrlError, fetch_image_bytes, image_response, process_image
from ..models import Product
from ..schemas import BulkResult, ImageUrlIn, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(
    prefix="/api/products",
    tags=["products"],
    dependencies=[Depends(get_current_user)],
)


def _get_or_404(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return p


@router.get("", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=False),
) -> list[Product]:
    stmt = select(Product)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search.strip()}%"))
    return list(db.execute(stmt.order_by(Product.name.asc())).scalars().all())


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    product = Product(
        name=payload.name,
        category=payload.category,
        unit=payload.unit,
        unit_price=payload.unit_price,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)) -> Product:
    product = _get_or_404(db, product_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    product = _get_or_404(db, product_id)
    db.delete(product)
    db.commit()


@router.post("/{product_id}/image", response_model=ProductOut)
async def upload_product_image(
    product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> Product:
    """Attach a photo to an item. The image is re-encoded to a small thumbnail,
    which also strips any embedded metadata and rejects non-image files."""
    product = _get_or_404(db, product_id)
    raw = await file.read()
    product.image_data, product.image_type = process_image(raw)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/image/from-url", response_model=ProductOut)
def set_product_image_from_url(
    product_id: int, payload: ImageUrlIn, db: Session = Depends(get_db)
) -> Product:
    """Fetch a real product photo from a public image URL and store it."""
    product = _get_or_404(db, product_id)
    try:
        raw = fetch_image_bytes(payload.url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    product.image_data, product.image_type = process_image(raw)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}/image")
def get_product_image(
    product_id: int,
    request: Request,
    v: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    product = _get_or_404(db, product_id)
    if not product.image_data:
        raise HTTPException(status_code=404, detail="No image for this item")
    return image_response(
        product.image_data, product.image_type or "image/jpeg", request, versioned=v is not None
    )


@router.delete("/{product_id}/image", response_model=ProductOut)
def delete_product_image(product_id: int, db: Session = Depends(get_db)) -> Product:
    product = _get_or_404(db, product_id)
    product.image_data = None
    product.image_type = None
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/template", response_class=Response)
def download_template() -> Response:
    """A ready-to-fill CSV template for bulk item upload."""
    csv_text = (
        "name,category,unit,unit_price,image_url\n"
        "Rice,Grains,kg,60,\n"
        "Milk,Dairy,500 ml,30,\n"
        "Sugar,Grocery,kg,45,\n"
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=items_template.csv"},
    )


@router.post("/bulk", response_model=BulkResult)
async def bulk_upload(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> BulkResult:
    content = await file.read()
    rows = parse_upload(file, content)

    created = 0
    skipped = 0
    errors: list[str] = []
    # Existing names (lowercased) to skip duplicates.
    existing = {n.lower() for (n,) in db.execute(select(Product.name)).all()}

    to_add: list[Product] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = pick(row, "name", "item", "item_name", "product")
        if not name:
            errors.append(f"Row {i}: missing name — skipped")
            skipped += 1
            continue
        if name.lower() in existing:
            skipped += 1
            continue
        price_raw = pick(row, "unit_price", "price", "rate", "amount")
        try:
            price = Decimal(price_raw) if price_raw else Decimal(0)
            if price < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            errors.append(f"Row {i} ({name}): invalid price '{price_raw}' — skipped")
            skipped += 1
            continue
        unit = pick(row, "unit", "units", "uom") or "unit"
        category = pick(row, "category", "group", "type") or "General"
        product = Product(
            name=name[:120], category=category[:60], unit=unit[:20], unit_price=price
        )

        # Optional photo: fetch it now so the catalog comes in with real images.
        image_url = pick(row, "image_url", "image", "photo", "photo_url", "img")
        if image_url:
            try:
                product.image_data, product.image_type = process_image(
                    fetch_image_bytes(image_url)
                )
            except (UnsafeUrlError, HTTPException) as e:
                detail = e.detail if isinstance(e, HTTPException) else str(e)
                errors.append(f"Row {i} ({name}): image not loaded — {detail}")

        to_add.append(product)
        existing.add(name.lower())
        created += 1

    if to_add:
        db.add_all(to_add)
        db.commit()

    return BulkResult(created=created, skipped=skipped, errors=errors[:50])
