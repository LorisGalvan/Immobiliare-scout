import { DEMO, supabase } from "./supabase";
import type { Annuncio, Dataset, Esecuzione, Frazionabile, Mediana, Prezzo, Valutazione, Zona } from "./types";

// ---------------------------------------------------------------- DEMO
interface DemoFile {
  territorio: string;
  generato: string;
  soglia_occasione_pct: number;
  fasce: string[];
  zone: Zona[];
  annunci: Annuncio[];
  prezzi: Prezzo[];
  mediane: Mediana[];
  frazionabili: Frazionabile[];
}
let demoCache: Promise<DemoFile> | null = null;
const demo = (): Promise<DemoFile> => (demoCache ??= fetch("./demo.json").then((r) => r.json() as Promise<DemoFile>));

// ---------------------------------------------------------------- Supabase
async function tutte<T>(table: string, filtro: (q: any) => any, cols = "*"): Promise<T[]> {
  const out: T[] = [];
  const passo = 1000;
  for (let da = 0; ; da += passo) {
    const { data, error } = await filtro(supabase!.from(table).select(cols)).range(da, da + passo - 1);
    if (error) throw error;
    out.push(...(data as T[]));
    if (!data || data.length < passo) break;
  }
  return out;
}

export async function territori(): Promise<string[]> {
  if (DEMO) return [(await demo()).territorio];
  const rows = await tutte<{ territorio: string }>("zone", (q) => q, "territorio");
  return [...new Set(rows.map((r) => r.territorio))].sort();
}

export async function caricaDataset(territorio: string): Promise<Dataset> {
  if (DEMO) {
    const d = await demo();
    const salvate = zoneDemoSalvate();
    return {
      territorio: d.territorio,
      zone: salvate ? salvate.map((z) => ({ ...z, territorio: d.territorio })) : d.zone,
      annunci: d.annunci,
      mediane: d.mediane,
      frazionabili: d.frazionabili,
      soglia: d.soglia_occasione_pct,
      fasce: d.fasce,
      ultimaEsecuzione: {
        territorio: d.territorio, ts: d.generato, annunci: d.annunci.length,
        occasioni: d.annunci.filter((a) => a.occasione).length, frazionabili: d.frazionabili.length, report_xlsx: null,
      },
    };
  }
  const eq = (q: any) => q.eq("territorio", territorio);
  const [zone, annunci, mediane, frazionabili, esec] = await Promise.all([
    tutte<Zona>("zone", (q) => eq(q).order("ordine")),
    tutte<Annuncio>("annunci", eq),
    tutte<Mediana>("mediane", eq),
    tutte<Frazionabile>("frazionabili", eq),
    supabase!.from("esecuzioni").select("*").eq("territorio", territorio).order("ts", { ascending: false }).limit(1),
  ]);
  const ult = (esec.data?.[0] as Esecuzione) ?? null;
  return {
    territorio, zone, annunci, mediane, frazionabili, ultimaEsecuzione: ult,
    soglia: -15, fasce: ["30/50", "50/70", "70/100", "100+"],
  };
}

export async function prezzi(uid: string): Promise<Prezzo[]> {
  if (DEMO) return (await demo()).prezzi.filter((p) => p.uid === uid).sort((a, b) => a.data.localeCompare(b.data));
  const { data, error } = await supabase!.from("prezzi").select("*").eq("uid", uid).order("data");
  if (error) throw error;
  return data as Prezzo[];
}

export async function urlReport(path: string): Promise<string | null> {
  if (DEMO || !path) return null;
  const { data } = await supabase!.storage.from("report").createSignedUrl(path, 3600);
  return data?.signedUrl ?? null;
}

// ---------------------------------------------------------------- Valutazioni (lavoro di squadra)
const LS = "scout-valutazioni-demo";
const leggiLS = (): Valutazione[] => {
  try { return JSON.parse(localStorage.getItem(LS) || "[]"); } catch { return []; }
};

