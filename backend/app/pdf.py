"""Generate a printable thermal-receipt style PDF for a single bill."""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import Customer, LedgerEntry

# The built-in PDF fonts don't include the ₹ glyph, so we print "Rs." instead.
_CUR = "Rs."

# India has no DST, so a fixed +5:30 offset is exact (avoids a tzdata dependency).
_IST = timezone(timedelta(hours=5, minutes=30))

# Roughly an 80mm thermal receipt roll.
_WIDTH = 80 * mm
_MARGIN = 5 * mm


def _time_ist(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_IST).strftime("%I:%M %p").lstrip("0")


def _money(value: Decimal | float) -> str:
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    frac = int(round((n - whole) * 100))
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{sign}{_CUR}{s}.{frac:02d}"


def _fmt_qty(q: Decimal | float) -> str:
    f = float(q)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _dashes() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.6, color=colors.black, dash=(1, 2),
                      spaceBefore=4, spaceAfter=4)


def build_bill_pdf(entry: LedgerEntry, customer: Customer, shop) -> bytes:
    """`shop` is the Settings object (shop_name/address/phone, app_name)."""
    inner = _WIDTH - 2 * _MARGIN

    # --- styles ---
    center = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, alignment=TA_CENTER, leading=11)
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15, alignment=TA_CENTER, leading=17)
    normal = ParagraphStyle("n", fontName="Helvetica", fontSize=8.5, alignment=TA_LEFT, leading=11)
    bold = ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=8.5, alignment=TA_LEFT, leading=11)
    itemname = ParagraphStyle("in", fontName="Helvetica", fontSize=8.5, alignment=TA_LEFT, leading=10)
    thanks = ParagraphStyle("th", fontName="Helvetica", fontSize=9, alignment=TA_CENTER, leading=12)

    shop_name = (getattr(shop, "shop_name", "") or getattr(shop, "app_name", "") or "Shop").strip()

    story: list = []
    story.append(Paragraph(shop_name, title))
    if getattr(shop, "shop_address", ""):
        story.append(Paragraph(shop.shop_address, center))
    if getattr(shop, "shop_phone", ""):
        story.append(Paragraph(f"Tel: {shop.shop_phone}", center))
    story.append(_dashes())

    # --- meta rows (label left, value right) ---
    def kv(label: str, value: str):
        return [Paragraph(label, normal), Paragraph(value, ParagraphStyle("r", parent=normal, alignment=2))]

    meta = [
        kv("Bill No:", f"#{entry.id}"),
        kv("Date:", f"{entry.occurred_on.strftime('%d %b %Y')}  {_time_ist(entry.created_at)}"),
        kv("Customer:", customer.name),
    ]
    if customer.phone:
        meta.append(kv("Phone:", customer.phone))
    meta_tbl = Table(meta, colWidths=[inner * 0.42, inner * 0.58])
    meta_tbl.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(_dashes())

    # --- items: Name | Qty | Price ---
    header = [Paragraph("Name", bold),
              Paragraph("Qty", ParagraphStyle("qh", parent=bold, alignment=1)),
              Paragraph("Price", ParagraphStyle("ph", parent=bold, alignment=2))]
    rows = [header]
    if entry.items:
        for it in entry.items:
            rows.append([
                Paragraph(it.name, itemname),
                Paragraph(_fmt_qty(it.quantity), ParagraphStyle("q", parent=normal, alignment=1)),
                Paragraph(_money(it.line_total), ParagraphStyle("p", parent=normal, alignment=2)),
            ])
    else:
        rows.append([
            Paragraph(entry.description or "Item", itemname),
            Paragraph("1", ParagraphStyle("q", parent=normal, alignment=1)),
            Paragraph(_money(entry.amount), ParagraphStyle("p", parent=normal, alignment=2)),
        ])
    items_tbl = Table(rows, colWidths=[inner * 0.56, inner * 0.16, inner * 0.28])
    items_tbl.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.grey),
    ]))
    story.append(items_tbl)
    story.append(_dashes())

    paid = sum((p.amount for p in entry.payments), Decimal(0))
    remaining = entry.amount - paid

    # --- totals ---
    big_l = ParagraphStyle("bl", fontName="Helvetica-Bold", fontSize=12, alignment=TA_LEFT)
    big_r = ParagraphStyle("br", fontName="Helvetica-Bold", fontSize=12, alignment=2)
    tot_rows = [[Paragraph("SUB TOTAL", big_l), Paragraph(_money(entry.amount), big_r)]]
    tot_tbl = Table(tot_rows, colWidths=[inner * 0.5, inner * 0.5])
    tot_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(tot_tbl)

    def line(label: str, value: str, strong: bool = False, color=None):
        ls = ParagraphStyle("ll", parent=(bold if strong else normal))
        rs = ParagraphStyle("lr", parent=(bold if strong else normal), alignment=2)
        if color is not None:
            rs.textColor = color
        t = Table([[Paragraph(label, ls), Paragraph(value, rs)]], colWidths=[inner * 0.5, inner * 0.5])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        return t

    story.append(line("PAID", _money(paid)))
    story.append(line(
        "BALANCE DUE" if remaining > 0 else "BALANCE",
        _money(remaining),
        strong=True,
        color=colors.HexColor("#c0261e") if remaining > 0 else colors.HexColor("#0a7d3f"),
    ))

    # --- payment history ---
    if entry.payments:
        story.append(_dashes())
        story.append(Paragraph("PAYMENTS", bold))
        pr = [[Paragraph("Date", normal),
               Paragraph("Time", ParagraphStyle("pt", parent=normal, alignment=1)),
               Paragraph("Amount", ParagraphStyle("pa", parent=normal, alignment=2))]]
        for p in entry.payments:
            pr.append([
                Paragraph(p.paid_on.strftime("%d %b %Y"), normal),
                Paragraph(_time_ist(p.created_at), ParagraphStyle("pt", parent=normal, alignment=1)),
                Paragraph(_money(p.amount), ParagraphStyle("pa", parent=normal, alignment=2)),
            ])
        pay_tbl = Table(pr, colWidths=[inner * 0.42, inner * 0.28, inner * 0.30])
        pay_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                     ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.grey)]))
        story.append(pay_tbl)

    story.append(_dashes())
    story.append(Spacer(1, 4))
    story.append(Paragraph("THANK YOU!", ParagraphStyle("ty", parent=thanks, fontName="Helvetica-Bold")))
    story.append(Paragraph("Please visit again.", thanks))

    # --- dynamic page height so the roll fits the content ---
    n_items = len(entry.items) or 1
    n_pay = len(entry.payments)
    height = (70 + 6 * n_items + (18 + 6 * n_pay if n_pay else 0) + 45) * mm
    height = max(height, 150 * mm)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(_WIDTH, height),
        topMargin=6 * mm,
        bottomMargin=6 * mm,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=f"Bill #{entry.id}",
    )
    doc.build(story)
    return buf.getvalue()


