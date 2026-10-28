// Indian number grouping: 123456 → ₹1,23,456
export function rupees(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "₹—";
  const n = Math.round(x);
  const s = String(Math.abs(n));
  let out = s;
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const groups: string[] = [];
    while (head.length > 2) { groups.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) groups.unshift(head);
    out = `${groups.join(",")},${tail}`;
  }
  return `${n < 0 ? "-" : ""}₹${out}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function shortDate(iso?: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}${y !== 2025 ? ` ${y}` : ""}`;
}

export const KIND: Record<string, { label: string; sign: string; tone: string }> = {
  credit_sale: { label: "Udhaar", sign: "+", tone: "text-red-700 bg-red-50 ring-red-200" },
  payment: { label: "Payment", sign: "−", tone: "text-emerald-700 bg-emerald-50 ring-emerald-200" },
  return: { label: "Return", sign: "−", tone: "text-sky-700 bg-sky-50 ring-sky-200" },
};

export function bandTone(band: string): string {
  if (band.startsWith("Pays regularly")) return "bg-emerald-100 text-emerald-800";
  if (band.startsWith("Usually")) return "bg-amber-100 text-amber-800";
  if (band.startsWith("Often")) return "bg-orange-100 text-orange-800";
  return "bg-red-100 text-red-800";
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
