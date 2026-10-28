"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Shop } from "../../lib/api";

const LANG_LABEL: Record<string, string> = { "hi-IN": "Hindi / Hinglish", "gu-IN": "Gujarati", "mr-IN": "Marathi", "en-IN": "English" };

const Card = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
    <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</h2>
    {children}
  </section>
);

export default function ShopPage() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api.shop().then(setShop).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function startEmpty() {
    setErr(null);
    try {
      const r = await api.startEmpty();
      const n = (k: number, w: string) => `${k} ${w}${k === 1 ? "" : "s"}`;
      setMsg(`Removed ${n(r.removed.Customer, "customer")}, ${n(r.removed.LedgerEvent, "entry").replace("entrys", "entries")} and ${n(r.removed.Reminder, "reminder draft")}. Products and local names were kept.`);
      setConfirm(""); setShop(r.shop);
      window.dispatchEvent(new Event("kl-shop-changed"));
    } catch (e) { setErr((e as Error).message); }
  }

  if (!shop) return <p className="text-sm text-stone-500">{err ?? "Loading…"}</p>;
  const c = shop.counts;
  return (
    <div className="space-y-4">
      <Card title="Your shop">
        <p className="text-lg font-bold">{shop.name}</p>
        <p className="text-sm text-stone-600">{shop.locality || "No area set"} · speaks {LANG_LABEL[shop.language] ?? shop.language}</p>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Customers</dt><dd className="text-base font-semibold">{c.customers}</dd></div>
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Entries</dt><dd className="text-base font-semibold">{c.entries}</dd></div>
          <div className="rounded-lg bg-stone-50 p-2"><dt className="text-stone-500">Products</dt><dd className="text-base font-semibold">{c.products}</dd></div>
        </dl>
        <Link href="/setup/" className="mt-3 flex min-h-11 items-center justify-center rounded-xl bg-stone-100 text-sm font-semibold">✎ Edit shop details</Link>
        {shop.mode === "demo" && <p className="mt-2 text-xs text-stone-500">Demo shop with synthetic data. Run <code>make start</code> for your own shop.</p>}
      </Card>

      <Card title="Build your knowledge graph">
        <div className="grid grid-cols-2 gap-2">
          <Link href="/customer-new/" className="flex min-h-14 flex-col items-center justify-center rounded-xl bg-amber-50 text-sm font-semibold ring-1 ring-amber-200">👤 Add customer</Link>
          <Link href="/products/" className="flex min-h-14 flex-col items-center justify-center rounded-xl bg-amber-50 text-sm font-semibold ring-1 ring-amber-200">🧺 Products &amp; local names</Link>
        </div>
        <p className="mt-2 text-xs text-stone-500">
          {c.shop_products} product{c.shop_products === 1 ? "" : "s"} added by you. Each local name you teach (e.g. &ldquo;bhaat&rdquo; for rice)
          becomes an <code>alias_of</code> fact in the graph, and the voice parser understands it straight away.
        </p>
      </Card>

      <Card title="Export your graph">
        <p className="mb-2 text-sm text-stone-600">Download everything (customers, entries, who-owes-what, with provenance for every fact) in open formats.</p>
        <div className="grid grid-cols-3 gap-2">
          <a href={api.exportUrl("turtle")} download className="flex min-h-11 items-center justify-center rounded-lg bg-stone-100 text-sm font-semibold">Turtle</a>
          <a href={api.exportUrl("jsonld")} download className="flex min-h-11 items-center justify-center rounded-lg bg-stone-100 text-sm font-semibold">JSON-LD</a>
          <a href={api.exportUrl("json")} download className="flex min-h-11 items-center justify-center rounded-lg bg-stone-100 text-sm font-semibold">JSON</a>
        </div>
        <a href={api.exportUrl("turtle", true)} download className="mt-2 block text-center text-xs text-stone-500 underline">…including the full product &amp; alias catalogue</a>
      </Card>

      <Card title="Start empty">
        <p className="text-sm text-stone-700">Permanently delete all customers, ledger entries and reminder drafts. Shop details, products and local names stay.</p>
        <label className="mt-3 block">
          <span className="mb-1 block text-xs text-stone-500">Type <b>DELETE</b> to confirm</span>
          <input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off"
            className="min-h-11 w-full rounded-lg border border-red-200 bg-white px-3" />
        </label>
        <button type="button" onClick={startEmpty} disabled={confirm !== "DELETE"}
          className="mt-2 min-h-11 w-full rounded-xl bg-red-600 font-semibold text-white disabled:opacity-30">Delete ledger and start empty</button>
        {msg && <p role="status" className="mt-2 text-sm text-emerald-800">{msg}</p>}
        {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      </Card>
    </div>
  );
}
