import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import area from "@turf/area";
import intersect from "@turf/intersect";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { featureCollection, feature } from "@turf/helpers";
import { assegnaZona, salvaZone, versioniZone, type VersioneZone, type ZonaEditabile } from "../lib/data";
import { dataOra, eur, FONTE, num } from "../lib/format";
import { useAuth, useData } from "../lib/store";
import type { Annuncio } from "../lib/types";
import { colore } from "../components/Mappa";
import { Titolo, Vuoto } from "../components/ui";

type Geo = GeoJSON.Polygon | GeoJSON.MultiPolygon;
interface Voce { id: number; nome: string; props?: Record<string, unknown> }
type Scheda = "zone" | "senza" | "versioni";

let prossimoId = 1;

function geometriaDi(layer: L.Polygon): Geo {
  return (layer.toGeoJSON() as GeoJSON.Feature<Geo>).geometry;
}

export default function EditorZone() {
  const { dataset, territorio, ricaricaDataset, manuali, ricaricaManuali } = useData();
  const { utente } = useAuth();
  const divMappa = useRef<HTMLDivElement>(null);
  const mappa = useRef<L.Map | null>(null);
  const strato = useRef<L.FeatureGroup | null>(null);
  const puntini = useRef<L.LayerGroup | null>(null);
  const layers = useRef(new Map<number, L.Polygon>());

  const [voci, setVoci] = useState<Voce[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [modificate, setModificate] = useState(0);          // numero di modifiche non salvate
  const [versioneGeo, setVersioneGeo] = useState(0);        // forza i ricalcoli dopo un'edit
  const [disegno, setDisegno] = useState(false);
  const [scheda, setScheda] = useState<Scheda>("zone");
  const [cerca, setCerca] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [versioni, setVersioni] = useState<VersioneZone[]>([]);
  const [mostraAnnunci, setMostraAnnunci] = useState(true);

  const mediane = useMemo(() => {
    const m: Record<string, number> = {};
    dataset?.mediane.forEach((r) => { m[r.microzona] = r.mediana_zona; });
    return m;
  }, [dataset]);
  const [vmin, vmax] = useMemo(() => {
    const v = Object.values(mediane);
    return [Math.min(...v), Math.max(...v)];
  }, [mediane]);

  // ------------------------------------------------------------ stile e selezione
  const stile = useCallback((nome: string, selezionata: boolean): L.PathOptions => ({
    color: selezionata ? "#1d4ed8" : "#334155",
    weight: selezionata ? 3 : 1.2,
    fillColor: colore(mediane[nome], vmin, vmax),
    fillOpacity: selezionata ? 0.35 : 0.25,
  }), [mediane, vmin, vmax]);

  const segnaModifica = useCallback(() => {
    setModificate((n) => n + 1);
    setVersioneGeo((n) => n + 1);
  }, []);

  const aggancia = useCallback((id: number, layer: L.Polygon) => {
    layer.on("click", () => { if (!disegnoRef.current) setSel(id); });
    layer.on("pm:edit", segnaModifica);
    layer.on("pm:remove", () => {
      layers.current.delete(id);
      setVoci((v) => v.filter((x) => x.id !== id));
      setSel((s) => (s === id ? null : s));
      segnaModifica();
    });
    layers.current.set(id, layer);
  }, [segnaModifica]);
  const disegnoRef = useRef(false);
  useEffect(() => { disegnoRef.current = disegno; }, [disegno]);

  // ------------------------------------------------------------ carica le zone nella mappa
  const caricaZone = useCallback((zone: ZonaEditabile[]) => {
    const g = strato.current;
    if (!g) return;
    g.clearLayers();
    layers.current.clear();
    const nuove: Voce[] = [];
    for (const z of zone) {
      const id = prossimoId++;
      const gj = L.geoJSON(z.geojson as GeoJSON.GeoJsonObject);
      const layer = gj.getLayers()[0] as L.Polygon | undefined;
      if (!layer) continue;
      layer.setStyle(stile(z.nome, false));
      layer.bindTooltip(z.nome, { sticky: true });
      layer.addTo(g);
      aggancia(id, layer);
      nuove.push({ id, nome: z.nome, props: z.props });
    }
    setVoci(nuove);
    setSel(null);
    setModificate(0);
    setVersioneGeo((n) => n + 1);
    if (g.getLayers().length) mappa.current?.fitBounds(g.getBounds(), { padding: [20, 20] });
  }, [aggancia, stile]);

  // ------------------------------------------------------------ init mappa + geoman
  useEffect(() => {
    if (!divMappa.current || mappa.current) return;
    const m = L.map(divMappa.current, { zoomControl: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(m);
    strato.current = L.featureGroup().addTo(m);
    puntini.current = L.layerGroup().addTo(m);
    m.setView([45.4384, 10.9916], 13);
    m.pm.setLang("it");
    m.pm.setGlobalOptions({ snappable: true, snapDistance: 18, allowSelfIntersection: false, layerGroup: strato.current });
    m.on("pm:create", (e: { layer: L.Layer }) => {
      const layer = e.layer as L.Polygon;
      const id = prossimoId++;
      setVoci((v) => {
        const usati = new Set(v.map((x) => x.nome));
        let k = v.length + 1;
        while (usati.has(`Nuova zona ${k}`)) k++;
        const nome = `Nuova zona ${k}`;
        layer.bindTooltip(nome, { sticky: true });
        return [...v, { id, nome, props: { fonte: "editor" } }];
      });
      aggancia(id, layer);
      setSel(id);
      setDisegno(false);
      segnaModifica();
    });
    mappa.current = m;
    return () => { m.remove(); mappa.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (dataset && mappa.current) caricaZone(dataset.zone);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  // stile al cambio selezione + editing solo della zona selezionata
  useEffect(() => {
    for (const v of voci) {
      const l = layers.current.get(v.id);
      if (!l) continue;
      const s = v.id === sel;
      l.setStyle(stile(v.nome, s));
      l.setTooltipContent(v.nome);
      if (s) { l.pm.enable({ snappable: true, allowSelfIntersection: false }); l.bringToFront(); }
      else if (l.pm.enabled()) l.pm.disable();
    }
  }, [sel, voci, stile]);

  // puntini degli annunci
  useEffect(() => {
    const g = puntini.current;
    if (!g || !dataset) return;
    g.clearLayers();
    if (!mostraAnnunci) return;
    for (const a of dataset.annunci) {
      if (!a.attivo || a.lat == null || a.lon == null) continue;
      L.circleMarker([a.lat, a.lon], {
        radius: 3, color: a.microzona ? "#475569" : "#dc2626", weight: 1, fillOpacity: 0.8, interactive: false,
      }).addTo(g);
    }
  }, [dataset, mostraAnnunci]);

  // ------------------------------------------------------------ analisi geometrie
  const info = useMemo(() => {
    const out = new Map<number, { km2: number; annunci: number }>();
    const punti = (dataset?.annunci ?? []).filter((a) => a.attivo && a.lat != null && a.lon != null);
    for (const v of voci) {
      const l = layers.current.get(v.id);
      if (!l) continue;
      const g = geometriaDi(l);
      const f = feature(g);
      out.set(v.id, {
        km2: area(f) / 1e6,
        annunci: v.id === sel ? punti.filter((a) => booleanPointInPolygon([a.lon!, a.lat!], f)).length : -1,
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voci, sel, versioneGeo, dataset]);

  const sovrapposizioni = useMemo(() => {
    const res: { a: string; b: string; pct: number }[] = [];
    const geo = voci.map((v) => ({ v, l: layers.current.get(v.id) })).filter((x) => x.l)
      .map(({ v, l }) => ({ v, f: feature(geometriaDi(l!)), b: l!.getBounds() }));
    for (let i = 0; i < geo.length; i++) {
      for (let j = i + 1; j < geo.length; j++) {
        if (!geo[i].b.intersects(geo[j].b)) continue;
        try {
          const x = intersect(featureCollection([geo[i].f, geo[j].f]) as GeoJSON.FeatureCollection<Geo>);
          if (!x) continue;
          const pct = (100 * area(x)) / Math.min(area(geo[i].f), area(geo[j].f));
          if (pct >= 2) res.push({ a: geo[i].v.nome, b: geo[j].v.nome, pct });
        } catch { /* geometria non valida durante l'edit */ }
      }
    }
    return res.sort((x, y) => y.pct - x.pct);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voci, versioneGeo]);

  // ------------------------------------------------------------ azioni
  const rinomina = (id: number, nome: string) => {
    setVoci((v) => v.map((x) => (x.id === id ? { ...x, nome } : x)));
    setModificate((n) => n + 1);
  };
  const elimina = (id: number) => {
    const v = voci.find((x) => x.id === id);
    if (!v || !window.confirm(`Eliminare la microzona "${v.nome}"?`)) return;
    const l = layers.current.get(id);
    if (l) strato.current?.removeLayer(l);
    layers.current.delete(id);
    setVoci((x) => x.filter((z) => z.id !== id));
    setSel(null);
    segnaModifica();
  };
  const disegna = () => {
    const m = mappa.current!;
    if (disegno) { m.pm.disableDraw(); setDisegno(false); return; }
    setSel(null);
    m.pm.enableDraw("Polygon", { snappable: true, snapDistance: 18, allowSelfIntersection: false, finishOn: "dblclick" } as L.PM.DrawModeOptions);
    setDisegno(true);
  };
  const centra = (id: number) => {
    const l = layers.current.get(id);
    if (l) mappa.current?.fitBounds(l.getBounds(), { padding: [40, 40], maxZoom: 16 });
    setSel(id);
  };
  const zoneCorrenti = (): ZonaEditabile[] => voci.map((v, i) => ({
    nome: v.nome, geojson: geometriaDi(layers.current.get(v.id)!), props: v.props, ordine: i,
  }));

  const nomiDuplicati = useMemo(() => {
    const c = new Map<string, number>();
    voci.forEach((v) => c.set(v.nome.trim().toLowerCase(), (c.get(v.nome.trim().toLowerCase()) ?? 0) + 1));
    return new Set([...c].filter(([, n]) => n > 1).map(([k]) => k));
  }, [voci]);
  const nomeVuoto = voci.some((v) => !v.nome.trim());

  const salva = async () => {
    if (!territorio || !utente) return;
    if (nomiDuplicati.size || nomeVuoto) { setMsg({ ok: false, t: "Ci sono nomi vuoti o duplicati: correggili prima di salvare." }); return; }
    const nota = window.prompt("Nota per lo storico (facoltativa), es. 'allargata Borgo Roma m1':", "") ?? null;
    if (nota === null) return;
    setSalvando(true); setMsg(null);
    try {
      const n = await salvaZone(territorio, zoneCorrenti(), nota, utente.email);
      setMsg({ ok: true, t: `Salvate ${n} microzone. Gli annunci verranno riassegnati alla prossima esecuzione del bot.` });
      await ricaricaDataset();
      if (scheda === "versioni") setVersioni(await versioniZone(territorio));
    } catch (e) {
      setMsg({ ok: false, t: `Salvataggio non riuscito: ${(e as Error).message}` });
    } finally {
      setSalvando(false);
    }
  };
  const annulla = () => {
    if (dataset && window.confirm("Annullare tutte le modifiche non salvate?")) caricaZone(dataset.zone);
  };
  const esporta = () => {
    const fc = { type: "FeatureCollection", features: zoneCorrenti().map((z) => ({ type: "Feature", properties: { ...z.props, nome: z.nome }, geometry: z.geojson })) };
    const url = URL.createObjectURL(new Blob([JSON.stringify(fc)], { type: "application/geo+json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `microzone_${territorio}.geojson`; a.click();
    URL.revokeObjectURL(url);
  };
  const importa = async (file: File) => {
    try {
      const fc = JSON.parse(await file.text()) as GeoJSON.FeatureCollection<Geo>;
      const zone = fc.features.filter((f) => f.geometry && /Polygon/.test(f.geometry.type))
        .map((f, i) => ({ nome: String(f.properties?.nome ?? f.properties?.name ?? `Zona importata ${i + 1}`), geojson: f.geometry, props: f.properties ?? {} }));
      if (!zone.length) throw new Error("nessun poligono nel file");
      caricaZone(zone);
      setModificate(1);
      setMsg({ ok: true, t: `Importate ${zone.length} zone dal file: controlla e premi Salva.` });
    } catch (e) {
      setMsg({ ok: false, t: `File non valido: ${(e as Error).message}` });
    }
  };

  useEffect(() => {
    if (scheda === "versioni" && territorio) versioniZone(territorio).then(setVersioni).catch(() => setVersioni([]));
  }, [scheda, territorio]);

  // avviso se si lascia la pagina con modifiche non salvate
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (modificate) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [modificate]);

  if (!dataset) return null;
  const selVoce = voci.find((v) => v.id === sel);
  const selInfo = sel != null ? info.get(sel) : undefined;
  const filtrate = voci.filter((v) => v.nome.toLowerCase().includes(cerca.toLowerCase()));
  const senzaZona = dataset.annunci.filter((a) => a.attivo && !a.microzona);

  return (
    <>
      <Titolo sotto="Clic su una zona per modificarne i vertici (trascina i punti, clic sul punto a metà lato per aggiungerne). I bordi si agganciano alle zone vicine."
        azioni={
          <div className="flex flex-wrap gap-2">
            <button className={disegno ? "btn bg-amber-100 text-amber-900" : "btn-ghost border border-slate-200 bg-white"} onClick={disegna}>
              {disegno ? "Annulla disegno" : "+ Nuova zona"}
            </button>
            <button className="btn-ghost border border-slate-200 bg-white" onClick={annulla} disabled={!modificate}>Annulla modifiche</button>
            <button className="btn-primary" onClick={salva} disabled={!modificate || salvando}>
              {salvando ? "Salvataggio…" : modificate ? `Salva modifiche (${modificate})` : "Nessuna modifica"}
            </button>
          </div>
        }>
        Editor microzone
      </Titolo>
      {disegno && (
        <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Clicca sulla mappa per aggiungere i vertici della nuova zona; <b>doppio clic</b> (o clic sul primo punto) per chiudere il poligono.
        </div>
      )}
      {msg && <div className={`mb-3 rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-700"}`}>{msg.t}</div>}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="relative">
          <div ref={divMappa} className="h-[60vh] w-full overflow-hidden rounded-xl border border-slate-200 lg:h-[calc(100vh-230px)]" />
          <label className="absolute bottom-3 left-3 z-[500] inline-flex items-center gap-2 rounded-lg bg-white/95 px-2.5 py-1.5 text-xs shadow">
            <input type="checkbox" checked={mostraAnnunci} onChange={(e) => setMostraAnnunci(e.target.checked)} />
            Annunci (<span className="text-rose-600">rossi</span> = senza zona)
          </label>
        </div>

        <div className="card flex max-h-[calc(100vh-230px)] min-h-[300px] flex-col overflow-hidden">
          <div className="grid grid-cols-3 border-b border-slate-200 text-sm">
            {([["zone", `Zone (${voci.length})`], ["senza", `Senza zona (${senzaZona.length})`], ["versioni", "Storico"]] as [Scheda, string][]).map(([k, t]) => (
              <button key={k} onClick={() => setScheda(k)}
                className={`px-2 py-2.5 font-medium ${scheda === k ? "border-b-2 border-brand-600 text-brand-700" : "text-slate-500 hover:text-slate-800"}`}>{t}</button>
            ))}
          </div>

          {scheda === "zone" && (
            <>
              {selVoce && (
                <div className="space-y-2 border-b border-slate-200 bg-brand-50/50 p-3">
                  <label className="label">Nome della zona selezionata</label>
                  <input className={`input ${nomiDuplicati.has(selVoce.nome.trim().toLowerCase()) || !selVoce.nome.trim() ? "border-rose-400" : ""}`}
                    value={selVoce.nome} onChange={(e) => rinomina(selVoce.id, e.target.value)} />
                  <div className="flex flex-wrap gap-x-4 text-xs text-slate-600">
                    <span>{selInfo ? `${selInfo.km2.toFixed(2).replace(".", ",")} km²` : ""}</span>
                    {selInfo && selInfo.annunci >= 0 && <span>{selInfo.annunci} annunci con coordinate dentro</span>}
                    {mediane[selVoce.nome] != null && <span>mediana {num(mediane[selVoce.nome])} €/mq</span>}
                  </div>
                  <div className="flex gap-2">
                    <button className="btn-ghost border border-slate-200 bg-white text-xs" onClick={() => centra(selVoce.id)}>Centra</button>
                    <button className="btn-ghost border border-rose-200 bg-white text-xs text-rose-700" onClick={() => elimina(selVoce.id)}>Elimina zona</button>
                    <button className="btn-ghost ml-auto text-xs" onClick={() => setSel(null)}>Chiudi</button>
                  </div>
                </div>
              )}
              <div className="p-2"><input className="input" placeholder="Cerca zona…" value={cerca} onChange={(e) => setCerca(e.target.value)} /></div>
              <ul className="flex-1 divide-y divide-slate-100 overflow-y-auto text-sm">
                {filtrate.map((v) => (
                  <li key={v.id}>
                    <button onClick={() => centra(v.id)} className={`flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 ${v.id === sel ? "bg-brand-50" : ""}`}>
                      <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-300" style={{ background: colore(mediane[v.nome], vmin, vmax) }} />
                      <span className="flex-1 truncate">{v.nome}</span>
                      <span className="text-xs tabular-nums text-slate-400">{info.get(v.id)?.km2.toFixed(2).replace(".", ",")} km²</span>
                    </button>
                  </li>
                ))}
              </ul>
              {sovrapposizioni.length > 0 && (
                <div className="max-h-32 overflow-y-auto border-t border-slate-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <b>Zone sovrapposte</b> (un annuncio nella parte comune va alla zona più piccola):
                  <ul className="mt-1 space-y-0.5">{sovrapposizioni.slice(0, 8).map((o) => <li key={o.a + o.b}>{o.a} / {o.b}: {o.pct.toFixed(0)}%</li>)}</ul>
                </div>
              )}
              <div className="flex gap-2 border-t border-slate-200 p-2">
                <button className="btn-ghost flex-1 text-xs" onClick={esporta}>Scarica GeoJSON</button>
                <label className="btn-ghost flex-1 cursor-pointer text-xs">
                  Carica GeoJSON
                  <input type="file" accept=".geojson,.json,application/geo+json" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) importa(f); e.target.value = ""; }} />
                </label>
              </div>
            </>
          )}

          {scheda === "senza" && (
            <SenzaZona annunci={senzaZona} zone={voci.map((v) => v.nome)} manuali={manuali}
              onAssegna={async (uid, z) => {
                if (!territorio) return;
                try { await assegnaZona(territorio, uid, z); ricaricaManuali(); }
                catch (e) { setMsg({ ok: false, t: `Assegnazione non salvata: ${(e as Error).message}` }); }
              }}
              onMostra={(a) => { if (a.lat != null && a.lon != null) mappa.current?.setView([a.lat, a.lon], 17); }} />
          )}

          {scheda === "versioni" && (
            <ul className="flex-1 divide-y divide-slate-100 overflow-y-auto text-sm">
              {!versioni.length && <li className="p-4 text-slate-500">Nessun salvataggio dall'editor finora.</li>}
              {versioni.map((v) => (
                <li key={v.id} className="flex items-start gap-2 p-3">
                  <div className="flex-1">
                    <div className="font-medium">{dataOra(v.ts)} · {v.zone.length} zone</div>
                    <div className="text-xs text-slate-500">{v.salvato_da ?? "–"}{v.nota ? ` — ${v.nota}` : ""}</div>
                  </div>
                  <button className="btn-ghost border border-slate-200 text-xs" onClick={() => {
                    if (window.confirm("Caricare questa versione nell'editor? Poi premi Salva per renderla definitiva.")) {
                      caricaZone(v.zone); setModificate(1); setScheda("zone");
                    }
                  }}>Ripristina</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

function SenzaZona({ annunci, zone, manuali, onAssegna, onMostra }: {
  annunci: Annuncio[]; zone: string[]; manuali: Record<string, string>;
  onAssegna: (uid: string, z: string | null) => void; onMostra: (a: Annuncio) => void;
}) {
  const ordinate = useMemo(() => [...zone].sort((a, b) => a.localeCompare(b, "it", { numeric: true })), [zone]);
  if (!annunci.length) return <div className="p-4"><Vuoto>Tutti gli annunci attivi hanno una microzona.</Vuoto></div>;
  return (
    <div className="flex-1 overflow-y-auto">
      <p className="p-3 text-xs text-slate-500">
        Annunci attivi che non cadono in nessuna microzona (spesso senza indirizzo). Assegnali a mano: la scelta vale finché non la cambi e il bot la applica alla prossima esecuzione.
      </p>
      <ul className="divide-y divide-slate-100">
        {annunci.map((a) => (
          <li key={a.uid} className="space-y-1.5 px-3 py-2 text-sm">
            <div className="flex items-start gap-2">
              <button className="min-w-0 flex-1 text-left" onClick={() => onMostra(a)} title={a.lat != null ? "Mostra sulla mappa" : "Senza coordinate"}>
                <div className="truncate font-medium">{a.indirizzo || a.titolo}</div>
                <div className="text-xs text-slate-500">{num(a.mq)} mq · {eur(a.prezzo)} · {FONTE[a.source] ?? a.source}{a.lat == null ? " · senza posizione" : ""}</div>
              </button>
              <a href={a.url} target="_blank" rel="noreferrer" className="text-xs text-brand-600 hover:underline">annuncio</a>
            </div>
            <select className="input py-1 text-xs" value={manuali[a.uid] ?? ""} onChange={(e) => onAssegna(a.uid, e.target.value || null)}>
              <option value="">— assegna una microzona —</option>
              {ordinate.map((z) => <option key={z}>{z}</option>)}
            </select>
          </li>
        ))}
      </ul>
    </div>
  );
}
