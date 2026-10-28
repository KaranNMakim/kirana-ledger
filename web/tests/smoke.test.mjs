// Web smoke test: the static export exists, every screen was generated, the PWA bits are present,
// and the shell stays small enough for low-bandwidth phones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const PAGES = ["index.html", "customers/index.html", "customer/index.html", "insights/index.html", "graph/index.html", "reminder/index.html",
  "setup/index.html", "shop/index.html", "customer-new/index.html", "products/index.html"];

test("static export contains every screen", () => {
  for (const p of PAGES) {
    assert.ok(existsSync(join(OUT, p)), `missing ${p}`);
    const html = readFileSync(join(OUT, p), "utf8");
    assert.match(html, /<title>Kirana Ledger<\/title>/);
    assert.match(html, /name="viewport" content="width=device-width, initial-scale=1"/);
    assert.match(html, /\/app\/_next\/static\//, "assets must be served under the /app base path");
  }
});

test("ledger screen has mic, typed fallback and bottom nav", () => {
  const html = readFileSync(join(OUT, "index.html"), "utf8");
  assert.match(html, /aria-label="Start speaking"/);
  assert.match(html, /id="utt"/);
  for (const label of ["Ledger", "Customers", "Insights", "Graph", "Shop"]) assert.ok(html.includes(`>${label}<`), label);
});

test("PWA manifest and service worker", () => {
  const m = JSON.parse(readFileSync(join(OUT, "manifest.webmanifest"), "utf8"));
  assert.equal(m.start_url, "/app/");
  assert.equal(m.display, "standalone");
  assert.ok(existsSync(join(OUT, "sw.js")) && existsSync(join(OUT, "icon.svg")));
});

test("ledger page JS stays small; Cytoscape is lazy-loaded (low-bandwidth budget)", () => {
  const html = readFileSync(join(OUT, "index.html"), "utf8");
  const scripts = [...new Set([...html.matchAll(/\/app\/(_next\/static\/[^"']+?\.js)/g)].map((m) => m[1]))];
  assert.ok(scripts.length > 0);
  const loaded = scripts.filter((rel) => !rel.includes("polyfills")); // nomodule: skipped by modern browsers
  const kb = loaded.reduce((sum, rel) => sum + gzipSync(readFileSync(join(OUT, rel))).length, 0) / 1024;
  assert.ok(kb < 150, `ledger page loads ${kb.toFixed(0)} KB of JS (gzipped)`);
  for (const rel of scripts) assert.ok(!readFileSync(join(OUT, rel), "utf8").includes("cytoscape"), `${rel} bundles cytoscape`);
});
