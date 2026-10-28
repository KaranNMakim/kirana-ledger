"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type CustomerRow } from "../../lib/api";
import { bandTone, rupees, shortDate } from "../../lib/format";

export default function CustomersPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<CustomerRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => api.customers(q || undefined).then(setRows).catch((e) => setErr(e.message)), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-3">
      <label htmlFor="q" className="sr-only">Search customers</label>
      <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: Ramesh, meenaben, Kishor…"
        className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" />
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      {!rows && !err && <p className="text-sm text-stone-500">Loading…</p>}
      <ul className="space-y-2">
        {rows?.map((c) => (
          <li key={c.id}>
            <Link href={`/customer/?id=${encodeURIComponent(c.id)}`} className="block rounded-xl bg-white p-3 ring-1 ring-stone-200 active:bg-amber-50">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.name}</p>
                  <p className="text-xs text-stone-500">{c.locality} · last paid {c.last_payment_date ? `${rupees(c.last_payment_amount)} on ${shortDate(c.last_payment_date)}` : "never"}</p>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${c.balance > 0 ? "text-red-700" : "text-emerald-700"}`}>{rupees(c.balance)}</p>
                  {c.oldest_unpaid_days > 30 && <p className="text-[11px] text-stone-500">oldest {c.oldest_unpaid_days}d</p>}
                </div>
              </div>
              <span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${bandTone(c.band)}`}>{c.band}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="pb-2 text-center text-[11px] text-stone-400">Behaviour labels are a demo heuristic, not a credit score.</p>
    </div>
  );
}
