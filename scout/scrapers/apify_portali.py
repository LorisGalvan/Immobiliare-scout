"""Idealista e Casa.it tramite Apify.

Entrambi i portali bloccano le richieste dirette del bot. Gli actor scelti:
- Idealista: ``epicscrapers/idealista-scraper`` (circa 1 $ ogni 1.000 annunci), ricerca per comune;
- Casa.it: ``logiover/casa-it-scraper-italy-real-estate`` (circa 1,50 $ ogni 1.000), ricerca per "slug" del comune.

Gli annunci diventano ``idealista:<id>`` e ``casa:<id>``. Quelli presenti anche su altri portali
vengono riconosciuti come doppioni dalla pulizia (stesso prezzo, mq e posizione) e contano una volta sola.
Stesso token di Apify (``apify.token`` in config.local.yaml).
"""
from __future__ import annotations

import logging
import os
import re

import requests

from ..models import Listing
from ..normalize import num, piano, si_no
from .apify_immobiliare import ApifyErrore, _g, esegui_actor, token

log = logging.getLogger(__name__)

PORTALI = {
    "idealista": {"attore": "epicscrapers/idealista-scraper", "base": "https://www.idealista.it"},
    "casa": {"attore": "logiover/casa-it-scraper-italy-real-estate", "base": "https://www.casa.it"},
}
_PRIVATO = re.compile(r"privat|owner|particular", re.I)


def input_actor(cfg: dict, portale: str) -> dict:
    t = cfg["territorio"]
    p = (cfg.get("portali_apify") or {}).get(portale) or {}
    f = cfg.get("scraping", {}).get("filtri", {})
    max_ = int(p.get("max_annunci", 3000))
    proxy = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "IT"}
    if portale == "idealista":
        return {"country": "it", "operation": "sale", "propertyType": "homes",
                "locationQuery": p.get("luogo") or t["comune"], "maxResults": max_,
                "fetchDetails": bool(p.get("descrizione", True)), "proxyConfiguration": proxy}
    out = {"locationSlugs": [p.get("slug") or t.get("slug_immobiliare") or t["comune"].lower()],
           "transaction": "sale", "propertyType": "apartment",
           "maxListings": max_, "maxPagesPerTask": int(p.get("max_pagine", 200)), "proxyConfiguration": proxy}
    if f.get("prezzo_min"):
        out["priceMin"] = int(f["prezzo_min"])
    if f.get("prezzo_max"):
        out["priceMax"] = int(f["prezzo_max"])
    return out


def a_listing(r: dict, portale: str) -> Listing | None:
    base = PORTALI[portale]["base"]
    rid = _g(r, "propertyCode", "adId", "id", "listingId")
    prezzo = _g(r, "price", "priceInfo.price.amount", "priceInfo.amount")
    prezzo = prezzo if isinstance(prezzo, (int, float)) else num(prezzo)
    if rid is None or not prezzo:
        return None
    if str(_g(r, "operation", "transaction", "listingType") or "sale").lower() in ("rent", "affitto"):
        return None
    url = str(_g(r, "url", "detailUrl") or "")
    if url.startswith("/"):
        url = base + url
    tipo_ins = str(_g(r, "publisherType", "contactInfo.userType", "contactInfo.contactType",
                      "contactInfo.commercialName") or "")
    agenzia = _g(r, "agencyName", "contactInfo.commercialName", "contactInfo.agencyName")
    privato = True if _PRIVATO.search(tipo_ins) else (False if agenzia or "agen" in tipo_ins.lower() else None)
    return Listing(
        source=portale, source_id=str(rid),
        url=url or (f"{base}/immobile/{rid}/" if portale == "idealista" else f"{base}/immobili/{rid}/"),
        titolo=str(_g(r, "title", "suggestedTexts.title") or ""),
        descrizione=str(_g(r, "description") or ""), prezzo=prezzo,
        mq=num(_g(r, "size", "areaSqm", "surface")),
        piano=piano(_g(r, "floor")), ascensore=si_no(_g(r, "hasLift", "lift")),
        bagni=int(num(_g(r, "bathrooms", "baths")) or 0) or None,
        locali=int(num(_g(r, "rooms")) or 0) or None,
        privato=privato, agenzia=None if privato else (str(agenzia) if agenzia else None),
        indirizzo=_g(r, "address", "street"),
        lat=num(_g(r, "latitude", "lat")), lon=num(_g(r, "longitude", "lng", "lon")),
        tipologia=_g(r, "extendedPropertyType", "propertyType", "typology"),
    )


def scrape(cfg: dict, portale: str) -> tuple[list[Listing], bool]:
    tok = token(cfg)
    if not tok:
        log.error("%s: manca il token Apify (apify.token in config.local.yaml)", portale)
        return [], False
    p = (cfg.get("portali_apify") or {}).get(portale) or {}
    inp = input_actor(cfg, portale)
    try:
        righe = esegui_actor(tok, p.get("attore", PORTALI[portale]["attore"]), inp,
                             int(p.get("attesa_max_min", 60)) * 60, run_id=os.environ.get("SCOUT_APIFY_RUN"))
    except (ApifyErrore, requests.RequestException) as e:
        log.error("%s: %s", portale, e)
        return [], False
    res = {l.uid: l for l in (a_listing(r, portale) for r in righe if isinstance(r, dict)) if l}
    max_ = inp.get("maxResults") or inp.get("maxListings") or 0
    completa = not getattr(righe, "parziale", False) and len(righe) < max_
    log.info("%s: %d righe, %d annunci in vendita (privati: %d)%s", portale, len(righe), len(res),
             sum(l.privato is True for l in res.values()), "" if completa else " - elenco parziale")
    return list(res.values()), completa and bool(res)
