"""Decodifica/codifica dei poligoni usati nei link di ricerca dei portali.

- Immobiliare.it:  parametro ``vrt=lat,lon;lat,lon;...``
- Idealista:       parametro ``shape=((<polyline codificata Google>))``
- Casa.it:         parametro ``geopolygon={"polygon":[[lat,lon],...]}``

Tutte le funzioni lavorano con liste di coppie (lat, lon).
"""
from __future__ import annotations

import json
import re
import urllib.parse

LatLon = tuple[float, float]


# ----------------------------------------------------------------- Google polyline
def decode_polyline(s: str, precision: int = 5) -> list[LatLon]:
    idx = lat = lng = 0
    pts: list[LatLon] = []
    factor = 10 ** precision
    while idx < len(s):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                if idx >= len(s):
                    raise ValueError("polyline troncata")
                b = ord(s[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        pts.append((lat / factor, lng / factor))
    return pts


def encode_polyline(points: list[LatLon], precision: int = 5) -> str:
    factor = 10 ** precision
    out = []
    plat = plng = 0
    for lat, lng in points:
        ilat, ilng = round(lat * factor), round(lng * factor)
        for d in (ilat - plat, ilng - plng):
            v = ~(d << 1) if d < 0 else d << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plng = ilat, ilng
    return "".join(out)


# ----------------------------------------------------------------- decoder per URL
def _query_param(url: str, name: str) -> str | None:
    # i link nei file Excel non sempre sono URL "puliti": regex tollerante
    m = re.search(rf"[?&]{name}=([^&#]+)", url)
    return urllib.parse.unquote(m.group(1)) if m else None


def decode_immobiliare_vrt(url: str) -> list[LatLon] | None:
    vrt = _query_param(url, "vrt")
    if not vrt:
        return None
    pts = []
    for pair in vrt.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        lat, lon = pair.split(",")[:2]
        pts.append((float(lat), float(lon)))
    return pts if len(pts) >= 3 else None


def decode_idealista_shape(url: str) -> list[LatLon] | None:
    shape = _query_param(url, "shape")
    if not shape:
        return None
    shape = shape.strip()
    # può contenere più anelli: ((ring1),(ring2)) -> prendiamo il primo
    inner = shape.strip("()")
    ring = inner.split("),(")[0]
    pts = decode_polyline(ring)
    return pts if len(pts) >= 3 else None


def decode_casa_geopolygon(url: str) -> list[LatLon] | None:
    raw = _query_param(url, "geopolygon")
    if not raw:
        return None
    m = re.search(r'"polygon"\s*:\s*(\[\s*\[.*?\]\s*\])', raw)
    if not m:
        return None
    try:
        arr = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    pts = [(float(a), float(b)) for a, b in arr]
    return pts if len(pts) >= 3 else None


def decode_any(url: str) -> tuple[str, list[LatLon]] | None:
    if not isinstance(url, str):
        return None
    for name, fn in (("immobiliare", decode_immobiliare_vrt),
                     ("idealista", decode_idealista_shape),
                     ("casa", decode_casa_geopolygon)):
        try:
            pts = fn(url)
        except (ValueError, IndexError):
            pts = None
        if pts:
            return name, pts
    return None


# ----------------------------------------------------------------- costruttori URL
def _closed(points: list[LatLon]) -> list[LatLon]:
    return points if points[0] == points[-1] else points + [points[0]]


def build_immobiliare_vrt(points: list[LatLon]) -> str:
    return ";".join(f"{lat:.6f},{lon:.6f}" for lat, lon in points)


def build_idealista_shape(points: list[LatLon]) -> str:
    return "((" + encode_polyline(_closed(points)) + "))"


def immobiliare_search_url(points: list[LatLon], slug: str = "verona", page: int = 1) -> str:
    # /vendita-case/<comune>/ è consentito da robots.txt (ricerca.php no)
    q = {"criterio": "superficie", "ordine": "asc", "vrt": build_immobiliare_vrt(points)}
    if page > 1:
        q["pag"] = page
    return f"https://www.immobiliare.it/vendita-case/{slug}/?" + urllib.parse.urlencode(q, safe=",;")


def idealista_search_url(points: list[LatLon]) -> str:
    return ("https://www.idealista.it/aree/vendita-case/?ordine=area-asc&shape="
            + urllib.parse.quote(build_idealista_shape(points), safe=""))


def casa_search_url(points: list[LatLon]) -> str:
    poly = json.dumps({"polygon": [[round(a, 6), round(b, 6)] for a, b in points]},
                      separators=(",", ":"))
    return ("https://www.casa.it/srp/?tr=vendita&category=residenziale&surrounding=false"
            "&sortType=surface_asc&geopolygon=" + urllib.parse.quote(poly, safe=",:[]{}\""))
