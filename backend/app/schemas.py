"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import EntryType, PaymentType

# ---- Auth ----------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


# ---- Customers -----------------------------------------------------------

class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    note: str | None = None
    payment_type: PaymentType = PaymentType.per_use

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("phone", "address")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    note: str | None = None
    payment_type: PaymentType | None = None
    is_active: bool | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: str | None
    address: str | None
    note: str | None
    payment_type: PaymentType
    is_active: bool
    created_at: datetime


class CustomerWithBalance(CustomerOut):
    balance: float          # outstanding: unpaid bills - payments (positive = owes shop)
    total_debts: float      # sum of unpaid bills
    total_received: float   # paid bills + payments received
    last_activity: date | None = None


# ---- Ledger entries (bills / payments) -----------------------------------

class LedgerEntryBase(BaseModel):
    entry_type: EntryType
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)
    occurred_on: date | None = None

    @field_validator("description")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class LedgerEntryCreate(LedgerEntryBase):
    pass


class BillItemIn(BaseModel):
    product_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="unit", max_length=20)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Item name cannot be empty")
        return v


class BillItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int | None
    name: str
    unit: str
    unit_price: float
    quantity: float
    line_total: float


def _items_total(items: list[BillItemIn]) -> Decimal:
    return sum((i.unit_price * i.quantity for i in items), Decimal(0))


class BillCreate(BaseModel):
    """Create a bill from line items (preferred) or a manual amount, optionally
    with a part-payment made at the same time."""
    items: list[BillItemIn] = Field(default_factory=list)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    paid_now: Decimal = Field(default=0, ge=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)
    occurred_on: date | None = None

    @field_validator("description")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @property
    def total(self) -> Decimal:
        return _items_total(self.items) if self.items else (self.amount or Decimal(0))

    @model_validator(mode="after")
    def _check(self) -> "BillCreate":
        total = self.total
        if total <= 0:
            raise ValueError("Add at least one item, or a bill amount greater than 0")
        if self.paid_now > total:
            raise ValueError("Amount paid now cannot be more than the bill total")
        return self


class BillUpdate(BaseModel):
    """Edit a bill's items/total/note/date. Payments are managed separately via
    the bill-payment endpoints (so paid amount is not set here)."""
    items: list[BillItemIn] | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)
    occurred_on: date | None = None

    @field_validator("description")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class BillPaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class BillPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: float
    paid_on: date
    note: str | None
    created_at: datetime


class SettleIn(BaseModel):
    """A lump-sum payment to spread across the customer's unpaid bills.
    Never exceeds the outstanding total — extra money is an advance instead."""
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class AdvanceIn(BaseModel):
    """Money taken from the customer up front, not tied to any bill."""
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    occurred_on: date | None = None
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class SettleAllocation(BaseModel):
    entry_id: int
    applied: float
    bill_total: float
    bill_remaining: float   # remaining on that bill AFTER this payment


class SettleResult(BaseModel):
    total_paid: float
    bills_settled: int          # bills brought fully to zero
    bills_touched: int          # bills that received any amount
    applied_to_bills: float
    allocations: list[SettleAllocation]


class LedgerEntryUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    paid_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)
    occurred_on: date | None = None


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    entry_type: EntryType
    amount: float
    paid_amount: float
    description: str | None
    occurred_on: date
    created_at: datetime
    items: list[BillItemOut] = []
    payments: list[BillPaymentOut] = []


class CustomerDetail(CustomerWithBalance):
    entries: list[LedgerEntryOut]


# ---- Dashboard -----------------------------------------------------------

class TopDebtor(BaseModel):
    id: int
    name: str
    balance: float


class DashboardStats(BaseModel):
    total_customers: int
    active_customers: int
    total_outstanding: float          # sum of all positive balances owed to shop
    total_advance: float              # sum of balances where customer overpaid
    debts_this_month: float           # unpaid bills added this month
    collected_this_month: float       # money received this month (paid bills + payments)
    top_debtors: list[TopDebtor]


class MetaOut(BaseModel):
    app_name: str
    currency_code: str
    currency_symbol: str


# ---- Products / items ----------------------------------------------------

class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="General", max_length=60)
    unit: str = Field(default="unit", max_length=20)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("category")
    @classmethod
    def _clean_category(cls, v: str) -> str:
        v = (v or "").strip()
        return v or "General"

    @field_validator("unit")
    @classmethod
    def _clean_unit(cls, v: str) -> str:
        v = (v or "").strip()
        return v or "unit"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    unit: str | None = Field(default=None, max_length=20)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str
    unit: str
    unit_price: float
    is_active: bool
    has_image: bool = False
    image_version: str = "0"


# ---- Bulk upload ---------------------------------------------------------

class BulkResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


class ImageUrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class CategoryImageInfo(BaseModel):
    name: str
    version: str = "0"
