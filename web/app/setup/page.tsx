"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Shop } from "../../lib/api";

const LANGS = [
  { code: "hi-IN", label: "हिंदी / Hinglish" }, { code: "gu-IN", label: "ગુજરાતી" },
  { code: "mr-IN", label: "मराठी" }, { code: "en-IN", label: "English" },
];

/** First-run setup for your own shop (also reachable from Shop → Edit). */
export default function SetupPage() {
  const router = useRouter();
  const [shop, setShop] = useState<Shop | null>(null);
  const [name, setName] = useState("");
  const [locality, setLocality] = useState("");
  const [language, setLanguage] = useState("hi-IN");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.shop().then((s) => {
      setShop(s);
      if (s.configured) { setName(s.name); setLocality(s.locality ?? ""); setLanguage(s.language); }
    }).catch((e) => setErr(e.message));
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api.updateShop({ name: name.trim(), locality: locality.trim() || undefined, language });
      try { localStorage.setItem("kl-lang", language); } catch { /* private mode */ }
      window.dispatchEvent(new Event("kl-shop-changed"));
      router.push(shop?.configured ? "/shop/" : "/");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }

  const first = shop && !shop.configured;
  return (
    <form onSubmit={save} className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">{first ? "Namaste 🙏 Set up your shop" : "Shop details"}</h2>
        {first && (
          <p className="mt-1 text-sm text-stone-600">
            Your ledger starts empty. Add customers as you go, or just speak an entry: new names are offered as new
            customers. {shop?.counts.products} grocery items with local names are already loaded.
          </p>
        )}
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-stone-500">Shop name *</span>
        <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Patel Provision Store"
          className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" maxLength={80} />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-stone-500">Area / locality</span>
        <input value={locality} onChange={(e) => setLocality(e.target.value)} placeholder="e.g. Navrangpura, Ahmedabad"
          className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" maxLength={80} />
      </label>
      <fieldset>
        <legend className="mb-1 text-xs font-semibold uppercase text-stone-500">Speaking language</legend>
        <div className="grid grid-cols-2 gap-2">
          {LANGS.map((l) => (
            <button key={l.code} type="button" onClick={() => setLanguage(l.code)} aria-pressed={language === l.code}
              className={`min-h-12 rounded-xl text-sm font-semibold ring-1 ${language === l.code ? "bg-amber-100 ring-2 ring-amber-500" : "bg-white ring-stone-300"}`}>
              {l.label}
            </button>
          ))}
        </div>
      </fieldset>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <button type="submit" disabled={busy || !name.trim()} className="min-h-12 w-full rounded-xl bg-emerald-600 font-bold text-white disabled:opacity-40">
        {busy ? "Saving…" : first ? "Start my ledger →" : "Save"}
      </button>
      {shop?.mode === "demo" && (
        <p className="rounded-lg bg-stone-100 p-3 text-xs text-stone-600">
          You are in the demo shop (synthetic data, reset on every <code>make demo</code>). For your own shop run
          <code> make start</code>: it uses a separate database that starts empty and keeps your data.
        </p>
      )}
    </form>
  );
}
