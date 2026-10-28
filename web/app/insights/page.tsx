"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { bandTone, rupees, shortDate } from "../../lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Row = { id: string; name: string; balance: number; oldest_unpaid_days: number; avg_days_to_pay: number | null; band: string };

function Bars({ data, keys }: { data: { label: string; [k: string]: number | string }[]; keys: { key: string; color: string; name: string }[] }) {
  const max = Math.max(1, ...data.flatMap((d) => keys.map((k) => Number(d[k.key]) || 0)));
  return (
    <div>
      <div className="flex h-36 items-end gap-2" role="img" aria-label="bar chart">
        {data.map((d) => (
          <div key={d.label} className="flex flex-1 flex-col items-center gap-1">
            <div className="flex h-28 w-full items-end justify-center gap-0.5">
              {keys.map((k) => (
                <div key={k.key} title={`${k.name}: ${rupees(Number(d[k.key]))}`} className="w-1/2 rounded-t"
                  style={{ height: `${(Number(d[k.key]) / max) * 100}%`, background: k.color }} />
              ))}
            </div>
            <span className="text-[10px] text-stone-500">{d.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3 text-[11px] text-stone-600">
        {keys.map((k) => <span key={k.key} className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: k.color }} />{k.name}</span>)}
      </div>
    </div>
  );
}

function CustList({ rows, extra }: { rows: Row[]; extra: (r: Row) => string }) {
  return (
    <ul className="divide-y divide-stone-100">
      {rows.map((r) => (
        <li key={r.id}>
          <Link href={`/customer/?id=${encodeURIComponent(r.id)}`} className="flex min-h-12 items-center justify-between gap-2 py-2">
            <span className="min-w-0">
              <span className="block truncate font-medium">{r.name}</span>
              <span className={`mt-0.5 inline-block rounded-full px-2 text-[10px] font-semibold ${bandTone(r.band)}`}>{r.band}</span>
            </span>
            <span className="shrink-0 text-right text-sm">
              <span className="block font-bold text-red-700">{rupees(r.balance)}</span>
              <span className="text-[11px] text-stone-500">{extra(r)}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

const Card = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
    <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</h2>
    {children}
  </section>
);

export default function InsightsPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.insights().then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <p role="alert" className="text-red-700">{err}</p>;
  if (!d) return <p className="text-sm text-stone-500">Loading…</p>;
  const t = d.totals, s = d.seasonality;
  if (!d.monthly.length) return <p className="rounded-xl bg-white p-4 text-sm text-stone-600 ring-1 ring-stone-200">No ledger entries yet. Insights appear once you record some udhaar.</p>;
  const months = d.monthly.map((m: any) => ({ label: shortDate(`${m.month}-01`).split(" ")[1], credit: m.credit, payments: m.payments }));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl bg-red-50 p-3 ring-1 ring-red-100"><p className="text-xs text-red-800">Total udhaar out</p><p className="text-xl font-bold text-red-800">{rupees(t.outstanding)}</p><p className="text-[11px] text-red-700">{t.customers_owing} of {t.customers} customers</p></div>
        <div className="rounded-2xl bg-emerald-50 p-3 ring-1 ring-emerald-100"><p className="text-xs text-emerald-800">Collected (30 days)</p><p className="text-xl font-bold text-emerald-800">{rupees(t.collected_last_30d)}</p><p className="text-[11px] text-emerald-700">given {rupees(t.credit_last_30d)}</p></div>
      </div>
      <Card title="Who owes most"><CustList rows={d.top_owed.slice(0, 5)} extra={(r) => r.oldest_unpaid_days ? `oldest ${r.oldest_unpaid_days}d` : ""} /></Card>
      <Card title="Who pays late"><CustList rows={d.late_payers.slice(0, 5)} extra={(r) => r.avg_days_to_pay ? `~${Math.round(r.avg_days_to_pay)} days to pay` : `oldest ${r.oldest_unpaid_days}d`} /></Card>
      <Card title="Udhaar given vs collected, by month">
        <Bars data={months} keys={[{ key: "credit", color: "#dc2626", name: "Udhaar given" }, { key: "payments", color: "#059669", name: "Collected" }]} />
      </Card>
      {d.seasons.length > 0 && <Card title="Seasonal pattern">
        <p className="text-sm">Festive and wedding days average <b>{rupees(s.festive_credit_per_day)}/day</b> of udhaar, against <b>{rupees(s.normal_credit_per_day)}/day</b> on other days ({(s.festive_credit_per_day / s.normal_credit_per_day).toFixed(1)}×).</p>
        {s.festive_avg_days_to_pay != null && s.normal_avg_days_to_pay != null && (
          <p className="mt-1 text-sm">Purchases made in festive seasons take <b>{Math.round(s.festive_avg_days_to_pay)} days</b> to clear on average, against <b>{Math.round(s.normal_avg_days_to_pay)}</b> otherwise. Open a customer to see their own festival pattern.</p>
        )}
        <ul className="mt-2 space-y-2">
          {d.seasons.map((x: any) => (
            <li key={x.id} className="rounded-lg bg-stone-50 p-2 text-sm">
              <div className="flex justify-between"><span className="font-medium">{x.name}</span><span className="text-stone-600">{rupees(x.credit_per_day)}/day</span></div>
              <p className="truncate text-xs text-stone-500">{shortDate(x.start)}–{shortDate(x.end)} · {x.top_products.slice(0, 3).map((p: any) => p.name).join(", ")}</p>
            </li>
          ))}
        </ul>
      </Card>}
      <Card title="Top products on udhaar">
        <ol className="space-y-1 text-sm">
          {d.top_products.slice(0, 8).map((p: any, i: number) => (
            <li key={p.sku} className="flex justify-between"><span>{i + 1}. {p.name}</span><span className="text-stone-600">{rupees(p.value)}</span></li>
          ))}
        </ol>
      </Card>
      <p className="text-center text-[11px] text-stone-400">{d.disclaimer}</p>
    </div>
  );
}
