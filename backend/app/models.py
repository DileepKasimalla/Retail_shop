"""SQLAlchemy ORM models."""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaymentType(str, enum.Enum):
    """How a customer typically settles up."""
    per_use = "per_use"      # pays each time / on the spot
    periodic = "periodic"    # pays monthly / periodically (runs a tab)


class EntryType(str, enum.Enum):
    """A ledger entry either adds to what a customer owes, or reduces it."""
    charge = "charge"        # a bill -> if unpaid, increases balance owed (a debt)
    payment = "payment"      # customer paid down their tab -> decreases balance owed


class User(Base):
    """The shopkeeper. Single-operator system, but the table supports more."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, native_enum=False, length=20),
        default=PaymentType.per_use,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="LedgerEntry.occurred_on.desc(), LedgerEntry.id.desc()",
    )


class LedgerEntry(Base):
    """A single bill (charge) or payment against a customer's account."""
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entry_type: Mapped[EntryType] = mapped_column(
        Enum(EntryType, native_enum=False, length=20), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # For a bill (charge): how much of `amount` was paid at billing time
    #   (0 = full debt, == amount = fully paid, in between = partially paid).
    #   Remaining debt for the bill = amount - paid_amount.
    # For a payment: not used (0); the payment's value is `amount`.
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_on: Mapped[date] = mapped_column(Date, default=date.today, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="entries")
    items: Mapped[list["BillItem"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="BillItem.id.asc()",
    )
    # Payments made toward this bill over time (partial then remaining, etc.).
    payments: Mapped[list["BillPayment"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="BillPayment.paid_on.asc(), BillPayment.id.asc()",
    )


class BillItem(Base):
    """A single line on a bill: an item, its price snapshot, and the quantity."""
    __tablename__ = "bill_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_entries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Kept nullable so deleting a product doesn't erase historical bills.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)        # snapshot at billing time
    unit: Mapped[str] = mapped_column(String(20), default="unit", nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    entry: Mapped["LedgerEntry"] = relationship(back_populates="items")

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class CategoryImage(Base):
    """A picture for a category tile. Keyed by the category name that products use."""
    __tablename__ = "category_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_type: Mapped[str] = mapped_column(String(40), default="image/jpeg", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class BillPayment(Base):
    """A single payment made toward a bill, with the date it was paid."""
    __tablename__ = "bill_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_entries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, default=date.today, index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entry: Mapped["LedgerEntry"] = relationship(back_populates="payments")


class Product(Base):
    """An item the shop sells, with a price per unit. Used to build bills."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="General", index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="unit", nullable=False)  # kg, pc, litre...
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Optional photo, stored as a resized thumbnail so it backs up with the DB.
    # Deferred: listing products must not drag every photo out of the database.
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    image_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    @property
    def has_image(self) -> bool:
        # Checks the small type column, so it never loads the deferred blob.
        return self.image_type is not None

    @property
    def image_version(self) -> str:
        """Changes whenever the item is saved, so image URLs can be cached hard."""
        return str(int(self.updated_at.timestamp())) if self.updated_at else "0"
