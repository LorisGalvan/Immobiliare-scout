"""Scraper Subito.it (categoria Immobili > Appartamenti, vendita).

Le pagine di lista sono Next.js: gli annunci sono nel JSON ``__NEXT_DATA__``
(oggetti con ``urn`` e ``features``). Le caratteristiche sono nella forma
``"/price": {"values": [{"key": "150000", "value": "150.000 €"}]}``
(dizionario) oppure lista ``[{"uri": "/price", "values": [...]}]``.
"""
from __future__ import annotations

import logging
import re

from ..geo.geocode import estrai_indirizzo
from ..models import Listing
from ..normalize import num, piano, si_no, stato
from .base import BloccatoError, PoliteClient, next_data, walk

log = logging.getLogger(__name__)
SOURCE = "subito"


def search_url(cfg: dict, page: int = 1, categoria: str = "appartamenti") -> str:
    t = cfg["territorio"]
    reg, com, prov = t.get("subito_regione", "veneto"), t.get("subito_comune", "verona"), \
        t.get("subito_provincia", t.get("subito_comune", "verona"))
    url = f"https://www.subito.it/annunci-{reg}/vendita/{categoria}/{prov}/{com}/"
    f = cfg.get("scraping", {}).get("filtri", {})
    q = []
    if page > 1:
        q.append(f"o={page}")
    if f.get("prezzo_min"):
        q.append(f"ps={int(f['prezzo_min'])}")
    if f.get("prezzo_max"):
        q.append(f"pe={int(f['prezzo_max'])}")
    return url + ("?" + "&".join(q) if q else "")


def _features(item: dict) -> dict[str, tuple[str | None, str | None]]:
    """-> {'/price': (key, value), ...}"""
    out = {}
    f = item.get("features")
    if isinstance(f, dict):
        for k, v in f.items():
            vals = (v or {}).get("values") or []
            if vals:
                out[k if k.startswith("/") else "/" + k] = (vals[0].get("key"), vals[0].get("value"))
    elif isinstance(f, list):
        for v in f:
            vals = v.get("values") or []
            if vals and v.get("uri"):
                out[v["uri"]] = (vals[0].get("key"), vals[0].get("value"))
    return out


def _val(feats, key, prefer="key"):
    if key not in feats:
        return None
    k, v = feats[key]
    return (k if prefer == "key" else v) or (v if prefer == "key" else k)


def parse_item(item: dict) -> Listing | None:
    urn = item.get("urn") or ""
    m = re.search(r"(\d+)$", urn)
    sid = m.group(1) if m else str(item.get("id") or "")
    if not sid:
        return None
    feats = _features(item)
    prezzo = num(_val(feats, "/price"))
    mq = num(_val(feats, "/size"))
    adv = item.get("advertiser") or {}
    company = adv.get("company")
    if company is None and "type" in adv:
        company = adv.get("type") == 1
    geo = item.get("geo") or {}
    mapd = geo.get("map") or {}
    lat = num(mapd.get("latitude")) if mapd else None
    lon = num(mapd.get("longitude")) if mapd else None
    titolo = item.get("subject") or ""
    body = item.get("body") or ""
    url = ((item.get("urls") or {}).get("default")) or ""
    data = item.get("date")
    data = data[:10] if isinstance(data, str) and re.match(r"\d{4}-\d{2}-\d{2}", data) else None
    asc_raw = _val(feats, "/elevator", "value")
    return Listing(
        source=SOURCE, source_id=sid, url=url, titolo=titolo, descrizione=body,
        prezzo=prezzo, mq=mq,
        piano=piano(_val(feats, "/floor", "value")),
        ascensore=si_no(asc_raw) if asc_raw is not None else None,
        bagni=int(num(_val(feats, "/bathrooms", "value"))) if num(_val(feats, "/bathrooms", "value")) else None,
        locali=int(num(_val(feats, "/room", "value"))) if num(_val(feats, "/room", "value")) else None,
        stato=stato(_val(feats, "/building_condition", "value")),
        stato_raw=_val(feats, "/building_condition", "value"),
        agenzia=(adv.get("name") or adv.get("shopName")) if company else None,
        privato=(not company) if company is not None else None,
        data_pubblicazione=data,
        indirizzo=estrai_indirizzo(titolo) or estrai_indirizzo(body),
        lat=lat, lon=lon, coord_precise=bool(lat),
        tipologia=(item.get("category") or {}).get("friendlyName") if isinstance(item.get("category"), dict) else None,
    )


def parse_search_page(html: str) -> tuple[list[Listing], int | None]:
    data = next_data(html)
    if not data:
        return [], None
    out, seen, tot = [], set(), None
    for d in walk(data):
        if "totalPages" in d and isinstance(d.get("totalPages"), int):
            tot = d["totalPages"]
        if isinstance(d.get("urn"), str) and "features" in d and ("subject" in d or "body" in d):
            l = parse_item(d)
            if l and l.source_id not in seen:
                seen.add(l.source_id)
                out.append(l)
    return out, tot


def scrape(cfg: dict, client: PoliteClient) -> list[Listing]:
    max_pag = int(cfg.get("scraping", {}).get("max_pagine", 40))
    categorie = cfg.get("scraping", {}).get("subito_categorie", ["appartamenti"])
    tutti: dict[str, Listing] = {}
    for cat in categorie:
        page, tot = 1, None
        while page <= max_pag and (tot is None or page <= tot):
            try:
                r = client.get(search_url(cfg, page, cat))
            except BloccatoError as e:
                log.error("Subito: %s", e)
                return list(tutti.values())
            except (PermissionError, RuntimeError) as e:
                log.error("Subito: %s", e)
                break
            annunci, tot_pag = parse_search_page(r.text)
            tot = tot_pag or tot
            log.info("Subito %s pag %d/%s: %d annunci", cat, page, tot, len(annunci))
            if not annunci:
                break
            for a in annunci:
                tutti[a.source_id] = a
            page += 1
    return list(tutti.values())
