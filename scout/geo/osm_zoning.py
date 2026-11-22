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

import hashlib
import json
import logging
import math
import time
from pathlib import Path

import requests
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .microzones import Microzona, MicrozoneSet

log = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# Overpass rifiuta (HTTP 406/429) gli User-Agent da browser finto o generici: serve un nome chiaro del programma
UA_OVERPASS = "ScoutImmobili/1.0 (bot personale di analisi immobiliare; microzone da OSM)"

ROAD_LEVELS = {
    "base": "motorway|trunk|primary",
    "medio": "motorway|trunk|primary|secondary",
    "fine": "motorway|trunk|primary|secondary|tertiary",
}


def overpass(query: str, user_agent: str | None = None, tentativi: int = 2) -> dict:
    """Interroga Overpass provando più server. ``user_agent`` è ignorato di proposito: quello da browser
    usato per i portali viene rifiutato da Overpass."""
    # risposte già scaricate: un nuovo tentativo non richiede di nuovo gli stessi dati
    cache = Path("data/cache/osm") / (hashlib.sha1(query.encode()).hexdigest()[:16] + ".json")
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    last = None
    headers = {"User-Agent": UA_OVERPASS, "Accept": "application/json,*/*;q=0.8"}
    for i in range(tentativi):
        for url in OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": query}, headers=headers, timeout=150)
                if r.status_code == 200:
                    try:
                        dati = r.json()
                    except ValueError:
                        last = f"{url}: risposta non JSON"
                        continue
                    if dati.get("remark") and not dati.get("elements"):
                        last = f"{url}: {dati['remark'][:200]}"      # es. timeout lato server
                        log.warning("Overpass %s", last)
                        continue
                    try:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.write_text(json.dumps(dati), encoding="utf-8")
                    except OSError:
                        pass
                    return dati
                last = f"{url}: HTTP {r.status_code}"
                log.warning("Overpass %s", last)
            except requests.RequestException as e:
                last = f"{url}: {e}"
                log.warning("Overpass %s", last)
        if i < tentativi - 1:
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"Overpass non raggiungibile (ultimo errore {last})")


def _tratti(geometria) -> list[LineString]:
    """Con ``out geom(bbox)`` Overpass mette null al posto dei punti fuori dal riquadro:
    la linea si spezza lì invece di unire punti lontani (o andare in errore)."""
    out, tratto = [], []
    for p in (geometria or []) + [None]:
        if p and p.get("lon") is not None and p.get("lat") is not None:
            tratto.append((p["lon"], p["lat"]))
            continue
        if len(tratto) >= 2:
            out.append(LineString(tratto))
        tratto = []
    return out


def _ways_to_lines(elements) -> list[LineString]:
    lines = []
    for el in elements:
        if el.get("type") == "way" and "geometry" in el:
            lines.extend(_tratti(el["geometry"]))
        elif el.get("type") == "relation":
            for m in el.get("members", []):
                if m.get("type") == "way" and "geometry" in m:
                    lines.extend(_tratti(m["geometry"]))
    return lines


def _relation_polygon(el) -> Polygon | None:
    lines = [t for m in el.get("members", [])
             if m.get("type") == "way" and m.get("role") in ("outer", "") and "geometry" in m
             for t in _tratti(m["geometry"])]
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        return None
    return unary_union(polys)


