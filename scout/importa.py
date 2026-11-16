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
    if "immobiliare.it" in low:
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


ESCLUSE = {"importate", "non_riconosciute"}


def pagine_da_importare(cartella: str | Path) -> list[Path]:
    """File .htm/.html nella cartella, escluse le sottocartelle d'archivio e le
    cartelle '<nome>_files' create da "Salva pagina web completa"."""
    base = Path(cartella)
    out = []
    for p in sorted(base.glob("**/*.htm*")):
        rel = p.relative_to(base).parts[:-1]
        if any(x in ESCLUSE or x.endswith("_files") for x in rel):
            continue
        out.append(p)
    return out


def importa_html(cartella: str | Path, archivia: bool = False) -> list[Listing]:
    """Importa le pagine salvate. Con archivia=True sposta i file letti in
    'importate/<data>/' e quelli non riconosciuti in 'non_riconosciute/'."""
    import datetime as dt
    import shutil

    base = Path(cartella)
    out = []
    oggi = dt.date.today().isoformat()
    for p in pagine_da_importare(base):
        try:
            res = parse_html_file(p)
        except Exception as e:  # noqa: BLE001 - un file rovinato non deve fermare gli altri
            log.warning("%s: errore di lettura (%s)", p.name, e)
            res = []
        out += res
        if archivia:
            dest = base / ("importate/" + oggi if res else "non_riconosciute")
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / p.name
            k = 2
            while target.exists():
                target = dest / f"{p.stem}_{k}{p.suffix}"
                k += 1
            shutil.move(str(p), target)
            cartella_files = p.with_name(p.stem + "_files")
            if cartella_files.is_dir():
                shutil.move(str(cartella_files), dest / (target.stem + "_files"))
            if not res:
                log.warning("%s: nessun annuncio riconosciuto (spostato in non_riconosciute/)", p.name)
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