def build_statement_pdf(
    entries: list[LedgerEntry],
    customer: Customer,
    shop,
    detailed: bool = True,
) -> bytes:
    """An A4 statement listing every bill (and advance) for one customer.

    `detailed=True` lists each bill's items under it; False keeps one row per bill.
    """
    story: list = []

    center = ParagraphStyle("sc", fontName="Helvetica", fontSize=9, alignment=TA_CENTER, leading=12)
    title = ParagraphStyle("st", fontName="Helvetica-Bold", fontSize=17, alignment=TA_CENTER, leading=20)
    sub = ParagraphStyle("ss", fontName="Helvetica-Bold", fontSize=11, alignment=TA_CENTER, leading=14)
    normal = ParagraphStyle("sn", fontName="Helvetica", fontSize=8.5, alignment=TA_LEFT, leading=11)
    bold = ParagraphStyle("sb", fontName="Helvetica-Bold", fontSize=8.5, alignment=TA_LEFT, leading=11)
    small = ParagraphStyle("ssm", fontName="Helvetica", fontSize=7.5, alignment=TA_LEFT,
                           leading=9.5, textColor=colors.HexColor("#555555"))
    right = ParagraphStyle("sr", parent=normal, alignment=2)
    right_b = ParagraphStyle("srb", parent=bold, alignment=2)
    sub_left = ParagraphStyle("sl", fontName="Helvetica-Bold", fontSize=10,
                              alignment=TA_LEFT, leading=13)

    shop_name = (getattr(shop, "shop_name", "") or getattr(shop, "app_name", "") or "Shop").strip()
    story.append(Paragraph(shop_name, title))
    if getattr(shop, "shop_address", ""):
        story.append(Paragraph(shop.shop_address, center))
    if getattr(shop, "shop_phone", ""):
        story.append(Paragraph(f"Tel: {shop.shop_phone}", center))
    story.append(Spacer(1, 6))
    story.append(Paragraph("CUSTOMER STATEMENT", sub))
    story.append(Spacer(1, 8))

    # Customer meta
    meta = [[
        Paragraph(f"<b>Customer:</b> {customer.name}", normal),
        Paragraph(f"<b>Phone:</b> {customer.phone or '-'}", normal),
        Paragraph(f"<b>Bills:</b> {sum(1 for e in entries if e.entry_type.value == 'charge')}", right),
    ]]
    mt = Table(meta, colWidths=[80 * mm, 50 * mm, 40 * mm])
    mt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(mt)
    story.append(_dashes())

    # Table of entries
    story.append(Paragraph("BILLS", sub_left))
    story.append(Spacer(1, 4))
    head = [
        Paragraph("Date", bold), Paragraph("Time", bold), Paragraph("Details", bold),
        Paragraph("Total", right_b), Paragraph("Paid", right_b), Paragraph("Balance", right_b),
    ]
    rows = [head]
    total_billed = Decimal(0)
    total_paid = Decimal(0)
    total_due = Decimal(0)
    total_advance = Decimal(0)

    # oldest first reads better on a statement
    ordered = sorted(entries, key=lambda e: (e.occurred_on, e.id))
    for e in ordered:
        is_bill = e.entry_type.value == "charge"
        if is_bill:
            due = e.amount - e.paid_amount
            total_billed += e.amount
            total_paid += e.paid_amount
            total_due += due
            if e.items:
                summary = ", ".join(f"{_fmt_qty(i.quantity)} {i.unit} {i.name}" for i in e.items)
            else:
                summary = e.description or "-"
            detail_cell = [Paragraph(f"<b>Bill #{e.id}</b> — {summary}", normal)]
            if detailed and e.payments:
                for p in e.payments:
                    bits = f"paid {_money(p.amount)} on {p.paid_on.strftime('%d %b %Y')} {_time_ist(p.created_at)}"
                    if p.note:
                        bits += f" ({p.note})"
                    detail_cell.append(Paragraph(f"• {bits}", small))
            elif detailed:
                detail_cell.append(Paragraph("• no payments yet", small))
            rows.append([
                Paragraph(e.occurred_on.strftime("%d %b %Y"), normal),
                Paragraph(_time_ist(e.created_at), normal),
                detail_cell,
                Paragraph(_money(e.amount), right),
                Paragraph(_money(e.paid_amount), right),
                Paragraph(_money(due), right),
            ])
        else:
            total_advance += e.amount
            rows.append([
                Paragraph(e.occurred_on.strftime("%d %b %Y"), normal),
                Paragraph(_time_ist(e.created_at), normal),
                Paragraph(f"{e.description or 'Advance'} (advance)", normal),
                Paragraph("-", right),
                Paragraph(_money(e.amount), right),
                Paragraph("-", right),
            ])

    tbl = Table(rows, colWidths=[22 * mm, 17 * mm, 70 * mm, 21 * mm, 21 * mm, 21 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f4")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d3dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # ---- Payment history: every payment across all bills, plus advances ----
    pay_rows = [[
        Paragraph("Date", bold), Paragraph("Time", bold), Paragraph("Against", bold),
        Paragraph("Note", bold), Paragraph("Amount", right_b),
    ]]
    history: list[tuple] = []
    for e in ordered:
        if e.entry_type.value == "charge":
            for p in e.payments:
                history.append((p.paid_on, p.created_at, f"Bill #{e.id}", p.note or "-", p.amount))
        else:
            history.append((e.occurred_on, e.created_at, "Advance", e.description or "-", e.amount))
    history.sort(key=lambda r: (r[0], r[1] or datetime.min.replace(tzinfo=timezone.utc)))

    story.append(Paragraph("PAYMENT HISTORY", sub_left))
    story.append(Spacer(1, 4))
    if not history:
        story.append(Paragraph("No payments recorded yet.", normal))
    else:
        for d, created, against, note, amt in history:
            pay_rows.append([
                Paragraph(d.strftime("%d %b %Y"), normal),
                Paragraph(_time_ist(created), normal),
                Paragraph(against, normal),
                Paragraph(note, normal),
                Paragraph(_money(amt), right),
            ])
        pay_rows.append([
            Paragraph("", normal), Paragraph("", normal), Paragraph("", normal),
            Paragraph("Total received", bold),
            Paragraph(_money(sum(r[4] for r in history)), right_b),
        ])
        ptbl = Table(pay_rows, colWidths=[24 * mm, 18 * mm, 26 * mm, 63 * mm, 41 * mm], repeatRows=1)
        ptbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f4")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d3dc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#fafbfc")]),
            ("BACKGROUND", (0, len(pay_rows) - 1), (-1, len(pay_rows) - 1), colors.HexColor("#f2f4f7")),
        ]))
        story.append(ptbl)
    story.append(Spacer(1, 12))

    # Summary
    net = total_due - total_advance
    summary_rows = [
        ["Total billed", _money(total_billed)],
        ["Total received", _money(total_paid + total_advance)],
    ]
    if total_advance:
        summary_rows.append(["Advance held", _money(total_advance)])
    summary_rows.append(
        ["BALANCE DUE" if net > 0 else ("ADVANCE BALANCE" if net < 0 else "FULLY SETTLED"),
         _money(abs(net))]
    )
    st = Table(summary_rows, colWidths=[132 * mm, 40 * mm])
    st.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, len(summary_rows) - 1), (-1, len(summary_rows) - 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, len(summary_rows) - 1), (1, len(summary_rows) - 1),
         colors.HexColor("#c0261e") if net > 0 else colors.HexColor("#0a7d3f")),
        ("LINEABOVE", (0, 0), (-1, 0), 0.4, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(st)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Statement - {customer.name}",
    )
    doc.build(story)
    return buf.getvalue()
