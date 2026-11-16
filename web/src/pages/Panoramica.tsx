import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { urlReport } from "../lib/data";
import { dataOra, eur, num, pct } from "../lib/format";
import { useData } from "../lib/store";
import ListaAnnunci from "../components/ListaAnnunci";
import { ICONE, Icona, Kpi, Titolo } from "../components/ui";

export default function Panoramica() {
  const { dataset, soglia } = useData();
  const [report, setReport] = useState<string | null>(null);
  useEffect(() => {
    if (dataset?.ultimaEsecuzione?.report_xlsx) urlReport(dataset.ultimaEsecuzione.report_xlsx).then(setReport);
  }, [dataset]);

  const s = useMemo(() => {
    if (!dataset) return null;
    const attivi = dataset.annunci.filter((a) => a.attivo);
    const occ = attivi.filter((a) => (a.scostamento_pct ?? 0) <= soglia).sort((a, b) => a.scostamento_pct! - b.scostamento_pct!);
    const nuoviSett = attivi.filter((a) => a.first_seen && Date.now() - new Date(a.first_seen).getTime() < 7 * 864e5);
    const ribassi = attivi.filter((a) => (a.ribasso_pct ?? 0) < 0);
    const ppm = attivi.map((a) => a.prezzo_mq).sort((a, b) => a - b);
    const fraz = [...dataset.frazionabili].sort((a, b) => b.margine_pct - a.margine_pct);
    return { attivi, occ, nuoviSett, ribassi, med: ppm[Math.floor(ppm.length / 2)], fraz };
  }, [dataset, soglia]);

  if (!dataset || !s) return null;
  const perUid = new Map(dataset.annunci.map((a) => [a.uid, a]));
  return (
    <>
      <Titolo
        sotto={`Ultimo aggiornamento: ${dataOra(dataset.ultimaEsecuzione?.ts)}`}
        azioni={report && (
          <a href={report} className="btn-primary"><Icona d={ICONE.scarica} className="h-4 w-4" />Scarica Excel</a>
        )}>
        {dataset.territorio}
      </Titolo>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Annunci attivi" valore={num(s.attivi.length)} sotto={`${dataset.zone.length} microzone`} />
        <Kpi label="Occasioni" valore={num(s.occ.length)} sotto={`soglia ${soglia}%`} accento="text-sky-600" />
        <Kpi label="Frazionabili" valore={num(s.fraz.length)} sotto="margine sopra il minimo" accento="text-violet-600" />
        <Kpi label="Nuovi (7 giorni)" valore={num(s.nuoviSett.length)} />
        <Kpi label="Mediana città" valore={`${num(s.med)} €`} sotto={`${num(s.ribassi.length)} annunci ribassati`} />
      </div>

      <section className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">Migliori occasioni</h2>
          <Link to="/occasioni" className="text-sm text-brand-600 hover:underline">Vedi tutte →</Link>
        </div>
        <ListaAnnunci annunci={s.occ.slice(0, 8)} vuoto="Nessuna occasione sotto la soglia." />
      </section>

      {s.fraz.length > 0 && (
        <section className="mt-6">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">Frazionamenti più promettenti</h2>
            <Link to="/frazionabili" className="text-sm text-brand-600 hover:underline">Vedi tutti →</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {s.fraz.slice(0, 3).map((f) => {
              const a = perUid.get(f.uid);
              if (!a) return null;
              return (
                <Link key={f.uid} to={`/annuncio/${encodeURIComponent(f.uid)}`} className="card block p-4 hover:border-brand-300">
                  <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
                  <div className="text-xs text-slate-500">{a.microzona}</div>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="text-sm">{num(a.mq)} mq → {f.n_unita} × {num(f.mq_unita)} mq</span>
                    <span className="text-lg font-semibold text-violet-700">{pct(f.margine_pct, 0)}</span>
                  </div>
                  <div className="text-xs text-slate-500">Margine stimato {eur(f.margine)}</div>
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}
