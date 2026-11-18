import { useMemo, useState } from "react";
import { FONTE } from "../lib/format";
import { useData } from "../lib/store";
import ListaAnnunci from "../components/ListaAnnunci";
import { Titolo } from "../components/ui";

type Ordine = "scostamento" | "recenti" | "giorni" | "prezzo";

/** Annunci di privati (senza agenzia): contatti diretti con chi vende, su tutto il mercato libero. */
export default function Privati() {
  const { dataset } = useData();
  const [zona, setZona] = useState("");
  const [fonte, setFonte] = useState("");
  const [prezzoMax, setPrezzoMax] = useState("");
  const [soloSotto, setSoloSotto] = useState(false);
  const [ordine, setOrdine] = useState<Ordine>("scostamento");
  const [testo, setTesto] = useState("");

  const privati = useMemo(() => dataset?.annunci.filter((a) => a.attivo && a.privato) ?? [], [dataset]);
  const lista = useMemo(() => {
    const t = testo.trim().toLowerCase();
    const max = Number(prezzoMax) || Infinity;
    const l = privati.filter((a) =>
      (!zona || a.microzona === zona) && (!fonte || a.source === fonte) && a.prezzo <= max &&
      (!soloSotto || (a.scostamento_pct != null && a.scostamento_pct < 0)) &&
      (!t || `${a.indirizzo} ${a.titolo}`.toLowerCase().includes(t)));
    const v = (x: number | null | undefined) => x ?? 1e9;
    const cmp: Record<Ordine, (a: typeof l[0], b: typeof l[0]) => number> = {
      scostamento: (a, b) => v(a.scostamento_pct) - v(b.scostamento_pct),
      recenti: (a, b) => (b.first_seen ?? "").localeCompare(a.first_seen ?? ""),
      giorni: (a, b) => (b.giorni_online ?? 0) - (a.giorni_online ?? 0),
      prezzo: (a, b) => a.prezzo - b.prezzo,
    };
    return [...l].sort(cmp[ordine]);
  }, [privati, zona, fonte, prezzoMax, soloSotto, ordine, testo]);

  if (!dataset) return null;
  const fonti = [...new Set(privati.map((a) => a.source))];
  return (
    <>
      <Titolo sotto="Annunci pubblicati da privati, senza agenzia: si può trattare direttamente con chi vende. Chi è in vendita da più giorni è spesso più disposto a trattare.">
        Privati <span className="text-slate-400">({lista.length})</span>
      </Titolo>
      <div className="card mb-4 grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-6">
        <div>
          <label className="label">Microzona</label>
          <select className="input" value={zona} onChange={(e) => setZona(e.target.value)}>
            <option value="">Tutte</option>
            {dataset.zone.map((z) => <option key={z.nome}>{z.nome}</option>)}
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
          <label className="label">Prezzo massimo €</label>
          <input className="input" inputMode="numeric" placeholder="es. 250000" value={prezzoMax}
            onChange={(e) => setPrezzoMax(e.target.value.replace(/\D/g, ""))} />
        </div>
        <div>
          <label className="label">Ordina per</label>
          <select className="input" value={ordine} onChange={(e) => setOrdine(e.target.value as Ordine)}>
            <option value="scostamento">% vs mercato</option>
            <option value="giorni">Più giorni online</option>
            <option value="recenti">Più recenti</option>
            <option value="prezzo">Prezzo</option>
          </select>
        </div>
        <div>
          <label className="label">Cerca</label>
          <input className="input" placeholder="via, zona…" value={testo} onChange={(e) => setTesto(e.target.value)} />
        </div>
        <label className="inline-flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={soloSotto} onChange={(e) => setSoloSotto(e.target.checked)} />Solo sotto mercato
        </label>
      </div>
      <ListaAnnunci annunci={lista} vuoto="Nessun annuncio di privati con questi filtri." />
    </>
  );
}
