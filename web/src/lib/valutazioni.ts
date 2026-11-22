import type { StatoValutazione, Valutazione } from "./types";

/** Le tre liste della pagina: chi non è ancora stato guardato, chi è in lavorazione, chi è stato scartato. */
export type Gruppo = "da_valutare" | "in_valutazione" | "scartati";

export interface Team {
  /** stato più recente segnato da qualcuno del team (null = nessuno ha scelto uno stato) */
  stato: StatoValutazione | null;
  /** chi ha segnato quello stato */
  autore: string | null;
  /** tutte le valutazioni (stato o nota), la più recente per prima */
  voci: Valutazione[];
  gruppo: Gruppo;
}

export const nomeUtente = (v: Pick<Valutazione, "user_email">) => v.user_email?.split("@")[0] || "qualcuno";

export function gruppoDi(stato: StatoValutazione | null, haNote: boolean): Gruppo {
  if (stato === "scartato") return "scartati";
  if (stato && stato !== "da_vedere") return "in_valutazione";
  return haNote ? "in_valutazione" : "da_valutare";
}

/** Riassume le valutazioni del team per annuncio (uid → Team). */
export function perAnnuncio(valutazioni: Valutazione[]): Map<string, Team> {
  const per = new Map<string, Valutazione[]>();
  for (const v of valutazioni) {
    if (!v.stato && !v.nota?.trim()) continue; // valutazione svuotata
    const l = per.get(v.uid);
    if (l) l.push(v); else per.set(v.uid, [v]);
  }
  const out = new Map<string, Team>();
  for (const [uid, voci] of per) {
    voci.sort((a, b) => b.aggiornato.localeCompare(a.aggiornato));
    const conStato = voci.find((v) => v.stato);
    const stato = conStato?.stato ?? null;
    out.set(uid, {
      stato, autore: conStato ? nomeUtente(conStato) : null, voci,
      gruppo: gruppoDi(stato, voci.some((v) => v.nota?.trim())),
    });
  }
  return out;
}

export const NESSUNA: Team = { stato: null, autore: null, voci: [], gruppo: "da_valutare" };
