import type { Annuncio } from "./types";

/** Segnalazione del bot: l'annuncio è posizionato all'indirizzo dell'agenzia, non dell'immobile. */
export const FLAG_AGENZIA = "indirizzo dell'agenzia";

/** Il motivo della segnalazione, o null se l'annuncio è a posto. */
export function indirizzoAgenzia(a: Pick<Annuncio, "flags">): string | null {
  const f = a.flags?.find((x) => x.startsWith(FLAG_AGENZIA));
  return f ? f.slice(FLAG_AGENZIA.length).replace(/^:\s*/, "") : null;
}
