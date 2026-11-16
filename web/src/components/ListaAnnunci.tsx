import { useNavigate } from "react-router-dom";
import { eur, FONTE, num, piano } from "../lib/format";
import { useData } from "../lib/store";
import type { Annuncio } from "../lib/types";
import { BadgeStato, Scostamento, Vuoto } from "./ui";

/** Tabella su desktop, schede su telefono. */
export default function ListaAnnunci({ annunci, vuoto = "Nessun annuncio" , mostraZona = true }:
  { annunci: Annuncio[]; vuoto?: string; mostraZona?: boolean }) {
  const nav = useNavigate();
  const { valutazioni } = useData();
  const statoDi = (uid: string) => {
    const v = valutazioni.filter((x) => x.uid === uid).sort((a, b) => b.aggiornato.localeCompare(a.aggiornato))[0];
    return v?.stato;
  };
  if (!annunci.length) return <Vuoto>{vuoto}</Vuoto>;
  return (
    <>
      <div className="card hidden overflow-x-auto md:block">
        <table className="min-w-full divide-y divide-slate-100">
          <thead className="bg-slate-50">
            <tr>
              <th className="th">Scost.</th>
              {mostraZona && <th className="th">Microzona</th>}
              <th className="th">Indirizzo</th>
              <th className="th text-right">MQ</th>
              <th className="th text-right">Prezzo</th>
              <th className="th text-right">€/mq</th>
              <th className="th text-right">Rif. €/mq</th>
              <th className="th">Piano</th>
              <th className="th">Inserzionista</th>
              <th className="th text-right">Giorni</th>
              <th className="th">Team</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {annunci.map((a) => (
              <tr key={a.uid} onClick={() => nav(`/annuncio/${encodeURIComponent(a.uid)}`)}
                className={`cursor-pointer hover:bg-brand-50/50 ${a.attivo ? "" : "text-slate-400 line-through"}`}>
                <td className="td"><Scostamento v={a.scostamento_pct} /></td>
                {mostraZona && <td className="td text-slate-600">{a.microzona ?? "–"}</td>}
                <td className="td max-w-[16rem] truncate font-medium">{a.indirizzo || a.titolo}</td>
                <td className="td text-right tabular-nums">{num(a.mq)}</td>
                <td className="td text-right tabular-nums">
                  {eur(a.prezzo)}
                  {(a.ribasso_pct ?? 0) < 0 && <span className="ml-1 text-xs text-rose-600">↓{Math.abs(a.ribasso_pct!).toFixed(0)}%</span>}
                </td>
                <td className="td text-right tabular-nums">{num(a.prezzo_mq)}</td>
                <td className="td text-right tabular-nums text-slate-500">{num(a.riferimento_mq)}</td>
                <td className="td">{piano(a.piano)}</td>
                <td className="td max-w-[10rem] truncate text-slate-600">
                  {a.privato ? <span className="chip bg-violet-100 text-violet-800">Privato</span> : a.agenzia ?? "–"}
                  <span className="ml-1 text-xs text-slate-400">{FONTE[a.source]?.split(".")[0]}</span>
                </td>
                <td className="td text-right tabular-nums text-slate-500">{a.giorni_online ?? "–"}</td>
                <td className="td"><BadgeStato stato={statoDi(a.uid)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-2 md:hidden">
        {annunci.map((a) => (
          <button key={a.uid} onClick={() => nav(`/annuncio/${encodeURIComponent(a.uid)}`)}
            className={`card block w-full p-3 text-left ${a.attivo ? "" : "opacity-60"}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
                {mostraZona && <div className="truncate text-xs text-slate-500">{a.microzona}</div>}
              </div>
              <Scostamento v={a.scostamento_pct} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm tabular-nums">
              <span className="font-semibold">{eur(a.prezzo)}</span>
              <span>{num(a.mq)} mq</span>
              <span className="text-slate-500">{num(a.prezzo_mq)} €/mq</span>
              {(a.ribasso_pct ?? 0) < 0 && <span className="text-xs text-rose-600">↓{Math.abs(a.ribasso_pct!).toFixed(0)}%</span>}
              {a.privato && <span className="chip bg-violet-100 text-violet-800">Privato</span>}
              <BadgeStato stato={statoDi(a.uid)} />
            </div>
          </button>
        ))}
      </div>
    </>
  );
}
