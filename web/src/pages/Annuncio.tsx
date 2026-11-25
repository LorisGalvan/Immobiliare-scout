import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { prezzi as caricaPrezzi, salvaValutazione } from "../lib/data";
import { data as fData, dataOra, eur, FONTE, num, pct, piano, STATO } from "../lib/format";
import { copie } from "../lib/doppioni";
import { indirizzoAgenzia } from "../lib/agenzia";
import { useAuth, useData } from "../lib/store";
import type { Prezzo, StatoValutazione } from "../lib/types";
import GraficoPrezzi from "../components/GraficoPrezzi";
import Mappa from "../components/Mappa";
import { BadgeStato, ICONE, Icona, Scostamento, STATI_VAL, Vuoto } from "../components/ui";

function Riga({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-4 py-1.5 text-sm"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium">{v}</dd></div>;
}

export default function Annuncio() {
  const { uid = "" } = useParams();
  const nav = useNavigate();
  const { dataset, valutazioni, ricaricaValutazioni } = useData();
  const { utente } = useAuth();
  const [storia, setStoria] = useState<Prezzo[]>([]);
  const a = dataset?.annunci.find((x) => x.uid === uid) ?? dataset?.aste.find((x) => x.uid === uid);
  const fr = dataset?.frazionabili.find((x) => x.uid === uid);
  const mie = valutazioni.find((v) => v.uid === uid && v.user_id === utente?.id);
  const altre = valutazioni.filter((v) => v.uid === uid && v.user_id !== utente?.id);
  const [stato, setStato] = useState<StatoValutazione | null>(null);
  const [nota, setNota] = useState("");
  const [salvato, setSalvato] = useState(false);

  useEffect(() => { caricaPrezzi(uid).then(setStoria).catch(() => setStoria([])); }, [uid]);
  useEffect(() => { setStato(mie?.stato ?? null); setNota(mie?.nota ?? ""); }, [mie?.stato, mie?.nota, uid]);

  const zoneSolo = useMemo(() => dataset?.zone.filter((z) => z.nome === a?.microzona) ?? [], [dataset, a]);
  const valori = useMemo(() => ({ [a?.microzona ?? ""]: a?.riferimento_mq ?? undefined }), [a]);
  const lista = useMemo(() => (a ? [a] : []), [a]);
  const evid = useMemo(() => new Set([uid]), [uid]);

  if (!dataset) return null;
  if (!a) return <Vuoto>Annuncio non trovato (forse rimosso da tempo).</Vuoto>;

  const sedeAgenzia = indirizzoAgenzia(a);
  const salva = async () => {
    if (!utente) return;
    await salvaValutazione({ uid, stato, nota: nota || null }, utente.id, utente.email);
    ricaricaValutazioni();
    setSalvato(true);
    setTimeout(() => setSalvato(false), 2000);
  };

  return (
    <>
      <button onClick={() => nav(-1)} className="mb-2 inline-flex items-center text-sm text-slate-500 hover:text-slate-800"><Icona d={ICONE.indietro} className="h-4 w-4" />Indietro</button>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold sm:text-2xl">{a.indirizzo || a.titolo}</h1>
          <p className="text-sm text-slate-500">
            {a.microzona ? <Link className="text-brand-600 hover:underline" to={`/microzone/${encodeURIComponent(a.microzona)}`}>{a.microzona}</Link> : "Fuori zona"}
            {" · "}fascia {a.fascia} mq{!a.attivo && <> · <b className="text-rose-600">rimosso il {fData(a.removed_at)}</b></>}
          </p>
        </div>
        <a href={a.url} target="_blank" rel="noreferrer" className="btn-primary"><Icona d={ICONE.link} className="h-4 w-4" />Apri su {FONTE[a.source] ?? a.source}</a>
      </div>
      {sedeAgenzia != null && (
        <div className="mb-4 rounded-xl border-2 border-orange-300 bg-orange-50 p-3 text-sm text-orange-900">
          <b>📍 Indirizzo dell'agenzia, non dell'immobile</b>: la posizione sulla mappa è quella dell'ufficio, quindi
          l'annuncio è escluso dalla valutazione della microzona (niente mediana, scostamento né occasione).
          {sedeAgenzia && <> Motivo: {sedeAgenzia}.</>} Chiedi all'agenzia dove si trova davvero.
        </div>
      )}
      {(a.tipo_vendita === "asta" || a.tipo_vendita === "possibile_asta") && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          <b>{a.tipo_vendita === "asta" ? "Asta giudiziaria" : "Possibile asta, da verificare"}</b>: esclusa dalla valutazione del territorio.
          {!!a.indizi_vendita?.length && <> Indizi nel testo: {a.indizi_vendita.join(", ")}.</>}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="card grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
            <div><div className="label">Prezzo</div><div className="text-xl font-semibold tabular-nums">{eur(a.prezzo)}</div></div>
            <div><div className="label">Superficie</div><div className="text-xl font-semibold tabular-nums">{num(a.mq)} mq</div></div>
            <div><div className="label">€/mq</div><div className="text-xl font-semibold tabular-nums">{num(a.prezzo_mq)}</div><div className="text-xs text-slate-500">rif. {num(a.riferimento_mq)}</div></div>
            <div><div className="label">Scostamento</div><Scostamento v={a.scostamento_pct} grande /><div className="mt-1 text-xs text-slate-500">grezzo {pct(a.scostamento_grezzo_pct)}</div></div>
          </div>

          <div className="card p-4">
            <h2 className="mb-2 font-semibold">Andamento prezzo</h2>
            <GraficoPrezzi prezzi={storia} />
            <p className="mt-2 text-xs text-slate-500">
              Online da {a.giorni_online ?? "–"} giorni (prima rilevazione {fData(a.first_seen)})
              {(a.ribasso_pct ?? 0) < 0 && <> · ribasso {pct(a.ribasso_pct)} da {eur(a.prezzo_iniziale)}</>}
            </p>
          </div>

          {a.descrizione && (
            <div className="card p-4">
              <h2 className="mb-2 font-semibold">Descrizione</h2>
              <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{a.descrizione}</p>
            </div>
          )}

          {fr && (
            <div className="card border-violet-200 p-4">
              <h2 className="mb-2 font-semibold text-violet-800">Frazionamento</h2>
              <dl className="divide-y divide-slate-100">
                <Riga k="Unità ricavabili" v={`${fr.n_unita} × ${num(fr.mq_unita)} mq`} />
                <Riga k="Mediana fascia piccola in zona" v={`${num(fr.mediana_piccole_mq)} €/mq (${fr.n_campione_piccole} annunci)`} />
                <Riga k="Valore post frazionamento" v={eur(fr.valore_post)} />
                <Riga k="Lavori + spese tecniche" v={eur(fr.costo_lavori)} />
                <Riga k="Impianti + oneri" v={eur(fr.costo_impianti_oneri)} />
                <Riga k="Notaio, imposte, provvigioni" v={eur(fr.costi_transazione)} />
                <Riga k="Margine" v={<span className="text-violet-700">{eur(fr.margine)} ({pct(fr.margine_pct, 0)})</span>} />
              </dl>
              {fr.indizi && <div className="mt-2 flex flex-wrap gap-1">{fr.indizi.split(", ").map((i) => <span key={i} className="chip bg-violet-100 text-violet-800">{i}</span>)}</div>}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <h2 className="mb-2 font-semibold">Valutazione del team</h2>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {STATI_VAL.map((s) => (
                <button key={s.v} onClick={() => setStato(stato === s.v ? null : s.v)}
                  className={`chip border px-2.5 py-1 ${stato === s.v ? s.cls + " border-transparent ring-2 ring-brand-300" : "border-slate-200 bg-white text-slate-600"}`}>
                  {s.label}
                </button>
              ))}
            </div>
            <textarea className="input min-h-[80px]" placeholder="Nota (visita, contatto agenzia, prezzo trattabile…)" value={nota} onChange={(e) => setNota(e.target.value)} />
            <button className="btn-primary mt-2 w-full" onClick={salva}>{salvato ? "Salvato ✓" : "Salva"}</button>
            {altre.length > 0 && (
              <ul className="mt-4 space-y-2 border-t border-slate-100 pt-3">
                {altre.map((v) => (
                  <li key={v.user_id} className="text-sm">
                    <div className="flex items-center gap-2"><span className="font-medium">{v.user_email?.split("@")[0]}</span><BadgeStato stato={v.stato} /><span className="ml-auto text-xs text-slate-400">{dataOra(v.aggiornato)}</span></div>
                    {v.nota && <p className="mt-0.5 text-slate-600">{v.nota}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card p-4">
            <h2 className="mb-1 font-semibold">Dettagli</h2>
            <dl className="divide-y divide-slate-100">
              <Riga k="Piano" v={piano(a.piano)} />
              <Riga k="Ascensore" v={a.ascensore == null ? "–" : a.ascensore ? "Sì" : "No"} />
              <Riga k="Bagni" v={a.bagni ?? "–"} />
              <Riga k="Locali" v={a.locali ?? "–"} />
              <Riga k="Stato" v={a.stato ? STATO[a.stato] ?? a.stato : "–"} />
              <Riga k="Inserzionista" v={a.privato ? "Privato" : a.agenzia ?? "–"} />
              <Riga k="Pubblicato" v={fData(a.data_pubblicazione)} />
              <Riga k="Confronto" v={<span className="text-xs">{a.base_confronto}</span>} />
              {a.coeff != null && Math.abs(a.coeff - 1) > 0.001 && <Riga k="Coefficiente correzione" v={a.coeff.toFixed(2)} />}
              {a.omi_min != null && <Riga k={`OMI ${a.zona_omi ?? ""}`} v={`${num(a.omi_min)}–${num(a.omi_max)} €/mq`} />}
            </dl>
          </div>

          {(a.flags.length > 0 || a.doppioni.length > 0) && (
            <div className="card p-4">
              {a.flags.length > 0 && <>
                <h2 className="mb-2 font-semibold">Segnalazioni</h2>
                <ul className="mb-3 space-y-1 text-sm text-amber-800">{a.flags.map((f) => <li key={f}>⚠ {f}</li>)}</ul>
              </>}
              {a.doppioni.length > 0 && <>
                <h2 className="mb-1 font-semibold">Stesso immobile, {copie(a).length} annunci</h2>
                <p className="mb-2 text-xs text-slate-500">Il bot li ha riconosciuti come lo stesso immobile e li mostra in una scheda sola.</p>
                <ul className="divide-y divide-slate-100 text-sm">{copie(a).map((c, i) => (
                  <li key={i} className="flex items-center gap-2 py-1.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{c.chi === "privato" ? "Privato" : c.chi}</div>
                      <div className="text-xs text-slate-500">{FONTE[c.source] ?? c.source}{c.principale && " · questa scheda"}</div>
                    </div>
                    <span className={`tabular-nums ${c.prezzo != null && c.prezzo === Math.min(...copie(a).map((x) => x.prezzo ?? Infinity)) ? "font-semibold text-emerald-700" : ""}`}>{eur(c.prezzo)}</span>
                    {c.url && <a className="text-brand-600 hover:underline" href={c.url} target="_blank" rel="noreferrer">Apri</a>}
                  </li>
                ))}</ul>
              </>}
            </div>
          )}

          {a.lat != null && zoneSolo.length > 0 && (
            <Mappa zone={zoneSolo} valoreZona={valori} annunci={lista} evidenziati={evid} altezza="240px" />
          )}
        </div>
      </div>
    </>
  );
}
