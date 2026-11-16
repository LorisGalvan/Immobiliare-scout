"""Casa.it (pagine salvate dal browser).

Gli annunci sono nello stato iniziale della pagina:
``window.__INITIAL_STATE__ = JSON.parse("...")`` -> ``search.list`` (venti per pagina).
Ogni annuncio ha prezzo, mq, piano, bagni, inserzionista e coordinate (``geoInfos``).
``search.surroundingsList`` contiene annunci dei comuni vicini: ignorati.
"""
from __future__ import annotations

import json
import logging
import re

from ..models import Listing
from ..normalize import num, piano

log = logging.getLogger(__name__)
SOURCE = "casa"
BASE = "https://www.casa.it"

_STATE_RE = re.compile(r'__INITIAL_STATE__\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)', re.S)


def stato_iniziale(html: str) -> dict | None:
    m = _STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(json.loads(m.group(1)))
    except ValueError:
        return None


def parse_item(it: dict) -> Listing | None:
    sid = it.get("id")
    if sid is None:
        return None
    f = it.get("features") or {}
    price = f.get("price") or {}
    prezzo = num((price.get("marker") or {}).get("originalPrice")) or num(price.get("value"))
    if price.get("show") is False:
        prezzo = None
    geo = it.get("geoInfos") or {}
    pub = it.get("publisher") or {}
    tipo_pub = (pub.get("publisherType") or "").lower()
    privato = True if tipo_pub.startswith("priv") else False if tipo_pub else None
    titolo = (it.get("title") or {}).get("main") or it.get("highlight") or ""
    if it.get("isAuction"):
        tipologia = "Asta"
    elif it.get("isProjectProfile") or it.get("projectData"):
        tipologia = "Progetto"
    else:
        tipologia = (it.get("propertyType") or "").capitalize() or None
    if (price.get("marker") or {}).get("hasPriceRange"):
        tipologia = "Progetto"
    indirizzo = geo.get("street") if geo.get("has_street") else None
    return Listing(
        source=SOURCE, source_id=str(sid),
        url=BASE + it["uri"] if str(it.get("uri", "")).startswith("/") else it.get("uri", ""),
        titolo=titolo, descrizione=it.get("description") or "",
        prezzo=prezzo, mq=num(f.get("mq")),
        piano=piano(f.get("level")),
        bagni=int(f["bathrooms"]) if isinstance(f.get("bathrooms"), (int, float)) else None,
        locali=int(f["rooms"]) if isinstance(f.get("rooms"), (int, float)) else None,
        agenzia=None if privato else pub.get("publisherName"),
        privato=privato,
        indirizzo=indirizzo,
        lat=num(geo.get("lat")), lon=num(geo.get("lon")),
        coord_precise=bool(geo.get("has_street") and geo.get("show_address")),
        tipologia=tipologia,
    )


def parse_search_page(html: str) -> tuple[list[Listing], int | None]:
    st = stato_iniziale(html)
    if not st:
        return [], None
    search = st.get("search") or {}
    out = [l for l in (parse_item(it) for it in search.get("list") or []) if l]
    tot = (search.get("paginator") or {}).get("totalPages")
    return out, tot if isinstance(tot, int) else None
