// Chat del sito: risponde alle domande sui risultati del bot (annunci, mediane, aste, frazionabili).
//
// Gira su Supabase (Edge Function), così la chiave di Claude resta sul server e non finisce mai
// nel sito pubblico. Solo gli utenti che hanno fatto il login possono usarla: la funzione legge i dati
// con il token dell'utente, quindi valgono gli stessi permessi del sito.
//
// Installazione (una volta, vedi SITO_WEB.md):
//   supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
//   supabase functions deploy chiedi
import Anthropic from "npm:@anthropic-ai/sdk@1.5.0";
import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2.45.4";

const MODELLO = "claude-opus-5-5";
const MAX_GIRI_STRUMENTI = 6;
const MAX_DOMANDA = 2000;
const MAX_STORICO = 12;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

// ---------------------------------------------------------------- dati
const COLONNE = "uid,source,url,titolo,indirizzo,microzona,fascia,prezzo,mq,prezzo_mq,riferimento_mq," +
  "scostamento_pct,base_confronto,occasione,giorni_online,ribasso_pct,piano,stato,agenzia,privato,first_seen," +
  "flags,tipo_vendita,prezzo_base,offerta_minima,data_asta,scostamento_minima_pct,valore_mercato,diritto,occupazione";
const COLONNE_SENZA_ASTE = COLONNE.split(",").filter((c) =>
  !["tipo_vendita", "prezzo_base", "offerta_minima", "data_asta", "scostamento_minima_pct", "valore_mercato",
    "diritto", "occupazione"].includes(c)
).join(",");

type Filtri = {
  tipo: "compravendita" | "asta" | "tutti";
  microzona: string | null;
  fascia: string | null;
  prezzo_min: number | null;
  prezzo_max: number | null;
  mq_min: number | null;
  mq_max: number | null;
  solo_occasioni: boolean;
  ordina: "scostamento" | "prezzo" | "prezzo_mq" | "recenti" | "data_asta" | "giorni_online";
  limite: number;
};

const arrotonda = (r: Record<string, unknown>) => {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(r)) {
    if (v === null || v === undefined || (Array.isArray(v) && !v.length)) continue;
    out[k] = typeof v === "number" ? Math.round(v * 10) / 10 : v;
  }
  return out;
};

async function cercaAnnunci(db: SupabaseClient, territorio: string, f: Filtri, conAste: boolean) {
  let q = db.from("annunci").select(conAste ? COLONNE : COLONNE_SENZA_ASTE)
    .eq("territorio", territorio).eq("attivo", true);
  if (conAste && f.tipo === "compravendita") q = q.eq("tipo_vendita", "compravendita");
  if (conAste && f.tipo === "asta") q = q.in("tipo_vendita", ["asta", "possibile_asta"]);
  if (!conAste && f.tipo === "asta") return { errore: "Le aste non sono ancora nel database (manca la migrazione 003)." };
  if (f.microzona) q = q.ilike("microzona", `%${f.microzona}%`);
  if (f.fascia) q = q.eq("fascia", f.fascia);
  if (f.prezzo_min != null) q = q.gte("prezzo", f.prezzo_min);
  if (f.prezzo_max != null) q = q.lte("prezzo", f.prezzo_max);
  if (f.mq_min != null) q = q.gte("mq", f.mq_min);
  if (f.mq_max != null) q = q.lte("mq", f.mq_max);
  if (f.solo_occasioni) q = q.eq("occasione", true);
  const ordine: Record<Filtri["ordina"], [string, boolean]> = {
    scostamento: ["scostamento_pct", true], prezzo: ["prezzo", true], prezzo_mq: ["prezzo_mq", true],
    recenti: ["first_seen", false], data_asta: ["data_asta", true], giorni_online: ["giorni_online", false],
  };
  const [col, asc] = ordine[f.ordina] ?? ordine.scostamento;
  q = q.order(conAste || col !== "data_asta" ? col : "scostamento_pct", { ascending: asc, nullsFirst: false })
    .limit(Math.min(Math.max(f.limite || 20, 1), 50));
  const { data, error } = await q;
  if (error) return { errore: error.message };
  return { n: data?.length ?? 0, annunci: (data ?? []).map((r) => arrotonda(r as unknown as Record<string, unknown>)) };
}

