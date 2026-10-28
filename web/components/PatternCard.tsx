"use client";
import { useState } from "react";
import type { Pattern } from "../lib/api";
import { bandTone } from "../lib/format";

/** Behaviour summary with a "Why?" evidence list. Clearly labelled as a demo heuristic, not a credit score. */
export function PatternCard({ p }: { p: Pattern }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-500">{p.label}</h3>
        <span className="text-xs text-stone-500">{p.score}/100</span>
      </div>
      <p className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${bandTone(p.band)}`}>{p.band}</p>
      <p className="mt-2 text-sm text-stone-700">{p.summary}</p>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="mt-3 min-h-10 rounded-lg bg-stone-100 px-3 text-sm font-semibold">{open ? "Hide" : "Why?"}</button>
      {open && (
        <ul className="mt-3 space-y-2">
          {p.evidence.map((e) => (
            <li key={e.factor} className="rounded-lg bg-stone-50 p-2 text-sm">
              <div className="flex justify-between gap-2">
                <span className="font-medium">{e.factor}</span>
                <span className={e.impact < 0 ? "font-semibold text-red-700" : "text-stone-500"}>{e.impact < 0 ? e.impact : "0"}</span>
              </div>
              <p className="text-stone-700">{e.value}</p>
              <p className="text-xs text-stone-500">{e.explanation}</p>
            </li>
          ))}
          <li className="text-xs text-stone-500">Data: {p.data_sufficiency} · starts at 100, deductions above.</li>
        </ul>
      )}
      <p className="mt-3 rounded-lg bg-amber-50 p-2 text-[11px] leading-snug text-amber-900" role="note">⚠️ {p.disclaimer}</p>
    </section>
  );
}
