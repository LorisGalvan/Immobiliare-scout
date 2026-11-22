import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { eur, FONTE, num, piano } from "../lib/format";
import { useData } from "../lib/store";
import type { Annuncio } from "../lib/types";
import { nomeUtente, NESSUNA, perAnnuncio } from "../lib/valutazioni";
import { BadgeStato, Scostamento, Vuoto } from "./ui";

/** Tabella su desktop, schede su telefono. */
type Inserzionista = "tutti" | "privati" | "agenzie";
const ETICHETTE: Record<Inserzionista, string> = { tutti: "Tutti", privati: "Privati", agenzie: "Agenzie" };
const passa = (a: Annuncio, f: Inserzionista) => f === "tutti" || (f === "privati" ? !!a.privato : !a.privato);

/** Tabella su desktop, schede su telefono. Sopra, il filtro Tutti / Privati / Agenzie. */
export default function ListaAnnunci({ annunci: tutti, vuoto = "Nessun annuncio", mostraZona = true, filtroInserzionista = true }:
  { annunci: Annuncio[]; vuoto?: string; mostraZona?: boolean; filtroInserzionista?: boolean }) {
  const [ins, setIns] = useState<Inserzionista>("tutti");
  const annunci = filtroInserzionista ? tutti.filter((a) => passa(a, ins)) : tutti;
  const filtro = filtroInserzionista && tutti.length > 0 && (
    <div className="mb-2 inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-sm" role="group" aria-label="Inserzionista">
      {(Object.keys(ETICHETTE) as Inserzionista[]).map((k) => (
        <button key={k} type="button" onClick={() => setIns(k)} aria-pressed={ins === k}
          className={`rounded-md px-3 py-1 font-medium ${ins === k ? "bg-brand-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
          {ETICHETTE[k]} <span className={ins === k ? "text-white/70" : "text-slate-400"}>{tutti.filter((a) => passa(a, k)).length}</span>
        </button>
      ))}
    </div>
  );
  return <>{filtro}<Elenco annunci={annunci} vuoto={vuoto} mostraZona={mostraZona} /></>;
}

function Elenco({ annunci, vuoto, mostraZona }: { annunci: Annuncio[]; vuoto: string; mostraZona: boolean }) {
  const nav = useNavigate();
  const { valutazioni } = useData();
  const team = perAnnuncio(valutazioni);
  const teamDi = (uid: string) => team.get(uid) ?? NESSUNA;
  const statoDi = (uid: string) => teamDi(uid).stato;
  // al passaggio del mouse: chi ha valutato e cosa ha scritto
  const dettaglio = (uid: string) =>
    teamDi(uid).voci.map((v) => `${nomeUtente(v)}${v.nota?.trim() ? ": " + v.nota.trim() : ""}`).join("\n") || undefined;
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
                <td className="td" title={dettaglio(a.uid)}>
                  <BadgeStato stato={statoDi(a.uid)} />
                  {teamDi(a.uid).autore && <span className="ml-1 text-xs text-slate-400">{teamDi(a.uid).autore}</span>}
                  {teamDi(a.uid).voci.some((v) => v.nota?.trim()) && <span className="ml-1 text-xs text-slate-400" aria-label="con nota">✎</span>}
                </td>
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
              {teamDi(a.uid).autore && <span className="text-xs text-slate-400">{teamDi(a.uid).autore}</span>}
            </div>
          </button>
        ))}
      </div>
    </>
  );
}
