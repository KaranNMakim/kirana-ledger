"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { shortDate } from "../lib/format";

export function Header() {
  const [h, setH] = useState<{ shop: string; today: string; llm_mode: string } | null>(null);
  useEffect(() => {
    api.health().then(setH).catch(() => setH(null));
    if ("serviceWorker" in navigator && location.hostname !== "localhost:3141") {
      navigator.serviceWorker.register("/app/sw.js").catch(() => undefined);
    }
  }, []);
  return (
    <header className="sticky top-0 z-20 border-b border-amber-200/70 bg-[var(--color-paper)]/95 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="truncate text-base font-bold text-[var(--color-saffron)]">{h?.shop ?? "Kirana Ledger"}</h1>
          <p className="text-[11px] text-stone-500">Demo · synthetic data · {h ? `as of ${shortDate(h.today)}` : "offline?"}</p>
        </div>
        {h && (
          <span className="shrink-0 rounded-full bg-stone-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-700">
            {h.llm_mode === "live" ? "LLM live" : "rules (mock)"}
          </span>
        )}
      </div>
    </header>
  );
}
