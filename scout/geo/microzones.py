"""Gestione delle microzone (poligoni GeoJSON) e point-in-polygon."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from .polygons import LatLon


@dataclass
class Microzona:
    nome: str
    geom: Polygon                  # coordinate (lon, lat) come da standard GeoJSON
    props: dict = field(default_factory=dict)

    @property
    def latlon(self) -> list[LatLon]:
        ext = self.geom.exterior if hasattr(self.geom, "exterior") else self.geom.geoms[0].exterior
        return [(y, x) for x, y in ext.coords]


def polygon_from_latlon(points: list[LatLon]) -> Polygon:
    poly = Polygon([(lon, lat) for lat, lon in points])
    if not poly.is_valid:
        poly = poly.buffer(0)   # ripara poligoni auto-intersecanti disegnati a mano
    return poly


class MicrozoneSet:
    def __init__(self, zone: list[Microzona]):
        self.zone = zone
        self._tree = STRtree([z.geom for z in zone]) if zone else None
        if zone:
            c = self.union_bounds_center()
            self._kx = 111_320 * math.cos(math.radians(c[1]))   # metri per grado di lon
            self._ky = 110_540                                  # metri per grado di lat

    # ------------------------------------------------------------- I/O
    @classmethod
    def load(cls, path: str | Path) -> "MicrozoneSet":
        path = Path(path)
        if not path.exists():
            return cls([])
        data = json.loads(path.read_text(encoding="utf-8"))
        zone = []
        for f in data.get("features", []):
            props = dict(f.get("properties") or {})
            nome = props.get("nome") or props.get("name") or f"zona_{len(zone) + 1}"
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            zone.append(Microzona(nome, g, props))
        return cls(zone)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        feats = []
        for z in self.zone:
            props = {**z.props, "nome": z.nome}
            feats.append({"type": "Feature", "properties": props, "geometry": mapping(z.geom)})
        path.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                   ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------- query
    def __len__(self):
        return len(self.zone)

    def names(self) -> list[str]:
        return [z.nome for z in self.zone]

    def get(self, nome: str) -> Microzona | None:
        return next((z for z in self.zone if z.nome == nome), None)

    def union_bounds_center(self) -> tuple[float, float]:
        xs, ys = [], []
        for z in self.zone:
            minx, miny, maxx, maxy = z.geom.bounds
            xs += [minx, maxx]
            ys += [miny, maxy]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    def _to_m(self, g):
        return transform(lambda x, y, z=None: (x * self._kx, y * self._ky), g)

    def assign(self, lat: float | None, lon: float | None, tolleranza_m: float = 0) -> str | None:
        """Nome della microzona che contiene il punto (o la più vicina entro la tolleranza)."""
        if lat is None or lon is None or not self._tree:
            return None
        p = Point(lon, lat)
        hits = self._tree.query(p, predicate="intersects")
        if len(hits):
            # se i poligoni si sovrappongono vince il più piccolo (il più specifico)
            best = min(hits, key=lambda i: self.zone[i].geom.area)
            return self.zone[best].nome
        if tolleranza_m > 0:
            idx = self._tree.nearest(p)
            if idx is not None:
                d = self._to_m(self.zone[idx].geom).distance(self._to_m(p))
                if d <= tolleranza_m:
                    return self.zone[idx].nome
        return None

    def area_m2(self, nome: str) -> float:
        z = self.get(nome)
        return self._to_m(z.geom).area if z else 0.0

    def overlaps_report(self, min_pct: float = 5) -> list[tuple[str, str, float]]:
        """Coppie di zone che si sovrappongono più di min_pct% (da correggere a mano)."""
        out = []
        for i, a in enumerate(self.zone):
            for b in self.zone[i + 1:]:
                if a.geom.intersects(b.geom):
                    inter = a.geom.intersection(b.geom).area
                    pct = 100 * inter / min(a.geom.area, b.geom.area)
                    if pct >= min_pct:
                        out.append((a.nome, b.nome, round(pct, 1)))
        return out
