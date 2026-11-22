import { ReactNode } from "react";
import { coloreScostamento, pct } from "../lib/format";
import { dataOra } from "../lib/format";
import type { StatoValutazione } from "../lib/types";
import { nomeUtente, type Team } from "../lib/valutazioni";

export function Scostamento({ v, grande }: { v: number | null | undefined; grande?: boolean }) {
  return (
    <span className={`chip tabular-nums ${coloreScostamento(v)} ${grande ? "text-base px-3 py-1" : ""}`}>
      {pct(v)}
    </span>
  );
}

export function Kpi({ label, valore, sotto, accento }: { label: string; valore: ReactNode; sotto?: ReactNode; accento?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accento ?? ""}`}>{valore}</div>
      {sotto && <div className="mt-0.5 text-xs text-slate-500">{sotto}</div>}
    </div>
  );
}

export function Titolo({ children, azioni, sotto }: { children: ReactNode; azioni?: ReactNode; sotto?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{children}</h1>
        {sotto && <p className="mt-0.5 text-sm text-slate-500">{sotto}</p>}
      </div>
      {azioni}
    </div>
  );
}

export function Vuoto({ children }: { children: ReactNode }) {
  return <div className="card p-8 text-center text-sm text-slate-500">{children}</div>;
}

export const STATI_VAL: { v: StatoValutazione; label: string; cls: string }[] = [
  { v: "da_vedere", label: "Da vedere", cls: "bg-slate-200 text-slate-700" },
  { v: "interessante", label: "Interessante", cls: "bg-amber-100 text-amber-800" },
  { v: "visitato", label: "Visitato", cls: "bg-indigo-100 text-indigo-800" },
  { v: "in_trattativa", label: "In trattativa", cls: "bg-emerald-100 text-emerald-800" },
  { v: "scartato", label: "Scartato", cls: "bg-rose-100 text-rose-700 line-through" },
];

export function BadgeStato({ stato }: { stato: StatoValutazione | null | undefined }) {
  const s = STATI_VAL.find((x) => x.v === stato);
  return s ? <span className={`chip ${s.cls}`}>{s.label}</span> : null;
}

/** Bordo colorato della scheda secondo lo stato del team (scartati sbiaditi). */
export const BORDO_STATO: Record<StatoValutazione, string> = {
  da_vedere: "border-l-4 border-l-slate-400",
  interessante: "border-l-4 border-l-amber-400 bg-amber-50/40",
  visitato: "border-l-4 border-l-indigo-400 bg-indigo-50/40",
  in_trattativa: "border-l-4 border-l-emerald-500 bg-emerald-50/40",
  scartato: "border-l-4 border-l-rose-400 bg-slate-50 opacity-60 hover:opacity-100",
};
export const bordoStato = (t: Team) =>
  t.stato ? BORDO_STATO[t.stato] : t.voci.length ? "border-l-4 border-l-sky-300" : "";

/** Riquadro sulla scheda: chi ha valutato, con quale stato e la sua nota. */
export function ValutazioneTeam({ team, max = 2 }: { team: Team; max?: number }) {
  if (!team.voci.length) return <div className="mt-3 text-xs italic text-slate-400">Non ancora valutato</div>;
  const altre = team.voci.length - max;
  return (
    <div className="mt-3 space-y-1.5 rounded-lg border border-slate-100 bg-white/70 p-2 text-xs">
      {team.voci.slice(0, max).map((v) => (
        <div key={v.user_id}>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-slate-700">{nomeUtente(v)}</span>
            <BadgeStato stato={v.stato} />
            <span className="ml-auto text-slate-400">{dataOra(v.aggiornato)}</span>
          </div>
          {v.nota?.trim() && <p className="mt-0.5 line-clamp-2 whitespace-pre-line text-slate-600">{v.nota}</p>}
        </div>
      ))}
      {altre > 0 && <div className="text-slate-400">+{altre} altre valutazioni</div>}
    </div>
  );
}

export function Legenda() {
  const voci = [
    ["bg-yellow-200", "> 0%"], ["bg-lime-100", "0 / -10%"], ["bg-green-500", "-10 / -20%"], ["bg-sky-500", "oltre -20%"],
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
      {voci.map(([c, t]) => (
        <span key={t} className="inline-flex items-center gap-1"><span className={`h-3 w-3 rounded ${c}`} />{t}</span>
      ))}
    </div>
  );
}

export function Icona({ d, className = "h-5 w-5" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
      strokeLinejoin="round" className={className} aria-hidden="true"><path d={d} /></svg>
  );
}

export const ICONE = {
  home: "M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z",
  stella: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
  mappa: "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14",
  zone: "M4 5h7v7H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 14h7v5H4z",
  forbici: "M6 9a3 3 0 100-6 3 3 0 000 6zm0 12a3 3 0 100-6 3 3 0 000 6zM20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12",
  freccia: "M12 5v14M5 12l7 7 7-7",
  esci: "M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3",
  link: "M10 14a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 10a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1",
  scarica: "M12 3v12M7 10l5 5 5-5M5 21h14",
  indietro: "M15 18l-6-6 6-6",
  chat: "M21 12a8 8 0 01-11.6 7.1L4 20l1-4.2A8 8 0 1121 12z",
  chiudi: "M6 6l12 12M18 6L6 18",
  persona: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  martello: "M14 4l6 6M11 7l6 6M12.5 5.5l-6 6 3 3 6-6M8 13l-5 5 2 2 5-5M4 21h9",
};
