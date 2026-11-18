import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { data, eur, FONTE, num } from "../lib/format";
import { useData } from "../lib/store";
import type { Annuncio } from "../lib/types";
import { Scostamento, Titolo, Vuoto } from "../components/ui";

type Ordine = "scostamento" | "minima" | "data" | "prezzo";

const TIPO: Record<string, { label: string; cls: string }> = {
  asta: { label: "Asta", cls: "bg-rose-100 text-rose-800" },
  possibile_asta: { label: "Da verificare", cls: "bg-amber-100 text-amber-800" },
};

export default function Aste() {
  const { dataset } = useData();
  const nav = useNavigate();
  const [tipo, setTipo] = useState("");
  const [zona, setZona] = useState("");
  const [soglia, setSoglia] = useState(0);
  const [soloFuture, setSoloFuture] = useState(true);
  const [ordine, setOrdine] = useState<Ordine>("scostamento");
  const oggi = new Date().toISOString().slice(0, 10);

  const lista = useMemo(() => {
    if (!dataset) return [];
    const l = dataset.aste.filter((a) =>
      a.attivo && (!tipo || a.tipo_vendita === tipo) && (!zona || a.microzona === zona) &&
      (soglia === 0 || (a.scostamento_pct != null && a.scostamento_pct <= soglia)) &&
      (!soloFuture || !a.data_asta || a.data_asta >= oggi));
    const v = (x: number | null | undefined) => x ?? 1e9;
    const cmp: Record<Ordine, (a: Annuncio, b: Annuncio) => number> = {
      scostamento: (a, b) => v(a.scostamento_pct) - v(b.scostamento_pct),
      minima: (a, b) => v(a.scostamento_minima_pct ?? a.scostamento_pct) - v(b.scostamento_minima_pct ?? b.scostamento_pct),
      data: (a, b) => (a.data_asta ?? "9999").localeCompare(b.data_asta ?? "9999"),
      prezzo: (a, b) => a.prezzo - b.prezzo,
    };
    return l.sort(cmp[ordine]);
  }, [dataset, tipo, zona, soglia, soloFuture, ordine, oggi]);

  if (!dataset) return null;
  return (
    <>
      <Titolo sotto="Riconosciute leggendo il testo degli annunci. Non entrano nelle mediane: sono confrontate con il mercato libero della loro microzona e fascia.">
        Aste <span className="text-slate-400">({lista.length})</span>
      </Titolo>
      <div className="card mb-4 grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-5">
        <div>
          <label className="label">Tipo</label>
          <select className="input" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Tutte</option>
            <option value="asta">Asta certa</option>
            <option value="possibile_asta">Da verificare</option>
          </select>
        </div>
        <div>
          <label className="label">Microzona</label>
          <select className="input" value={zona} onChange={(e) => setZona(e.target.value)}>
            <option value="">Tutte</option>
            {dataset.zone.map((z) => <option key={z.nome}>{z.nome}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Sotto mercato di almeno: <b className="text-slate-800">{soglia}%</b></label>
          <input type="range" min={-60} max={0} step={5} value={soglia} onChange={(e) => setSoglia(Number(e.target.value))} className="w-full accent-brand-600" />
        </div>
        <div>
          <label className="label">Ordina per</label>
          <select className="input" value={ordine} onChange={(e) => setOrdine(e.target.value as Ordine)}>
            <option value="scostamento">% vs mercato</option>
            <option value="minima">% offerta minima</option>
            <option value="data">Data asta</option>
            <option value="prezzo">Prezzo</option>
          </select>
        </div>
        <label className="inline-flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={soloFuture} onChange={(e) => setSoloFuture(e.target.checked)} />Nascondi aste passate
        </label>
      </div>
      {!lista.length ? <Vuoto>Nessuna asta con questi filtri.</Vuoto> : (
        <div className="grid gap-3 md:grid-cols-2">
          {lista.map((a) => (
            <button key={a.uid} onClick={() => nav(`/annuncio/${encodeURIComponent(a.uid)}`)}
              className="card p-4 text-left hover:border-brand-300">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className={`chip ${TIPO[a.tipo_vendita ?? ""]?.cls ?? "bg-slate-100"}`}>{TIPO[a.tipo_vendita ?? ""]?.label ?? "Asta"}</span>
                <Scostamento v={a.scostamento_pct} />
              </div>
              <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
              <div className="text-sm text-slate-500">
                {a.microzona ?? "fuori zona"} · {num(a.mq)} mq · {FONTE[a.source] ?? a.source}
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm sm:grid-cols-3">
                <div><dt className="text-xs text-slate-400">Prezzo annuncio</dt><dd className="tabular-nums">{eur(a.prezzo)}</dd></div>
                <div><dt className="text-xs text-slate-400">Valore di mercato</dt><dd className="tabular-nums">{eur(a.valore_mercato)}</dd></div>
                <div><dt className="text-xs text-slate-400">Data asta</dt><dd>{data(a.data_asta)}</dd></div>
                <div><dt className="text-xs text-slate-400">Prezzo base</dt><dd className="tabular-nums">{eur(a.prezzo_base)}</dd></div>
                <div>
                  <dt className="text-xs text-slate-400">Offerta minima</dt>
                  <dd className="tabular-nums">{eur(a.offerta_minima)} {a.scostamento_minima_pct != null && <Scostamento v={a.scostamento_minima_pct} />}</dd>
                </div>
                <div><dt className="text-xs text-slate-400">Confronto</dt><dd className="truncate text-slate-600">{a.base_confronto ?? "–"}</dd></div>
              </dl>
              {!!a.indizi_vendita?.length && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {a.indizi_vendita.slice(0, 5).map((i) => <span key={i} className="chip bg-slate-100 text-slate-600">{i}</span>)}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
