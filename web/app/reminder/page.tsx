"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Lang, type ReminderDraft } from "../../lib/api";

const LANGS: { code: Lang; label: string }[] = [
  { code: "hinglish", label: "Hinglish" }, { code: "gu", label: "Gujarati" }, { code: "en", label: "English" },
];

function Reminder() {
  const id = useSearchParams().get("id") ?? "";
  const [lang, setLang] = useState<Lang>("hinglish");
  const [tone, setTone] = useState<"gentle" | "firm">("gentle");
  const [draft, setDraft] = useState<ReminderDraft | null>(null);
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setErr(null);
    api.reminder(id, lang, tone).then((d) => { setDraft(d); setText(d.text); }).catch((e) => setErr(e.message));
  }, [id, lang, tone]);

  async function copy() {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.getElementById("draft") as HTMLTextAreaElement | null;
      ta?.select(); document.execCommand("copy");
    }
    setCopied(true); setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="space-y-4">
      <Link href={`/customer/?id=${encodeURIComponent(id)}`} className="inline-flex min-h-11 items-center text-sm text-stone-500">← {draft?.customer_name ?? "Customer"}</Link>
      <h2 className="text-lg font-bold">Payment reminder</h2>
      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Language">
        {LANGS.map((l) => (
          <button key={l.code} type="button" role="radio" aria-checked={lang === l.code} onClick={() => setLang(l.code)}
            className={`min-h-11 rounded-lg text-sm font-semibold ring-1 ${lang === l.code ? "bg-amber-100 ring-2 ring-amber-500" : "bg-white ring-stone-300"}`}>{l.label}</button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Tone">
        {(["gentle", "firm"] as const).map((t) => (
          <button key={t} type="button" role="radio" aria-checked={tone === t} onClick={() => setTone(t)}
            className={`min-h-11 rounded-lg text-sm font-semibold capitalize ring-1 ${tone === t ? "bg-amber-100 ring-2 ring-amber-500" : "bg-white ring-stone-300"}`}>{t}</button>
        ))}
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <label htmlFor="draft" className="sr-only">Reminder text</label>
      <textarea id="draft" value={text} onChange={(e) => setText(e.target.value)} rows={8}
        className="w-full rounded-xl border border-stone-300 bg-[#e7ffdb] p-3 text-[15px] leading-relaxed" />
      <button type="button" onClick={copy} disabled={!text} className="min-h-12 w-full rounded-xl bg-emerald-600 font-bold text-white">
        {copied ? "✓ Copied" : "📋 Copy text"}
      </button>
      <p className="rounded-lg bg-stone-100 p-3 text-xs text-stone-600" role="note">
        {draft?.note ?? "Draft only. Nothing is sent from this app."}
      </p>
    </div>
  );
}

export default function ReminderPage() {
  return <Suspense fallback={<p className="text-sm text-stone-500">Loading…</p>}><Reminder /></Suspense>;
}