def fetch_comune_boundary(comune: str, user_agent: str | None = None,
                          bbox: tuple[float, float, float, float] | None = None) -> Polygon:
    """Confine comunale. Con ``bbox`` (minx, miny, maxx, maxy) la ricerca è limitata a quel riquadro:
    molto più leggera che cercare in tutta Italia, che manda in errore 502/504 i server Overpass."""
    if bbox:
        minx, miny, maxx, maxy = bbox
        q = f"""[out:json][timeout:90][bbox:{miny},{minx},{maxy},{maxx}];
    rel["boundary"="administrative"]["admin_level"="8"]["name"="{comune}"];
    out geom;"""
    else:
        q = f"""[out:json][timeout:120];
    area["ISO3166-1"="IT"]["admin_level"="2"]->.it;
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
    # solo "way" (niente relazione intera del fiume: l'Adige completo è enorme) e geometrie tagliate al riquadro
    q = f"""[out:json][timeout:120];
    (
      way["highway"~"^({roads})$"]({bbox});
      way["railway"="rail"]["service"!~"."]({bbox});
      way["waterway"~"^(river|canal)$"]({bbox});
    );
    out geom({bbox});
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
                geom = el.get("geometry") or []
                coords = [(g["lon"], g["lat"]) for g in geom if g]
                # un quartiere tagliato dal riquadro (punti null) non è un poligono affidabile
                p = Polygon(coords) if len(coords) >= 4 and len(coords) == len(geom) else None
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
    riquadro = None
    if esistenti and len(esistenti):
        # cerco il confine solo attorno alle tue zone (allargate di circa 10 km)
        minx, miny, maxx, maxy = unary_union([z.geom for z in esistenti.zone]).bounds
        riquadro = (minx - 0.13, miny - 0.09, maxx + 0.13, maxy + 0.09)
    territorio = territorio or fetch_comune_boundary(comune, user_agent, riquadro)
    if esistenti and len(esistenti):
        # genera solo dove non ci sono già le tue microzone
        territorio = territorio.difference(unary_union([z.geom for z in esistenti.zone])).buffer(0)
    feats = fetch_cut_features(territorio.envelope, user_agent, livello)
    nuove = build_zones(territorio if territorio.geom_type == "Polygon" else territorio,
                        feats["tagli"], feats["quartieri"], area_min_m2)
    zone = (list(esistenti.zone) if esistenti else []) + nuove
    return MicrozoneSet(zone)


def disegna_hinterland(cfg: dict, livello: str = "medio", area_min_m2: float = 150_000,
                       rifai: bool = False) -> list[str]:
    """Per ogni comune dell'hinterland senza zone automatiche: confine comunale da OSM, tagliato da
    strade principali, ferrovie e fiumi (come per Verona). Le zone disegnate a mano restano:
    le nuove coprono solo il resto del comune. Restituisce un riepilogo riga per riga."""
    from ..config import get, resolve
    from ..territori import RIQUADRO_VR, comuni_hinterland, file_zone, nome_breve
    ua = get(cfg, "scraping.user_agent")
    righe = []
    for c in comuni_hinterland(cfg):
        path = resolve(cfg, file_zone(c))
        zs = MicrozoneSet.load(path)
        auto = [z for z in zs.zone if z.props.get("fonte") == "osm_auto"]
        if auto and not rifai:
            righe.append(f"{c['nome']}: {len(zs)} microzone già presenti")
            continue
        mie = MicrozoneSet([z for z in zs.zone if z.props.get("fonte") != "osm_auto"])
        try:
            confine = fetch_comune_boundary(c.get("nome_osm", c["nome"]), ua, RIQUADRO_VR)
            tutte = proponi_microzone(c["nome"], ua, livello, area_min_m2, territorio=confine,
                                      esistenti=mie if len(mie) else None)
        except Exception as e:  # noqa: BLE001 - un comune che non riesce non ferma gli altri
            righe.append(f"{c['nome']}: microzone non disegnate ({e}); si riprova al prossimo giro")
            continue
        breve, nomi = nome_breve(c), set(mie.names())
        for z in tutte.zone[len(mie):]:
            resto = z.nome.removeprefix("Auto ").strip()
            z.nome = f"{breve} {resto}"
            while z.nome in nomi:
                z.nome += "b"
            nomi.add(z.nome)
            z.props["comune"] = c["nome"]
        tutte.save(path)
        righe.append(f"{c['nome']}: {len(tutte) - len(mie)} microzone nuove"
                     + (f" (più le tue {len(mie)})" if len(mie) else "") + f" -> {path.name}")
        time.sleep(5)                    # gentilezza verso i server Overpass tra un comune e l'altro
    return righe


__all__ = ["disegna_hinterland", "proponi_microzone", "build_zones", "fetch_comune_boundary", "Point"]
