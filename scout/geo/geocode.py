"""Geocoding degli indirizzi con Nominatim (OpenStreetMap) e cache su SQLite."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time

import requests

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"

_PREFISSI = (r"(?:via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|lungadige|largo|stradone|"
             r"strada|circonvallazione|contr[àa]|contrada|salita|vicoletto|interrato|stradella)")
_NOME = r"[A-ZÀ-Üa-zà-ü'\.]+(?:\s+[A-ZÀ-Üa-zà-ü'\.]+){0,4}?"
# 1) "via Mameli 12" (con numero civico)  2) "via Mameli," (senza numero, chiuso da punteggiatura/parola)
_VIA_NUM_RE = re.compile(rf"\b({_PREFISSI}\s+{_NOME}),?\s+(\d{{1,4}}(?:/?[a-zA-Z])?)\b", re.IGNORECASE)
_VIA_RE = re.compile(rf"\b({_PREFISSI}\s+{_NOME})(?=\s*[,.;:\n(]|\s+(?:a|in|di|zona|vicino|con|al|nel|nei|presso)\b|\s*$)",
                     re.IGNORECASE)


def estrai_indirizzo(testo: str) -> str | None:
    """Prova a trovare 'via X 12' nel titolo/descrizione di un annuncio."""
    if not testo:
        return None
    m = _VIA_NUM_RE.search(testo)
    if m:
        return re.sub(r"\s+", " ", f"{m.group(1)} {m.group(2)}").strip(" .")
    m = _VIA_RE.search(testo)
    if not m:
        return None
    via = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    return via if len(via.split()) >= 2 else None


class Geocoder:
    def __init__(self, db_path: str, user_agent: str, pausa_s: float = 1.1, attivo: bool = True):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS geocache (q TEXT PRIMARY KEY, res TEXT, ts REAL)")
        self.ua = user_agent
        self.pausa = pausa_s
        self.attivo = attivo
        self._last = 0.0

    def geocode(self, indirizzo: str, comune: str, provincia: str = "") -> tuple[float, float] | None:
        q = f"{indirizzo}, {comune} {provincia}, Italia".strip()
        row = self.conn.execute("SELECT res FROM geocache WHERE q=?", (q.lower(),)).fetchone()
        if row:
            res = json.loads(row[0])
            return tuple(res) if res else None
        if not self.attivo:
            return None
        wait = self.pausa - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        try:
            r = requests.get(NOMINATIM, params={"q": q, "format": "json", "limit": 1,
                                                "countrycodes": "it"},
                             headers={"User-Agent": self.ua}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("geocoding fallito per %r: %s", q, e)
            return None
        res = None
        if data:
            # scarta risultati che sono solo il comune (indirizzo non trovato)
            if data[0].get("addresstype") not in ("city", "town", "village", "municipality", "county"):
                res = (float(data[0]["lat"]), float(data[0]["lon"]))
        self.conn.execute("INSERT OR REPLACE INTO geocache VALUES (?,?,?)",
                          (q.lower(), json.dumps(res), time.time()))
        self.conn.commit()
        return res
