import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { indirizzoAgenzia } from "../lib/agenzia";
import { urlReport } from "../lib/data";
import { dataOra, eur, num, pct } from "../lib/format";
import { useData } from "../lib/store";
import { NESSUNA, perAnnuncio } from "../lib/valutazioni";
import ListaAnnunci from "../components/ListaAnnunci";
import { BadgeStato, bordoStato, ICONE, Icona, Kpi, Titolo } from "../components/ui";

export default function Panoramica() {
  const { dataset, soglia, valutazioni } = useData();
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
    // i più promettenti tra quelli non ancora scartati dal team
    const scartati = new Set([...perAnnuncio(valutazioni)].filter(([, t]) => t.gruppo === "scartati").map(([uid]) => uid));
    const fraz = [...dataset.frazionabili].sort((a, b) => b.margine_pct - a.margine_pct);
    const frazAperti = fraz.filter((f) => !scartati.has(f.uid));
    const sedeAgenzia = attivi.filter((a) => indirizzoAgenzia(a) != null);
    return { sedeAgenzia, attivi, occ, nuoviSett, ribassi, med: ppm[Math.floor(ppm.length / 2)], fraz, frazAperti, team: perAnnuncio(valutazioni) };
  }, [dataset, soglia, valutazioni]);

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

      {s.sedeAgenzia.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-1 font-semibold text-orange-800">📍 Da controllare: indirizzo dell'agenzia ({s.sedeAgenzia.length})</h2>
          <p className="mb-2 text-sm text-slate-500">
            Annunci messi sulla mappa all'indirizzo dell'agenzia invece che a quello dell'immobile. Sono esclusi dalle
            mediane delle microzone, così non falsano la valutazione.
          </p>
          <ListaAnnunci annunci={s.sedeAgenzia} filtroInserzionista={false} />
        </section>
      )}

      {s.frazAperti.length > 0 && (
        <section className="mt-6">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">Frazionamenti più promettenti</h2>
            <Link to="/frazionabili" className="text-sm text-brand-600 hover:underline">Vedi tutti →</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {s.frazAperti.slice(0, 3).map((f) => {
              const a = perUid.get(f.uid);
              if (!a) return null;
              const t = s.team.get(f.uid) ?? NESSUNA;
              return (
                <Link key={f.uid} to={`/annuncio/${encodeURIComponent(f.uid)}`} className={`card block p-4 hover:border-brand-300 ${bordoStato(t)}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
                    <BadgeStato stato={t.stato} />
                  </div>
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
