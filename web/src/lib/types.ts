export interface Zona {
  territorio: string;
  nome: string;
  geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  props?: Record<string, unknown>;
  ordine?: number;
}

export interface Annuncio {
  uid: string;
  territorio: string;
  source: string;
  url: string;
  titolo: string | null;
  descrizione: string | null;
  prezzo: number;
  mq: number;
  prezzo_mq: number;
  piano: string | null;
  ascensore: boolean | null;
  bagni: number | null;
  locali: number | null;
  stato: string | null;
  agenzia: string | null;
  privato: boolean | null;
  data_pubblicazione: string | null;
  indirizzo: string | null;
  lat: number | null;
  lon: number | null;
  microzona: string | null;
  fascia: string;
  riferimento_mq: number | null;
  scostamento_pct: number | null;
  scostamento_grezzo_pct: number | null;
  base_confronto: string | null;
  coeff: number | null;
  occasione: boolean;
  giorni_online: number | null;
  ribasso_pct: number | null;
  prezzo_iniziale: number | null;
  first_seen: string | null;
  last_seen: string | null;
  attivo: boolean;
  removed_at: string | null;
  flags: string[];
  doppioni: string[];
  zona_omi: string | null;
  omi_min: number | null;
  omi_max: number | null;
  // aste (migrazione 003): assenti nei dati vecchi
  tipo_vendita?: "compravendita" | "asta" | "possibile_asta" | null;
  indizi_vendita?: string[] | null;
  prezzo_base?: number | null;
  offerta_minima?: number | null;
  data_asta?: string | null;
  scostamento_minima_pct?: number | null;
  valore_mercato?: number | null;
  diritto?: string | null;
  occupazione?: string | null;
}

export interface Mediana {
  territorio: string;
  microzona: string;
  fascia: string;
  n: number;
  mediana_mq: number;
  media_mq: number;
  mediana_zona: number;
  n_zona: number;
}

export interface Frazionabile {
  uid: string;
  n_unita: number;
  mq_unita: number;
  mediana_piccole_mq: number;
  n_campione_piccole: number;
  valore_post: number;
  costo_lavori: number;
  costo_impianti_oneri: number;
  costi_transazione: number;
  costi_totali: number;
  margine: number;
  margine_pct: number;
  indizi: string;
  punteggio_indizi: number;
}

export interface Prezzo {
  uid: string;
  data: string;
  prezzo: number;
}

export type StatoValutazione = "da_vedere" | "interessante" | "visitato" | "in_trattativa" | "scartato";

export interface Valutazione {
  uid: string;
  user_id: string;
  user_email: string | null;
  stato: StatoValutazione | null;
  nota: string | null;
  aggiornato: string;
}

export interface Esecuzione {
  territorio: string;
  ts: string;
  annunci: number;
  occasioni: number;
  frazionabili: number;
  report_xlsx: string | null;
}

export interface Dataset {
  territorio: string;
  zone: Zona[];
  /** solo compravendite: entrano nella valutazione del territorio */
  annunci: Annuncio[];
  /** aste e possibili aste lette dal testo: tenute a parte */
  aste: Annuncio[];
  mediane: Mediana[];
  frazionabili: Frazionabile[];
  ultimaEsecuzione: Esecuzione | null;
  soglia: number;
  fasce: string[];
}
