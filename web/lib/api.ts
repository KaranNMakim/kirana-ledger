// Typed client for the kirana-ledger API. Same origin when served from FastAPI; override for `next dev`.
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Intent = "credit_sale" | "payment" | "return" | "query";
export type Lang = "en" | "hinglish" | "gu";

export interface LedgerItem { sku: string; name: string; qty: number; unit: string; unit_price?: number | null; amount?: number | null }
export interface Provenance { source: string; timestamp: string; confidence: number; method: "rule" | "model" | "human" }
export interface LedgerEvent {
  id: string; kind: Exclude<Intent, "query">; customer_id: string; customer_name: string; amount: number; date: string;
  items: LedgerItem[]; status: "active" | "voided"; utterance?: string | null; amount_source?: string | null;
  supersedes?: string | null; superseded_by?: string | null; history: Record<string, unknown>[]; provenance: Provenance;
}
export interface FieldCheck { field: string; value: string | null; confidence: number; ok: boolean; reason?: string | null }
export interface QuestionOption { id?: string | null; sku?: string; label: string; balance?: number; locality?: string | null; new_customer_name?: string }
export interface Question { field: string; prompt: string; options: QuestionOption[] }
export interface ResolvedItem {
  raw: string; product_text: string; sku?: string | null; product_name?: string | null; qty: number; unit: string;
  line_amount?: number | null; confidence: number; match: string; alternatives: { sku: string; name: string; score: number }[]; notes: string[];
}
export interface Interpretation {
  intent: Intent; customer: { status: string; query?: string | null; customer_id?: string | null; name?: string | null; confidence: number;
    candidates: { id: string; name: string; score: number; balance: number; locality?: string | null }[] };
  items: ResolvedItem[]; amount: number | null; amount_source: string; date: string; fields: FieldCheck[]; questions: Question[];
  confidence: number; summary: string;
}
export interface UtteranceResult {
  utterance_id: string; decision: "saved" | "needs_confirmation" | "answered" | "rejected";
  parsed: { text: string; intent: Intent; method: string; notes: string[] };
  interpretation: Interpretation; pending_id?: string | null; event?: LedgerEvent | null; answer?: string | null; reasons: string[];
}
export interface CustomerRow {
  id: string; name: string; locality?: string | null; balance: number; last_payment_date?: string | null;
  last_payment_amount?: number | null; oldest_unpaid_days: number; band: string; score: number; summary: string;
}
export interface Evidence { factor: string; value: string; impact: number; explanation: string }
export interface Pattern { label: string; score: number; band: string; data_sufficiency: string; summary: string; evidence: Evidence[]; disclaimer: string }
export interface CustomerDetail {
  id: string; name: string; locality?: string | null; features: Record<string, number | string | null>;
  pattern: Pattern; events: LedgerEvent[]; reminders: { id: string; language: string; text: string }[]; props: Record<string, string>;
}
export interface ReminderDraft { customer_id: string; customer_name: string; language: Lang; tone: string; balance: number; text: string; method: string; sent: false; note: string }
export interface ConfirmBody {
  pending_id: string; intent?: Exclude<Intent, "query">; customer_id?: string; new_customer_name?: string;
  items?: { sku: string; qty: number; unit?: string | null; amount?: number | null }[]; amount?: number; cancel?: boolean;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public body: Record<string, unknown>) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: { "content-type": "application/json" }, cache: "no-store", ...init });
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try { body = await res.json(); } catch { /* not json */ }
    const d = body.detail ?? res.statusText;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg).join("; ") : JSON.stringify(d);
    throw new ApiError(msg, res.status, body);
  }
  return res.json() as Promise<T>;
}
const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });
const send = <T,>(method: string, path: string, body: unknown) => call<T>(path, { method, body: JSON.stringify(body) });

export interface Shop {
  id: string; name: string; locality?: string | null; language: string; mode: "demo" | "own"; configured: boolean;
  counts: { customers: number; entries: number; products: number; shop_products: number };
}
export interface ProductRow { sku: string; name: string; category: string; unit: string; price: number; aliases: Record<string, string[]>; custom?: boolean }
export interface Vocab { categories: string[]; languages: Record<string, string>; units: Record<string, { kind: string; surface: string[] }> }

export const api = {
  health: () => call<{ today: string; shop: string; llm_mode: string }>("/health"),
  utterance: (text: string, lang?: string) => post<UtteranceResult>("/utterance", { text, lang }),
  confirm: (body: ConfirmBody) => post<UtteranceResult>("/utterance/confirm", body),
  ledger: (limit = 30, customerId?: string) =>
    call<LedgerEvent[]>(`/ledger?limit=${limit}${customerId ? `&customer_id=${encodeURIComponent(customerId)}` : ""}`),
  undo: (id: string, reason?: string) => post<LedgerEvent>(`/ledger/${id}/undo`, { reason }),
  edit: (id: string, body: Record<string, unknown>) => post<LedgerEvent>(`/ledger/${id}/edit`, body),
  customers: (q?: string) => call<CustomerRow[]>(`/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  customer: (id: string) => call<CustomerDetail>(`/customers/${encodeURIComponent(id)}`),
  insights: () => call<any>("/insights"), // eslint-disable-line @typescript-eslint/no-explicit-any
  graph: (limit = 20, customerId?: string) =>
    call<{ nodes: { data: Record<string, any> }[]; edges: { data: Record<string, any> }[] }>( // eslint-disable-line @typescript-eslint/no-explicit-any
      `/graph?limit=${limit}${customerId ? `&customer_id=${encodeURIComponent(customerId)}` : ""}`),
  reminder: (customer_id: string, language: Lang, tone: "gentle" | "firm") =>
    post<ReminderDraft>("/reminders/draft", { customer_id, language, tone }),
  products: (q?: string) => call<{ products: ProductRow[] }>(`/products/aliases${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  vocab: () => call<Vocab>("/products/vocab"),
  addProduct: (body: { name: string; category: string; unit: string; price: number; aliases: Record<string, string[]> }) =>
    post<ProductRow>("/products", body),
  addAlias: (sku: string, text: string, lang: string) => post<ProductRow>(`/products/${encodeURIComponent(sku)}/aliases`, { text, lang }),
  setPrice: (sku: string, price: number) => send<ProductRow>("PATCH", `/products/${encodeURIComponent(sku)}`, { price }),
  shop: () => call<Shop>("/shop"),
  updateShop: (body: { name: string; locality?: string; language?: string }) => send<Shop>("PUT", "/shop", body),
  startEmpty: () => post<{ removed: Record<string, number>; shop: Shop }>("/shop/start-empty", { confirm: "DELETE" }),
  addCustomer: (body: { name: string; gender?: string; locality?: string; nickname?: string; force?: boolean }) =>
    post<{ id: string; name: string }>("/customers", body),
  exportUrl: (format: "turtle" | "jsonld" | "json", includeCatalog = false) =>
    `${API}/export?format=${format}${includeCatalog ? "&include_catalog=true" : ""}`,
};
