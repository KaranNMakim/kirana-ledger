"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { rupees } from "../../lib/format";

const BAND_COLOR: Record<string, string> = {
  "Pays regularly": "#059669", "Usually pays, sometimes slow": "#d97706", "Often slow to pay": "#ea580c", "Frequently late": "#dc2626",
};

type Sel = { id: string; label: string; type: string; balance?: number; band?: string };

function Graph() {
  const focus = useSearchParams().get("id") ?? undefined;
  const box = useRef<HTMLDivElement>(null);
  const [sel, setSel] = useState<Sel | null>(null);
  const [limit, setLimit] = useState(15);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cy: { destroy(): void } | null = null;
    let cancelled = false;
    (async () => {
      try {
        const [{ default: cytoscape }, g] = await Promise.all([import("cytoscape"), api.graph(limit, focus)]);
        if (cancelled || !box.current) return;
        const maxBal = Math.max(1, ...g.nodes.map((n) => n.data.balance ?? 0));
        const inst = cytoscape({
          container: box.current,
          elements: [...g.nodes, ...g.edges],
          wheelSensitivity: 0.3,
          style: [
            { selector: "node", style: { label: "data(label)", "font-size": 9, "text-valign": "bottom", "text-margin-y": 3, color: "#292524", "text-wrap": "ellipsis", "text-max-width": "80px" } },
            { selector: 'node[type="Shop"]', style: { "background-color": "#b45309", width: 34, height: 34, shape: "round-rectangle", "font-weight": "bold" } },
            { selector: 'node[type="Customer"]', style: {
              "background-color": (n: any) => BAND_COLOR[n.data("band")] ?? "#78716c", // eslint-disable-line @typescript-eslint/no-explicit-any
              width: (n: any) => 14 + 26 * Math.sqrt((n.data("balance") || 0) / maxBal), // eslint-disable-line @typescript-eslint/no-explicit-any
              height: (n: any) => 14 + 26 * Math.sqrt((n.data("balance") || 0) / maxBal) } }, // eslint-disable-line @typescript-eslint/no-explicit-any
            { selector: 'node[type="Product"]', style: { "background-color": "#a8a29e", shape: "diamond", width: 12, height: 12, "font-size": 8, color: "#57534e" } },
            { selector: 'edge[rel="owes"]', style: { width: 2, "line-color": "#fca5a5", "target-arrow-color": "#fca5a5", "target-arrow-shape": "triangle", "curve-style": "bezier" } },
            { selector: 'edge[rel="bought"]', style: { width: 1, "line-color": "#d6d3d1", "line-style": "dashed", "curve-style": "bezier" } },
            { selector: ":selected", style: { "border-width": 3, "border-color": "#1c1917" } },
          ],
          layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 70, padding: 12 } as any, // eslint-disable-line @typescript-eslint/no-explicit-any
        });
        inst.on("tap", "node", (e: any) => setSel(e.target.data())); // eslint-disable-line @typescript-eslint/no-explicit-any
        cy = inst;
      } catch (e) { setErr((e as Error).message); }
    })();
    return () => { cancelled = true; cy?.destroy(); };
  }, [limit, focus]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Udhaar graph</h2>
        {!focus ? (
          <select aria-label="How many customers" value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="min-h-10 rounded-lg border border-stone-300 bg-white px-2 text-sm">
            {[10, 15, 25, 40].map((n) => <option key={n} value={n}>Top {n} owing</option>)}
          </select>
        ) : <Link href="/graph/" className="text-sm underline">Show all</Link>}
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div ref={box} className="h-[58vh] min-h-80 w-full rounded-2xl bg-white ring-1 ring-stone-200" aria-label="Graph of customers, the shop and products" />
      <p className="text-[11px] text-stone-500">Customer → <b>owes</b> → shop (size = balance, colour = payment pattern). Dashed lines: products bought on udhaar.</p>
      {sel && (
        <div className="rounded-xl bg-white p-3 ring-1 ring-stone-200">
          <p className="font-semibold">{sel.label} <span className="text-xs font-normal text-stone-500">· {sel.type}</span></p>
          {sel.type === "Customer" && (
            <>
              <p className="text-sm">owes {rupees(sel.balance)} · {sel.band}</p>
              <Link href={`/customer/?id=${encodeURIComponent(sel.id)}`} className="mt-1 inline-block text-sm font-semibold text-[var(--color-saffron)] underline">Open customer →</Link>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function GraphPage() {
  return <Suspense fallback={<p className="text-sm text-stone-500">Loading…</p>}><Graph /></Suspense>;
}