export async function valutazioni(uid?: string): Promise<Valutazione[]> {
  if (DEMO) return leggiLS().filter((v) => !uid || v.uid === uid);
  let q = supabase!.from("valutazioni").select("*");
  if (uid) q = q.eq("uid", uid);
  const { data, error } = await q;
  if (error) throw error;
  return data as Valutazione[];
}

export async function salvaValutazione(v: Pick<Valutazione, "uid" | "stato" | "nota">, userId: string, email: string) {
  const rec: Valutazione = { ...v, user_id: userId, user_email: email, aggiornato: new Date().toISOString() };
  if (DEMO) {
    const all = leggiLS().filter((x) => !(x.uid === v.uid && x.user_id === userId));
    try { localStorage.setItem(LS, JSON.stringify([...all, rec])); } catch { /* storage non disponibile */ }
    return;
  }
  const { error } = await supabase!.from("valutazioni").upsert(
    { uid: v.uid, user_id: userId, stato: v.stato, nota: v.nota, aggiornato: rec.aggiornato },
    { onConflict: "uid,user_id" },
  );
  if (error) throw error;
}

// ---------------------------------------------------------------- Editor microzone
export interface ZonaEditabile { nome: string; geojson: Zona["geojson"]; props?: Record<string, unknown>; ordine?: number }
export interface VersioneZone { id: number; ts: string; salvato_da: string | null; nota: string | null; zone: ZonaEditabile[] }

const LS_ZONE = "scout-zone-demo";
const LS_VERS = "scout-zone-versioni-demo";
const LS_MAN = "scout-zona-manuale-demo";
const leggi = <T,>(k: string, def: T): T => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? def; } catch { return def; } };
const scrivi = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignora */ } };

/** Zone salvate in demo (solo in questo browser), se l'utente le ha modificate. */
export const zoneDemoSalvate = (): ZonaEditabile[] | null => (DEMO ? leggi<ZonaEditabile[] | null>(LS_ZONE, null) : null);

export async function salvaZone(territorio: string, zone: ZonaEditabile[], nota: string, email: string): Promise<number> {
  const pulite = zone.map((z, i) => ({ nome: z.nome.trim(), geojson: z.geojson, props: z.props ?? {}, ordine: i }));
  if (DEMO) {
    scrivi(LS_ZONE, pulite);
    const v = leggi<VersioneZone[]>(LS_VERS, []);
    scrivi(LS_VERS, [{ id: Date.now(), ts: new Date().toISOString(), salvato_da: email, nota, zone: pulite }, ...v].slice(0, 20));
    return pulite.length;
  }
  const { data, error } = await supabase!.rpc("salva_zone", { p_territorio: territorio, p_zone: pulite, p_nota: nota || null });
  if (error) throw error;
  return data as number;
}

export async function versioniZone(territorio: string): Promise<VersioneZone[]> {
  if (DEMO) return leggi<VersioneZone[]>(LS_VERS, []);
  const { data, error } = await supabase!.from("zone_versioni").select("*").eq("territorio", territorio)
    .order("ts", { ascending: false }).limit(20);
  if (error) throw error;
  return data as VersioneZone[];
}

export async function zoneManuali(territorio: string): Promise<Record<string, string>> {
  if (DEMO) return leggi<Record<string, string>>(LS_MAN, {});
  const { data, error } = await supabase!.from("zona_manuale").select("uid,microzona").eq("territorio", territorio);
  if (error) return {};          // migrazione non ancora eseguita
  return Object.fromEntries((data ?? []).map((r: { uid: string; microzona: string }) => [r.uid, r.microzona]));
}

export async function assegnaZona(territorio: string, uid: string, microzona: string | null) {
  if (DEMO) {
    const m = leggi<Record<string, string>>(LS_MAN, {});
    if (microzona) m[uid] = microzona; else delete m[uid];
    scrivi(LS_MAN, m);
    return;
  }
  const r = microzona
    ? await supabase!.from("zona_manuale").upsert({ uid, territorio, microzona, aggiornato: new Date().toISOString() })
    : await supabase!.from("zona_manuale").delete().eq("uid", uid);
  if (r.error) throw r.error;
}
