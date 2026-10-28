"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";

export default function NewCustomerPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"" | "m" | "f">("");
  const [locality, setLocality] = useState("");
  const [nickname, setNickname] = useState("");
  const [similar, setSimilar] = useState<{ id: string; name: string }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(force = false) {
    setBusy(true); setErr(null);
    try {
      const c = await api.addCustomer({ name: name.trim(), gender: gender || undefined, locality: locality.trim() || undefined,
        nickname: nickname.trim() || undefined, force });
      router.push(`/customer/?id=${encodeURIComponent(c.id)}`);
    } catch (x) {
      if (x instanceof ApiError && x.status === 409) setSimilar((x.body.similar as { id: string; name: string }[]) ?? []);
      else setErr((x as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save(false); }}>
      <Link href="/customers/" className="inline-flex min-h-11 items-center text-sm text-stone-500">← Customers</Link>
      <h2 className="text-xl font-bold">Add customer</h2>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-stone-500">Name *</span>
        <input required value={name} onChange={(e) => { setName(e.target.value); setSimilar([]); }} placeholder="e.g. Ramesh Patel"
          className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" maxLength={60} />
        <span className="mt-1 block text-xs text-stone-500">Add the surname if two customers share a first name; it helps the voice matcher.</span>
      </label>
      <fieldset>
        <legend className="mb-1 text-xs font-semibold uppercase text-stone-500">Usually called</legend>
        <div className="grid grid-cols-3 gap-2">
          {([["m", "bhai"], ["f", "ben / ji"], ["", "skip"]] as const).map(([g, label]) => (
            <button key={label} type="button" onClick={() => setGender(g)} aria-pressed={gender === g}
              className={`min-h-11 rounded-lg text-sm font-semibold ring-1 ${gender === g ? "bg-amber-100 ring-2 ring-amber-500" : "bg-white ring-stone-300"}`}>{label}</button>
          ))}
        </div>
        <span className="mt-1 block text-xs text-stone-500">Used for polite reminders and to tell “Kiran bhai” from “Kiran ben”.</span>
      </fieldset>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-stone-500">Area / gali</span>
        <input value={locality} onChange={(e) => setLocality(e.target.value)} placeholder="e.g. Gali 3"
          className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" maxLength={60} />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-stone-500">Nickname</span>
        <input value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder="e.g. Pappu"
          className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3" maxLength={30} />
      </label>
      {similar.length > 0 && (
        <div role="alert" className="rounded-xl bg-amber-50 p-3 text-sm ring-1 ring-amber-300">
          <p className="font-semibold">Already on your ledger?</p>
          <ul className="mt-1 space-y-1">
            {similar.map((s) => <li key={s.id}><Link className="underline" href={`/customer/?id=${encodeURIComponent(s.id)}`}>{s.name}</Link></li>)}
          </ul>
          <button type="button" onClick={() => save(true)} className="mt-2 min-h-11 w-full rounded-lg bg-white font-semibold ring-1 ring-amber-400">
            No, add “{name.trim()}” as a different person
          </button>
        </div>
      )}
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <button type="submit" disabled={busy || !name.trim()} className="min-h-12 w-full rounded-xl bg-emerald-600 font-bold text-white disabled:opacity-40">
        {busy ? "Saving…" : "Add customer"}
      </button>
    </form>
  );
}
