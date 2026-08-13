"""Customer CRUD + per-customer ledger endpoints."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..bulk import parse_upload, pick
from ..database import get_db
from ..deps import get_current_user
from ..config import get_settings
from ..models import BillItem, BillPayment, Customer, EntryType, LedgerEntry, PaymentType
from ..pdf import build_bill_pdf, build_statement_pdf
from ..schemas import (
    AdvanceIn,
    BillCreate,
    BillItemIn,
    BillPaymentIn,
    BillUpdate,
    BulkResult,
    CustomerCreate,
    CustomerDetail,
    CustomerUpdate,
    CustomerWithBalance,
    LedgerEntryCreate,
    LedgerEntryOut,
    LedgerEntryUpdate,
    SettleAllocation,
    SettleIn,
    SettleResult,
)
from ..services import balances_for_customers, customer_balance

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.get("", response_model=list[CustomerWithBalance])
def list_customers(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=False),
    only_debtors: bool = Query(default=False),
) -> list[CustomerWithBalance]:
    stmt = select(Customer)
    if not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    stmt = stmt.order_by(Customer.name.asc())

    customers = db.execute(stmt).scalars().all()
    balances = balances_for_customers(db, [c.id for c in customers])

    result: list[CustomerWithBalance] = []
    for c in customers:
        b = balances[c.id]
        if only_debtors and b["balance"] <= 0:
            continue
        result.append(
            CustomerWithBalance(
                **{
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "address": c.address,
                    "note": c.note,
                    "payment_type": c.payment_type,
                    "is_active": c.is_active,
                    "created_at": c.created_at,
                    **b,
                }
            )
        )
    return result


# NOTE: these fixed paths must be declared BEFORE "/{customer_id}" so they are
# not swallowed by the dynamic route.
@router.get("/template", response_class=Response)
def download_template() -> Response:
    """A ready-to-fill CSV template for bulk customer upload."""
    csv_text = (
        "name,phone,address,payment_type,note\n"
        "Ramesh Kumar,9876543210,Main Road,periodic,Regular customer\n"
        "Suresh,9998887776,,per_use,\n"
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers_template.csv"},
    )


@router.post("/bulk", response_model=BulkResult)
async def bulk_upload(file: UploadFile = File(...), db: Session = Depends(get_db)) -> BulkResult:
    content = await file.read()
    rows = parse_upload(file, content)

    created = 0
    skipped = 0
    errors: list[str] = []
    to_add: list[Customer] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = pick(row, "name", "customer", "customer_name")
        if not name:
            errors.append(f"Row {i}: missing name — skipped")
            skipped += 1
            continue
        pt_raw = pick(row, "payment_type", "type").lower().replace(" ", "_")
        payment_type = (
            PaymentType.periodic if pt_raw in {"periodic", "monthly"} else PaymentType.per_use
        )
        to_add.append(
            Customer(
                name=name[:120],
                phone=(pick(row, "phone", "mobile", "phone_number") or None),
                address=(pick(row, "address") or None),
                note=(pick(row, "note", "notes") or None),
                payment_type=payment_type,
            )
        )
        created += 1

    if to_add:
        db.add_all(to_add)
        db.commit()

    return BulkResult(created=created, skipped=skipped, errors=errors[:50])


@router.post("", response_model=CustomerWithBalance, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> CustomerWithBalance:
    customer = Customer(
        name=payload.name,
        phone=payload.phone,
        address=payload.address,
        note=payload.note,
        payment_type=payload.payment_type,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    b = customer_balance(db, customer.id)
    return CustomerWithBalance.model_validate({**customer.__dict__, **b})


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerDetail:
    customer = _get_customer_or_404(db, customer_id)
    b = customer_balance(db, customer.id)
    entries = [LedgerEntryOut.model_validate(e) for e in customer.entries]
    return CustomerDetail.model_validate({**customer.__dict__, **b, "entries": entries})


@router.patch("/{customer_id}", response_model=CustomerWithBalance)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
) -> CustomerWithBalance:
    customer = _get_customer_or_404(db, customer_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "name" and value is not None:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="Name cannot be empty")
        setattr(customer, field, value)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    b = customer_balance(db, customer.id)
    return CustomerWithBalance.model_validate({**customer.__dict__, **b})


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    customer = _get_customer_or_404(db, customer_id)
    # Ledger entries are removed via ON DELETE CASCADE / relationship cascade.
    db.delete(customer)
    db.commit()


# ---- Ledger entries for a customer ---------------------------------------

@router.post(
    "/{customer_id}/entries",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_entry(
    customer_id: int, payload: LedgerEntryCreate, db: Session = Depends(get_db)
) -> LedgerEntryOut:
    _get_customer_or_404(db, customer_id)
    # This is used for standalone payments (Record Payment). A charge created
    # here is treated as a full debt (paid_amount=0); use POST /bill to set a
    # part-payment. A payment's paid_amount is unused.
    entry = LedgerEntry(
        customer_id=customer_id,
        entry_type=payload.entry_type,
        amount=payload.amount,
        paid_amount=0,
        description=payload.description,
        occurred_on=payload.occurred_on or date.today(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


def _make_items(rows: list[BillItemIn]) -> list[BillItem]:
    return [
        BillItem(
            product_id=r.product_id,
            name=r.name,
            unit=r.unit,
            unit_price=r.unit_price,
            quantity=r.quantity,
        )
        for r in rows
    ]


@router.post(
    "/{customer_id}/bill",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_bill(
    customer_id: int, payload: BillCreate, db: Session = Depends(get_db)
) -> LedgerEntryOut:
    """Record a bill as a SINGLE entry, built from line items (or a manual
    amount). `paid_now` is how much was paid at billing time (0 = full debt,
    == total = fully paid, in between = partial). Remaining debt = total - paid_now.
    """
    _get_customer_or_404(db, customer_id)
    on = payload.occurred_on or date.today()
    entry = LedgerEntry(
        customer_id=customer_id,
        entry_type=EntryType.charge,
        amount=payload.total,
        paid_amount=payload.paid_now,
        description=payload.description,
        occurred_on=on,
        items=_make_items(payload.items),
    )
    # Record the amount paid at billing time as the first payment (with a date),
    # so the bill carries a full payment history.
    if payload.paid_now > 0:
        entry.payments.append(BillPayment(amount=payload.paid_now, paid_on=on, note="At billing"))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.patch("/{customer_id}/bill/{entry_id}", response_model=LedgerEntryOut)
def update_bill(
    customer_id: int,
    entry_id: int,
    payload: BillUpdate,
    db: Session = Depends(get_db),
) -> LedgerEntryOut:
    """Edit a bill. If `items` is given, all line items are replaced and the
    total is recomputed from them; otherwise `amount` sets a manual total."""
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id or entry.entry_type != EntryType.charge:
        raise HTTPException(status_code=404, detail="Bill not found")

    data = payload.model_dump(exclude_unset=True)

    if payload.items is not None:
        entry.items.clear()  # cascade delete-orphan removes the old rows
        entry.items.extend(_make_items(payload.items))
        entry.amount = sum((i.unit_price * i.quantity for i in payload.items), Decimal(0))
    elif payload.amount is not None:
        entry.amount = payload.amount

    if "description" in data:
        entry.description = payload.description
    if payload.occurred_on is not None:
        entry.occurred_on = payload.occurred_on

    if entry.amount <= 0:
        raise HTTPException(status_code=422, detail="Bill total must be greater than 0")
    # Can't reduce a bill's total below what has already been paid on it.
    if entry.paid_amount > entry.amount:
        raise HTTPException(
            status_code=422,
            detail="Bill total can't be less than the amount already paid on it. Remove a payment first.",
        )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


def _recount_paid(entry: LedgerEntry) -> None:
    entry.paid_amount = sum((p.amount for p in entry.payments), Decimal(0))


@router.post(
    "/{customer_id}/bill/{entry_id}/payment",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_bill_payment(
    customer_id: int,
    entry_id: int,
    payload: BillPaymentIn,
    db: Session = Depends(get_db),
) -> LedgerEntryOut:
    """Record a payment toward an existing bill (partial or the remaining
    balance). The payment is attached to the SAME bill with its own date."""
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id or entry.entry_type != EntryType.charge:
        raise HTTPException(status_code=404, detail="Bill not found")

    already = sum((p.amount for p in entry.payments), Decimal(0))
    if already + payload.amount > entry.amount:
        remaining = entry.amount - already
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"That is more than the remaining balance ({remaining}).",
        )

    entry.payments.append(
        BillPayment(
            amount=payload.amount,
            paid_on=payload.paid_on or date.today(),
            note=payload.note,
        )
    )
    _recount_paid(entry)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.delete(
    "/{customer_id}/bill/{entry_id}/payment/{payment_id}",
    response_model=LedgerEntryOut,
)
def delete_bill_payment(
    customer_id: int,
    entry_id: int,
    payment_id: int,
    db: Session = Depends(get_db),
) -> LedgerEntryOut:
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id or entry.entry_type != EntryType.charge:
        raise HTTPException(status_code=404, detail="Bill not found")
    payment = db.get(BillPayment, payment_id)
    if payment is None or payment.entry_id != entry_id:
        raise HTTPException(status_code=404, detail="Payment not found")
    entry.payments.remove(payment)
    _recount_paid(entry)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.post("/{customer_id}/settle", response_model=SettleResult, status_code=status.HTTP_201_CREATED)
def settle_customer(
    customer_id: int, payload: SettleIn, db: Session = Depends(get_db)
) -> SettleResult:
    """Take a payment and apply it to the customer's unpaid bills, oldest first.
    Each bill gets its own dated payment, so bills settle to zero. The amount may
    not exceed the outstanding total — money beyond that is an advance, which is
    recorded separately via the advance endpoint.
    """
    _get_customer_or_404(db, customer_id)
    on = payload.paid_on or date.today()

    unpaid = db.execute(
        select(LedgerEntry)
        .where(
            LedgerEntry.customer_id == customer_id,
            LedgerEntry.entry_type == EntryType.charge,
            LedgerEntry.amount > LedgerEntry.paid_amount,
        )
        .order_by(LedgerEntry.occurred_on.asc(), LedgerEntry.id.asc())
    ).scalars().all()

    outstanding = sum((b.amount - b.paid_amount for b in unpaid), Decimal(0))
    if outstanding <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This customer has no outstanding bills. Use 'Add Advance' to record money paid up front.",
        )
    if payload.amount > outstanding:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"That is more than the outstanding total ({outstanding}). "
                "Pay up to that amount, and record any extra with 'Add Advance'."
            ),
        )

    left = payload.amount
    allocations: list[SettleAllocation] = []
    settled = 0

    for bill in unpaid:
        if left <= 0:
            break
        due = bill.amount - bill.paid_amount
        applied = min(due, left)
        bill.payments.append(
            BillPayment(amount=applied, paid_on=on, note=payload.note or "Settlement")
        )
        _recount_paid(bill)
        db.add(bill)
        left -= applied
        remaining_after = bill.amount - bill.paid_amount
        if remaining_after <= 0:
            settled += 1
        allocations.append(
            SettleAllocation(
                entry_id=bill.id,
                applied=float(applied),
                bill_total=float(bill.amount),
                bill_remaining=float(remaining_after),
            )
        )

    db.commit()

    return SettleResult(
        total_paid=float(payload.amount),
        bills_settled=settled,
        bills_touched=len(allocations),
        applied_to_bills=float(payload.amount - left),
        allocations=allocations,
    )


@router.post(
    "/{customer_id}/advance",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_advance(
    customer_id: int, payload: AdvanceIn, db: Session = Depends(get_db)
) -> LedgerEntryOut:
    """Record money the customer paid up front, not tied to any bill. It shows
    as a separate advance entry and offsets their balance."""
    _get_customer_or_404(db, customer_id)
    entry = LedgerEntry(
        customer_id=customer_id,
        entry_type=EntryType.payment,
        amount=payload.amount,
        paid_amount=0,
        description=payload.note or "Advance",
        occurred_on=payload.occurred_on or date.today(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.get("/{customer_id}/statement/pdf")
def customer_statement_pdf(
    customer_id: int,
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    detailed: bool = Query(default=True),
) -> Response:
    """All of a customer's bills (and advances) on one printable statement."""
    customer = _get_customer_or_404(db, customer_id)
    stmt = select(LedgerEntry).where(LedgerEntry.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(LedgerEntry.occurred_on >= date_from)
    if date_to:
        stmt = stmt.where(LedgerEntry.occurred_on <= date_to)
    entries = list(
        db.execute(stmt.order_by(LedgerEntry.occurred_on.asc(), LedgerEntry.id.asc()))
        .scalars()
        .all()
    )
    pdf = build_statement_pdf(entries, customer, get_settings(), detailed=detailed)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="statement_{customer_id}.pdf"'},
    )


