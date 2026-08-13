import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type {
  BillItemIn,
  CustomerDetail,
  LedgerEntry,
  PaymentType,
  Product,
  SettleResult,
} from "../api/types";
import BillItemsEditor, { qtyLabel, type BillLine } from "../components/BillItemsEditor";
import Modal from "../components/Modal";
import { formatDate, formatTime, money, todayISO } from "../lib/format";

function billSummary(entry: LedgerEntry): string {
  if (entry.items.length) {
    return entry.items.map((i) => `${qtyLabel(i.quantity)} ${i.unit} ${i.name}`).join(", ");
  }
  return entry.description ?? "";
}

function linesToItems(lines: BillLine[]): BillItemIn[] {
  return lines.map((l) => ({
    product_id: l.productId,
    name: l.name,
    unit: l.unit,
    unit_price: l.price,
    quantity: l.qty,
  }));
}

function entryToLines(entry: LedgerEntry): BillLine[] {
  return entry.items.map((it) => ({
    key: it.id,
    productId: it.product_id,
    name: it.name,
    unit: it.unit,
    price: it.unit_price,
    qty: it.quantity,
  }));
}

export default function CustomerDetailPage() {
  const { id } = useParams();
  const customerId = Number(id);
  const navigate = useNavigate();

  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showBill, setShowBill] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showAdvance, setShowAdvance] = useState(false);
  const [showStatement, setShowStatement] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<LedgerEntry | null>(null);
  const [viewingBill, setViewingBill] = useState<LedgerEntry | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCustomer(await api.getCustomer(customerId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load customer");
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (!Number.isFinite(customerId)) {
      setError("Invalid customer");
      setLoading(false);
      return;
    }
    load();
  }, [customerId, load]);

  // Newest first. Each row shows that bill's own balance (total - paid).
  const rows = useMemo(() => {
    if (!customer) return [];
    return [...customer.entries].sort(
      (a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.id - a.id,
    );
  }, [customer]);

  async function handleDeleteEntry(entry: LedgerEntry) {
    const label = entry.entry_type === "payment" ? "payment" : "bill";
    if (!confirm(`Delete this ${label} of ${money(entry.amount)}?`)) return;
    try {
      await api.deleteEntry(customerId, entry.id);
      load();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Could not delete entry");
    }
  }

  async function handleDeleteCustomer() {
    try {
      await api.deleteCustomer(customerId);
      navigate("/customers", { replace: true });
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Could not delete customer");
    }
  }

  if (loading) return <div className="spinner center" />;
  if (error) return <div className="alert alert-error">{error}</div>;
  if (!customer) return null;

  const balance = customer.balance;

  return (
    <div className="page">
      <Link to="/customers" className="link back">
        ← Back to customers
      </Link>

      <div className="detail-head">
        <div>
          <h2>
            {customer.name}
            {!customer.is_active && <span className="badge badge-muted">inactive</span>}
          </h2>
          <div className="meta-line">
            {customer.phone && <span>📞 {customer.phone}</span>}
            {customer.address && <span>📍 {customer.address}</span>}
            <span className={`badge ${customer.payment_type === "periodic" ? "badge-info" : "badge-muted"}`}>
              {customer.payment_type === "periodic" ? "Periodic" : "Per use"}
            </span>
          </div>
          {customer.note && <p className="note-box">{customer.note}</p>}
        </div>
        <div className="detail-actions">
          <button className="btn btn-ghost" onClick={() => setEditOpen(true)}>
            Edit
          </button>
          <button className="btn btn-danger-ghost" onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        </div>
      </div>

      <div className="balance-banner">
        <div className={`balance-main ${balance > 0 ? "owe" : balance < 0 ? "advance" : "settled"}`}>
          <span className="balance-label">
            {balance > 0 ? "Outstanding due" : balance < 0 ? "Advance balance" : "Fully settled"}
          </span>
          <span className="balance-amount">{money(Math.abs(balance))}</span>
        </div>
        <div className="balance-side">
          <div>
            <span className="muted">Total debts</span>
            <strong>{money(customer.total_debts)}</strong>
          </div>
          <div>
            <span className="muted">Total received</span>
            <strong>{money(customer.total_received)}</strong>
          </div>
        </div>
      </div>

      <div className="action-row">
        <button className="btn btn-primary" onClick={() => setShowBill(true)}>
          + Add Bill
        </button>
        <button className="btn btn-success" onClick={() => setShowPayment(true)}>
          + Record Payment
        </button>
        <button className="btn btn-ghost" onClick={() => setShowAdvance(true)}>
          + Add Advance
        </button>
      </div>

      <div className="card no-pad">
        <div className="card-head padded">
          <h3>Ledger ({customer.entries.length})</h3>
          {customer.entries.length > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={() => setShowStatement(true)}>
              🖨 Print all bills
            </button>
          )}
        </div>
        {rows.length === 0 ? (
          <p className="empty">No bills or payments yet. Add the first one above.</p>
        ) : (
          <div className="table-scroll">
            <table className="table ledger">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Details</th>
                  <th className="right">Total</th>
                  <th className="right">Paid</th>
                  <th className="right">Balance</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => {
                  const isBill = entry.entry_type === "charge";
                  const remaining = isBill ? entry.amount - entry.paid_amount : 0;
                  const paid = isBill ? entry.paid_amount : entry.amount;
                  const summary = billSummary(entry);
                  return (
                    <tr key={entry.id}>
                      <td className="nowrap">{formatDate(entry.occurred_on)}</td>
                      <td className="nowrap muted">{formatTime(entry.created_at)}</td>
                      <td>
                        {isBill ? (
                          <>
                            {summary ? summary : <span className="muted">—</span>}
                            {entry.items.length > 0 && entry.description && (
                              <span className="muted"> · {entry.description}</span>
                            )}
                          </>
                        ) : (
                          <>
                            {entry.description || <span className="muted">—</span>}
                            <span className="badge badge-info" style={{ marginLeft: 8 }}>
                              payment
                            </span>
                          </>
                        )}
                      </td>
                      <td className="right nowrap">{isBill ? money(entry.amount) : <span className="muted">—</span>}</td>
                      <td className="right">
                        {paid > 0 ? (
                          <span className="amount-paid">{money(paid)}</span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="right nowrap">
                        {isBill ? (
                          <span className={remaining > 0 ? "amount-owe" : "amount-paid"}>
                            {money(remaining)}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="right nowrap">
                        {isBill && (
                          <button
                            className="icon-btn"
                            title="View / pay / print"
                            onClick={() => setViewingBill(entry)}
                          >
                            🧾
                          </button>
                        )}
                        <button className="icon-btn" title="Edit entry" onClick={() => setEditingEntry(entry)}>
                          ✎
                        </button>
                        <button className="icon-btn danger" title="Delete entry" onClick={() => handleDeleteEntry(entry)}>
                          🗑
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showBill && (
        <BillModal
          customerId={customerId}
          defaultPaid={customer.payment_type === "per_use"}
          onClose={() => setShowBill(false)}
          onSaved={() => {
            setShowBill(false);
            load();
          }}
        />
      )}
      {showPayment && (
        <SettleModal
          customerId={customerId}
          outstanding={customer.total_debts}
          onClose={() => setShowPayment(false)}
          onSaved={() => {
            setShowPayment(false);
            load();
          }}
        />
      )}
      {showStatement && (
        <StatementModal customerId={customerId} onClose={() => setShowStatement(false)} />
      )}
      {showAdvance && (
        <AdvanceModal
          customerId={customerId}
          onClose={() => setShowAdvance(false)}
          onSaved={() => {
            setShowAdvance(false);
            load();
          }}
        />
      )}
      {viewingBill && (
        <BillDetailModal
          customerId={customerId}
          entry={viewingBill}
          onClose={() => setViewingBill(null)}
          onChanged={load}
          onEdit={(en) => {
            setViewingBill(null);
            setEditingEntry(en);
          }}
        />
      )}
      {editingEntry &&
        (editingEntry.entry_type === "charge" ? (
          <EditBillModal
            customerId={customerId}
            entry={editingEntry}
            onClose={() => setEditingEntry(null)}
            onSaved={() => {
              setEditingEntry(null);
              load();
            }}
          />
        ) : (
          <EditPaymentModal
            customerId={customerId}
            entry={editingEntry}
            onClose={() => setEditingEntry(null)}
            onSaved={() => {
              setEditingEntry(null);
              load();
            }}
          />
        ))}
      {editOpen && (
        <EditCustomerModal
          customer={customer}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            load();
          }}
        />
      )}
      {confirmDelete && (
        <Modal
          title="Delete customer?"
          onClose={() => setConfirmDelete(false)}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleDeleteCustomer}>
                Delete permanently
              </button>
            </>
          }
        >
          <p>
            This will permanently delete <strong>{customer.name}</strong> and all{" "}
            {customer.entries.length} ledger entries. This cannot be undone.
          </p>
          <p className="muted">
            Tip: to keep the history but hide the customer, use <em>Edit → mark inactive</em> instead.
          </p>
        </Modal>
      )}
    </div>
  );
}

// ---- Shared payment-status control ---------------------------------------

function PayStatus({
  payMode,
  setPayMode,
  paidNow,
  setPaidNow,
  total,
}: {
  payMode: "debt" | "partial" | "paid";
  setPayMode: (m: "debt" | "partial" | "paid") => void;
  paidNow: string;
  setPaidNow: (v: string) => void;
  total: number;
}) {
  return (
    <div className="full">
      <span className="field-label">Payment status</span>
      <div className="segmented">
        <button type="button" className={`seg ${payMode === "debt" ? "active danger" : ""}`} onClick={() => setPayMode("debt")}>
          Not paid (Debt)
        </button>
        <button type="button" className={`seg ${payMode === "partial" ? "active" : ""}`} onClick={() => setPayMode("partial")}>
          Partial
        </button>
        <button type="button" className={`seg ${payMode === "paid" ? "active success" : ""}`} onClick={() => setPayMode("paid")}>
          Paid
        </button>
      </div>
      {payMode === "partial" && (
        <div className="partial-box">
          <label className="field">
            <span>Amount paid now</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              max={total || undefined}
              value={paidNow}
              onChange={(e) => setPaidNow(e.target.value)}
              placeholder="e.g. 40"
            />
          </label>
          {total > 0 && Number(paidNow) > 0 && Number(paidNow) < total && (
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: 8 }}>
              Paying <strong className="amount-paid">{money(Number(paidNow))}</strong> now · remaining{" "}
              <strong className="amount-owe">{money(total - Number(paidNow))}</strong> becomes debt.
            </p>
          )}
        </div>
      )}
      <p className="muted" style={{ fontSize: "0.82rem", marginTop: 6 }}>
        {payMode === "paid"
          ? "Recorded as paid — it won't add to what the customer owes."
          : payMode === "partial"
            ? "The unpaid remainder is added to the customer's outstanding balance."
            : "Recorded as a debt — the full amount adds to the customer's outstanding balance."}
      </p>
    </div>
  );
}

