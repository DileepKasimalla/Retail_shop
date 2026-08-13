export type PaymentType = "per_use" | "periodic";
export type EntryType = "charge" | "payment";

export interface Meta {
  app_name: string;
  currency_code: string;
  currency_symbol: string;
}

export interface User {
  id: number;
  username: string;
}

export interface Customer {
  id: number;
  name: string;
  phone: string | null;
  address: string | null;
  note: string | null;
  payment_type: PaymentType;
  is_active: boolean;
  created_at: string;
  balance: number;
  total_debts: number;
  total_received: number;
  last_activity: string | null;
}

export interface BillItem {
  id: number;
  product_id: number | null;
  name: string;
  unit: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface BillItemIn {
  product_id?: number | null;
  name: string;
  unit: string;
  unit_price: number;
  quantity: number;
}

export interface BillPayment {
  id: number;
  amount: number;
  paid_on: string;
  note: string | null;
  created_at: string;
}

export interface BillPaymentInput {
  amount: number;
  paid_on?: string | null;
  note?: string | null;
}

export interface SettleInput {
  amount: number;
  paid_on?: string | null;
  note?: string | null;
}

export interface SettleResult {
  total_paid: number;
  bills_settled: number;
  bills_touched: number;
  applied_to_bills: number;
  allocations: {
    entry_id: number;
    applied: number;
    bill_total: number;
    bill_remaining: number;
  }[];
}

export interface AdvanceInput {
  amount: number;
  occurred_on?: string | null;
  note?: string | null;
}

export interface LedgerEntry {
  id: number;
  customer_id: number;
  entry_type: EntryType;
  amount: number;
  paid_amount: number; // for a bill: total paid so far; remaining = amount - paid_amount
  description: string | null;
  occurred_on: string;
  created_at: string;
  items: BillItem[];
  payments: BillPayment[];
}

export interface Product {
  id: number;
  name: string;
  category: string;
  unit: string;
  unit_price: number;
  is_active: boolean;
  has_image: boolean;
  image_version: string;
}

export interface ProductInput {
  name: string;
  category: string;
  unit: string;
  unit_price: number;
}

export interface BulkResult {
  created: number;
  skipped: number;
  errors: string[];
}

export interface CustomerDetail extends Customer {
  entries: LedgerEntry[];
}

export interface DashboardStats {
  total_customers: number;
  active_customers: number;
  total_outstanding: number;
  total_advance: number;
  debts_this_month: number;
  collected_this_month: number;
  top_debtors: { id: number; name: string; balance: number }[];
}

export interface CustomerInput {
  name: string;
  phone?: string | null;
  address?: string | null;
  note?: string | null;
  payment_type: PaymentType;
}

export interface EntryInput {
  entry_type: EntryType;
  amount: number;
  description?: string | null;
  occurred_on?: string | null;
}

export interface EntryUpdate {
  amount?: number;
  paid_amount?: number;
  description?: string | null;
  occurred_on?: string | null;
}

export interface BillInput {
  items?: BillItemIn[];    // line items (total computed from these)
  amount?: number;         // manual total when there are no items
  paid_now?: number;       // amount paid on the spot (0 = full debt)
  description?: string | null;
  occurred_on?: string | null;
}

export interface BillUpdateInput {
  items?: BillItemIn[];    // if given, replaces all line items and recomputes total
  amount?: number;         // manual total when there are no items
  description?: string | null;
  occurred_on?: string | null;
}
