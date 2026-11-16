"""Idealista (fase 2).

Idealista usa protezioni anti-bot aggressive: lo scraping HTTP diretto spesso
viene bloccato. Il modulo fornisce:
- costruzione dell'URL di ricerca a poligono (shape) per ogni microzona;
- parser delle pagine di lista (HTML server-side: <article class="item">),
  usabile sia via HTTP sia su pagine salvate dal browser (`scout importa-html`).
Le coordinate non sono nella lista: si geocodifica l'indirizzo del titolo.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..geo.polygons import idealista_search_url
from ..models import Listing
from ..normalize import num, piano
from .base import BloccatoError, PoliteClient

log = logging.getLogger(__name__)
SOURCE = "idealista"
BASE = "https://www.idealista.it"


def parse_search_page(html: str) -> tuple[list[Listing], bool]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for art in soup.select("article.item, article[data-element-id]"):
        sid = art.get("data-element-id") or art.get("data-adid")
        link = art.select_one("a.item-link")
        if link is None:      # annunci "promossi" di altri comuni, senza link alla scheda
            continue
        if not sid:
            m = re.search(r"/immobile/(\d+)", link.get("href", ""))
            sid = m.group(1) if m else None
        if not sid:
            continue
        titolo = link.get_text(" ", strip=True) if link else ""
        prezzo = num((art.select_one(".item-price") or art).get_text(" ", strip=True)) \
            if art.select_one(".item-price") else None
        mq = locali = None
        piano_raw = None
        asc = None
        for det in art.select(".item-detail-char .item-detail, .item-detail"):
            t = det.get_text(" ", strip=True).lower()
            if "m²" in t or "m2" in t:
                mq = num(t)
            elif "local" in t:
                locali = int(num(t) or 0) or None
            elif "piano" in t or "terra" in t or "rialzato" in t or "attico" in t:
                piano_raw = t
                if "con ascensore" in t:
                    asc = True
                elif "senza ascensore" in t:
                    asc = False
        desc = art.select_one(".item-description")
        agenzia = art.select_one(".logo-branding img, .item-logo img")
        from ..geo.geocode import estrai_indirizzo
        pulito = re.sub(r"\bs\.?n\.?c\.?\b", "", titolo, flags=re.I)
        m = re.search(r"\bin\s+(.+?)(?:,\s*[^,]+)?$", pulito)
        indirizzo = estrai_indirizzo(pulito) or (m.group(1) if m else None)
        out.append(Listing(
            source=SOURCE, source_id=str(sid),
            url=BASE + link["href"] if link and link.get("href", "").startswith("/") else (link or {}).get("href", ""),
            titolo=titolo, descrizione=desc.get_text(" ", strip=True) if desc else "",
            prezzo=prezzo, mq=mq, locali=locali, piano=piano(piano_raw), ascensore=asc,
            agenzia=agenzia.get("alt") if agenzia else None,
            privato=None if agenzia else None,
            indirizzo=indirizzo, coord_precise=False,
        ))
    has_next = bool(soup.select_one(".pagination .next a, a.icon-arrow-right-after"))
    return out, has_next


def scrape(cfg: dict, client: PoliteClient, poligoni: dict[str, list]) -> list[Listing]:
    tutti: dict[str, Listing] = {}
    max_pag = int(cfg.get("scraping", {}).get("max_pagine", 40))
    for nome, poly in poligoni.items():
        base_url = idealista_search_url(poly)
        for page in range(1, max_pag + 1):
            url = base_url if page == 1 else base_url.replace("/vendita-case/", f"/vendita-case/pagina-{page}")
            try:
                r = client.get(url)
            except BloccatoError as e:
                log.error("Idealista: %s", e)
                return list(tutti.values())
            except (PermissionError, RuntimeError) as e:
                log.error("Idealista: %s", e)
                break
            annunci, has_next = parse_search_page(r.text)
            for a in annunci:
                a.microzona = nome
                tutti[a.source_id] = a
            if not has_next or not annunci:
                break
    return list(tutti.values())
