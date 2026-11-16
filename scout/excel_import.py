"""Importazione dei file Excel di mappatura manuale.

Per ogni foglio (= microzona):
- righe 1-3: link di ricerca Immobiliare (vrt), Idealista (shape), Casa.it (geopolygon)
- blocchi per fascia: riga intestazione "VIA | MQ 30/50 | PREZZO | ..." seguita dagli annunci
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
from pathlib import Path

import openpyxl

from .geo.microzones import Microzona, MicrozoneSet, polygon_from_latlon
from .geo.polygons import decode_any
from .models import Listing
from .normalize import piano as norm_piano

log = logging.getLogger(__name__)

PRIORITA_FONTE = ["immobiliare", "idealista", "casa"]


def _cell_url(cell) -> str | None:
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    return cell.value if isinstance(cell.value, str) and cell.value.startswith("http") else None


def _zona_nome(title: str, usati: set[str]) -> str:
    nome = re.sub(r"\s+", " ", title).strip()
    base, k = nome, 2
    while nome in usati:
        nome = f"{base} ({k})"
        k += 1
    usati.add(nome)
    return nome


def importa_poligoni(files: list[str | Path], comune: str | None = None) -> tuple[MicrozoneSet, list[str]]:
    zone, avvisi, usati = [], [], set()
    for f in files:
        wb = openpyxl.load_workbook(f, data_only=False)
        for ws in wb.worksheets:
            trovati: dict[str, list] = {}
            links = {}
            for r in range(1, 6):
                for c in range(1, 4):
                    url = _cell_url(ws.cell(r, c))
                    if not url:
                        continue
                    dec = decode_any(url)
                    if dec:
                        trovati.setdefault(dec[0], dec[1])
                        links[dec[0]] = url
            if not trovati:
                avvisi.append(f"{Path(f).name} / '{ws.title}': nessun poligono trovato (foglio saltato)")
                continue
            fonte = next(k for k in PRIORITA_FONTE if k in trovati)
            poly = polygon_from_latlon(trovati[fonte])
            nome = _zona_nome(ws.title, usati)
            m = re.match(r"\s*(\d+)", ws.title)
            props = {"fonte": f"excel:{fonte}", "file": Path(f).name, "foglio": ws.title,
                     "numero": int(m.group(1)) if m else None, "comune": comune or "",
                     "link_originali": links}
            zone.append(Microzona(nome, poly, props))
    zs = MicrozoneSet(zone)
    for a, b, pct in zs.overlaps_report():
        avvisi.append(f"sovrapposizione {pct}% tra '{a}' e '{b}'")
    return zs, avvisi


# ------------------------------------------------------------------ annunci storici
def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d,\.]", "", v).replace(".", "").replace(",", ".")
        try:
            return float(s) if s else None
        except ValueError:
            return None
    return None


def _si_no(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s.startswith("si") or s.startswith("sì"):
        return True
    if s.startswith("no"):
        return False
    return None


def _data(v):
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, str):
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", v)
        if m:
            d, mth, y = map(int, m.groups())
            y = y + 2000 if y < 100 else y
            try:
                return dt.date(y, mth, d).isoformat()
            except ValueError:
                return None
    return None


def _stato(v):
    if v is None:
        return None
    s = str(v).lower()
    if "ristrutturar" in s or s.strip() == "no":
        return "da_ristrutturare"
    if "nuov" in s:
        return "nuovo"
    if s.startswith("si") or "ristrutturat" in s:
        return "ottimo"
    return None


def importa_annunci_storici(files: list[str | Path], zone_names: dict[tuple[str, str], str]) -> list[Listing]:
    """Legge le righe annuncio. zone_names: (file, foglio) -> nome microzona."""
    out = []
    for f in files:
        wb = openpyxl.load_workbook(f, data_only=True)
        for ws in wb.worksheets:
            zona = zone_names.get((Path(f).name, ws.title))
            in_blocco = False
            for row in ws.iter_rows(min_row=1, max_col=14):
                a = row[0].value
                b = row[1].value
                if isinstance(a, str) and a.strip().upper() == "VIA" and isinstance(b, str) and "MQ" in b.upper():
                    in_blocco = True
                    continue
                if not in_blocco:
                    continue
                if isinstance(b, str) and b.strip().lower().startswith("media"):
                    in_blocco = False
                    continue
                mq, prezzo = _num(b), _num(row[2].value)
                if not mq or not prezzo:
                    continue
                link = _cell_url(row[11]) if len(row) > 11 else None
                via = str(a).strip() if a else None
                agenzia = str(row[10].value).strip() if row[10].value else None
                data = _data(row[9].value)
                key = f"{Path(f).name}|{ws.title}|{row[0].row}|{mq}|{prezzo}"
                sid = hashlib.md5(key.encode()).hexdigest()[:12]
                piano = row[5].value
                l = Listing(
                    source="excel", source_id=sid, url=link or "", prezzo=prezzo, mq=mq,
                    piano=norm_piano(piano),
                    ascensore=_si_no(row[6].value),
                    bagni=int(_num(row[7].value)) if _num(row[7].value) else None,
                    stato=_stato(row[8].value), stato_raw=str(row[8].value) if row[8].value else None,
                    agenzia=agenzia,
                    privato=(agenzia or "").lower().startswith("privat") if agenzia else None,
                    data_pubblicazione=data, indirizzo=via, microzona=zona,
                    descrizione=str(row[12].value or "") + " " + str(row[13].value or ""),
                )
                out.append(l)
    return out
