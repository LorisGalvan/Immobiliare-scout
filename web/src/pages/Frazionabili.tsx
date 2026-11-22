import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { eur, num, pct } from "../lib/format";
import { useData } from "../lib/store";
import { type Gruppo, NESSUNA, perAnnuncio } from "../lib/valutazioni";
import { bordoStato, Scostamento, Titolo, ValutazioneTeam, Vuoto } from "../components/ui";

type Filtro = "tutti" | Gruppo;
const FILTRI: { k: Filtro; label: string }[] = [
  { k: "da_valutare", label: "Da valutare" },
  { k: "in_valutazione", label: "Valutati" },
  { k: "scartati", label: "Scartati" },
  { k: "tutti", label: "Tutti" },
];
const CHIAVE = "scout-filtro-frazionabili";
const leggi = (): Filtro => {
  try { const v = localStorage.getItem(CHIAVE); return FILTRI.some((f) => f.k === v) ? (v as Filtro) : "tutti"; } catch { return "tutti"; }
};
// in "Tutti": prima i non ancora visti, poi quelli in lavorazione, gli scartati in fondo
const ORDINE: Record<Gruppo, number> = { da_valutare: 0, in_valutazione: 1, scartati: 2 };

export default function Frazionabili() {
  const { dataset, valutazioni } = useData();
  const [filtro, setFiltroS] = useState<Filtro>(leggi);
  const setFiltro = (f: Filtro) => { setFiltroS(f); try { localStorage.setItem(CHIAVE, f); } catch { /* ignora */ } };

  const righe = useMemo(() => {
    if (!dataset) return [];
    const per = new Map(dataset.annunci.map((a) => [a.uid, a]));
    const team = perAnnuncio(valutazioni);
    return dataset.frazionabili
      .map((f) => ({ f, a: per.get(f.uid)!, t: team.get(f.uid) ?? NESSUNA }))
      .filter((x) => x.a)
      .sort((x, y) => ORDINE[x.t.gruppo] - ORDINE[y.t.gruppo] || y.f.margine_pct - x.f.margine_pct);
  }, [dataset, valutazioni]);
  if (!dataset) return null;

  const conta = (k: Filtro) => (k === "tutti" ? righe.length : righe.filter((r) => r.t.gruppo === k).length);
  const visibili = filtro === "tutti" ? righe : righe.filter((r) => r.t.gruppo === filtro);
  return (
    <>
      <Titolo sotto="Immobili grandi: valore se divisi in unità piccole (mediana della fascia piccola nella stessa microzona) meno costi stimati">
        Frazionabili <span className="text-slate-400">({righe.length})</span>
      </Titolo>
      {righe.length > 0 && (
        <div className="mb-3 inline-flex flex-wrap rounded-lg border border-slate-200 bg-white p-0.5 text-sm" role="group" aria-label="Valutazione">
          {FILTRI.map(({ k, label }) => (
            <button key={k} type="button" onClick={() => setFiltro(k)} aria-pressed={filtro === k}
              className={`rounded-md px-3 py-1 font-medium ${filtro === k ? "bg-brand-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
              {label} <span className={filtro === k ? "text-white/70" : "text-slate-400"}>{conta(k)}</span>
            </button>
          ))}
        </div>
      )}
      {!righe.length && <Vuoto>Nessun candidato sopra il margine minimo configurato.</Vuoto>}
      {righe.length > 0 && !visibili.length && <Vuoto>Nessun immobile in questa lista.</Vuoto>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {visibili.map(({ f, a, t }) => (
          <Link key={f.uid} to={`/annuncio/${encodeURIComponent(f.uid)}`}
            className={`card block p-4 transition-opacity hover:border-brand-300 ${bordoStato(t)}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className={`truncate font-medium ${t.stato === "scartato" ? "line-through" : ""}`}>{a.indirizzo || a.titolo}</div>
                <div className="text-xs text-slate-500">{a.microzona}</div>
              </div>
              <div className="text-right">
                <div className="text-xl font-semibold text-violet-700">{pct(f.margine_pct, 0)}</div>
                <div className="text-xs text-slate-500">{eur(f.margine)}</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-slate-50 p-2"><div className="text-slate-500">Acquisto</div><div className="font-semibold tabular-nums">{eur(a.prezzo)}</div></div>
              <div className="rounded-lg bg-slate-50 p-2"><div className="text-slate-500">Costi</div><div className="font-semibold tabular-nums">{eur(f.costi_totali)}</div></div>
              <div className="rounded-lg bg-violet-50 p-2"><div className="text-violet-700">Valore post</div><div className="font-semibold tabular-nums">{eur(f.valore_post)}</div></div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <span>{num(a.mq)} mq → <b>{f.n_unita}</b> × {num(f.mq_unita)} mq</span>
              <Scostamento v={a.scostamento_pct} />
            </div>
            {f.indizi && (
              <div className="mt-2 flex flex-wrap gap-1">
                {f.indizi.split(", ").map((i) => <span key={i} className="chip bg-violet-100 text-violet-800">{i}</span>)}
              </div>
            )}
            <ValutazioneTeam team={t} />
          </Link>
        ))}
      </div>
    </>
  );
}
