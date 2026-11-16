import type { Zona } from "./types";

/** Anello esterno in [lat, lon] dal GeoJSON (lon, lat). */
export function anello(z: Zona): [number, number][] {
  const g = z.geojson;
  const ring = g.type === "Polygon" ? g.coordinates[0] : g.coordinates[0][0];
  return ring.map(([lon, lat]) => [lat, lon]);
}

function encodePolyline(pts: [number, number][]) {
  let out = "", plat = 0, plng = 0;
  for (const [lat, lng] of pts) {
    const ilat = Math.round(lat * 1e5), ilng = Math.round(lng * 1e5);
    for (const d of [ilat - plat, ilng - plng]) {
      let v = d < 0 ? ~(d << 1) : d << 1;
      while (v >= 0x20) { out += String.fromCharCode((0x20 | (v & 0x1f)) + 63); v >>= 5; }
      out += String.fromCharCode(v + 63);
    }
    plat = ilat; plng = ilng;
  }
  return out;
}

/** Link di ricerca a poligono (come nelle righe 1-3 dei tuoi Excel). */
export function linkRicerca(z: Zona, slugImmobiliare = "verona") {
  const pts = anello(z);
  const vrt = pts.map(([a, b]) => `${a.toFixed(6)},${b.toFixed(6)}`).join(";");
  const chiuso = pts[0][0] === pts.at(-1)![0] && pts[0][1] === pts.at(-1)![1] ? pts : [...pts, pts[0]];
  return {
    immobiliare: `https://www.immobiliare.it/vendita-case/${slugImmobiliare}/?criterio=superficie&ordine=asc&vrt=${vrt}`,
    idealista: `https://www.idealista.it/aree/vendita-case/?ordine=area-asc&shape=${encodeURIComponent(`((${encodePolyline(chiuso)}))`)}`,
  };
}

export function slug(territorio: string) {
  return territorio.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-");
}
