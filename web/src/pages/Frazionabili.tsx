import { useMemo } from "react";
import { Link } from "react-router-dom";
import { eur, num, pct } from "../lib/format";
import { useData } from "../lib/store";
import { Scostamento, Titolo, Vuoto } from "../components/ui";

export default function Frazionabili() {
  const { dataset } = useData();
  const righe = useMemo(() => {
    if (!dataset) return [];
    const per = new Map(dataset.annunci.map((a) => [a.uid, a]));
    return dataset.frazionabili.map((f) => ({ f, a: per.get(f.uid)! })).filter((x) => x.a)
      .sort((x, y) => y.f.margine_pct - x.f.margine_pct);
  }, [dataset]);
  if (!dataset) return null;
  return (
    <>
      <Titolo sotto="Immobili grandi: valore se divisi in unità piccole (mediana della fascia piccola nella stessa microzona) meno costi stimati">
        Frazionabili <span className="text-slate-400">({righe.length})</span>
      </Titolo>
      {!righe.length && <Vuoto>Nessun candidato sopra il margine minimo configurato.</Vuoto>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {righe.map(({ f, a }) => (
          <Link key={f.uid} to={`/annuncio/${encodeURIComponent(f.uid)}`} className="card block p-4 hover:border-brand-300">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
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
          </Link>
        ))}
      </div>
    </>
  );
}
