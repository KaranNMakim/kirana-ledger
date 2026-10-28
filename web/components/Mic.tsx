"use client";
import { useEffect, useRef, useState } from "react";

// Minimal typing for the (vendor-prefixed) Web Speech API.
type SR = {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null; onend: (() => void) | null;
};

export const LANGS = [
  { code: "hi-IN", label: "हिंदी / Hinglish" },
  { code: "gu-IN", label: "ગુજરાતી" },
  { code: "en-IN", label: "English (IN)" },
];

export function Mic({ lang, onFinal, onInterim, disabled }: {
  lang: string; onFinal: (text: string) => void; onInterim?: (text: string) => void; disabled?: boolean;
}) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<SR | null>(null);

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR };
    setSupported(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
    return () => rec.current?.abort();
  }, []);

  function toggle() {
    if (listening) { rec.current?.stop(); return; }
    const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = lang; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    let finalText = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finalText += res[0].transcript; else interim += res[0].transcript;
      }
      onInterim?.(finalText + interim);
    };
    r.onerror = (e) => setError(e.error === "not-allowed" ? "Microphone permission denied. Type instead." : `Speech error: ${e.error}`);
    r.onend = () => { setListening(false); if (finalText.trim()) onFinal(finalText.trim()); };
    setError(null);
    rec.current = r;
    r.start();
    setListening(true);
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={toggle}
        disabled={disabled || supported === false}
        aria-pressed={listening}
        aria-label={listening ? "Stop listening" : "Start speaking"}
        className={`flex h-28 w-28 items-center justify-center rounded-full text-5xl shadow-lg transition active:scale-95 disabled:opacity-40 ${listening ? "listening bg-red-600 text-white" : "bg-[var(--color-saffron)] text-white"}`}
      >
        <span aria-hidden>{listening ? "■" : "🎙️"}</span>
      </button>
      <p className="text-center text-sm text-stone-600">
        {supported === false ? "Voice not supported in this browser. Type below." : listening ? "Listening… bolo" : "Tap and speak the entry"}
      </p>
      {error && <p role="alert" className="text-center text-xs text-red-700">{error}</p>}
    </div>
  );
}
