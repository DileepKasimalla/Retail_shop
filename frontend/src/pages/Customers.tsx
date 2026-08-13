import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Customer, CustomerInput, PaymentType } from "../api/types";
import BulkUploadModal from "../components/BulkUploadModal";
import Modal from "../components/Modal";
import { money } from "../lib/format";

export default function CustomersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");        // text in the box
  const [query, setQuery] = useState("");          // the applied search term
  const [onlyDebtors, setOnlyDebtors] = useState(searchParams.get("filter") === "debtors");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showBulk, setShowBulk] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCustomers({
        search: query.trim() || undefined,
        only_debtors: onlyDebtors || undefined,
      });
      setCustomers(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load customers");
    } finally {
      setLoading(false);
    }
  }

  // Reload whenever the applied query or filter changes.
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, onlyDebtors]);

  useEffect(() => {
    setSearchParams(onlyDebtors ? { filter: "debtors" } : {}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlyDebtors]);

  const totalOwed = useMemo(
    () => customers.reduce((s, c) => s + (c.balance > 0 ? c.balance : 0), 0),
    [customers],
  );

  return (
    <div className="page">
      <div className="page-head row">
        <div>
          <h2>Customers</h2>
          <p className="muted">
            {customers.length} shown · {money(totalOwed)} outstanding
          </p>
        </div>
        <div className="action-row">
          <button className="btn btn-ghost" onClick={() => setShowBulk(true)}>
            ⬆ Bulk upload
          </button>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            + Add Customer
          </button>
        </div>
      </div>

      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search);
        }}
      >
        <input
          className="search"
          placeholder="Search by name or phone…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="btn btn-primary" type="submit">
          Search
        </button>
        {query && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setSearch("");
              setQuery("");
            }}
          >
            Clear
          </button>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={onlyDebtors}
            onChange={(e) => setOnlyDebtors(e.target.checked)}
          />
          Only those who owe
        </label>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="spinner center" />
      ) : customers.length === 0 ? (
        <div className="card empty-card">
          <p className="empty">No customers found.</p>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            Add your first customer
          </button>
        </div>
      ) : (
        <div className="card no-pad">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Type</th>
                <th className="right">Balance</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id} className="clickable-row">
                  <td>
                    <Link to={`/customers/${c.id}`} className="cell-link">
                      <span className="cust-name">{c.name}</span>
                      {!c.is_active && <span className="badge badge-muted">inactive</span>}
                    </Link>
                  </td>
                  <td className="muted">{c.phone || "—"}</td>
                  <td>
                    <span className={`badge ${c.payment_type === "periodic" ? "badge-info" : "badge-muted"}`}>
                      {c.payment_type === "periodic" ? "Periodic" : "Per use"}
                    </span>
                  </td>
                  <td className="right">
                    <BalanceCell balance={c.balance} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <AddCustomerModal
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}
      {showBulk && (
        <BulkUploadModal
          title="Bulk upload customers"
          columnsHint="name (required), phone, address, payment_type, note"
          onUpload={api.bulkUploadCustomers}
          onDownloadTemplate={api.downloadCustomerTemplate}
          onClose={() => setShowBulk(false)}
          onDone={() => {
            setShowBulk(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function BalanceCell({ balance }: { balance: number }) {
  if (balance > 0) return <span className="amount-owe">{money(balance)} owed</span>;
  if (balance < 0) return <span className="amount-advance">{money(-balance)} advance</span>;
  return <span className="muted">Settled</span>;
}

function AddCustomerModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CustomerInput>({
    name: "",
    phone: "",
    address: "",
    note: "",
    payment_type: "per_use",
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Please enter a name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createCustomer({ ...form, name: form.name.trim() });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save customer");
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Add Customer"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="add-cust" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <form id="add-cust" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error">{error}</div>}
        <label className="field">
          <span>Name *</span>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            autoFocus
            required
          />
        </label>
        <label className="field">
          <span>Phone</span>
          <input
            value={form.phone ?? ""}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            inputMode="tel"
          />
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
          <span>Address</span>
          <input
            value={form.address ?? ""}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </label>
        <label className="field full">
          <span>Note</span>
          <textarea
            rows={2}
            value={form.note ?? ""}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </label>
      </form>
    </Modal>
  );
}
