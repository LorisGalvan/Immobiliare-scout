"""Wikicasa.it tramite Apify: portale con molti annunci di privati (inserimento gratuito).

Wikicasa blocca le richieste dirette del bot, quindi si usa l'actor
``stealth_mode/wikicasa-property-search-scraper`` (circa 3 $ ogni 1.000 annunci).
L'actor legge le pagine di elenco (``https://www.wikicasa.it/vendita-case/verona/?p=N``).
Un annuncio senza agenzia è di un privato. Stesso token di Apify (``apify.token``).
"""
from __future__ import annotations

import logging
import os
import re

import requests

from ..models import Listing
from ..normalize import num
from .apify_immobiliare import ApifyErrore, _g, esegui_actor, token

log = logging.getLogger(__name__)
SOURCE = "wikicasa"
BASE = "https://www.wikicasa.it"
ATTORE = "stealth_mode/wikicasa-property-search-scraper"


def url_pagine(cfg: dict) -> list[str]:
    w = cfg.get("wikicasa") or {}
    slug = w.get("slug") or (cfg.get("territorio") or {}).get("slug_immobiliare", "verona")
    base = f"{BASE}/vendita-case/{slug}/"
    return [base if p == 1 else f"{base}?p={p}" for p in range(1, int(w.get("pagine", 8)) + 1)]


def input_actor(cfg: dict) -> dict:
    w = cfg.get("wikicasa") or {}
    return {"urls": url_pagine(cfg), "ignore_url_failures": True,
            "max_items_per_url": int(w.get("annunci_per_pagina", 30)),
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "IT"}}


def a_listing(r: dict) -> Listing | None:
    url = str(_g(r, "url") or "")
    m = re.search(r"/annuncio/(\d+)", url)
    rid = _g(r, "real_estate_id", "realestate_id", "id") or (m.group(1) if m else None)
    prezzo = _g(r, "price_sale", "price")
    prezzo = prezzo if isinstance(prezzo, (int, float)) else num(prezzo)
    if rid is None or not prezzo or _g(r, "rent") is True:
        return None
    if url.startswith("/"):
        url = BASE + url
    ag = r.get("agency") if isinstance(r.get("agency"), dict) else None
    nome_ag = (ag or {}).get("name")
    privato = not nome_ag
    return Listing(
        source=SOURCE, source_id=str(rid), url=url or f"{BASE}/annuncio/{rid}",
        titolo=str(_g(r, "title") or " ".join(str(x) for x in (_g(r, "typology_name", "typology"), _g(r, "zone_name")) if x)),
        descrizione=str(_g(r, "description") or ""), prezzo=prezzo,
        mq=num(_g(r, "sqm", "surface")),
        bagni=int(num(_g(r, "bathrooms")) or 0) or None,
        locali=int(num(_g(r, "rooms")) or 0) or None,
        privato=privato, agenzia=nome_ag,
        indirizzo=_g(r, "address"),
        lat=num(_g(r, "place_dto.latitude", "latitude")),
        lon=num(_g(r, "place_dto.longitude", "longitude")),
        tipologia=_g(r, "typology_name", "typology"),
    )


def scrape(cfg: dict) -> tuple[list[Listing], bool]:
    """(annunci, completa). Si leggono solo le prime pagine: ``completa`` è False,
    così gli annunci non visti in questo giro non vengono segnati come rimossi."""
    tok = token(cfg)
    if not tok:
        log.error("Wikicasa: manca il token Apify (apify.token in config.local.yaml)")
        return [], False
    w = cfg.get("wikicasa") or {}
    try:
        righe = esegui_actor(tok, w.get("attore", ATTORE), input_actor(cfg), int(w.get("attesa_max_min", 30)) * 60,
                             run_id=os.environ.get("SCOUT_APIFY_RUN"))
    except (ApifyErrore, requests.RequestException) as e:
        log.error("Wikicasa: %s", e)
        return [], False
    res = {l.uid: l for l in map(a_listing, righe) if l}
    log.info("Wikicasa: %d righe, %d annunci in vendita (privati: %d)",
             len(righe), len(res), sum(l.privato is True for l in res.values()))
    return list(res.values()), False
