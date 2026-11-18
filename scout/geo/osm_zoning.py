"""Proposta automatica di microzone da OpenStreetMap.

Il territorio (confine comunale o un poligono a scelta) viene tagliato con:
- strade principali (motorway, trunk, primary, secondary; opzionale tertiary)
- ferrovie
- fiumi e canali
- confini di quartiere (admin_level 9/10, place=suburb/quarter)

Le "facce" risultanti troppo piccole vengono fuse con la vicina con cui
condividono il bordo più lungo. Il risultato è un GeoJSON da rivedere a mano
(es. con `scout editor`, geojson.io o QGIS).
"""
from __future__ import annotations

import logging
import math
import time

import requests
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .microzones import Microzona, MicrozoneSet

log = logging.getLogger(__name__)

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter"]

ROAD_LEVELS = {
    "base": "motorway|trunk|primary",
    "medio": "motorway|trunk|primary|secondary",
    "fine": "motorway|trunk|primary|secondary|tertiary",
}


def overpass(query: str, user_agent: str, tentativi: int = 3) -> dict:
    last = None
    for i in range(tentativi):
        for url in OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": query}, headers={"User-Agent": user_agent},
                                  timeout=180)
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last = str(e)
        time.sleep(15 * (i + 1))
    raise RuntimeError(f"Overpass non raggiungibile: {last}")


def _ways_to_lines(elements) -> list[LineString]:
    lines = []
    for el in elements:
        if el.get("type") == "way" and "geometry" in el:
            coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(coords) >= 2:
                lines.append(LineString(coords))
        elif el.get("type") == "relation":
            for m in el.get("members", []):
                if m.get("type") == "way" and "geometry" in m:
                    coords = [(p["lon"], p["lat"]) for p in m["geometry"] if p]
                    if len(coords) >= 2:
                        lines.append(LineString(coords))
    return lines


def _relation_polygon(el) -> Polygon | None:
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
             for m in el.get("members", [])
             if m.get("type") == "way" and m.get("role") in ("outer", "") and "geometry" in m]
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        return None
    return unary_union(polys)


def fetch_comune_boundary(comune: str, user_agent: str) -> Polygon:
    q = f"""[out:json][timeout:120];
    area["name"="Italia"]["admin_level"="2"]->.it;
    rel(area.it)["boundary"="administrative"]["admin_level"="8"]["name"="{comune}"];
    out geom;"""
    data = overpass(q, user_agent)
    for el in data.get("elements", []):
        poly = _relation_polygon(el)
        if poly is not None:
            return poly
    raise RuntimeError(f"Confine comunale di {comune!r} non trovato su OSM")


def fetch_cut_features(poly: Polygon, user_agent: str, livello: str = "medio") -> dict:
    minx, miny, maxx, maxy = poly.bounds
    bbox = f"{miny},{minx},{maxy},{maxx}"
    roads = ROAD_LEVELS.get(livello, ROAD_LEVELS["medio"])
    q = f"""[out:json][timeout:180];
    (
      way["highway"~"^({roads})$"]({bbox});
      way["railway"="rail"]["service"!~"."]({bbox});
      way["waterway"~"^(river|canal)$"]({bbox});
      rel["waterway"="river"]({bbox});
    );
    out geom;
    (
      rel["boundary"="administrative"]["admin_level"~"^(9|10)$"]({bbox});
      rel["place"~"^(suburb|quarter)$"]({bbox});
      way["place"~"^(suburb|quarter)$"]({bbox});
    );
    out geom;"""
    data = overpass(q, user_agent)
    tagli, quartieri = [], []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if "boundary" in tags or "place" in tags:
            if el["type"] == "relation":
                p = _relation_polygon(el)
            else:
                coords = [(g["lon"], g["lat"]) for g in el.get("geometry", [])]
                p = Polygon(coords) if len(coords) >= 4 else None
            if p is not None and p.is_valid:
                quartieri.append((tags.get("name", ""), p))
        else:
            tagli.extend(_ways_to_lines([el]))
    return {"tagli": tagli, "quartieri": quartieri}