@router.get("/{customer_id}/bill/{entry_id}/pdf")
def bill_pdf(customer_id: int, entry_id: int, db: Session = Depends(get_db)) -> Response:
    customer = _get_customer_or_404(db, customer_id)
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id or entry.entry_type != EntryType.charge:
        raise HTTPException(status_code=404, detail="Bill not found")
    pdf = build_bill_pdf(entry, customer, get_settings())
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="bill_{entry_id}.pdf"'},
    )


@router.get("/{customer_id}/entries", response_model=list[LedgerEntryOut])
def list_entries(customer_id: int, db: Session = Depends(get_db)) -> list[LedgerEntryOut]:
    _get_customer_or_404(db, customer_id)
    entries = db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.customer_id == customer_id)
        .order_by(LedgerEntry.occurred_on.desc(), LedgerEntry.id.desc())
    ).scalars().all()
    return [LedgerEntryOut.model_validate(e) for e in entries]


@router.patch("/{customer_id}/entries/{entry_id}", response_model=LedgerEntryOut)
def update_entry(
    customer_id: int,
    entry_id: int,
    payload: LedgerEntryUpdate,
    db: Session = Depends(get_db),
) -> LedgerEntryOut:
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(entry, field, value)
    # A bill can never have paid more than its total.
    if entry.entry_type == EntryType.charge and entry.paid_amount > entry.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Amount paid cannot be more than the bill total",
        )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


@router.delete(
    "/{customer_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_entry(customer_id: int, entry_id: int, db: Session = Depends(get_db)) -> None:
    entry = db.get(LedgerEntry, entry_id)
    if entry is None or entry.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