// ---- Add Bill ------------------------------------------------------------

function BillModal({
  customerId,
  defaultPaid,
  onClose,
  onSaved,
}: {
  customerId: number;
  defaultPaid: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<BillLine[]>([]);
  const [manualAmount, setManualAmount] = useState("");
  const [note, setNote] = useState("");
  const [payMode, setPayMode] = useState<"debt" | "partial" | "paid">(defaultPaid ? "paid" : "debt");
  const [paidNow, setPaidNow] = useState("");
  const [date, setDate] = useState(todayISO());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.listProducts().then(setProducts).catch(() => setProducts([]));
  }, []);

  const itemsTotal = lines.reduce((s, l) => s + l.price * l.qty, 0);
  const total = lines.length ? itemsTotal : Number(manualAmount);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const amount = Math.round(total * 100) / 100;
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Add items or enter an amount greater than 0.");
      return;
    }
    let paid_now = 0;
    if (payMode === "paid") {
      paid_now = amount;
    } else if (payMode === "partial") {
      paid_now = Math.round(Number(paidNow) * 100) / 100;
      if (!Number.isFinite(paid_now) || paid_now <= 0) {
        setError("Enter how much is being paid now.");
        return;
      }
      if (paid_now >= amount) {
        setError("Amount paid now must be less than the total. Choose 'Paid' if fully paid.");
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await api.addBill(customerId, {
        items: lines.length ? linesToItems(lines) : undefined,
        amount: lines.length ? undefined : amount,
        paid_now,
        description: note.trim() || null,
        occurred_on: date || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Add Bill"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="bill-form" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Add Bill"}
          </button>
        </>
      }
    >
      <form id="bill-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <div className="full">
          <span className="field-label">Items</span>
          <BillItemsEditor products={products} lines={lines} setLines={setLines} />
        </div>
        {lines.length === 0 && (
          <label className="field">
            <span>Amount *</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={manualAmount}
              onChange={(e) => setManualAmount(e.target.value)}
            />
          </label>
        )}
        <label className="field">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayISO()} />
        </label>
        <label className="field full">
          <span>Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. remarks" />
        </label>
        <PayStatus payMode={payMode} setPayMode={setPayMode} paidNow={paidNow} setPaidNow={setPaidNow} total={total} />
      </form>
    </Modal>
  );
}

