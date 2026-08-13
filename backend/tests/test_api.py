"""End-to-end API tests: auth, customers, ledger (paid_amount), products, bulk, dashboard."""
from __future__ import annotations

import io


def _new_customer(client, headers, **overrides):
    payload = {"name": "Test Customer", "phone": "9990001111", "payment_type": "periodic"}
    payload.update(overrides)
    res = client.post("/api/customers", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _bill(client, headers, cid, amount, paid_now=0, **extra):
    """Create a bill via the single-transaction /bill endpoint."""
    body = {"amount": amount, "paid_now": paid_now}
    body.update(extra)
    return client.post(f"/api/customers/{cid}/bill", json=body, headers=headers)


def _payment(client, headers, cid, amount, **extra):
    body = {"entry_type": "payment", "amount": amount}
    body.update(extra)
    return client.post(f"/api/customers/{cid}/entries", json=body, headers=headers)


# ---- Auth ----------------------------------------------------------------

def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/meta").json()["currency_code"] == "INR"


def test_protected_requires_auth(client):
    assert client.get("/api/customers").status_code == 401
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_login_wrong_password(client, shopkeeper):
    res = client.post("/api/auth/login", json={"username": shopkeeper["username"], "password": "wrong"})
    assert res.status_code == 401


def test_login_and_me(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert "hashed_password" not in me.json()


# ---- Customers -----------------------------------------------------------

def test_create_and_get_customer(client, auth_headers):
    c = _new_customer(client, auth_headers, name="  Ramesh  ")
    assert c["name"] == "Ramesh"
    assert c["balance"] == 0.0
    assert client.get(f"/api/customers/{c['id']}", headers=auth_headers).json()["entries"] == []


def test_create_customer_blank_name_rejected(client, auth_headers):
    res = client.post("/api/customers", json={"name": "   ", "payment_type": "per_use"}, headers=auth_headers)
    assert res.status_code == 422


def test_search_and_debtor_filter(client, auth_headers):
    a = _new_customer(client, auth_headers, name="Alice Kumar", phone="8887776665")
    _new_customer(client, auth_headers, name="Bob Singh", phone="7776665554")
    res = client.get("/api/customers", params={"search": "Alice"}, headers=auth_headers)
    names = [x["name"] for x in res.json()]
    assert "Alice Kumar" in names and "Bob Singh" not in names
    res = client.get("/api/customers", params={"search": "7776665554"}, headers=auth_headers)
    assert any(x["name"] == "Bob Singh" for x in res.json())
    _bill(client, auth_headers, a["id"], 50, 0)  # unpaid bill => a debt
    res = client.get("/api/customers", params={"only_debtors": "true"}, headers=auth_headers)
    assert all(x["balance"] > 0 for x in res.json())


# ---- Bills: single-row, with paid_amount ---------------------------------

def test_bill_full_debt(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    r = _bill(client, auth_headers, cid, 87, 0)
    assert r.status_code == 201, r.text
    assert r.json()["paid_amount"] == 0.0
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 87.0 and d["total_debts"] == 87.0 and d["total_received"] == 0.0
    assert len(d["entries"]) == 1  # ONE row


def test_bill_partial_is_one_row(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    r = _bill(client, auth_headers, cid, 87, 40)  # ₹87 bill, ₹40 paid
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 87.0 and r.json()["paid_amount"] == 40.0
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 47.0          # remaining debt
    assert d["total_debts"] == 47.0
    assert d["total_received"] == 40.0
    assert len(d["entries"]) == 1        # ONE row, not two


def test_bill_fully_paid(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 87, 87)
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 0.0 and d["total_received"] == 87.0
    assert len(d["entries"]) == 1


def test_bill_with_items_stores_lines(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    items = [
        {"name": "Bread", "unit": "piece", "unit_price": 45, "quantity": 1},
        {"name": "Eggs", "unit": "piece", "unit_price": 6, "quantity": 7},
    ]
    r = client.post(f"/api/customers/{cid}/bill", json={"items": items, "paid_now": 40}, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount"] == 87.0          # 45 + 42, computed from items
    assert body["paid_amount"] == 40.0
    assert len(body["items"]) == 2
    assert body["items"][0]["line_total"] == 45.0
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 47.0


def test_edit_bill_replaces_items(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = client.post(
        f"/api/customers/{cid}/bill",
        json={"items": [{"name": "Rice", "unit": "kg", "unit_price": 60, "quantity": 1}], "paid_now": 0},
        headers=auth_headers,
    ).json()
    assert e["amount"] == 60.0
    # edit: change quantity to 2 and add another item -> total recomputed
    new_items = [
        {"name": "Rice", "unit": "kg", "unit_price": 60, "quantity": 2},
        {"name": "Sugar", "unit": "kg", "unit_price": 45, "quantity": 1},
    ]
    r = client.patch(f"/api/customers/{cid}/bill/{e['id']}", json={"items": new_items}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 165.0     # 120 + 45
    assert len(r.json()["items"]) == 2


def test_bill_payment_history_same_transaction(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 87, 40).json()  # ₹40 paid at billing
    assert len(e["payments"]) == 1 and e["payments"][0]["amount"] == 40.0
    # pay the remaining ₹47 later -> same bill, now fully paid
    r = client.post(f"/api/customers/{cid}/bill/{e['id']}/payment", json={"amount": 47}, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["paid_amount"] == 87.0
    assert len(r.json()["payments"]) == 2
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 0.0
    assert len(d["entries"]) == 1  # still ONE transaction


def test_bill_payment_exceeding_remaining_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 100, 60).json()  # remaining 40
    r = client.post(f"/api/customers/{cid}/bill/{e['id']}/payment", json={"amount": 50}, headers=auth_headers)
    assert r.status_code == 422


def test_delete_bill_payment(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 100, 100).json()  # fully paid, 1 payment
    pid = e["payments"][0]["id"]
    r = client.delete(f"/api/customers/{cid}/bill/{e['id']}/payment/{pid}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["paid_amount"] == 0.0
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 100.0


def test_settle_clears_bills_oldest_first(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    b1 = _bill(client, auth_headers, cid, 100, 0, occurred_on="2026-08-01").json()
    b2 = _bill(client, auth_headers, cid, 200, 0, occurred_on="2026-08-02").json()
    # pay 250 -> clears b1 fully, 150 into b2 (50 left on b2)
    r = client.post(f"/api/customers/{cid}/settle", json={"amount": 250}, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["applied_to_bills"] == 250.0
    assert body["bills_settled"] == 1

    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 50.0
    by_id = {e["id"]: e for e in d["entries"]}
    assert by_id[b1["id"]]["amount"] - by_id[b1["id"]]["paid_amount"] == 0.0   # settled -> shows 0
    assert by_id[b2["id"]]["amount"] - by_id[b2["id"]]["paid_amount"] == 50.0
    assert len(d["entries"]) == 2  # no loose payment row created


def test_settle_all_debts_at_once(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 360, 185)   # 175 due
    _bill(client, auth_headers, cid, 350, 0)     # 350 due
    due = client.get(f"/api/customers/{cid}", headers=auth_headers).json()["total_debts"]
    assert due == 525.0
    r = client.post(f"/api/customers/{cid}/settle", json={"amount": due}, headers=auth_headers)
    assert r.json()["bills_settled"] == 2
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 0.0 and d["total_debts"] == 0.0
    # every bill now shows zero remaining
    assert all(e["amount"] - e["paid_amount"] == 0.0 for e in d["entries"] if e["entry_type"] == "charge")


def test_settle_rejects_more_than_outstanding(client, auth_headers):
    """Record Payment must never create an advance — extra money is rejected."""
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 100, 0)
    r = client.post(f"/api/customers/{cid}/settle", json={"amount": 300}, headers=auth_headers)
    assert r.status_code == 422
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 100.0          # unchanged
    assert len(d["entries"]) == 1         # no advance row created


def test_settle_with_no_debts_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    r = client.post(f"/api/customers/{cid}/settle", json={"amount": 500}, headers=auth_headers)
    assert r.status_code == 422
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 0.0


def test_advance_is_separate_and_not_applied_to_bills(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    b = _bill(client, auth_headers, cid, 100, 0).json()
    r = client.post(f"/api/customers/{cid}/advance", json={"amount": 250, "note": "Deposit"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["entry_type"] == "payment"
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    # the bill is untouched; the advance stands on its own
    bill = next(e for e in d["entries"] if e["id"] == b["id"])
    assert bill["paid_amount"] == 0.0
    assert d["total_debts"] == 100.0
    assert d["balance"] == -150.0         # 100 owed - 250 advance
    advances = [e for e in d["entries"] if e["entry_type"] == "payment"]
    assert len(advances) == 1 and advances[0]["amount"] == 250.0


def test_statement_pdf_all_bills(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    client.post(
        f"/api/customers/{cid}/bill",
        json={"items": [{"name": "Rice", "unit": "kg", "unit_price": 60, "quantity": 2}], "paid_now": 50},
        headers=auth_headers,
    )
    _bill(client, auth_headers, cid, 300, 300)
    client.post(f"/api/customers/{cid}/advance", json={"amount": 100}, headers=auth_headers)
    r = client.get(f"/api/customers/{cid}/statement/pdf", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    # date filter still returns a valid document
    r2 = client.get(
        f"/api/customers/{cid}/statement/pdf",
        params={"date_from": "2000-01-01", "detailed": "false"},
        headers=auth_headers,
    )
    assert r2.status_code == 200 and r2.content[:4] == b"%PDF"


def test_bill_pdf(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = client.post(
        f"/api/customers/{cid}/bill",
        json={"items": [{"name": "Rice", "unit": "kg", "unit_price": 60, "quantity": 2}], "paid_now": 50},
        headers=auth_headers,
    ).json()
    r = client.get(f"/api/customers/{cid}/bill/{e['id']}/pdf", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_bill_paid_now_exceeds_total_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    assert _bill(client, auth_headers, c["id"], 50, 60).status_code == 422


def test_bill_negative_or_zero_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    assert _bill(client, auth_headers, c["id"], -5, 0).status_code == 422
    assert _bill(client, auth_headers, c["id"], 0, 0).status_code == 422


# ---- Payments & edits ----------------------------------------------------

def test_payment_reduces_debt(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 500, 0)
    _payment(client, auth_headers, cid, 200)
    d = client.get(f"/api/customers/{cid}", headers=auth_headers).json()
    assert d["balance"] == 300.0
    assert d["total_debts"] == 500.0
    assert d["total_received"] == 200.0


def test_overpayment_gives_advance(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 50, 0)
    _payment(client, auth_headers, cid, 80)
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == -30.0


def test_edit_bill_paid_amount(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 120, 0).json()
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 120.0
    # edit to record ₹50 paid -> remaining 70
    r = client.patch(f"/api/customers/{cid}/entries/{e['id']}", json={"paid_amount": 50}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["paid_amount"] == 50.0
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 70.0


def test_edit_paid_more_than_total_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 100, 0).json()
    r = client.patch(f"/api/customers/{cid}/entries/{e['id']}", json={"paid_amount": 150}, headers=auth_headers)
    assert r.status_code == 422


def test_negative_payment_rejected(client, auth_headers):
    c = _new_customer(client, auth_headers)
    assert _payment(client, auth_headers, c["id"], -5).status_code == 422


def test_delete_entry_updates_balance(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    e = _bill(client, auth_headers, cid, 75, 0).json()
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 75.0
    assert client.delete(f"/api/customers/{cid}/entries/{e['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).json()["balance"] == 0.0


def test_entry_wrong_customer_404(client, auth_headers):
    c1 = _new_customer(client, auth_headers)
    c2 = _new_customer(client, auth_headers)
    e = _bill(client, auth_headers, c1["id"], 10, 0).json()
    assert client.delete(f"/api/customers/{c2['id']}/entries/{e['id']}", headers=auth_headers).status_code == 404


def test_delete_customer_cascades(client, auth_headers):
    c = _new_customer(client, auth_headers)
    cid = c["id"]
    _bill(client, auth_headers, cid, 20, 0)
    assert client.delete(f"/api/customers/{cid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/customers/{cid}", headers=auth_headers).status_code == 404


# ---- Products ------------------------------------------------------------

def test_product_crud(client, auth_headers):
    r = client.post(
        "/api/products",
        json={"name": "Rice", "category": "Grains", "unit": "kg", "unit_price": 60},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["unit_price"] == 60.0
    assert r.json()["category"] == "Grains"
    r2 = client.post("/api/products", json={"name": "Loose Item", "unit": "pc", "unit_price": 5}, headers=auth_headers)
    assert r2.json()["category"] == "General"
    r = client.patch(f"/api/products/{pid}", json={"unit_price": 65, "category": "Staples"}, headers=auth_headers)
    assert r.json()["unit_price"] == 65.0 and r.json()["category"] == "Staples"
    assert any(p["id"] == pid for p in client.get("/api/products", headers=auth_headers).json())
    assert client.delete(f"/api/products/{pid}", headers=auth_headers).status_code == 204


def _png_bytes(size=(80, 60)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_product_image_upload_fetch_delete(client, auth_headers):
    pid = client.post(
        "/api/products", json={"name": "Photo Item", "unit": "kg", "unit_price": 10}, headers=auth_headers
    ).json()["id"]
    assert client.get("/api/products", headers=auth_headers).json()[0]["has_image"] in (True, False)

    files = {"file": ("pic.png", io.BytesIO(_png_bytes()), "image/png")}
    r = client.post(f"/api/products/{pid}/image", files=files, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["has_image"] is True

    img = client.get(f"/api/products/{pid}/image", headers=auth_headers)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"   # re-encoded to a thumbnail
    assert img.content[:2] == b"\xff\xd8"                 # JPEG magic

    r = client.delete(f"/api/products/{pid}/image", headers=auth_headers)
    assert r.status_code == 200 and r.json()["has_image"] is False
    assert client.get(f"/api/products/{pid}/image", headers=auth_headers).status_code == 404


def test_replaced_image_is_not_served_stale(client, auth_headers):
    """Re-importing a photo must show up immediately, not sit behind a cache."""
    pid = client.post(
        "/api/products", json={"name": "Cache Item", "unit": "kg", "unit_price": 10}, headers=auth_headers
    ).json()["id"]

    client.post(
        f"/api/products/{pid}/image",
        files={"file": ("a.png", io.BytesIO(_png_bytes((80, 60))), "image/png")},
        headers=auth_headers,
    )
    first = client.get(f"/api/products/{pid}/image", headers=auth_headers)
    etag = first.headers["etag"]
    assert "no-cache" in first.headers["cache-control"]

    # unchanged -> browser revalidates cheaply with 304
    again = client.get(
        f"/api/products/{pid}/image", headers={**auth_headers, "If-None-Match": etag}
    )
    assert again.status_code == 304

    # replace the photo -> same request must now return the NEW bytes, not 304
    client.post(
        f"/api/products/{pid}/image",
        files={"file": ("b.png", io.BytesIO(_png_bytes((200, 200))), "image/png")},
        headers=auth_headers,
    )
    after = client.get(
        f"/api/products/{pid}/image", headers={**auth_headers, "If-None-Match": etag}
    )
    assert after.status_code == 200
    assert after.headers["etag"] != etag
    assert after.content != first.content


def test_product_image_rejects_non_image(client, auth_headers):
    pid = client.post(
        "/api/products", json={"name": "Bad Photo", "unit": "kg", "unit_price": 10}, headers=auth_headers
    ).json()["id"]
    files = {"file": ("evil.png", io.BytesIO(b"<?php echo 1; ?>"), "image/png")}
    r = client.post(f"/api/products/{pid}/image", files=files, headers=auth_headers)
    assert r.status_code == 400


def test_image_url_blocks_unsafe_targets(client, auth_headers):
    """SSRF guard: the server must refuse to fetch internal/private addresses."""
    import pytest

    from app.imaging import UnsafeUrlError, validate_image_url

    for bad in [
        "http://localhost/x.jpg",
        "http://127.0.0.1/x.jpg",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://10.0.0.5/x.jpg",
        "http://192.168.1.1/x.jpg",
        "file:///etc/passwd",
        "ftp://example.com/x.jpg",
    ]:
        with pytest.raises(UnsafeUrlError):
            validate_image_url(bad)


def test_image_from_url_rejects_bad_url_via_api(client, auth_headers):
    pid = client.post(
        "/api/products", json={"name": "Url Item", "unit": "kg", "unit_price": 10}, headers=auth_headers
    ).json()["id"]
    r = client.post(
        f"/api/products/{pid}/image/from-url",
        json={"url": "http://127.0.0.1:8000/api/health"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert client.get(f"/api/products/{pid}/image", headers=auth_headers).status_code == 404


def test_bulk_image_url_failure_is_reported_not_fatal(client, auth_headers):
    csv_data = b"name,category,unit,unit_price,image_url\nUrlBulk,Grains,kg,50,http://127.0.0.1/x.jpg\n"
    files = {"file": ("items.csv", io.BytesIO(csv_data), "text/csv")}
    r = client.post("/api/products/bulk", files=files, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1                       # item still created
    assert any("image not loaded" in e for e in body["errors"])
    item = next(p for p in client.get("/api/products", params={"search": "UrlBulk"}, headers=auth_headers).json())
    assert item["has_image"] is False


def test_product_image_requires_auth(client, auth_headers):
    pid = client.post(
        "/api/products", json={"name": "Auth Photo", "unit": "kg", "unit_price": 10}, headers=auth_headers
    ).json()["id"]
    assert client.get(f"/api/products/{pid}/image").status_code == 401


def test_category_image_lifecycle(client, auth_headers):
    name = "Dairy & Bread"          # spaces + & prove the query-param keying works
    def names():
        return [c["name"] for c in client.get("/api/categories/images", headers=auth_headers).json()]

    assert name not in names()

    files = {"file": ("cat.png", io.BytesIO(_png_bytes()), "image/png")}
    r = client.post(
        "/api/categories/image", params={"name": name}, files=files, headers=auth_headers
    )
    assert r.status_code == 204, r.text
    assert name in names()

    img = client.get("/api/categories/image", params={"name": name}, headers=auth_headers)
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"   # JPEG

    # replacing keeps a single row
    files = {"file": ("cat2.png", io.BytesIO(_png_bytes((40, 40))), "image/png")}
    assert client.post(
        "/api/categories/image", params={"name": name}, files=files, headers=auth_headers
    ).status_code == 204
    assert names().count(name) == 1

    assert client.delete(
        "/api/categories/image", params={"name": name}, headers=auth_headers
    ).status_code == 204
    assert client.get(
        "/api/categories/image", params={"name": name}, headers=auth_headers
    ).status_code == 404


def test_category_image_requires_auth_and_blocks_ssrf(client, auth_headers):
    assert client.get("/api/categories/images").status_code == 401
    r = client.post(
        "/api/categories/image/from-url",
        params={"name": "Grains"},
        json={"url": "http://169.254.169.254/latest/meta-data"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_product_search(client, auth_headers):
    client.post("/api/products", json={"name": "Sugarcane", "unit": "kg", "unit_price": 40}, headers=auth_headers)
    res = client.get("/api/products", params={"search": "sugarca"}, headers=auth_headers)
    assert any(p["name"] == "Sugarcane" for p in res.json())


def test_product_template_and_bulk(client, auth_headers):
    t = client.get("/api/products/template", headers=auth_headers)
    assert t.status_code == 200 and "name" in t.text
    csv_data = b"name,category,unit,unit_price\nWheat,Grains,kg,45\nOil,Grocery,litre,120\nWheat,Grains,kg,50\n"
    files = {"file": ("items.csv", io.BytesIO(csv_data), "text/csv")}
    r = client.post("/api/products/bulk", files=files, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["skipped"] == 1
    wheat = next(p for p in client.get("/api/products", params={"search": "Wheat"}, headers=auth_headers).json())
    assert wheat["category"] == "Grains"


def test_product_bulk_bad_price(client, auth_headers):
    csv_data = b"name,unit,unit_price\nBadItem,pc,abc\n"
    files = {"file": ("items.csv", io.BytesIO(csv_data), "text/csv")}
    r = client.post("/api/products/bulk", files=files, headers=auth_headers)
    assert r.json()["created"] == 0 and r.json()["skipped"] == 1
    assert r.json()["errors"]


# ---- Bulk customers ------------------------------------------------------

def test_customer_bulk_upload(client, auth_headers):
    csv_data = (
        b"name,phone,address,payment_type,note\n"
        b"Bulk One,111,Addr1,periodic,note1\n"
        b"Bulk Two,222,,per_use,\n"
        b",333,,per_use,missing name\n"
    )
    files = {"file": ("customers.csv", io.BytesIO(csv_data), "text/csv")}
    r = client.post("/api/customers/bulk", files=files, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    assert r.json()["skipped"] == 1
    listing = client.get("/api/customers", params={"search": "Bulk"}, headers=auth_headers).json()
    assert len(listing) >= 2


def test_bulk_rejects_bad_filetype(client, auth_headers):
    files = {"file": ("data.txt.pdf", io.BytesIO(b"nope"), "application/pdf")}
    r = client.post("/api/products/bulk", files=files, headers=auth_headers)
    assert r.status_code == 400


# ---- Dashboard -----------------------------------------------------------

def test_dashboard_totals(client, auth_headers):
    c = _new_customer(client, auth_headers, name="Dash Debtor")
    cid = c["id"]
    _bill(client, auth_headers, cid, 500, 0)     # a debt
    _bill(client, auth_headers, cid, 100, 100)   # cash sale (fully paid)
    _payment(client, auth_headers, cid, 200)     # pays part of debt
    stats = client.get("/api/dashboard", headers=auth_headers).json()
    assert stats["total_outstanding"] >= 300.0
    assert stats["debts_this_month"] >= 300.0     # 500 billed - 200 paid down
    assert stats["collected_this_month"] >= 300.0  # 100 cash + 200 payment
    assert any(d["name"] == "Dash Debtor" for d in stats["top_debtors"])


# ---- Password change -----------------------------------------------------

def test_change_password_flow(client, shopkeeper):
    login = client.post("/api/auth/login", json=shopkeeper)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    bad = client.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "brandnew123"}, headers=headers)
    assert bad.status_code == 400
    ok = client.post("/api/auth/change-password", json={"current_password": shopkeeper["password"], "new_password": "brandnew123"}, headers=headers)
    assert ok.status_code == 204
    assert client.post("/api/auth/login", json=shopkeeper).status_code == 401
    assert client.post("/api/auth/login", json={"username": shopkeeper["username"], "password": "brandnew123"}).status_code == 200
