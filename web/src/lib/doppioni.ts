import type { Annuncio } from "./types";

/** Un annuncio dello stesso immobile (letto dalla riga "fonte: url (inserzionista, prezzo€)" del bot). */
export interface Copia {
  source: string;
  url: string | null;
  chi: string;
  prezzo: number | null;
  principale?: boolean;
}

const RIGA = /^(\w+):\s*(\S+)?\s*\((.*), (\d[\d.,]*)\s*€\)\s*$/;

export function leggiCopia(d: string): Copia {
  const m = d.match(RIGA);
  if (!m) {
    const url = d.match(/https?:\/\/\S+/)?.[0] ?? null;
    return { source: d.split(":")[0], url, chi: "?", prezzo: null };
  }
  const prezzo = Number(m[4].replace(/[.,]/g, ""));
  return { source: m[1], url: m[2]?.startsWith("http") ? m[2] : null, chi: m[3].trim() || "?", prezzo: prezzo || null };
}

/** Tutti gli annunci dello stesso immobile, il principale per primo. */
export function copie(a: Annuncio): Copia[] {
  const prima: Copia = { source: a.source, url: a.url || null, chi: a.privato ? "privato" : a.agenzia ?? "?", prezzo: a.prezzo, principale: true };
  return [prima, ...(a.doppioni ?? []).map(leggiCopia)];
}

/** Quanti inserzionisti diversi pubblicano l'immobile. */
export function nInserzionisti(a: Annuncio): number {
  return new Set(copie(a).map((c) => c.chi.trim().toLowerCase()).filter((c) => c && c !== "?")).size;
}
