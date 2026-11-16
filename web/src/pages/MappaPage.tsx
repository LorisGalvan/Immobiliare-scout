import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../lib/store";
import Mappa, { LegendaScala } from "../components/Mappa";
import { Titolo } from "../components/ui";

export default function MappaPage() {
  const { dataset, soglia } = useData();
  const nav = useNavigate();
  const [tutti, setTutti] = useState(false);
  const valori = useMemo(() => {
    const m: Record<string, number> = {};
    dataset?.mediane.forEach((r) => { m[r.microzona] = r.mediana_zona; });
    return m;
  }, [dataset]);
  const occ = useMemo(() => dataset?.annunci.filter((a) => a.attivo && (a.scostamento_pct ?? 0) <= soglia) ?? [], [dataset, soglia]);
  const evid = useMemo(() => new Set(occ.map((a) => a.uid)), [occ]);
  const annunci = useMemo(() => (tutti ? dataset?.annunci.filter((a) => a.attivo) ?? [] : occ), [tutti, dataset, occ]);
  const vs = Object.values(valori);
  const onZona = useCallback((n: string) => nav(`/microzone/${encodeURIComponent(n)}`), [nav]);
  if (!dataset) return null;
  return (
    <>
      <Titolo sotto="Colore = mediana €/mq della microzona · punti rossi = occasioni · clic su una zona per il dettaglio"
        azioni={
          <div className="flex flex-wrap items-center gap-4">
            <LegendaScala min={Math.min(...vs)} max={Math.max(...vs)} />
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={tutti} onChange={(e) => setTutti(e.target.checked)} />Mostra tutti gli annunci</label>
          </div>
        }>
        Mappa
      </Titolo>
      <Mappa zone={dataset.zone} valoreZona={valori} annunci={annunci} evidenziati={evid} onZona={onZona} altezza="calc(100vh - 220px)" />
    </>
  );
}
