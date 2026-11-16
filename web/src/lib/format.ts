const eur0 = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const num0 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });

export const eur = (v: number | null | undefined) => (v == null ? "–" : eur0.format(v));
export const num = (v: number | null | undefined) => (v == null ? "–" : num0.format(v));
export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(digits).replace(".", ",")}%`;
export const data = (v: string | null | undefined) => {
  if (!v) return "–";
  const d = new Date(v.length <= 10 ? v + "T00:00:00" : v);
  return isNaN(d.getTime()) ? v : d.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
};
export const dataOra = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";

export const PIANO: Record<string, string> = { T: "Terra", R: "Rialzato", S: "Seminterrato", A: "Attico" };
export const piano = (p: string | null) => (p == null ? "–" : PIANO[p] ?? `${p}°`);

export const STATO: Record<string, string> = {
  nuovo: "Nuovo",
  ottimo: "Ottimo / ristrutturato",
  buono: "Buono / abitabile",
  da_ristrutturare: "Da ristrutturare",
};

export const FONTE: Record<string, string> = {
  immobiliare: "Immobiliare.it",
  subito: "Subito.it",
  idealista: "Idealista",
  casa: "Casa.it",
  facebook: "Facebook",
  excel: "Storico Excel",
};

/** Stessa legenda colori dei fogli Excel. */
export function coloreScostamento(v: number | null | undefined) {
  if (v == null) return "bg-slate-100 text-slate-500";
  if (v > 0) return "bg-yellow-200 text-yellow-900";
  if (v > -10) return "bg-lime-100 text-lime-900";
  if (v > -20) return "bg-green-500 text-white";
  return "bg-sky-500 text-white";
}
