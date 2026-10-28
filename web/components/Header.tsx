"use client";
import { useEffect, useState } from "react";
import { api, type Shop } from "../lib/api";
import { shortDate } from "../lib/format";

export function Header() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [h, setH] = useState<{ today: string; llm_mode: string } | null>(null);
  useEffect(() => {
    const load = () => {
      api.shop().then(setShop).catch(() => setShop(null));
      api.health().then(setH).catch(() => setH(null));
    };
    load();
    window.addEventListener("kl-shop-changed", load);
    if ("serviceWorker" in navigator && location.port !== "3141") {
      navigator.serviceWorker.register("/app/sw.js").catch(() => undefined);
    }
    return () => window.removeEventListener("kl-shop-changed", load);
  }, []);
  const sub = !h ? "offline?" : shop?.mode === "own"
    ? `${shop.locality ? `${shop.locality} · ` : ""}${shortDate(h.today)}`
    : `Demo · synthetic data · as of ${shortDate(h.today)}`;
  return (
    <header className="sticky top-0 z-20 border-b border-amber-200/70 bg-[var(--color-paper)]/95 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="truncate text-base font-bold text-[var(--color-saffron)]">{shop?.name ?? "Kirana Ledger"}</h1>
          <p className="text-[11px] text-stone-500">{sub}</p>
        </div>
        {h && (
          <span className="shrink-0 rounded-full bg-stone-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-700">
            {shop?.mode === "own" ? "my shop" : "demo"} · {h.llm_mode === "live" ? "LLM" : "rules"}
          </span>
        )}
      </div>
    </header>
  );
}
