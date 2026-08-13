"""Dashboard / totals endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Customer, LedgerEntry
from ..schemas import DashboardStats, TopDebtor
from ..services import _debt_amount, _received_amount, _signed_amount, month_range

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)) -> DashboardStats:
    total_customers = db.scalar(select(func.count(Customer.id))) or 0
    active_customers = (
        db.scalar(select(func.count(Customer.id)).where(Customer.is_active.is_(True))) or 0
    )

    # Per-customer balances (subquery), then split into outstanding vs advance.
    balance_sq = (
        select(
            LedgerEntry.customer_id.label("cid"),
            func.coalesce(func.sum(_signed_amount), 0).label("bal"),
        )
        .group_by(LedgerEntry.customer_id)
        .subquery()
    )

    total_outstanding = db.scalar(
        select(func.coalesce(func.sum(case((balance_sq.c.bal > 0, balance_sq.c.bal), else_=0)), 0))
    ) or 0
    total_advance = db.scalar(
        select(func.coalesce(func.sum(case((balance_sq.c.bal < 0, -balance_sq.c.bal), else_=0)), 0))
    ) or 0

    start, next_start = month_range(date.today())
    month_filter = (LedgerEntry.occurred_on >= start, LedgerEntry.occurred_on < next_start)
    debts_this_month = db.scalar(
        select(func.coalesce(func.sum(_debt_amount), 0)).where(*month_filter)
    ) or 0
    collected_this_month = db.scalar(
        select(func.coalesce(func.sum(_received_amount), 0)).where(*month_filter)
    ) or 0

    # Top debtors (largest positive balances).
    debtor_rows = db.execute(
        select(Customer.id, Customer.name, balance_sq.c.bal)
        .join(balance_sq, balance_sq.c.cid == Customer.id)
        .where(balance_sq.c.bal > 0)
        .order_by(balance_sq.c.bal.desc())
        .limit(5)
    ).all()
    top_debtors = [
        TopDebtor(id=r[0], name=r[1], balance=float(r[2])) for r in debtor_rows
    ]

    return DashboardStats(
        total_customers=total_customers,
        active_customers=active_customers,
        total_outstanding=float(total_outstanding),
        total_advance=float(total_advance),
        debts_this_month=float(debts_this_month),
        collected_this_month=float(collected_this_month),
        top_debtors=top_debtors,
    )
