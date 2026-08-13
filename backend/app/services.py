"""Business logic helpers: balance computation and aggregates."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Customer, EntryType, LedgerEntry

# Each bill (charge) stores paid_amount; remaining debt = amount - paid_amount.
#
# OUTSTANDING balance:
#   - a bill adds its remaining (amount - paid_amount) to what the customer owes
#   - a standalone payment reduces what they owe
# balance = sum(bill remainders) - sum(payments); positive = customer owes us.
_signed_amount = case(
    (LedgerEntry.entry_type == EntryType.charge, LedgerEntry.amount - LedgerEntry.paid_amount),
    (LedgerEntry.entry_type == EntryType.payment, -LedgerEntry.amount),
    else_=0,
)

# Money actually received: the paid part of bills + standalone payments.
_received_amount = case(
    (LedgerEntry.entry_type == EntryType.charge, LedgerEntry.paid_amount),
    (LedgerEntry.entry_type == EntryType.payment, LedgerEntry.amount),
    else_=0,
)

# Remaining (unpaid) portion of bills only — a customer's debts.
_debt_amount = case(
    (LedgerEntry.entry_type == EntryType.charge, LedgerEntry.amount - LedgerEntry.paid_amount),
    else_=0,
)


def _to_float(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


_EMPTY = {"balance": 0.0, "total_debts": 0.0, "total_received": 0.0, "last_activity": None}


def customer_balance(db: Session, customer_id: int) -> dict:
    """Return balance, total_debts, total_received, last_activity for one customer."""
    row = db.execute(
        select(
            func.coalesce(func.sum(_signed_amount), 0),
            func.coalesce(func.sum(_debt_amount), 0),
            func.coalesce(func.sum(_received_amount), 0),
            func.max(LedgerEntry.occurred_on),
        ).where(LedgerEntry.customer_id == customer_id)
    ).one()

    balance, debts, received, last = row
    return {
        "balance": _to_float(balance),
        "total_debts": _to_float(debts),
        "total_received": _to_float(received),
        "last_activity": last,
    }


def balances_for_customers(db: Session, customer_ids: list[int]) -> dict[int, dict]:
    """Batch balance lookup for a list of customers (avoids N+1 queries)."""
    if not customer_ids:
        return {}
    rows = db.execute(
        select(
            LedgerEntry.customer_id,
            func.coalesce(func.sum(_signed_amount), 0),
            func.coalesce(func.sum(_debt_amount), 0),
            func.coalesce(func.sum(_received_amount), 0),
            func.max(LedgerEntry.occurred_on),
        )
        .where(LedgerEntry.customer_id.in_(customer_ids))
        .group_by(LedgerEntry.customer_id)
    ).all()

    result: dict[int, dict] = {cid: dict(_EMPTY) for cid in customer_ids}
    for cid, balance, debts, received, last in rows:
        result[cid] = {
            "balance": _to_float(balance),
            "total_debts": _to_float(debts),
            "total_received": _to_float(received),
            "last_activity": last,
        }
    return result


def month_range(today: date) -> tuple[date, date]:
    """First day of the current month, and first day of next month."""
    start = today.replace(day=1)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start