async function contesto(db: SupabaseClient, territorio: string) {
  const [med, esec, zone, fraz] = await Promise.all([
    db.from("mediane").select("microzona,fascia,n,mediana_mq,mediana_zona,n_zona").eq("territorio", territorio),
    db.from("esecuzioni").select("ts,annunci,occasioni,frazionabili").eq("territorio", territorio)
      .order("ts", { ascending: false }).limit(1),
    db.from("zone").select("nome").eq("territorio", territorio).order("ordine"),
    db.from("frazionabili").select("uid,n_unita,mq_unita,valore_post,costi_totali,margine,margine_pct,indizi")
      .eq("territorio", territorio).order("margine_pct", { ascending: false }).limit(30),
  ]);
  const aste = await db.from("annunci").select("tipo_vendita").eq("territorio", territorio).eq("attivo", true)
    .neq("tipo_vendita", "compravendita");
  const conAste = !aste.error;
  const righeMed = (med.data ?? []).map((m) =>
    [m.microzona, m.fascia, m.n, Math.round(m.mediana_mq ?? 0), Math.round(m.mediana_zona ?? 0), m.n_zona].join(";")
  );
  const testo = [
    `Territorio: ${territorio}.`,
    esec.data?.[0]
      ? `Ultima esecuzione del bot: ${esec.data[0].ts}; annunci analizzati ${esec.data[0].annunci}, occasioni ${esec.data[0].occasioni}, frazionabili ${esec.data[0].frazionabili}.`
      : "Nessuna esecuzione registrata.",
    conAste ? `Aste attive (compresi i casi da verificare): ${aste.data?.length ?? 0}.` : "Aste: non ancora nel database.",
    `Microzone: ${(zone.data ?? []).map((z) => z.nome).join(", ")}.`,
    "",
    "Mediane del mercato libero (aste escluse). Colonne: microzona;fascia mq;n annunci;mediana €/mq della fascia;mediana €/mq della zona intera;n zona",
    ...righeMed,
    "",
    "Candidati al frazionamento (i migliori per margine %):",
    JSON.stringify((fraz.data ?? []).map(arrotonda)),
  ].join("\n");
  return { testo, conAste };
}

// ---------------------------------------------------------------- Claude
const SISTEMA = `Sei l'assistente del sito "Scout Immobili" di un investitore immobiliare. Rispondi in italiano, in modo diretto e concreto, come un collega esperto del mercato locale.

Come funziona il metodo:
- Il territorio è diviso in microzone tracciate lungo confini fisici (grandi strade, fiumi, ferrovie, quartieri).
- Per ogni microzona e fascia di superficie (30/50, 50/70, 70/100, 100+ mq) il bot calcola la mediana del prezzo al mq degli annunci in vendita.
- Lo scostamento % di un annuncio è la differenza tra il suo €/mq e quella mediana. Sotto la soglia (di solito -15%) è un'"occasione".
- Con meno di 3 annunci nella fascia la mediana non è affidabile e si usa quella della zona intera. Dillo quando succede.
- Le aste giudiziarie (riconosciute dal testo degli annunci o prese dal Portale delle Vendite Pubbliche) NON entrano nelle mediane. Sono confrontate con il mercato libero della loro microzona. Per le aste conta solo la piena proprietà: segnala quote, nuda proprietà, usufrutto e immobili occupati.
- I "frazionabili" sono immobili grandi che, divisi in unità piccole, potrebbero rendere di più.

Regole:
- Usa lo strumento cerca_annunci per qualsiasi domanda su annunci specifici. Non inventare annunci, prezzi o indirizzi.
- Quando citi un annuncio, metti il link in formato Markdown [indirizzo o titolo](url).
- Se i dati non bastano per rispondere, dillo e spiega cosa servirebbe.
- Le cifre sono stime da annunci, non perizie: ricordalo quando si parla di decisioni d'acquisto.
- Risposte brevi: elenco puntato per più annunci, al massimo una decina, ordinati per interesse.`;

const STRUMENTO: Anthropic.Beta.BetaTool = {
  name: "cerca_annunci",
  description:
    "Cerca tra gli annunci attivi del territorio (compravendite e/o aste) con filtri. Restituisce al massimo 50 annunci con prezzo, mq, €/mq, mediana di riferimento, scostamento %, microzona e link; per le aste anche prezzo base, offerta minima, data, diritto e occupazione.",
  strict: true,
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["tipo", "microzona", "fascia", "prezzo_min", "prezzo_max", "mq_min", "mq_max", "solo_occasioni", "ordina", "limite"],
    properties: {
      tipo: { type: "string", enum: ["compravendita", "asta", "tutti"], description: "compravendita = mercato libero, asta = aste giudiziarie" },
      microzona: { type: ["string", "null"], description: "nome (anche parziale) della microzona, null = tutte" },
      fascia: { type: ["string", "null"], description: "fascia di superficie: 30/50, 50/70, 70/100 o 100+; null = tutte" },
      prezzo_min: { type: ["number", "null"] },
      prezzo_max: { type: ["number", "null"] },
      mq_min: { type: ["number", "null"] },
      mq_max: { type: ["number", "null"] },
      solo_occasioni: { type: "boolean", description: "solo annunci sotto la soglia di scostamento" },
      ordina: { type: "string", enum: ["scostamento", "prezzo", "prezzo_mq", "recenti", "data_asta", "giorni_online"] },
      limite: { type: "integer", description: "quanti annunci (1-50)" },
    },
  },
};

