import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { linkRicerca, slug } from "../lib/link";
import { num } from "../lib/format";
import { useData } from "../lib/store";
import ListaAnnunci from "../components/ListaAnnunci";
import Mappa from "../components/Mappa";
import { ICONE, Icona, Kpi, Legenda, Titolo, Vuoto } from "../components/ui";

export default function Zona() {
  const { nome = "" } = useParams();
  const { dataset, soglia } = useData();
  const zona = dataset?.zone.find((z) => z.nome === nome);
  const annunci = useMemo(() => dataset?.annunci.filter((a) => a.microzona === nome) ?? [], [dataset, nome]);
  const valori = useMemo(() => {
    const m: Record<string, number> = {};
    dataset?.mediane.forEach((r) => { m[r.microzona] = r.mediana_zona; });
    return m;
  }, [dataset]);
  const evid = useMemo(() => new Set(annunci.filter((a) => a.attivo && (a.scostamento_pct ?? 0) <= soglia).map((a) => a.uid)), [annunci, soglia]);
  if (!dataset) return null;
  if (!zona) return <Vuoto>Microzona non trovata. <Link to="/microzone" className="text-brand-600">Torna all'elenco</Link></Vuoto>;
  const med = dataset.mediane.filter((m) => m.microzona === nome);
  const link = linkRicerca(zona, slug(dataset.territorio));
  const attivi = annunci.filter((a) => a.attivo);
  return (
    <>
      <Link to="/microzone" className="mb-2 inline-flex items-center text-sm text-slate-500 hover:text-slate-800"><Icona d={ICONE.indietro} className="h-4 w-4" />Microzone</Link>
      <Titolo sotto={`${attivi.length} annunci attivi · ${annunci.length - attivi.length} rimossi di recente`}
        azioni={
          <div className="flex flex-wrap gap-2">
            <a className="btn-ghost border border-slate-200" href={link.immobiliare} target="_blank" rel="noreferrer"><Icona d={ICONE.link} className="h-4 w-4" />Immobiliare</a>
            <a className="btn-ghost border border-slate-200" href={link.idealista} target="_blank" rel="noreferrer"><Icona d={ICONE.link} className="h-4 w-4" />Idealista</a>
          </div>
        }>
        {nome}
      </Titolo>
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <Mappa zone={dataset.zone} valoreZona={valori} annunci={attivi} evidenziati={evid} zonaSelezionata={nome} altezza="340px" />
        </div>
        <div className="grid grid-cols-2 gap-3 lg:col-span-3">
          {dataset.fasce.map((f) => {
            const m = med.find((x) => x.fascia === f);
            return <Kpi key={f} label={`Fascia ${f} mq`} valore={m ? `${num(m.mediana_mq)} €/mq` : "–"} sotto={m ? `${m.n} annunci · media ${num(m.media_mq)}` : "nessun annuncio"} />;
          })}
        </div>
      </div>
      {dataset.fasce.map((f) => {
        const lista = annunci.filter((a) => a.fascia === f).sort((a, b) => (a.scostamento_pct ?? 99) - (b.scostamento_pct ?? 99));
        return (
          <section key={f} className="mt-6">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-semibold">MQ {f}</h2>
              <Legenda />
            </div>
            <ListaAnnunci annunci={lista} mostraZona={false} vuoto="Nessun annuncio in questa fascia." />
          </section>
        );
      })}
    </>
  );
}