// ---- Record Payment: settle across the customer's unpaid bills -----------

function SettleModal({
  customerId,
  outstanding,
  onClose,
  onSaved,
}: {
  customerId: number;
  outstanding: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const due = Math.round(outstanding * 100) / 100;
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [date, setDate] = useState(todayISO());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<SettleResult | null>(null);

  const value = Number(amount) || 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than 0.");
      return;
    }
    if (value > due) {
      setError(
        `That's more than the outstanding ${money(due)}. Pay up to that amount, and use "Add Advance" for extra money.`,
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setResult(
        await api.settleCustomer(customerId, {
          amount: Math.round(value * 100) / 100,
          paid_on: date || null,
          note: note.trim() || null,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  if (result) {
    return (
      <Modal
        title="Payment recorded"
        onClose={onSaved}
        footer={
          <button className="btn btn-primary" onClick={onSaved}>
            Done
          </button>
        }
      >
        <div className="form-grid">
          <div className="alert alert-success full">
            Received <strong>{money(result.total_paid)}</strong>
          </div>
          <p className="full" style={{ fontSize: "0.92rem" }}>
            Paid <strong className="amount-paid">{money(result.applied_to_bills)}</strong> into{" "}
            <strong>{result.bills_touched}</strong> bill
            {result.bills_touched === 1 ? "" : "s"} · <strong>{result.bills_settled}</strong> now
            fully settled.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Record Payment"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-success" form="pay-form" type="submit" disabled={saving || due <= 0}>
            {saving ? "Saving…" : "Record Payment"}
          </button>
        </>
      }
    >
      <form id="pay-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}

        <div className="full outstanding-box">
          <span className="muted">Outstanding across all bills</span>
          <strong className={due > 0 ? "amount-owe" : "amount-paid"}>{money(due)}</strong>
        </div>

        {due <= 0 ? (
          <p className="muted full">
            This customer has no unpaid bills. To record money paid up front, use{" "}
            <strong>+ Add Advance</strong> instead.
          </p>
        ) : (
          <>
            <label className="field">
              <span>Amount *</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max={due}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={`Custom (max ${due})`}
                autoFocus
                required
              />
            </label>
            <label className="field">
              <span>Date</span>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayISO()} />
            </label>
            <label className="field full">
              <span>Note (optional)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Cash, UPI" />
            </label>

            <div className="full">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setAmount(String(due))}
              >
                Pay all debts ({money(due)})
              </button>
            </div>

            {value > 0 && value <= due && (
              <p className="muted full" style={{ fontSize: "0.85rem" }}>
                <strong className="amount-paid">{money(value)}</strong> will clear bills (oldest
                first). Remaining after this:{" "}
                <strong className="amount-owe">{money(due - value)}</strong>
              </p>
            )}
          </>
        )}
      </form>
    </Modal>
  );
}

// ---- Statement: all bills on one printable page --------------------------

function StatementModal({
  customerId,
  onClose,
}: {
  customerId: number;
  onClose: () => void;
}) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detailed, setDetailed] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      await api.downloadStatementPdf(customerId, {
        date_from: from || undefined,
        date_to: to || undefined,
        detailed,
      });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not generate the statement");
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Print all bills"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={download} disabled={busy}>
            {busy ? "Preparing…" : "🖨 Download statement"}
          </button>
        </>
      }
    >
      <div className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <p className="muted full" style={{ fontSize: "0.9rem" }}>
          One page listing every bill with its total, paid amount and balance — plus the overall
          summary. Leave the dates empty for the full history.
        </p>
        <label className="field">
          <span>From (optional)</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} max={todayISO()} />
        </label>
        <label className="field">
          <span>To (optional)</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} max={todayISO()} />
        </label>
        <label className="checkbox full">
          <input type="checkbox" checked={detailed} onChange={(e) => setDetailed(e.target.checked)} />
          Include payment dates under each bill
        </label>
      </div>
    </Modal>
  );
}

