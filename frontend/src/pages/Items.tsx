import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { Product, ProductInput } from "../api/types";
import BulkUploadModal from "../components/BulkUploadModal";
import CategoryImage from "../components/CategoryImage";
import ItemImage, { iconFor } from "../components/ItemImage";
import Modal from "../components/Modal";
import { money } from "../lib/format";

export default function ItemsPage() {
  const [items, setItems] = useState<Product[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null); // null = category tiles
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [showBulk, setShowBulk] = useState(false);
  const [catImages, setCatImages] = useState<Map<string, string>>(new Map());
  const [editingCategory, setEditingCategory] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [products, withImages] = await Promise.all([
        api.listProducts(),
        api.listCategoryImages().catch(() => [] as { name: string; version: string }[]),
      ]);
      setItems(products);
      setCatImages(new Map(withImages.map((c) => [c.name, c.version])));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load items");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Categories with their items, sorted.
  const grouped = useMemo(() => {
    const map = new Map<string, Product[]>();
    for (const p of items) {
      const list = map.get(p.category) ?? [];
      list.push(p);
      map.set(p.category, list);
    }
    return Array.from(map.entries())
      .map(([cat, list]) => [cat, list.sort((a, b) => a.name.localeCompare(b.name))] as const)
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  const searching = query.trim().length > 0;
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return items.filter(
      (p) => p.name.toLowerCase().includes(q) || p.category.toLowerCase().includes(q),
    );
  }, [items, query]);

  const shown = searching
    ? results
    : category
      ? (grouped.find(([c]) => c === category)?.[1] ?? [])
      : [];

  async function handleDelete(p: Product) {
    if (!confirm(`Delete item "${p.name}"?`)) return;
    try {
      await api.deleteProduct(p.id);
      load();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Could not delete");
    }
  }

  const showingTiles = !searching && !category;

  return (
    <div className="page">
      <div className="page-head row">
        <div>
          <h2>Items</h2>
          <p className="muted">
            {items.length} item{items.length === 1 ? "" : "s"} in {grouped.length} categor
            {grouped.length === 1 ? "y" : "ies"}
          </p>
        </div>
        <div className="action-row">
          <button className="btn btn-ghost" onClick={() => setShowBulk(true)}>
            ⬆ Bulk upload
          </button>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            + Add Item
          </button>
        </div>
      </div>

      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search);
          setCategory(null);
        }}
      >
        <input
          className="search"
          placeholder="Search items…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="btn btn-primary" type="submit">
          Search
        </button>
        {searching && (
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
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="spinner center" />
      ) : items.length === 0 ? (
        <div className="card empty-card">
          <p className="empty">No items yet.</p>
          <div className="action-row">
            <button className="btn btn-ghost" onClick={() => setShowBulk(true)}>
              Bulk upload
            </button>
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
              Add your first item
            </button>
          </div>
        </div>
      ) : showingTiles ? (
        /* ---------- Category tiles ---------- */
        <div className="cat-grid">
          {grouped.map(([cat, list]) => (
            <div key={cat} className="cat-tile-wrap">
              <button className="cat-tile" onClick={() => setCategory(cat)}>
                <div className="cat-thumb">
                  <CategoryImage
                    name={cat}
                    hasImage={catImages.has(cat)}
                    version={catImages.get(cat) ?? "0"}
                    fallback={<CategoryCollage items={list} category={cat} />}
                  />
                </div>
                <div className="cat-name">{cat}</div>
                <div className="cat-count muted">
                  {list.length} item{list.length === 1 ? "" : "s"}
                </div>
              </button>
              <button
                className="icon-btn cat-edit"
                title="Set category picture"
                onClick={() => setEditingCategory(cat)}
              >
                ✎
              </button>
            </div>
          ))}
        </div>
      ) : (
        /* ---------- Product grid ---------- */
        <>
          <div className="crumb-row">
            {searching ? (
              <span className="muted">
                {results.length} result{results.length === 1 ? "" : "s"} for “{query}”
              </span>
            ) : (
              <>
                <button className="link back" onClick={() => setCategory(null)}>
                  ← All categories
                </button>
                <h3 className="section-head">
                  {category} <span className="muted">({shown.length})</span>
                </h3>
              </>
            )}
          </div>

          {shown.length === 0 ? (
            <div className="card empty-card">
              <p className="empty">No items found.</p>
            </div>
          ) : (
            <div className="item-grid">
              {shown.map((p) => (
                <div key={p.id} className="item-card">
                  <div className="item-thumb">
                    <ItemImage
                      productId={p.id}
                      hasImage={p.has_image}
                      name={p.name}
                      category={p.category}
                      version={p.image_version}
                    />
                    <div className="item-actions">
                      <button className="icon-btn" title="Edit" onClick={() => setEditing(p)}>
                        ✎
                      </button>
                      <button className="icon-btn danger" title="Delete" onClick={() => handleDelete(p)}>
                        🗑
                      </button>
                    </div>
                  </div>
                  <div className="item-body">
                    <div className="item-name" title={p.name}>
                      {p.name}
                    </div>
                    <div className="item-unit muted">{p.unit}</div>
                    <div className="item-price">{money(p.unit_price)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {showAdd && (
        <ItemModal
          categories={grouped.map(([c]) => c)}
          defaultCategory={category ?? undefined}
          onClose={() => setShowAdd(false)}
          onSaved={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}
      {editing && (
        <ItemModal
          product={editing}
          categories={grouped.map(([c]) => c)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {editingCategory && (
        <CategoryImageModal
          category={editingCategory}
          hasImage={catImages.has(editingCategory)}
          version={catImages.get(editingCategory) ?? "0"}
          onClose={() => setEditingCategory(null)}
          onSaved={(name, nowHasImage) => {
            setCatImages((prev) => {
              const next = new Map(prev);
              if (nowHasImage) next.set(name, String(Date.now()));
              else next.delete(name);
              return next;
            });
            setEditingCategory(null);
          }}
        />
      )}
      {showBulk && (
        <BulkUploadModal
          title="Bulk upload items"
          columnsHint="name (required), category, unit, unit_price"
          onUpload={api.bulkUploadProducts}
          onDownloadTemplate={api.downloadProductTemplate}
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

/** Set or remove the picture shown on a category tile. */
function CategoryImageModal({
  category,
  hasImage,
  version,
  onClose,
  onSaved,
}: {
  category: string;
  hasImage: boolean;
  version: string;
  onClose: () => void;
  onSaved: (name: string, hasImage: boolean) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const u = URL.createObjectURL(file);
    setPreview(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  async function save() {
    if (!file && !url.trim()) {
      setError("Choose a picture or paste an image link.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (file) await api.uploadCategoryImage(category, file);
      else await api.setCategoryImageFromUrl(category, url.trim());
      onSaved(category, true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the picture");
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteCategoryImage(category);
      onSaved(category, false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove the picture");
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Picture for “${category}”`}
      onClose={onClose}
      footer={
        <>
          {hasImage && (
            <button className="btn btn-danger-ghost" onClick={remove} disabled={busy}>
              Remove picture
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save picture"}
          </button>
        </>
      }
    >
      <div className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}
        <div className="full photo-picker">
          <div className="photo-preview" onClick={() => fileRef.current?.click()} role="button">
            {preview ? (
              <img src={preview} alt="Preview" className="item-img cover" />
            ) : (
              <CategoryImage
                name={category}
                hasImage={hasImage}
                version={version}
                fallback={
                  <div className="item-img placeholder">
                    <span>{iconFor(category)}</span>
                  </div>
                }
              />
            )}
          </div>
          <div className="photo-actions">
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()}>
              Choose picture
            </button>
            <span className="muted" style={{ fontSize: "0.8rem" }}>
              JPG / PNG, up to 6 MB
            </span>
          </div>
        </div>
        <label className="field full">
          <span>…or paste an image link</span>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…/dairy.jpg"
            disabled={!!file}
          />
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            Must be a direct link to the image file itself (ends in .jpg / .png), not a web page.
          </span>
        </label>
      </div>
    </Modal>
  );
}

/** Up to 4 item photos arranged in a tile, like a category thumbnail. */
function CategoryCollage({ items, category }: { items: Product[]; category: string }) {
  const withPhotos = items.filter((p) => p.has_image).slice(0, 4);
  if (withPhotos.length === 0) {
    return (
      <div className="cat-collage empty">
        <span>{iconFor(category)}</span>
      </div>
    );
  }
  return (
    <div className={`cat-collage n${withPhotos.length}`}>
      {withPhotos.map((p) => (
        <ItemImage
          key={p.id}
          productId={p.id}
          hasImage
          name={p.name}
          category={p.category}
          version={p.image_version}
        />
      ))}
    </div>
  );
}

function ItemModal({
  product,
  categories,
  defaultCategory,
  onClose,
  onSaved,
}: {
  product?: Product;
  categories: string[];
  defaultCategory?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ProductInput>({
    name: product?.name ?? "",
    category: product?.category ?? defaultCategory ?? "General",
    unit: product?.unit ?? "unit",
    unit_price: product?.unit_price ?? 0,
  });
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [hasImage, setHasImage] = useState(product?.has_image ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!imageFile) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(imageFile);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  async function removePhoto() {
    if (imageFile) {
      setImageFile(null);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    if (!product || !hasImage) return;
    try {
      await api.deleteProductImage(product.id);
      setHasImage(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove photo");
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Please enter an item name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = product
        ? await api.updateProduct(product.id, form)
        : await api.createProduct(form);
      if (imageFile) {
        await api.uploadProductImage(saved.id, imageFile);
      } else if (imageUrl.trim()) {
        await api.setProductImageFromUrl(saved.id, imageUrl.trim());
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save item");
      setSaving(false);
    }
  }

  const showingPhoto = preview || (product && hasImage);

  return (
    <Modal
      title={product ? "Edit Item" : "Add Item"}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn-primary" form="item-form" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <form id="item-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert alert-error full">{error}</div>}

        <div className="full photo-picker">
          <div className="photo-preview" onClick={() => fileRef.current?.click()} role="button">
            {preview ? (
              <img src={preview} alt="Preview" className="item-img" />
            ) : product ? (
              <ItemImage
                productId={product.id}
                hasImage={hasImage}
                name={form.name}
                category={form.category}
                version={product.image_version}
              />
            ) : (
              <div className="item-img placeholder">
                <span>📷</span>
              </div>
            )}
          </div>
          <div className="photo-actions">
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                setImageFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()}>
              {showingPhoto ? "Change photo" : "Add photo"}
            </button>
            {showingPhoto && (
              <button type="button" className="btn btn-danger-ghost btn-sm" onClick={removePhoto}>
                Remove
              </button>
            )}
            <span className="muted" style={{ fontSize: "0.8rem" }}>
              JPG / PNG, up to 6 MB
            </span>
          </div>
        </div>

        <label className="field full">
          <span>…or paste an image link</span>
          <input
            type="url"
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            placeholder="https://…/product-photo.jpg"
            disabled={!!imageFile}
          />
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            Right-click a product photo on any site → “Copy image address”, then paste it here.
          </span>
        </label>

        <label className="field full">
          <span>Item name *</span>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            autoFocus
            required
          />
        </label>
        <label className="field">
          <span>Category</span>
          <input
            list="category-list"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            placeholder="Grains, Dairy, Grocery…"
          />
          <datalist id="category-list">
            {categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label className="field">
          <span>Unit / size</span>
          <input
            value={form.unit}
            onChange={(e) => setForm({ ...form, unit: e.target.value })}
            placeholder="kg, 500 ml, packet…"
          />
        </label>
        <label className="field">
          <span>Price *</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.unit_price}
            onChange={(e) => setForm({ ...form, unit_price: Number(e.target.value) })}
            required
          />
        </label>
      </form>
    </Modal>
  );
}
