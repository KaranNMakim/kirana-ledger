"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, type LedgerEvent, type UtteranceResult } from "../lib/api";
import { rupees } from "../lib/format";
import { Mic, LANGS } from "../components/Mic";
import { ConfirmCard } from "../components/ConfirmCard";
import { EventRow } from "../components/EventRow";

const EXAMPLES = [
  "Ramesh bhai ko 2 kilo chawal udhaar",
  "Meena ben ne 500 diye",
  "Suresh ka 3 packet Parle-G aur 1 litre tel likh do",
  "aaj Kishore ne aadha hisaab chukta kiya",
  "Kavitaben na khata ma 1 kilo khand lakhi do",
  "Kishore ka kitna baaki hai",
];

export default function LedgerPage() {
  const [lang, setLang] = useState("hi-IN");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UtteranceResult | null>(null);
  const [feed, setFeed] = useState<LedgerEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const router = useRouter();
  const refresh = useCallback(() => api.ledger(15).then(setFeed).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    api.shop().then((s) => {
      if (!s.configured) router.replace("/setup/");
      try { setLang(localStorage.getItem("kl-lang") || s.language || "hi-IN"); } catch { setLang(s.language || "hi-IN"); }
    }).catch(() => undefined);
    refresh();
  }, [refresh, router]);

  async function submit(t: string) {
    if (!t.trim()) return;
    setBusy(true); setErr(null); setResult(null);
    try { const r = await api.utterance(t.trim(), lang); setResult(r); setText(""); if (r.decision === "saved") refresh(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-amber-100">
        <div className="mb-3 flex justify-end">
          <label className="sr-only" htmlFor="lang">Speech language</label>
          <select id="lang" value={lang} onChange={(e) => { setLang(e.target.value); try { localStorage.setItem("kl-lang", e.target.value); } catch { /* ignore */ } }}
            className="min-h-10 rounded-lg border border-stone-300 bg-white px-2 text-sm">
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
        <Mic lang={lang} disabled={busy} onInterim={setText} onFinal={(t) => { setText(t); submit(t); }} />
        <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
          <label htmlFor="utt" className="sr-only">Type the entry</label>
          <input id="utt" value={text} onChange={(e) => setText(e.target.value)} placeholder="…or type: Ramesh ko 2 kilo chawal"
            className="min-h-12 flex-1 rounded-xl border border-stone-300 px-3 text-base" autoComplete="off" />
          <button type="submit" disabled={busy || !text.trim()} className="min-h-12 rounded-xl bg-[var(--color-ink)] px-4 font-semibold text-white disabled:opacity-40">
            {busy ? "…" : "Go"}
          </button>
        </form>
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1" aria-label="Examples">
          {EXAMPLES.map((x) => (
            <button key={x} type="button" onClick={() => submit(x)} className="min-h-9 shrink-0 rounded-full bg-amber-50 px-3 text-xs text-amber-900 ring-1 ring-amber-200">{x}</button>
          ))}
        </div>
      </section>

      {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}

      {result?.decision === "needs_confirmation" && (
        <ConfirmCard key={result.pending_id} result={result} onCancel={() => setResult(null)}
          onDone={(r) => { setResult(r); refresh(); }} />
      )}
      {result?.decision === "saved" && result.event && (
        <section role="status" className="rounded-2xl bg-emerald-50 p-4 ring-1 ring-emerald-200">
          <p className="font-bold text-emerald-800">✓ Saved: {result.interpretation.summary.split(":")[0]}</p>
          <p className="text-sm text-emerald-900">
            <Link className="underline" href={`/customer/?id=${encodeURIComponent(result.event.customer_id)}`}>{result.event.customer_name}</Link>
            {" "}· {rupees(result.event.amount)} {result.event.items.length ? `· ${result.event.items.map((i) => `${i.qty} ${i.unit} ${i.name}`).join(", ")}` : ""}
          </p>
          <button type="button" className="mt-2 min-h-10 rounded-lg bg-white px-3 text-sm font-medium ring-1 ring-emerald-300"
            onClick={async () => { await api.undo(result.event!.id, "undo right after saving"); setResult(null); refresh(); }}>↩ Undo</button>
        </section>
      )}
      {result?.decision === "answered" && (
        <section role="status" className="rounded-2xl bg-sky-50 p-4 text-sky-900 ring-1 ring-sky-200">
          <p className="font-semibold">{result.answer}</p>
        </section>
      )}
      {result?.decision === "rejected" && <p className="text-sm text-stone-500">Discarded.</p>}

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">Live ledger</h2>
        <ul className="space-y-2">
          {feed.map((e) => <EventRow key={e.id} e={e} onChange={refresh} />)}
        </ul>
        {feed.length === 0 && (
          <p className="rounded-xl bg-white p-4 text-sm text-stone-600 ring-1 ring-stone-200">
            No entries yet. Speak or type your first udhaar above, e.g. <i>“Ramesh bhai ko 2 kilo chawal udhaar”</i>. A name
            the app has not heard before is offered as a new customer.
          </p>
        )}
      </section>
    </div>
  );
}
