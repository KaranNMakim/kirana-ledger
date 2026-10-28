"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, type CustomerDetail } from "../../lib/api";
import { rupees, shortDate, pct } from "../../lib/format";
import { PatternCard } from "../../components/PatternCard";
import { EventRow } from "../../components/EventRow";

function Detail() {
  const id = useSearchParams().get("id") ?? "";
  const [c, setC] = useState<CustomerDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showVoided, setShowVoided] = useState(false);
  const load = useCallback(() => { if (id) api.customer(id).then(setC).catch((e) => setErr(e.message)); }, [id]);
  useEffect(load, [load]);

  if (err) return <p role="alert" className="text-red-700">{err}</p>;
  if (!c) return <p className="text-sm text-stone-500">Loading…</p>;
  const f = c.features as Record<string, number | null>;
  const events = c.events.filter((e) => showVoided || e.status === "active");
  return (
    <div className="space-y-4">
      <Link href="/customers/" className="inline-flex min-h-11 items-center text-sm text-stone-500">← Customers</Link>
      <section className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
        <h2 className="text-xl font-bold">{c.name}</h2>
        <p className="text-sm text-stone-500">{c.locality}</p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs uppercase text-stone-500">Balance</p>
            <p className={`text-2xl font-bold ${(f.balance ?? 0) > 0 ? "text-red-700" : "text-emerald-700"}`}>{rupees(f.balance)}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-stone-500">Last payment</p>
            <p className="text-lg font-semibold">{f.last_payment_amount ? rupees(f.last_payment_amount) : "—"}</p>
            <p className="text-xs text-stone-500">{shortDate(c.features.last_payment_date as string)}</p>
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Avg days to pay</dt><dd className="text-base font-semibold">{f.avg_days_to_pay ?? "—"}</dd></div>
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Oldest unpaid</dt><dd className="text-base font-semibold">{f.oldest_unpaid_days ? `${f.oldest_unpaid_days}d` : "—"}</dd></div>
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Partial pays</dt><dd className="text-base font-semibold">{f.partial_payment_share != null ? pct(f.partial_payment_share) : "—"}</dd></div>
        </dl>
        {(f.balance ?? 0) > 1 && (
          <Link href={`/reminder/?id=${encodeURIComponent(c.id)}`}
            className="mt-4 flex min-h-12 items-center justify-center rounded-xl bg-[var(--color-saffron)] font-semibold text-white">
            💬 Draft reminder
          </Link>
        )}
        <Link href={`/graph/?id=${encodeURIComponent(c.id)}`} className="mt-2 flex min-h-11 items-center justify-center rounded-xl bg-stone-100 text-sm font-medium">
          🕸️ See in udhaar graph
        </Link>
      </section>
      <PatternCard p={c.pattern} />
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Ledger ({events.length})</h3>
          <label className="flex items-center gap-2 text-xs text-stone-600">
            <input type="checkbox" checked={showVoided} onChange={(e) => setShowVoided(e.target.checked)} className="h-5 w-5" />
            show corrections
          </label>
        </div>
        <ul className="space-y-2">{events.slice(0, 60).map((e) => <EventRow key={e.id} e={e} onChange={load} showCustomer={false} />)}</ul>
      </section>
    </div>
  );
}

export default function CustomerPage() {
  return <Suspense fallback={<p className="text-sm text-stone-500">Loading…</p>}><Detail /></Suspense>;
}
