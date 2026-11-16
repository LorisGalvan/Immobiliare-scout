import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { num } from "../lib/format";
import { useData } from "../lib/store";
import { Titolo } from "../components/ui";

export default function Microzone() {
  const { dataset, soglia } = useData();
  const [ord, setOrd] = useState<"nome" | "mediana" | "occasioni">("nome");
  const righe = useMemo(() => {
    if (!dataset) return [];
    return dataset.zone.map((z, i) => {
      const med = dataset.mediane.filter((m) => m.microzona === z.nome);
      const att = dataset.annunci.filter((a) => a.attivo && a.microzona === z.nome);
      return {
        nome: z.nome, i, mediana: med[0]?.mediana_zona, attivi: att.length,
        occasioni: att.filter((a) => (a.scostamento_pct ?? 0) <= soglia).length,
        fasce: Object.fromEntries(med.map((m) => [m.fascia, m])),
      };
    }).sort((a, b) => ord === "nome" ? a.i - b.i : ord === "mediana" ? (b.mediana ?? 0) - (a.mediana ?? 0) : b.occasioni - a.occasioni);
  }, [dataset, soglia, ord]);
  if (!dataset) return null;
  return (
    <>
      <Titolo sotto="Mediana €/mq per fascia di superficie (tra parentesi il numero di annunci)"
        azioni={
          <select className="input w-auto" value={ord} onChange={(e) => setOrd(e.target.value as typeof ord)}>
            <option value="nome">Ordine dei fogli</option>
            <option value="mediana">Più care</option>
            <option value="occasioni">Più occasioni</option>
          </select>
        }>
        Microzone
      </Titolo>
      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead className="bg-slate-50">
            <tr>
              <th className="th">Microzona</th>
              {dataset.fasce.map((f) => <th key={f} className="th text-right">{f}</th>)}
              <th className="th text-right">Mediana zona</th>
              <th className="th text-right">Attivi</th>
              <th className="th text-right">Occasioni</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {righe.map((r) => (
              <tr key={r.nome} className="hover:bg-brand-50/50">
                <td className="td font-medium"><Link className="text-brand-700 hover:underline" to={`/microzone/${encodeURIComponent(r.nome)}`}>{r.nome}</Link></td>
                {dataset.fasce.map((f) => {
                  const m = r.fasce[f];
                  return (
                    <td key={f} className="td text-right tabular-nums">
                      {m ? <>{num(m.mediana_mq)} <span className={`text-xs ${m.n < 3 ? "text-amber-600" : "text-slate-400"}`}>({m.n})</span></> : <span className="text-slate-300">–</span>}
                    </td>
                  );
                })}
                <td className="td text-right font-semibold tabular-nums">{num(r.mediana)}</td>
                <td className="td text-right tabular-nums">{r.attivi}</td>
                <td className="td text-right tabular-nums">{r.occasioni ? <span className="chip bg-sky-100 text-sky-800">{r.occasioni}</span> : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">In arancione le fasce con meno di 3 annunci: lo scostamento usa la mediana di zona corretta per la fascia.</p>
    </>
  );
}
