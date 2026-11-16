"""Pulizia: validazione, segnalazione dati dubbi, unione dei doppioni."""
from __future__ import annotations

import math
import re

from .models import Listing

TIPOLOGIE_NO = ("progetto", "asta", "box", "garage", "posto auto", "terreno", "ufficio", "negozio", "capannone",
                "magazzino", "laboratorio", "locale commerciale")


def valida(l: Listing, cfg: dict) -> tuple[bool, str | None]:
    """Restituisce (tenere, motivo_scarto). Aggiunge flag di dubbio a l.flags."""
    p = cfg.get("pulizia", {})
    testo = f"{l.titolo} {l.descrizione}".lower()
    if not l.prezzo or l.prezzo <= 1000:
        return False, "prezzo mancante"
    if not l.mq:
        return False, "mq mancanti"
    if l.mq < p.get("mq_min", 18) or l.mq > p.get("mq_max", 1000):
        return False, f"mq fuori range ({l.mq:g})"
    if l.tipologia and any(t in l.tipologia.lower() for t in TIPOLOGIE_NO):
        return False, f"tipologia {l.tipologia}"
    for w in p.get("parole_escludi", []):
        if w.lower() in testo:
            return False, f"esclusione: '{w}'"
    ppm = l.prezzo / l.mq
    flags = set(l.flags)
    if ppm < p.get("prezzo_mq_min", 300):
        flags.add(f"€/mq molto basso ({ppm:.0f})")
    if ppm > p.get("prezzo_mq_max", 15000):
        return False, f"€/mq assurdo ({ppm:.0f})"
    for w in p.get("parole_dubbie", []):
        if re.search(r"\b" + re.escape(w.lower()) + r"\b", testo):
            flags.add(f"testo: '{w}'")
    # mq nel testo diversi da quelli dichiarati
    mq_testo = [float(x.replace(",", ".")) for x in re.findall(r"(\d{2,4}(?:,\d)?)\s*(?:mq|m2|m²|metri quadr)", testo)]
    if mq_testo and all(abs(x - l.mq) / l.mq > 0.25 for x in mq_testo):
        flags.add(f"mq nel testo diversi ({', '.join(f'{x:g}' for x in mq_testo[:3])})")
    if l.lat is None and not l.microzona:
        flags.add("senza coordinate")
    elif not l.coord_precise:
        flags.add("posizione approssimativa")
    l.flags = sorted(flags)
    return True, None


def _dist_m(a: Listing, b: Listing) -> float:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return math.inf
    kx = 111_320 * math.cos(math.radians(a.lat))
    return math.hypot((a.lon - b.lon) * kx, (a.lat - b.lat) * 110_540)


def _stessa_via(a: Listing, b: Listing) -> bool:
    if not a.indirizzo or not b.indirizzo:
        return False
    norm = lambda s: re.sub(r"[^a-z]", "", s.lower().split(",")[0])  # noqa: E731
    return norm(a.indirizzo) == norm(b.indirizzo)


def sono_doppioni(a: Listing, b: Listing, cfg: dict) -> bool:
    d = cfg.get("pulizia", {}).get("doppioni", {})
    if a.uid == b.uid or not (a.mq and b.mq and a.prezzo and b.prezzo):
        return False
    if abs(a.mq - b.mq) > d.get("tolleranza_mq", 3):
        return False
    if abs(a.prezzo - b.prezzo) / max(a.prezzo, b.prezzo) * 100 > d.get("tolleranza_prezzo_pct", 3):
        return False
    if a.microzona and b.microzona and a.microzona != b.microzona:
        return False
    vicini = _dist_m(a, b) <= d.get("distanza_max_m", 150)
    if vicini or _stessa_via(a, b):
        # stesso piano (se noto) come conferma
        if a.piano and b.piano and a.piano != b.piano:
            return False
        return True
    return False


PRIORITA = {"immobiliare": 0, "idealista": 1, "casa": 2, "subito": 3, "facebook": 4, "excel": 9}


def unisci_doppioni(listings: list[Listing], cfg: dict) -> list[Listing]:
    """Raggruppa i doppioni (stesso immobile su più siti/agenzie).

    Tiene un rappresentante per gruppo (il prezzo più basso; a parità la fonte
    con dati più ricchi) e gli altri link finiscono in ``doppioni``.
    Restituisce la lista dei rappresentanti.
    """
    n = len(listings)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # indicizzazione grossolana per mq per evitare O(n^2) completo
    ordinati = sorted(range(n), key=lambda i: listings[i].mq or 0)
    tol = cfg.get("pulizia", {}).get("doppioni", {}).get("tolleranza_mq", 3)
    for pos, i in enumerate(ordinati):
        for j in ordinati[pos + 1:]:
            if (listings[j].mq or 0) - (listings[i].mq or 0) > tol:
                break
            if sono_doppioni(listings[i], listings[j], cfg):
                parent[find(i)] = find(j)

    gruppi: dict[int, list[Listing]] = {}
    for i in range(n):
        gruppi.setdefault(find(i), []).append(listings[i])
    out = []
    for g in gruppi.values():
        g.sort(key=lambda l: (l.prezzo or 1e12, PRIORITA.get(l.source, 5)))
        rep = g[0]
        altri = [f"{x.source}: {x.url} ({x.agenzia or 'privato' if x.privato else x.agenzia or '?'}, {x.prezzo:,.0f}€)"
                 for x in g[1:]]
        rep.doppioni = altri
        if len({x.agenzia for x in g if x.agenzia}) > 1:
            rep.flags = sorted(set(rep.flags) | {f"pubblicato da {len(g)} inserzionisti"})
        # completa campi mancanti dal gruppo
        for x in g[1:]:
            for k in ("piano", "ascensore", "bagni", "stato", "lat", "lon", "indirizzo", "data_pubblicazione"):
                if getattr(rep, k) in (None, "") and getattr(x, k) not in (None, ""):
                    setattr(rep, k, getattr(x, k))
            if len(x.descrizione or "") > len(rep.descrizione or ""):
                rep.descrizione = x.descrizione
        out.append(rep)
    return out