def _m_per_deg(lat: float) -> tuple[float, float]:
    return 111_320 * math.cos(math.radians(lat)), 110_540


def build_zones(territorio: Polygon, tagli: list[LineString], quartieri: list[tuple[str, Polygon]],
                area_min_m2: float = 150_000, prefisso: str = "Auto") -> list[Microzona]:
    """Taglia il territorio con le linee e fonde le facce troppo piccole."""
    kx, ky = _m_per_deg(territorio.centroid.y)
    deg2_to_m2 = kx * ky

    linee = [territorio.boundary]
    linee += [l.intersection(territorio) for l in tagli]
    linee += [p.boundary.intersection(territorio) for _, p in quartieri]
    rete = unary_union([l for l in linee if not l.is_empty])
    facce = [f for f in polygonize(rete) if territorio.contains(f.representative_point())]
    log.info("facce iniziali: %d", len(facce))

    # fusione iterativa delle facce piccole con la vicina di bordo comune più lungo
    facce = sorted(facce, key=lambda f: f.area)
    changed = True
    while changed:
        changed = False
        for i, f in enumerate(facce):
            if f.area * deg2_to_m2 >= area_min_m2 or len(facce) <= 1:
                continue
            best, best_len = None, 0.0
            for j, g in enumerate(facce):
                if i == j:
                    continue
                inter = f.boundary.intersection(g.boundary)
                if inter.length > best_len:
                    best, best_len = j, inter.length
            if best is None:
                continue
            merged = unary_union([f, facce[best]]).buffer(0)
            facce = [h for k, h in enumerate(facce) if k not in (i, best)] + [merged]
            facce.sort(key=lambda x: x.area)
            changed = True
            break

    # scarti: strisce sottili e ritagli rimasti tra le zone esistenti (non sono zone vere:
    # gli annunci lì vengono comunque presi dalla tolleranza di confine)
    spessore = 30 / kx                                   # 30 m in gradi
    prima = len(facce)
    facce = [f for f in facce if f.area * deg2_to_m2 >= area_min_m2 * 0.2 and not f.buffer(-spessore).is_empty]
    if len(facce) < prima:
        log.info("scartati %d ritagli troppo piccoli o sottili", prima - len(facce))

    # nomi: quartiere OSM che contiene il centroide + progressivo
    contatori: dict[str, int] = {}
    zone = []
    for f in sorted(facce, key=lambda p: (-p.centroid.y, p.centroid.x)):
        if f.geom_type == "MultiPolygon":
            f = max(f.geoms, key=lambda g: g.area)
        c = f.representative_point()
        q = [n for n, p in quartieri if n and p.contains(c)]
        base = min(q, key=len) if q else prefisso
        contatori[base] = contatori.get(base, 0) + 1
        nome = f"{base} m{contatori[base]}"
        zone.append(Microzona(nome, f.simplify(0.00003), {"fonte": "osm_auto",
                                                         "area_m2": round(f.area * deg2_to_m2)}))
    return zone


def proponi_microzone(comune: str, user_agent: str, livello: str = "medio",
                      area_min_m2: float = 150_000, territorio: Polygon | None = None,
                      esistenti: MicrozoneSet | None = None) -> MicrozoneSet:
    territorio = territorio or fetch_comune_boundary(comune, user_agent)
    if esistenti and len(esistenti):
        # genera solo dove non ci sono già le tue microzone
        territorio = territorio.difference(unary_union([z.geom for z in esistenti.zone])).buffer(0)
    feats = fetch_cut_features(territorio.envelope, user_agent, livello)
    nuove = build_zones(territorio if territorio.geom_type == "Polygon" else territorio,
                        feats["tagli"], feats["quartieri"], area_min_m2)
    zone = (list(esistenti.zone) if esistenti else []) + nuove
    return MicrozoneSet(zone)


__all__ = ["proponi_microzone", "build_zones", "fetch_comune_boundary", "Point"]
