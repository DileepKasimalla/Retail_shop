import type {
  AdvanceInput,
  BillInput,
  BillPaymentInput,
  BillUpdateInput,
  BulkResult,
  Customer,
  CustomerDetail,
  CustomerInput,
  DashboardStats,
  EntryInput,
  EntryUpdate,
  LedgerEntry,
  Meta,
  Product,
  ProductInput,
  SettleInput,
  SettleResult,
  User,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "shop_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Called when a request comes back 401 — lets AuthContext force a logout.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  // A 401 on an *authenticated* request means our token expired — log out and
  // say so. A 401 with no token (e.g. the login call itself) is just bad
  // credentials, so surface the server's actual message.
  if (res.status === 401) {
    if (token) {
      onUnauthorized?.();
      throw new ApiError(401, "Your session has expired. Please log in again.");
    }
    throw new ApiError(401, extractDetail(data) ?? "Incorrect username or password");
  }

  if (!res.ok) {
    const detail = extractDetail(data) ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const form = new FormData();
  form.append("file", file);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: form });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  if (res.status === 401) {
    onUnauthorized?.();
    throw new ApiError(401, "Your session has expired. Please log in again.");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(data) ?? `Upload failed (${res.status})`);
  }
  return data as T;
}

/** Fetch a file (with auth) and trigger a browser download. */
async function downloadFile(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { headers });
  if (!res.ok) throw new ApiError(res.status, "Could not download the template.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function extractDetail(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors come back as an array of objects.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "";
    return field ? `${field}: ${first.msg}` : (first.msg ?? "Invalid input");
  }
  return null;
}

export const api = {
  // meta / auth
  meta: () => request<Meta>("/api/meta"),
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),

  // dashboard
  dashboard: () => request<DashboardStats>("/api/dashboard"),

  // customers
  listCustomers: (params: {
    search?: string;
    include_inactive?: boolean;
    only_debtors?: boolean;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.search) qs.set("search", params.search);
    if (params.include_inactive) qs.set("include_inactive", "true");
    if (params.only_debtors) qs.set("only_debtors", "true");
    const q = qs.toString();
    return request<Customer[]>(`/api/customers${q ? `?${q}` : ""}`);
  },
  getCustomer: (id: number) => request<CustomerDetail>(`/api/customers/${id}`),
  createCustomer: (data: CustomerInput) =>
    request<Customer>("/api/customers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateCustomer: (id: number, data: Partial<CustomerInput> & { is_active?: boolean }) =>
    request<Customer>(`/api/customers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteCustomer: (id: number) =>
    request<void>(`/api/customers/${id}`, { method: "DELETE" }),

  // ledger
  addBill: (customerId: number, data: BillInput) =>
    request<LedgerEntry>(`/api/customers/${customerId}/bill`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateBill: (customerId: number, entryId: number, data: BillUpdateInput) =>
    request<LedgerEntry>(`/api/customers/${customerId}/bill/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  addBillPayment: (customerId: number, entryId: number, data: BillPaymentInput) =>
    request<LedgerEntry>(`/api/customers/${customerId}/bill/${entryId}/payment`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteBillPayment: (customerId: number, entryId: number, paymentId: number) =>
    request<LedgerEntry>(`/api/customers/${customerId}/bill/${entryId}/payment/${paymentId}`, {
      method: "DELETE",
    }),
  settleCustomer: (customerId: number, data: SettleInput) =>
    request<SettleResult>(`/api/customers/${customerId}/settle`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  addAdvance: (customerId: number, data: AdvanceInput) =>
    request<LedgerEntry>(`/api/customers/${customerId}/advance`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  billPdfUrl: (customerId: number, entryId: number) =>
    `/api/customers/${customerId}/bill/${entryId}/pdf`,
  downloadBillPdf: (customerId: number, entryId: number) =>
    downloadFile(`/api/customers/${customerId}/bill/${entryId}/pdf`, `bill_${entryId}.pdf`),
  downloadStatementPdf: (
    customerId: number,
    opts: { date_from?: string; date_to?: string; detailed?: boolean } = {},
  ) => {
    const qs = new URLSearchParams();
    if (opts.date_from) qs.set("date_from", opts.date_from);
    if (opts.date_to) qs.set("date_to", opts.date_to);
    if (opts.detailed === false) qs.set("detailed", "false");
    const q = qs.toString();
    return downloadFile(
      `/api/customers/${customerId}/statement/pdf${q ? `?${q}` : ""}`,
      `statement_${customerId}.pdf`,
    );
  },
  addEntry: (customerId: number, data: EntryInput) =>
    request<LedgerEntry>(`/api/customers/${customerId}/entries`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateEntry: (customerId: number, entryId: number, data: EntryUpdate) =>
    request<LedgerEntry>(`/api/customers/${customerId}/entries/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteEntry: (customerId: number, entryId: number) =>
    request<void>(`/api/customers/${customerId}/entries/${entryId}`, {
      method: "DELETE",
    }),

  // bulk customers
  bulkUploadCustomers: (file: File) => uploadFile<BulkResult>("/api/customers/bulk", file),
  downloadCustomerTemplate: () =>
    downloadFile("/api/customers/template", "customers_template.csv"),

  // products / items
  listProducts: (params: { search?: string; include_inactive?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.search) qs.set("search", params.search);
    if (params.include_inactive) qs.set("include_inactive", "true");
    const q = qs.toString();
    return request<Product[]>(`/api/products${q ? `?${q}` : ""}`);
  },
  createProduct: (data: ProductInput) =>
    request<Product>("/api/products", { method: "POST", body: JSON.stringify(data) }),
  updateProduct: (id: number, data: Partial<ProductInput> & { is_active?: boolean }) =>
    request<Product>(`/api/products/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProduct: (id: number) =>
    request<void>(`/api/products/${id}`, { method: "DELETE" }),
  bulkUploadProducts: (file: File) => uploadFile<BulkResult>("/api/products/bulk", file),
  uploadProductImage: (id: number, file: File) =>
    uploadFile<Product>(`/api/products/${id}/image`, file),
  setProductImageFromUrl: (id: number, url: string) =>
    request<Product>(`/api/products/${id}/image/from-url`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  deleteProductImage: (id: number) =>
    request<Product>(`/api/products/${id}/image`, { method: "DELETE" }),
  /** Fetch an item photo with auth and return an object URL (revoke when done). */
  downloadProductTemplate: () =>
    downloadFile("/api/products/template", "items_template.csv"),

  // category tile images
  listCategoryImages: () =>
    request<{ name: string; version: string }[]>("/api/categories/images"),
  uploadCategoryImage: (name: string, file: File) =>
    uploadFile<void>(`/api/categories/image?name=${encodeURIComponent(name)}`, file),
  setCategoryImageFromUrl: (name: string, url: string) =>
    request<void>(`/api/categories/image/from-url?name=${encodeURIComponent(name)}`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  deleteCategoryImage: (name: string) =>
    request<void>(`/api/categories/image?name=${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
};