type Turno = { role: "user" | "assistant"; content: string };

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ errore: "usa POST" }, 405);

  const auth = req.headers.get("Authorization") ?? "";
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: auth } },
  });
  const { data: utente } = await db.auth.getUser(auth.replace(/^Bearer\s+/i, ""));
  if (!utente?.user) return json({ errore: "Accesso richiesto." }, 401);
  if (!Deno.env.get("ANTHROPIC_API_KEY")) {
    return json({ errore: "Chat non configurata: manca ANTHROPIC_API_KEY nei segreti di Supabase." }, 500);
  }

  let corpo: { territorio?: string; domanda?: string; storico?: Turno[] };
  try {
    corpo = await req.json();
  } catch {
    return json({ errore: "richiesta non valida" }, 400);
  }
  const territorio = String(corpo.territorio ?? "").slice(0, 100);
  const domanda = String(corpo.domanda ?? "").trim().slice(0, MAX_DOMANDA);
  if (!territorio || !domanda) return json({ errore: "mancano territorio o domanda" }, 400);
  const storico = (Array.isArray(corpo.storico) ? corpo.storico : [])
    .filter((t) => (t?.role === "user" || t?.role === "assistant") && typeof t.content === "string" && t.content.trim())
    .slice(-MAX_STORICO)
    .map((t) => ({ role: t.role, content: t.content.slice(0, 8000) }));
  while (storico.length && storico[0].role !== "user") storico.shift();

  const { testo: dati, conAste } = await contesto(db, territorio);
  const client = new Anthropic();
  const messaggi: Anthropic.Beta.BetaMessageParam[] = [...storico, { role: "user", content: domanda }];

  try {
    for (let giro = 0; giro < MAX_GIRI_STRUMENTI; giro++) {
      const risposta = await client.beta.messages.create({
        model: MODELLO,
        max_tokens: 8000,
        betas: ["server-side-fallback-2026-07-01"],
        fallbacks: "default",
        output_config: { effort: "medium" },
        // il riepilogo dei dati cambia solo a ogni esecuzione del bot: va in cache
        system: [
          { type: "text", text: SISTEMA },
          { type: "text", text: `Dati dell'ultima analisi:\n${dati}`, cache_control: { type: "ephemeral" } },
        ],
        tools: [STRUMENTO],
        messages: messaggi,
      });
      if (risposta.stop_reason === "refusal") {
        return json({ risposta: "Non posso rispondere a questa domanda. Prova a riformularla." });
      }
      messaggi.push({ role: "assistant", content: risposta.content });
      const chiamate = risposta.content.filter((b): b is Anthropic.Beta.BetaToolUseBlock => b.type === "tool_use");
      if (risposta.stop_reason !== "tool_use" || !chiamate.length) {
        const testo = risposta.content.filter((b) => b.type === "text").map((b) => (b as Anthropic.Beta.BetaTextBlock).text)
          .join("\n").trim();
        return json({
          risposta: testo || (risposta.stop_reason === "max_tokens" ? "Risposta troppo lunga, prova a restringere la domanda." : "…"),
        });
      }
      const risultati: Anthropic.Beta.BetaToolResultBlockParam[] = [];
      for (const c of chiamate) {
        const esito = c.name === "cerca_annunci"
          ? await cercaAnnunci(db, territorio, c.input as Filtri, conAste)
          : { errore: `strumento sconosciuto: ${c.name}` };
        risultati.push({
          type: "tool_result", tool_use_id: c.id, content: JSON.stringify(esito), is_error: "errore" in esito,
        });
      }
      messaggi.push({ role: "user", content: risultati });
    }
    return json({ risposta: "La domanda richiede troppe ricerche: prova a renderla più precisa." });
  } catch (e) {
    if (e instanceof Anthropic.RateLimitError) return json({ errore: "Troppe richieste, riprova tra un minuto." }, 429);
    if (e instanceof Anthropic.AuthenticationError) return json({ errore: "Chiave di Claude non valida." }, 500);
    if (e instanceof Anthropic.BadRequestError) {
      // il motivo (es. credito esaurito) non contiene dati riservati: lo mostro per capire cosa sistemare
      return json({ errore: `Errore del servizio (400): ${e.message}` }, 502);
    }
    if (e instanceof Anthropic.APIError) return json({ errore: `Errore del servizio (${e.status}): ${e.message}` }, 502);
    return json({ errore: "Errore interno." }, 500);
  }
});
