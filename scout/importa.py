"""Importazione semi-manuale.

1. Pagine salvate dal browser (Ctrl+S, "Pagina web completa" o "solo HTML") di
   Immobiliare, Subito, Idealista: utile quando un sito blocca il bot.
2. CSV manuale (es. Facebook Marketplace) con colonne:
   link,prezzo,mq,indirizzo,piano,ascensore,bagni,stato,agenzia,data,descrizione,lat,lon
"""
from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path

from .models import Listing
from .normalize import num, piano, si_no, stato
from .scrapers import idealista, immobiliare, subito

log = logging.getLogger(__name__)


def parse_html_file(path: Path) -> list[Listing]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    low = html[:300000].lower()
    if "immobiliare.it" in low and "realestate" in low:
        res, _ = immobiliare.parse_search_page(html)
        if not res:   # pagina di dettaglio
            res = []
    elif "subito.it" in low:
        res, _ = subito.parse_search_page(html)
    elif "idealista" in low:
        res, _ = idealista.parse_search_page(html)
    else:
        res = []
    log.info("%s: %d annunci", path.name, len(res))
    return res


def importa_html(cartella: str | Path) -> list[Listing]:
    out = []
    for p in sorted(Path(cartella).glob("**/*.htm*")):
        out += parse_html_file(p)
    return out


def importa_csv(path: str | Path, source: str = "facebook") -> list[Listing]:
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        for row in csv.DictReader(f, dialect=dialect):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            link = row.get("link", "")
            sid = hashlib.md5((link or str(row)).encode()).hexdigest()[:12]
            agenzia = row.get("agenzia") or None
            out.append(Listing(
                source=source, source_id=sid, url=link,
                titolo=row.get("titolo", ""), descrizione=row.get("descrizione", ""),
                prezzo=num(row.get("prezzo")), mq=num(row.get("mq")),
                piano=piano(row.get("piano")), ascensore=si_no(row.get("ascensore")),
                bagni=int(num(row.get("bagni"))) if num(row.get("bagni")) else None,
                stato=stato(row.get("stato")), stato_raw=row.get("stato"),
                agenzia=agenzia if agenzia and agenzia.lower() != "privato" else None,
                privato=(agenzia or "").lower() == "privato" or not agenzia,
                data_pubblicazione=row.get("data") or None,
                indirizzo=row.get("indirizzo") or None,
                lat=num(row.get("lat")), lon=num(row.get("lon")),
            ))
    return out