// ---- Add Advance: money paid up front, not tied to any bill --------------

function AdvanceModal({
  customerId,
  onClose,
  onSaved,
}: {
  customerId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [date, setDate] = useState(todayISO());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than 0.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.addAdvance(customerId, {
        amount: Math.round(value * 100) / 100,
        occurred_on: date || null,
        note: note.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Add Advance"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="adv-form" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Add Advance"}
          </button>
        </>
      }
    >
      <form id="adv-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <p className="muted full" style={{ fontSize: "0.88rem" }}>
          Money the customer pays up front, kept as credit. It is not applied to any bill — use{" "}
          <strong>Record Payment</strong> to pay off bills.
        </p>
        <label className="field">
          <span>Amount *</span>
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
            required
          />
        </label>
        <label className="field">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayISO()} />
        </label>
        <label className="field full">
          <span>Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Cash, UPI" />
        </label>
      </form>
    </Modal>
  );
}

// ---- Bill detail: items + payment history + add payment + PDF ------------

function BillDetailModal({
  customerId,
  entry: initialEntry,
  onClose,
  onChanged,
  onEdit,
}: {
  customerId: number;
  entry: LedgerEntry;
  onClose: () => void;
  onChanged: () => void;
  onEdit: (entry: LedgerEntry) => void;
}) {
  const [entry, setEntry] = useState<LedgerEntry>(initialEntry);
  const [payAmount, setPayAmount] = useState(""); // empty = type a custom amount
  const [payDate, setPayDate] = useState(todayISO());
  const [payNote, setPayNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function applyUpdated(updated: LedgerEntry) {
    setEntry(updated);
    onChanged();
  }

  async function addPayment() {
    const amt = Math.round(Number(payAmount) * 100) / 100;
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Enter an amount greater than 0.");
      return;
    }
    if (amt > entry.amount - entry.paid_amount + 0.001) {
      setError(`That's more than the remaining balance (${money(entry.amount - entry.paid_amount)}).`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.addBillPayment(customerId, entry.id, {
        amount: amt,
        paid_on: payDate || null,
        note: payNote.trim() || null,
      });
      applyUpdated(updated);
      setPayAmount("");
      setPayNote("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record payment");
    } finally {
      setBusy(false);
    }
  }

  async function removePayment(paymentId: number) {
    if (!confirm("Remove this payment?")) return;
    try {
      applyUpdated(await api.deleteBillPayment(customerId, entry.id, paymentId));
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Could not remove payment");
    }
  }

  const newRemaining = Math.round((entry.amount - entry.paid_amount) * 100) / 100;

  return (
    <Modal
      title={`Bill #${entry.id}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={() => onEdit(entry)}>
            Edit items
          </button>
          <button className="btn btn-ghost" onClick={() => api.downloadBillPdf(customerId, entry.id)}>
            🖨 Print / PDF
          </button>
          <button className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      <div className="bill-detail">
        {/* Items */}
        {entry.items.length > 0 ? (
          <table className="table mini">
            <thead>
              <tr>
                <th>Item</th>
                <th className="right">Qty</th>
                <th className="right">Rate</th>
                <th className="right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {entry.items.map((it) => (
                <tr key={it.id}>
                  <td>{it.name}</td>
                  <td className="right">{qtyLabel(it.quantity)} {it.unit}</td>
                  <td className="right">{money(it.unit_price)}</td>
                  <td className="right">{money(it.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">{entry.description || "No item breakdown for this bill."}</p>
        )}

        {/* Totals */}
        <div className="detail-totals">
          <div><span className="muted">Bill total</span><strong>{money(entry.amount)}</strong></div>
          <div><span className="muted">Paid</span><strong className="amount-paid">{money(entry.paid_amount)}</strong></div>
          <div>
            <span className="muted">Balance</span>
            <strong className={newRemaining > 0 ? "amount-owe" : "amount-paid"}>{money(newRemaining)}</strong>
          </div>
        </div>

        {/* Payment history */}
        <h4 className="detail-subhead">Payment history</h4>
        {entry.payments.length === 0 ? (
          <p className="muted" style={{ fontSize: "0.88rem" }}>No payments yet.</p>
        ) : (
          <div className="line-list">
            {entry.payments.map((p) => (
              <div key={p.id} className="line-item">
                <span>
                  {formatDate(p.paid_on)}
                  <span className="muted"> · {formatTime(p.created_at)}</span>
                  {p.note && <span className="muted"> · {p.note}</span>}
                </span>
                <span className="line-right">
                  <span className="amount-paid">{money(p.amount)}</span>
                  <button className="icon-btn danger" title="Remove payment" onClick={() => removePayment(p.id)}>
                    ✕
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Add payment */}
        {newRemaining > 0 && (
          <div className="add-payment">
            <h4 className="detail-subhead">Record a payment</h4>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="pay-row">
              <label className="field">
                <span>Amount</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={newRemaining}
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  placeholder={`Custom (max ${newRemaining})`}
                />
              </label>
              <label className="field">
                <span>Date</span>
                <input type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} max={todayISO()} />
              </label>
              <label className="field">
                <span>Note</span>
                <input value={payNote} onChange={(e) => setPayNote(e.target.value)} placeholder="Cash, UPI…" />
              </label>
            </div>
            <div className="pay-actions">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setPayAmount(String(newRemaining))}
              >
                Pay full ({money(newRemaining)})
              </button>
              <button type="button" className="btn btn-success" onClick={addPayment} disabled={busy}>
                {busy ? "Saving…" : "Add payment"}
              </button>
            </div>
          </div>
        )}
        {newRemaining <= 0 && entry.payments.length > 0 && (
          <p className="fully-paid-note">✓ This bill is fully paid.</p>
        )}
      </div>
    </Modal>
  );
}

// ---- Edit Bill (item-based) ----------------------------------------------

function EditBillModal({
  customerId,
  entry,
  onClose,
  onSaved,
}: {
  customerId: number;
  entry: LedgerEntry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<BillLine[]>(entryToLines(entry));
  const [manualAmount, setManualAmount] = useState(entry.items.length ? "" : String(entry.amount));
  const [note, setNote] = useState(entry.description ?? "");
  const [date, setDate] = useState(entry.occurred_on);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.listProducts().then(setProducts).catch(() => setProducts([]));
  }, []);

  const itemsTotal = lines.reduce((s, l) => s + l.price * l.qty, 0);
  const total = lines.length ? itemsTotal : Number(manualAmount);
  const remaining = Math.max(0, total - entry.paid_amount);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const amt = Math.round(total * 100) / 100;
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Add items or enter a bill amount greater than 0.");
      return;
    }
    if (amt < entry.paid_amount) {
      setError(
        `Bill total can't be less than what's already paid (${money(entry.paid_amount)}). Remove a payment first.`,
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateBill(customerId, entry.id, {
        items: lines.length ? linesToItems(lines) : undefined,
        amount: lines.length ? undefined : amt,
        description: note.trim() || null,
        occurred_on: date || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Edit Bill"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="edit-bill" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </>
      }
    >
      <form id="edit-bill" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <div className="full">
          <span className="field-label">Items — change quantities, add or remove</span>
          <BillItemsEditor products={products} lines={lines} setLines={setLines} />
        </div>
        {lines.length === 0 && (
          <label className="field">
            <span>Bill total *</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={manualAmount}
              onChange={(e) => setManualAmount(e.target.value)}
            />
          </label>
        )}
        <label className="field">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayISO()} />
        </label>
        <p className="muted full" style={{ fontSize: "0.85rem" }}>
          Bill total: <strong>{money(total)}</strong> · Paid so far:{" "}
          <strong className="amount-paid">{money(entry.paid_amount)}</strong> · Remaining:{" "}
          <strong className="amount-owe">{money(remaining)}</strong>
          <br />
          To record a payment, use the <strong>🧾 view</strong> button on the bill.
        </p>
        <label className="field full">
          <span>Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </form>
    </Modal>
  );
}

// ---- Edit Payment --------------------------------------------------------

function EditPaymentModal({
  customerId,
  entry,
  onClose,
  onSaved,
}: {
  customerId: number;
  entry: LedgerEntry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState(String(entry.amount));
  const [note, setNote] = useState(entry.description ?? "");
  const [date, setDate] = useState(entry.occurred_on);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const amt = Math.round(Number(amount) * 100) / 100;
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Enter an amount greater than 0.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateEntry(customerId, entry.id, {
        amount: amt,
        description: note.trim() || null,
        occurred_on: date || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Edit Payment"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="edit-pay" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </>
      }
    >
      <form id="edit-pay" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <label className="field">
          <span>Amount *</span>
          <input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </label>
        <label className="field">
          <span>Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayISO()} />
        </label>
        <label className="field full">
          <span>Note (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </form>
    </Modal>
  );
}

// ---- Edit customer -------------------------------------------------------

function EditCustomerModal({
  customer,
  onClose,
  onSaved,
}: {
  customer: CustomerDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: customer.name,
    phone: customer.phone ?? "",
    address: customer.address ?? "",
    note: customer.note ?? "",
    payment_type: customer.payment_type,
    is_active: customer.is_active,
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Name cannot be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateCustomer(customer.id, {
        name: form.name.trim(),
        phone: form.phone,
        address: form.address,
        note: form.note,
        payment_type: form.payment_type,
        is_active: form.is_active,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Edit Customer"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="edit-cust" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </>
      }
    >
      <form id="edit-cust" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <label className="field">
          <span>Name *</span>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </label>
        <label className="field">
          <span>Phone</span>
          <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </label>
        <label className="field">
          <span>Payment type</span>
          <select
            value={form.payment_type}
            onChange={(e) => setForm({ ...form, payment_type: e.target.value as PaymentType })}
          >
            <option value="per_use">Per use (pays each time)</option>
            <option value="periodic">Periodic (monthly / runs a tab)</option>
          </select>
        </label>
        <label className="field">
          <span>Status</span>
          <select
            value={form.is_active ? "active" : "inactive"}
            onChange={(e) => setForm({ ...form, is_active: e.target.value === "active" })}
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive (hidden from list)</option>
          </select>
        </label>
        <label className="field full">
          <span>Address</span>
          <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </label>
        <label className="field full">
          <span>Note</span>
          <textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </label>
      </form>
    </Modal>
  );
}
