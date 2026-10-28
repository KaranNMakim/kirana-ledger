"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Ledger", icon: "🎙️" },
  { href: "/customers/", label: "Customers", icon: "👥" },
  { href: "/insights/", label: "Insights", icon: "📊" },
  { href: "/graph/", label: "Graph", icon: "🕸️" },
  { href: "/shop/", label: "Shop", icon: "🏪" },
];

export function Nav() {
  const path = usePathname() || "/";
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href)
      || (href === "/customers/" && (path.startsWith("/customer") || path.startsWith("/reminder")))
      || (href === "/shop/" && (path.startsWith("/products") || path.startsWith("/setup")));
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-amber-200 bg-white/95 backdrop-blur" aria-label="Main">
      <ul className="mx-auto grid max-w-md grid-cols-5">
        {TABS.map((t) => (
          <li key={t.href}>
            <Link
              href={t.href}
              className={`flex min-h-14 flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium ${active(t.href) ? "text-[var(--color-saffron)]" : "text-stone-500"}`}
              aria-current={active(t.href) ? "page" : undefined}
            >
              <span aria-hidden className="text-lg leading-none">{t.icon}</span>
              {t.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
