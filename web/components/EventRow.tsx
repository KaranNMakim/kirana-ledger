"use client";
import Link from "next/link";
import { useState } from "react";
import { api, type LedgerEvent } from "../lib/api";
import { KIND, rupees, shortDate } from "../lib/format";

/** One ledger line with undo and a quick amount edit; both are recorded as human corrections. */
export function EventRow({ e, onChange, showCustomer = true }: { e: LedgerEvent; onChange: () => void; showCustomer?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(String(e.amount));
  const [err, setErr] = useState<string | null>(null);
  const k = KIND[e.kind];
  const voided = e.status === "voided";
  const by = e.provenance.method;

  async function run(f: () => Promise<unknown>) {
    setErr(null);
    try { await f(); setEditing(false); onChange(); } catch (x) { setErr((x as Error).message); }
  }

  return (
    <li className={`rounded-xl bg-white p-3 ring-1 ring-stone-200 ${voided ? "opacity-50" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1 ${k.tone}`}>{k.label}</span>
            {showCustomer ? (
              <Link href={`/customer/?id=${encodeURIComponent(e.customer_id)}`} className="inline-flex min-h-9 items-center truncate font-semibold underline-offset-2 hover:underline">{e.customer_name}</Link>
            ) : <span className="text-sm text-stone-500">{shortDate(e.date)}</span>}
          </div>
          {e.items.length > 0 && (
            <p className="mt-1 truncate text-sm text-stone-600">{e.items.map((i) => `${i.qty} ${i.unit} ${i.name}`).join(", ")}</p>
          )}
          <p className="mt-0.5 text-[11px] text-stone-400">
            {showCustomer && `${shortDate(e.date)} · `}
            {by === "human" ? "confirmed by you" : by === "model" ? "LLM" : e.provenance.source.startsWith("seed") ? "seed data" : "auto (rules)"}
            {e.amount_source === "price_list" ? " · price list" : ""}
            {voided ? (e.superseded_by ? " · corrected" : " · undone") : ""}
          </p>
        </div>
        <span className={`shrink-0 text-base font-bold ${voided ? "line-through" : ""} ${e.kind === "credit_sale" ? "text-red-700" : "text-emerald-700"}`}>
          {k.sign}{rupees(e.amount)}
        </span>
      </div>
      {!voided && (
        <div className="mt-2 flex gap-2">
          <button type="button" onClick={() => run(() => api.undo(e.id, "undone from app"))} className="min-h-10 rounded-lg bg-stone-100 px-3 text-sm font-medium">↩ Undo</button>
          <button type="button" onClick={() => setEditing(!editing)} className="min-h-10 rounded-lg bg-stone-100 px-3 text-sm font-medium">✎ Edit amount</button>
        </div>
      )}
      {editing && (
        <div className="mt-2 flex gap-2">
          <input aria-label="New amount" inputMode="decimal" value={amount} onChange={(x) => setAmount(x.target.value.replace(/[^\d.]/g, ""))}
            className="min-h-10 flex-1 rounded-lg border border-stone-300 px-3" />
          <button type="button" onClick={() => run(() => api.edit(e.id, { amount: Number(amount), reason: "edited in app" }))}
            className="min-h-10 rounded-lg bg-emerald-600 px-4 font-semibold text-white">Save</button>
        </div>
      )}
      {err && <p role="alert" className="mt-1 text-xs text-red-700">{err}</p>}
    </li>
  );
}
