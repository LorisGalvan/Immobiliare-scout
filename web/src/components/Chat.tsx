import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { DEMO, supabase } from "../lib/supabase";
import { useData } from "../lib/store";
import { ICONE, Icona } from "./ui";

type Turno = { role: "user" | "assistant"; content: string };

const ESEMPI = [
  "Quali sono le 5 migliori occasioni sotto i 200.000 €?",
  "Qual è la mediana €/mq dei bilocali in Borgo Trento?",
  "Ci sono aste in piena proprietà con offerta minima sotto il mercato?",
  "Quali immobili grandi conviene frazionare?",
];

/** Markdown minimo e sicuro (niente HTML): link, grassetto, elenchi puntati. */
function inline(t: string): ReactNode[] {
  const out: ReactNode[] = [];
  const rx = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|\*\*([^*]+)\*\*/g;
  let last = 0;
  for (const m of t.matchAll(rx)) {
    if (m.index! > last) out.push(t.slice(last, m.index));
    out.push(m[1]
      ? <a key={m.index} href={m[2]} target="_blank" rel="noreferrer" className="text-brand-700 underline">{m[1]}</a>
      : <b key={m.index}>{m[3]}</b>);
    last = m.index! + m[0].length;
  }
  if (last < t.length) out.push(t.slice(last));
  return out;
}

function Testo({ t }: { t: string }) {
  const righe = t.split("\n");
  return (
    <>
      {righe.map((r, i) => {
        const p = r.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
        if (p) return <div key={i} className="flex gap-1.5 pl-1"><span className="text-slate-400">•</span><span>{inline(p[1])}</span></div>;
        const h = r.match(/^#{1,4}\s+(.*)$/);
        if (h) return <div key={i} className="mt-1 font-semibold">{inline(h[1])}</div>;
        return r.trim() ? <p key={i}>{inline(r)}</p> : <Fragment key={i}><div className="h-1.5" /></Fragment>;
      })}
    </>
  );
}

export default function Chat() {
  const { territorio } = useData();
  const [aperta, setAperta] = useState(false);
  const [turni, setTurni] = useState<Turno[]>([]);
  const [testo, setTesto] = useState("");
  const [attesa, setAttesa] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);
  const fondo = useRef<HTMLDivElement>(null);

  useEffect(() => { fondo.current?.scrollIntoView({ behavior: "smooth" }); }, [turni, attesa]);

  const invia = async (domanda: string) => {
    domanda = domanda.trim();
    if (!domanda || attesa || !territorio) return;
    setErrore(null);
    const storico = turni;
    setTurni([...storico, { role: "user", content: domanda }]);
    setTesto("");
    setAttesa(true);
    try {
      const { data, error } = await supabase!.functions.invoke("chiedi", { body: { territorio, domanda, storico } });
      if (error) {
        let msg = error.message;
        try { msg = (await (error as { context?: Response }).context?.json())?.errore ?? msg; } catch { /* corpo non JSON */ }
        throw new Error(msg);
      }
      if (data?.errore) throw new Error(data.errore);
      setTurni((t) => [...t, { role: "assistant", content: data.risposta }]);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : String(e));
      setTurni(storico);            // la domanda non è andata: la rimetto nel campo
      setTesto(domanda);
    } finally {
      setAttesa(false);
    }
  };

  return (
    <>
      <button onClick={() => setAperta(!aperta)} title="Chiedi ai dati"
        className="fixed bottom-20 right-4 z-[1100] grid h-12 w-12 place-items-center rounded-full bg-brand-700 text-white shadow-lg hover:bg-brand-600 md:bottom-6">
        <Icona d={aperta ? ICONE.chiudi : ICONE.chat} className="h-6 w-6" />
      </button>
      {aperta && (
        <div className="fixed inset-x-2 bottom-36 top-16 z-[1100] flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl sm:inset-x-auto sm:right-4 sm:w-[26rem] md:bottom-24">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <div>
              <div className="font-semibold">Chiedi ai dati</div>
              <div className="text-xs text-slate-500">Risposte sui risultati di {territorio ?? "…"}</div>
            </div>
            {!!turni.length && <button className="btn-ghost px-2 text-xs" onClick={() => { setTurni([]); setErrore(null); }}>Nuova chat</button>}
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {DEMO ? (
              <p className="text-slate-500">La chat funziona con i dati veri: collega Supabase e attiva la funzione <code>chiedi</code> (vedi SITO_WEB.md).</p>
            ) : !turni.length ? (
              <div className="space-y-2">
                <p className="text-slate-500">Fai una domanda su annunci, mediane, aste o frazionabili. Per esempio:</p>
                {ESEMPI.map((e) => (
                  <button key={e} onClick={() => invia(e)} className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-left hover:bg-slate-50">{e}</button>
                ))}
              </div>
            ) : turni.map((t, i) => (
              <div key={i} className={t.role === "user" ? "ml-8 rounded-xl bg-brand-50 px-3 py-2" : "mr-2 space-y-1 leading-relaxed"}>
                {t.role === "user" ? t.content : <Testo t={t.content} />}
              </div>
            ))}
            {attesa && <div className="animate-pulse text-slate-400">Sto guardando i dati…</div>}
            {errore && <div className="rounded-lg bg-rose-50 px-3 py-2 text-rose-800">{errore}</div>}
            <div ref={fondo} />
          </div>
          {!DEMO && (
            <form className="flex gap-2 border-t border-slate-100 p-2" onSubmit={(e) => { e.preventDefault(); invia(testo); }}>
              <input className="input flex-1" placeholder="Scrivi una domanda…" value={testo} maxLength={2000}
                onChange={(e) => setTesto(e.target.value)} disabled={attesa} />
              <button className="btn-primary px-3" disabled={attesa || !testo.trim()}>Invia</button>
            </form>
          )}
        </div>
      )}
    </>
  );
}
