import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { eur, num, pct } from "../lib/format";
import type { Annuncio, Zona } from "../lib/types";

export interface MappaProps {
  zone: Zona[];
  valoreZona: Record<string, number | undefined>;   // es. mediana €/mq
  annunci?: Annuncio[];
  evidenziati?: Set<string>;                         // uid in evidenza (occasioni)
  zonaSelezionata?: string | null;
  onZona?: (nome: string) => void;
  altezza?: string;
}

const SCALA = ["#2c7bb6", "#7fbcd9", "#d4ecc8", "#fee08b", "#fdae61", "#d7191c"];

export function colore(v: number | undefined, min: number, max: number) {
  if (v == null || isNaN(v)) return "#cbd5e1";
  const t = max > min ? (v - min) / (max - min) : 0.5;
  return SCALA[Math.min(SCALA.length - 1, Math.max(0, Math.floor(t * SCALA.length)))];
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export default function Mappa({ zone, valoreZona, annunci = [], evidenziati, zonaSelezionata, onZona, altezza = "70vh" }: MappaProps) {
  const div = useRef<HTMLDivElement>(null);
  const mappa = useRef<L.Map | null>(null);
  const livelli = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!div.current || mappa.current) return;
    mappa.current = L.map(div.current, { zoomControl: true, scrollWheelZoom: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap",
    }).addTo(mappa.current);
    livelli.current = L.layerGroup().addTo(mappa.current);
    return () => { mappa.current?.remove(); mappa.current = null; };
  }, []);

  useEffect(() => {
    const m = mappa.current, g = livelli.current;
    if (!m || !g) return;
    g.clearLayers();
    const valori = Object.values(valoreZona).filter((v): v is number => v != null && !isNaN(v));
    const min = Math.min(...valori), max = Math.max(...valori);
    const bounds = L.latLngBounds([]);
    for (const z of zone) {
      const v = valoreZona[z.nome];
      const sel = zonaSelezionata === z.nome;
      const layer = L.geoJSON(z.geojson as GeoJSON.GeoJsonObject, {
        style: {
          color: sel ? "#1e3a8a" : "#334155", weight: sel ? 3 : 1, fillColor: colore(v, min, max),
          fillOpacity: sel ? 0.6 : 0.42,
        },
      });
      layer.bindTooltip(`<b>${esc(z.nome)}</b><br>${v != null ? num(v) + " €/mq" : "n.d."}`, { sticky: true });
      if (onZona) layer.on("click", () => onZona(z.nome));
      layer.addTo(g);
      bounds.extend(layer.getBounds());
    }
    for (const a of annunci) {
      if (a.lat == null || a.lon == null) continue;
      const ev = evidenziati?.has(a.uid);
      const mk = L.circleMarker([a.lat, a.lon], {
        radius: ev ? 7 : 4, color: ev ? "#be123c" : "#475569", weight: ev ? 2 : 1,
        fillColor: ev ? "#f43f5e" : "#94a3b8", fillOpacity: ev ? 0.9 : 0.7,
      });
      mk.bindPopup(
        `<div style="min-width:180px"><b>${esc(a.indirizzo || a.titolo || "")}</b><br>` +
        `${num(a.mq)} mq · ${eur(a.prezzo)}<br>${num(a.prezzo_mq)} €/mq · <b>${pct(a.scostamento_pct)}</b><br>` +
        `<a href="#/annuncio/${encodeURIComponent(a.uid)}">Apri scheda →</a></div>`,
      );
      mk.addTo(g);
      if (ev) mk.bringToFront();
    }
    if (bounds.isValid()) {
      const z = zonaSelezionata && zone.find((x) => x.nome === zonaSelezionata);
      m.fitBounds(z ? L.geoJSON(z.geojson as GeoJSON.GeoJsonObject).getBounds() : bounds, { padding: [20, 20] });
    } else {
      m.setView([45.4384, 10.9916], 13);
    }
  }, [zone, valoreZona, annunci, evidenziati, zonaSelezionata, onZona]);

  return <div ref={div} style={{ height: altezza }} className="w-full overflow-hidden rounded-xl border border-slate-200" />;
}

export function LegendaScala({ min, max }: { min: number; max: number }) {
  if (!isFinite(min) || !isFinite(max)) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span className="tabular-nums">{num(min)} €/mq</span>
      <div className="flex h-2.5 overflow-hidden rounded">
        {SCALA.map((c) => <span key={c} className="w-6" style={{ background: c }} />)}
      </div>
      <span className="tabular-nums">{num(max)} €/mq</span>
    </div>
  );
}
