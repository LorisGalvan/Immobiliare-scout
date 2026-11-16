import { useMemo, useState } from "react";
import { FONTE } from "../lib/format";
import { useData } from "../lib/store";
import ListaAnnunci from "../components/ListaAnnunci";
import { Legenda, STATI_VAL, Titolo } from "../components/ui";

type Ordine = "scostamento" | "prezzo" | "recenti" | "giorni";

export default function Occasioni() {
  const { dataset, soglia, setSoglia, valutazioni } = useData();
  const [zona, setZona] = useState("");
  const [fascia, setFascia] = useState("");
  const [fonte, setFonte] = useState("");
  const [soloPrivati, setSoloPrivati] = useState(false);
  const [nascondiScartati, setNascondiScartati] = useState(true);
  const [ordine, setOrdine] = useState<Ordine>("scostamento");
  const [testo, setTesto] = useState("");
  const [filtriAperti, setFiltriAperti] = useState(() => window.innerWidth >= 768);

  const scartati = useMemo(() => new Set(valutazioni.filter((v) => v.stato === "scartato").map((v) => v.uid)), [valutazioni]);
  const lista = useMemo(() => {
    if (!dataset) return [];
    const t = testo.trim().toLowerCase();
    const l = dataset.annunci.filter((a) =>
      a.attivo && a.scostamento_pct != null && a.scostamento_pct <= soglia &&
      (!zona || a.microzona === zona) && (!fascia || a.fascia === fascia) && (!fonte || a.source === fonte) &&
      (!soloPrivati || a.privato) && (!nascondiScartati || !scartati.has(a.uid)) &&
      (!t || `${a.indirizzo} ${a.titolo} ${a.agenzia}`.toLowerCase().includes(t)));
    const cmp: Record<Ordine, (a: typeof l[0], b: typeof l[0]) => number> = {
      scostamento: (a, b) => a.scostamento_pct! - b.scostamento_pct!,
      prezzo: (a, b) => a.prezzo - b.prezzo,
      recenti: (a, b) => (b.first_seen ?? "").localeCompare(a.first_seen ?? ""),
      giorni: (a, b) => (b.giorni_online ?? 0) - (a.giorni_online ?? 0),
    };
    return l.sort(cmp[ordine]);
  }, [dataset, soglia, zona, fascia, fonte, soloPrivati, nascondiScartati, ordine, testo, scartati]);

  if (!dataset) return null;
  const fonti = [...new Set(dataset.annunci.map((a) => a.source))];
  return (
    <>
      <Titolo sotto="Annunci attivi con €/mq sotto la mediana della loro microzona e fascia" azioni={<Legenda />}>
        Occasioni <span className="text-slate-400">({lista.length})</span>
      </Titolo>
      <button className="btn-ghost mb-2 w-full border border-slate-200 bg-white md:hidden" onClick={() => setFiltriAperti(!filtriAperti)}>
        {filtriAperti ? "Nascondi filtri" : `Filtri · soglia ${soglia}%`}
      </button>
      <div className={`card mb-4 grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-7 ${filtriAperti ? "grid" : "hidden md:grid"}`}>
        <div className="col-span-2 sm:col-span-3 lg:col-span-2">
          <label className="label">Soglia scostamento: <b className="text-slate-800">{soglia}%</b></label>
          <input type="range" min={-40} max={0} step={1} value={soglia} onChange={(e) => setSoglia(Number(e.target.value))} className="w-full accent-brand-600" />
        </div>
        <div>
          <label className="label">Microzona</label>
          <select className="input" value={zona} onChange={(e) => setZona(e.target.value)}>
            <option value="">Tutte</option>
            {dataset.zone.map((z) => <option key={z.nome}>{z.nome}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Fascia mq</label>
          <select className="input" value={fascia} onChange={(e) => setFascia(e.target.value)}>
            <option value="">Tutte</option>
            {dataset.fasce.map((f) => <option key={f}>{f}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Fonte</label>
          <select className="input" value={fonte} onChange={(e) => setFonte(e.target.value)}>
            <option value="">Tutte</option>
            {fonti.map((f) => <option key={f} value={f}>{FONTE[f] ?? f}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Ordina per</label>
          <select className="input" value={ordine} onChange={(e) => setOrdine(e.target.value as Ordine)}>
            <option value="scostamento">Scostamento</option>
            <option value="prezzo">Prezzo</option>
            <option value="recenti">Più recenti</option>
            <option value="giorni">Più giorni online</option>
          </select>
        </div>
        <div>
          <label className="label">Cerca</label>
          <input className="input" placeholder="via, agenzia…" value={testo} onChange={(e) => setTesto(e.target.value)} />
        </div>
        <div className="col-span-2 flex flex-wrap items-center gap-4 text-sm sm:col-span-3 lg:col-span-7">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={soloPrivati} onChange={(e) => setSoloPrivati(e.target.checked)} />Solo privati</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={nascondiScartati} onChange={(e) => setNascondiScartati(e.target.checked)} />Nascondi "{STATI_VAL[4].label}"</label>
        </div>
      </div>
      <ListaAnnunci annunci={lista} vuoto="Nessun annuncio con questi filtri." />
    </>
  );
}
