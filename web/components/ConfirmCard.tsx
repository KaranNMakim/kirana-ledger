"use client";
import { useState } from "react";
import { api, type ConfirmBody, type UtteranceResult } from "../lib/api";
import { rupees, shortDate, KIND } from "../lib/format";

const KINDS = ["credit_sale", "payment", "return"] as const;

/** Shows what was understood, highlights low-confidence fields, and offers one-tap fixes. */
export function ConfirmCard({ result, onDone, onCancel }: {
  result: UtteranceResult; onDone: (r: UtteranceResult) => void; onCancel: () => void;
}) {
  const it = result.interpretation;
  const [intent, setIntent] = useState<(typeof KINDS)[number]>(it.intent === "query" ? "credit_sale" : it.intent);
  const [customerId, setCustomerId] = useState<string | undefined>(it.customer.status === "matched" ? it.customer.customer_id ?? undefined : undefined);
  const [newName, setNewName] = useState<string | undefined>();
  const [amount, setAmount] = useState<string>(it.amount != null ? String(it.amount) : "");
  const [items, setItems] = useState(it.items.map((i) => ({ sku: i.sku ?? "", qty: i.qty, unit: i.unit, name: i.product_name ?? i.product_text, alts: i.alternatives, ok: !!i.sku })));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const custQ = it.questions.find((q) => q.field === "customer");
  const weak = new Set(it.fields.filter((f) => !f.ok).map((f) => f.field.replace(/\[\d+\]/, "")));
  const itemsChanged = items.some((x, n) => x.sku !== (it.items[n]?.sku ?? "") || x.qty !== it.items[n]?.qty);

  async function save() {
    setBusy(true); setErr(null);
    const body: ConfirmBody = { pending_id: result.pending_id!, intent };
    if (newName) body.new_customer_name = newName; else if (customerId) body.customer_id = customerId;
    if (intent !== "payment" && (itemsChanged || it.items.some((i) => !i.sku))) {
      body.items = items.filter((x) => x.sku).map((x) => ({ sku: x.sku, qty: x.qty }));
    }
    const typed = Number(amount);
    if (amount !== "" && !Number.isNaN(typed) && (typed !== it.amount || it.amount_source === "balance_fraction" || intent === "payment")) body.amount = typed;
    try { onDone(await api.confirm(body)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function cancel() {
    if (result.pending_id) await api.confirm({ pending_id: result.pending_id, cancel: true }).catch(() => undefined);
    onCancel();
  }

  return (
    <section aria-label="Please confirm" className="rounded-2xl border-2 border-amber-400 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h2 className="text-base font-bold">Please check ✋</h2>
        <span className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">not saved yet</span>
      </div>
      <p className="mb-1 text-sm text-stone-500">Heard: “{result.parsed.text}”</p>
      <p className="mb-3 text-sm font-medium">{it.summary}</p>
      {result.reasons.length > 0 && (
        <ul className="mb-3 space-y-1 rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
          {result.reasons.map((r) => <li key={r}>• {r}</li>)}
        </ul>
      )}

      <fieldset className="mb-3">
        <legend className={`mb-1 text-xs font-semibold uppercase ${weak.has("intent") ? "text-red-700" : "text-stone-500"}`}>Type</legend>
        <div className="grid grid-cols-3 gap-2">
          {KINDS.map((k) => (
            <button key={k} type="button" onClick={() => setIntent(k)}
              className={`min-h-11 rounded-lg px-2 text-sm font-semibold ring-1 ${intent === k ? KIND[k].tone + " ring-2" : "bg-white ring-stone-300"}`}>
              {KIND[k].label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="mb-3">
        <legend className={`mb-1 text-xs font-semibold uppercase ${weak.has("customer") ? "text-red-700" : "text-stone-500"}`}>
          {custQ?.prompt ?? "Customer"}
        </legend>
        {it.customer.status === "matched" && !custQ && (
          <p className="rounded-lg bg-stone-100 px-3 py-2 text-sm">{it.customer.name}</p>
        )}
        <div className="space-y-2">
          {custQ?.options.map((o) => {
            const chosen = o.new_customer_name ? newName === o.new_customer_name : customerId === o.id && !newName;
            return (
              <button key={o.id ?? o.label} type="button"
                onClick={() => { if (o.new_customer_name) { setNewName(o.new_customer_name); setCustomerId(undefined); } else { setCustomerId(o.id ?? undefined); setNewName(undefined); } }}
                className={`flex min-h-12 w-full items-center justify-between rounded-lg px-3 text-left text-sm ring-1 ${chosen ? "bg-amber-100 ring-2 ring-amber-500" : "bg-white ring-stone-300"}`}>
                <span className="font-medium">{o.label}{o.locality ? <span className="text-stone-500"> · {o.locality}</span> : null}</span>
                {o.balance !== undefined && <span className="text-xs text-stone-600">owes {rupees(o.balance)}</span>}
              </button>
            );
          })}
        </div>
      </fieldset>

      {intent !== "payment" && items.length > 0 && (
        <fieldset className="mb-3">
          <legend className={`mb-1 text-xs font-semibold uppercase ${weak.has("items") ? "text-red-700" : "text-stone-500"}`}>Items</legend>
          <ul className="space-y-2">
            {items.map((x, n) => (
              <li key={n} className="rounded-lg bg-stone-50 p-2">
                <div className="flex items-center gap-2">
                  <button type="button" aria-label="less" className="h-10 w-10 rounded-lg bg-white text-lg ring-1 ring-stone-300"
                    onClick={() => setItems(items.map((y, m) => m === n ? { ...y, qty: Math.max(0.25, +(y.qty - (y.qty > 1 ? 1 : 0.25)).toFixed(2)) } : y))}>−</button>
                  <span className="w-16 text-center text-sm font-semibold">{x.qty} {x.unit}</span>
                  <button type="button" aria-label="more" className="h-10 w-10 rounded-lg bg-white text-lg ring-1 ring-stone-300"
                    onClick={() => setItems(items.map((y, m) => m === n ? { ...y, qty: +(y.qty + (y.qty >= 1 ? 1 : 0.25)).toFixed(2) } : y))}>+</button>
                  <span className={`flex-1 truncate text-sm ${x.sku ? "" : "font-semibold text-red-700"}`}>{x.sku ? x.name : `“${x.name}”?`}</span>
                </div>
                {(!x.ok || it.items[n]?.match !== "exact") && x.alts.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {x.alts.slice(0, 5).map((a) => (
                      <button key={a.sku} type="button" onClick={() => setItems(items.map((y, m) => m === n ? { ...y, sku: a.sku, name: a.name } : y))}
                        className={`min-h-9 rounded-full px-3 text-xs ring-1 ${x.sku === a.sku ? "bg-amber-200 ring-amber-500" : "bg-white ring-stone-300"}`}>
                        {a.name}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </fieldset>
      )}

      <label className="mb-4 block">
        <span className={`mb-1 block text-xs font-semibold uppercase ${weak.has("amount") ? "text-red-700" : "text-stone-500"}`}>
          Amount (₹){it.amount_source === "price_list" ? " · from price list" : it.amount_source === "balance_fraction" ? " · from balance" : ""}
        </span>
        <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
          placeholder={intent === "payment" ? "How much was paid?" : "auto from items"}
          className="min-h-12 w-full rounded-lg border border-stone-300 px-3 text-lg" />
      </label>
      <p className="mb-3 text-xs text-stone-500">Date: {shortDate(it.date)}</p>
      {err && <p role="alert" className="mb-2 text-sm text-red-700">{err}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={cancel} className="min-h-12 rounded-xl bg-stone-200 font-semibold">Discard</button>
        <button type="button" onClick={save} disabled={busy} className="min-h-12 rounded-xl bg-emerald-600 font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : "✓ Save"}
        </button>
      </div>
    </section>
  );
}
