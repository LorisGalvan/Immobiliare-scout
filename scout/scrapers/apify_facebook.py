"""Facebook Marketplace (categoria "Immobili in vendita") tramite Apify.

Su Marketplace vendono soprattutto privati che non vogliono pagare l'agenzia: per questo gli annunci
vengono segnati come privati, salvo che il nome del venditore sembri un'agenzia.
Nessun accesso con l'account Facebook personale: l'actor legge solo le inserzioni pubbliche.

Actor predefinito: ``vivid-softwares/facebook-property-scraper`` (specifico per immobili: prezzo,
indirizzo, coordinate, descrizione, venditore). Configurazione nella sezione ``facebook`` di config.yaml;
il token è lo stesso di Apify (``apify.token`` in config.local.yaml).
"""
from __future__ import annotations

import logging
import re

import requests

from ..models import Listing
from ..normalize import num
from .apify_immobiliare import ApifyErrore, _g, esegui_actor, token

log = logging.getLogger(__name__)
SOURCE = "facebook"
ATTORE = "vivid-softwares/facebook-property-scraper"
# parole che indicano un professionista dietro al profilo del venditore
_AGENZIA = re.compile(r"\b(immobiliar\w*|agenzi\w*|real ?estate|tecnocasa|tempocasa|gabetti|remax|re/max|"
                      r"frimm|coldwell|engel|s\.?r\.?l|s\.?a\.?s|s\.?n\.?c|group|gruppo|studio)\b", re.I)
# frasi tipiche di un annuncio di privato
_PRIVATO_TXT = re.compile(r"\b(da privato|privato vende|vendo privatamente|no agenzi\w*|astenersi agenzi\w*|"
                          r"senza agenzi\w*|no intermediari)\b", re.I)


def url_ricerca(cfg: dict) -> str:
    f = cfg.get("facebook") or {}
    if f.get("url"):
        return f["url"]
    lat, lon = f.get("lat", 45.4384), f.get("lon", 10.9916)       # centro di Verona
    return (f"https://www.facebook.com/marketplace/category/propertyforsale?exact=false"
            f"&latitude={lat}&longitude={lon}&radius={int(f.get('raggio_km', 10))}")


def input_actor(cfg: dict) -> dict:
    f = cfg.get("facebook") or {}
    return {"startUrls": [{"url": url_ricerca(cfg)}], "maxItems": int(f.get("max_annunci", 100)),
            "includeDuplicates": True, "rentalsOnly": False, "forSaleOnly": True,
            "enhancedListingDetails": True}


def venditore_privato(nome: str | None, testo: str) -> bool | None:
    if _PRIVATO_TXT.search(testo or ""):
        return True
    if nome and _AGENZIA.search(nome):
        return False
    return True if nome else None


def a_listing(r: dict) -> Listing | None:
    rid = _g(r, "id", "listingId", "listing_id")
    prezzo = _g(r, "final_price", "price.value", "price.amount", "listing_price.amount", "price")
    prezzo = prezzo if isinstance(prezzo, (int, float)) else num(prezzo)
    if rid is None or not prezzo:
        return None
    if str(_g(r, "listingIntent") or "").lower() in ("rent", "rental", "affitto"):
        return None
    titolo = str(_g(r, "title", "listingTitle", "marketplace_listing_title") or "")
    descr = str(_g(r, "description", "redacted_description.text", "redacted_description") or "")
    nome = _g(r, "seller.name", "marketplace_listing_seller.name", "sellerName")
    privato = venditore_privato(str(nome) if nome else None, f"{titolo} {descr}")
    mq = num(_g(r, "squareMeters", "squareFeet", "area"))
    if mq and _g(r, "squareFeet") and not _g(r, "squareMeters"):
        mq = round(mq * 0.0929, 1)                               # l'actor può restituire piedi quadrati
    return Listing(
        source=SOURCE, source_id=str(rid),
        url=str(_g(r, "url", "listingUrl") or f"https://www.facebook.com/marketplace/item/{rid}/"),
        titolo=titolo, descrizione=descr, prezzo=prezzo, mq=mq,
        bagni=int(num(_g(r, "bathrooms")) or 0) or None,
        locali=int(num(_g(r, "beds", "bedrooms")) or 0) or None,
        privato=privato, agenzia=None if privato is not False else str(nome),
        indirizzo=_g(r, "address", "location.text", "city"),
        lat=num(_g(r, "latitude", "location.latitude", "item_location.latitude")),
        lon=num(_g(r, "longitude", "location.longitude", "item_location.longitude")),
        tipologia=_g(r, "property_type"),
    )


def scrape(cfg: dict) -> tuple[list[Listing], bool]:
    """(annunci, completa). Marketplace non dà mai un elenco completo: ``completa`` è sempre False,
    così il bot non segna come rimossi gli annunci non visti in questo giro."""
    tok = token(cfg)
    if not tok:
        log.error("Facebook: manca il token Apify (apify.token in config.local.yaml)")
        return [], False
    f = cfg.get("facebook") or {}
    try:
        righe = esegui_actor(tok, f.get("attore", ATTORE), input_actor(cfg), int(f.get("attesa_max_min", 30)) * 60)
    except (ApifyErrore, requests.RequestException) as e:
        log.error("Facebook: %s", e)
        return [], False
    res = {l.uid: l for l in map(a_listing, righe) if l}
    log.info("Facebook: %d righe, %d annunci in vendita con prezzo (privati: %d)",
             len(righe), len(res), sum(l.privato is True for l in res.values()))
    return list(res.values()), False
