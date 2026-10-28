"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ProductRow, type Vocab } from "../../lib/api";
import { rupees } from "../../lib/format";

const LANG_SHORT: Record<string, string> = { en: "EN", hi: "हि", gu: "ગુ", mr: "म" };
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

function NewProduct({ vocab, onDone }: { vocab: Vocab; onDone: (p: ProductRow) => void }) {
  const [f, setF] = useState({ name: "", category: "staples", unit: "kg", price: "", hi: "", gu: "", mr: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try {
      const aliases = Object.fromEntries((["hi", "gu", "mr"] as const).map((l) => [l, split(f[l])]).filter(([, v]) => v.length));
      onDone(await api.addProduct({ name: f.name.trim(), category: f.category, unit: f.unit, price: Number(f.price), aliases }));
    } catch (x) { setErr((x as Error).message); }
  }
  const input = "min-h-11 w-full rounded-lg border border-stone-300 bg-white px-3";
  return (
    <form onSubmit={save} className="space-y-3 rounded-2xl bg-white p-4 ring-2 ring-amber-300">
      <h3 className="font-bold">New product</h3>
      <input required placeholder="Name, e.g. Hapus Mango" value={f.name} onChange={set("name")} className={input} maxLength={60} aria-label="Product name" />
      <div className="grid grid-cols-2 gap-2">
        <select value={f.category} onChange={set("category")} className={input} aria-label="Category">
          {vocab.categories.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
        </select>
        <select value={f.unit} onChange={set("unit")} className={input} aria-label="Sold per">
          {Object.keys(vocab.units).map((u) => <option key={u} value={u}>per {u}</option>)}
        </select>
      </div>
      <input required inputMode="decimal" placeholder="Price ₹ per unit" value={f.price} onChange={set("price")} className={input} aria-label="Price" />
      <p className="text-xs font-semibold uppercase text-stone-500">Local names (comma separated)</p>
      <input placeholder="Hindi: aam, hapus aam" value={f.hi} onChange={set("hi")} className={input} aria-label="Hindi names" />
      <input placeholder="Gujarati: keri, hapus keri" value={f.gu} onChange={set("gu")} className={input} aria-label="Gujarati names" />
      <input placeholder="Marathi: amba" value={f.mr} onChange={set("mr")} className={input} aria-label="Marathi names" />
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <button type="submit" disabled={!f.name.trim() || !(Number(f.price) > 0)} className="min-h-12 w-full rounded-xl bg-emerald-600 font-bold text-white disabled:opacity-40">Add product</button>
    </form>
  );
}

function ProductCard({ p, onChange }: { p: ProductRow; onChange: (p: ProductRow) => void }) {
  const [open, setOpen] = useState(false);
  const [alias, setAlias] = useState("");
  const [lang, setLang] = useState("hi");
  const [price, setPrice] = useState(String(p.price));
  const [err, setErr] = useState<string | null>(null);
  async function run(f: () => Promise<Partial<ProductRow>>) {
    setErr(null);
    try { const r = await f(); onChange({ ...p, ...r }); setAlias(""); } catch (x) { setErr((x as Error).message); }
  }
  const names = Object.entries(p.aliases).flatMap(([l, forms]) => forms.map((a) => [l, a] as const));
  return (
    <li className="rounded-xl bg-white p-3 ring-1 ring-stone-200">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-start justify-between gap-2 text-left">
        <span className="min-w-0">
          <span className="block truncate font-semibold">{p.name} {p.custom && <span className="ml-1 rounded bg-amber-100 px-1.5 text-[10px] text-amber-800">yours</span>}</span>
          <span className="block truncate text-xs text-stone-500">{names.slice(0, 6).map(([, a]) => a).join(" · ") || "no local names yet"}</span>
        </span>
        <span className="shrink-0 text-sm font-semibold">{rupees(p.price)}<span className="text-xs font-normal text-stone-500">/{p.unit}</span></span>
      </button>
      {open && (
        <div className="mt-3 space-y-3 border-t border-stone-100 pt-3">
          <div className="flex flex-wrap gap-1.5">
            {names.map(([l, a]) => <span key={l + a} className="rounded-full bg-stone-100 px-2 py-1 text-xs"><b className="text-stone-500">{LANG_SHORT[l] ?? l}</b> {a}</span>)}
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api.addAlias(p.sku, alias, lang)); }}>
            <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language" className="min-h-11 rounded-lg border border-stone-300 bg-white px-2 text-sm">
              <option value="hi">हिंदी</option><option value="gu">ગુજરાતી</option><option value="mr">मराठी</option><option value="en">EN</option>
            </select>
            <input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="new local name" aria-label="New local name"
              className="min-h-11 min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3" maxLength={40} />
            <button type="submit" disabled={!alias.trim()} className="min-h-11 rounded-lg bg-[var(--color-ink)] px-3 text-sm font-semibold text-white disabled:opacity-40">Teach</button>
          </form>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api.setPrice(p.sku, Number(price))); }}>
            <label className="flex min-h-11 flex-1 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm">
              ₹ <input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} aria-label="Price" className="min-w-0 flex-1 outline-none" />
              <span className="text-stone-500">/{p.unit}</span>
            </label>
            <button type="submit" disabled={!(Number(price) > 0) || Number(price) === p.price} className="min-h-11 rounded-lg bg-stone-200 px-3 text-sm font-semibold disabled:opacity-40">Set price</button>
          </form>
          {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        </div>
      )}
    </li>
  );
}

export default function ProductsPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<ProductRow[] | null>(null);
  const [vocab, setVocab] = useState<Vocab | null>(null);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { api.vocab().then(setVocab).catch(() => undefined); }, []);
  useEffect(() => {
    const t = setTimeout(() => api.products(q || undefined).then((r) => setRows(r.products)).catch(() => setRows([])), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q]);
  const shown = (rows ?? []).filter((r) => q || r.custom).concat(q ? [] : (rows ?? []).filter((r) => !r.custom).slice(0, 25));
  return (
    <div className="space-y-3">
      <Link href="/shop/" className="inline-flex min-h-11 items-center text-sm text-stone-500">← Shop</Link>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-bold">Products &amp; local names</h2>
        <button type="button" onClick={() => setAdding(!adding)} className="min-h-11 shrink-0 rounded-xl bg-[var(--color-saffron)] px-3 text-sm font-semibold text-white">{adding ? "Close" : "+ New"}</button>
      </div>
      {adding && vocab && <NewProduct vocab={vocab} onDone={(p) => { setAdding(false); setNote(`Added ${p.name}. Try saying it on the Ledger tab.`); setQ(p.name); }} />}
      {note && <p role="status" className="rounded-lg bg-emerald-50 p-2 text-sm text-emerald-800">{note}</p>}
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: chawal, keri, Parle-G…" aria-label="Search products"
        className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" />
      <ul className="space-y-2">
        {shown.map((p) => <ProductCard key={p.sku} p={p} onChange={(np) => setRows((rows ?? []).map((r) => r.sku === np.sku ? { ...r, ...np } : r))} />)}
      </ul>
      {!q && rows && <p className="text-center text-xs text-stone-500">Showing your products and 25 of {rows.length}. Search to find any item.</p>}
    </div>
  );
}
