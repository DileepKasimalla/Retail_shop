import { useMemo, useState } from "react";
import type { Product } from "../api/types";
import { money } from "../lib/format";

export interface BillLine {
  key: number;
  productId: number | null;
  name: string;
  unit: string;
  price: number;
  qty: number;
}

const FRACTIONAL_UNITS = ["kg", "g", "gram", "grams", "litre", "liter", "l", "ltr", "ml"];

export function qtyLabel(q: number): string {
  const map: Record<string, string> = { "0.25": "¼", "0.5": "½", "0.75": "¾" };
  if (map[String(q)]) return map[String(q)];
  // Show a clean number: integers as-is, otherwise up to 3 decimals, no trailing zeros.
  return String(Math.round(q * 1000) / 1000);
}

export function lineFromProduct(p: Product, qty: number): BillLine {
  return {
    key: Date.now() + Math.random(),
    productId: p.id,
    name: p.name,
    unit: p.unit,
    price: p.unit_price,
    qty,
  };
}

/** Category -> item picker with an editable list of quantity lines. */
export default function BillItemsEditor({
  products,
  lines,
  setLines,
}: {
  products: Product[];
  lines: BillLine[];
  setLines: React.Dispatch<React.SetStateAction<BillLine[]>>;
}) {
  const [selCategory, setSelCategory] = useState("");
  const [pickProduct, setPickProduct] = useState("");
  const [pickQty, setPickQty] = useState("1");
  const [err, setErr] = useState<string | null>(null);

  const categories = useMemo(
    () => Array.from(new Set(products.map((p) => p.category))).sort(),
    [products],
  );
  const itemsInCategory = useMemo(
    () => products.filter((p) => p.category === selCategory),
    [products, selCategory],
  );
  const selected = products.find((p) => p.id === Number(pickProduct)) || null;
  const presets =
    selected && FRACTIONAL_UNITS.includes(selected.unit.toLowerCase())
      ? [0.25, 0.5, 0.75, 1, 2]
      : [1, 2, 3, 5];

  const itemsTotal = lines.reduce((s, l) => s + l.price * l.qty, 0);

  function addLine() {
    const qty = Number(pickQty);
    if (!selected || !Number.isFinite(qty) || qty <= 0) {
      setErr("Pick an item and a valid quantity.");
      return;
    }
    setErr(null);
    setLines((prev) => [...prev, lineFromProduct(selected, qty)]);
    setPickProduct("");
    setPickQty("1");
  }

  function setQty(key: number, value: string) {
    const q = value === "" ? 0 : Number(value);
    setLines((prev) =>
      prev.map((l) => (l.key === key ? { ...l, qty: Number.isFinite(q) ? q : 0 } : l)),
    );
  }

  return (
    <div className="picker">
      {products.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          No items in your catalog yet. Add them on the <strong>Items</strong> page, or type an
          amount below.
        </p>
      ) : (
        <>
          {err && <div className="alert alert-error">{err}</div>}
          <div className="picker-row">
            <select
              value={selCategory}
              onChange={(e) => {
                setSelCategory(e.target.value);
                setPickProduct("");
              }}
            >
              <option value="">Choose category…</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              value={pickProduct}
              onChange={(e) => setPickProduct(e.target.value)}
              disabled={!selCategory}
            >
              <option value="">{selCategory ? "Choose item…" : "Pick a category first"}</option>
              {itemsInCategory.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {money(p.unit_price)}/{p.unit}
                </option>
              ))}
            </select>
          </div>

          {selected && (
            <div className="qty-picker">
              <span className="muted qty-hint">Quantity (per {selected.unit}):</span>
              <div className="qty-presets">
                {presets.map((q) => (
                  <button
                    type="button"
                    key={q}
                    className={`chip ${Number(pickQty) === q ? "active" : ""}`}
                    onClick={() => setPickQty(String(q))}
                  >
                    {qtyLabel(q)}
                  </button>
                ))}
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={pickQty}
                  onChange={(e) => setPickQty(e.target.value)}
                  className="qty-input"
                  aria-label="Custom quantity"
                  placeholder="qty"
                />
                <button type="button" className="btn btn-primary" onClick={addLine}>
                  Add item
                </button>
              </div>
              <span className="qty-hint">
                = <strong>{money(selected.unit_price * (Number(pickQty) || 0))}</strong>
              </span>
            </div>
          )}
        </>
      )}

      {lines.length > 0 && (
        <div className="line-list">
          {lines.map((l) => (
            <div key={l.key} className="line-item editable">
              <span className="line-name">{l.name}</span>
              <span className="line-right">
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={l.qty}
                  onChange={(e) => setQty(l.key, e.target.value)}
                  className="qty-input small"
                  aria-label={`Quantity of ${l.name}`}
                />
                <span className="line-unit muted">{l.unit}</span>
                <span className="line-amt">{money(l.price * l.qty)}</span>
                <button
                  type="button"
                  className="icon-btn danger"
                  title="Remove"
                  onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}
                >
                  ✕
                </button>
              </span>
            </div>
          ))}
          <div className="line-item line-total">
            <span>Total</span>
            <strong>{money(itemsTotal)}</strong>
          </div>
        </div>
      )}
    </div>
  );
}
