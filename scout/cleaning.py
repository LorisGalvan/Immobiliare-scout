"""Pulizia: validazione, segnalazione dati dubbi, unione dei doppioni."""
from __future__ import annotations

import math
import re

from .models import Listing
from .tipo_vendita import classifica_listing

TIPOLOGIE_NO = ("progetto", "box", "garage", "posto auto", "terreno", "ufficio", "negozio", "capannone",
                "magazzino", "laboratorio", "locale commerciale")


def valida(l: Listing, cfg: dict) -> tuple[bool, str | None]:
    """Restituisce (tenere, motivo_scarto). Aggiunge flag di dubbio a l.flags.

    Le aste (lette dal testo con ``tipo_vendita``) non entrano nella valutazione del territorio:
    il motivo di scarto inizia con "asta" e ``l.tipo_vendita`` dice di che tipo sono.
    Il controllo è l'ultimo, così "asta" vuol dire "annuncio altrimenti valido".
    """
    p = cfg.get("pulizia", {})
    esito = classifica_listing(l)
    l.tipo_vendita, l.indizi_vendita = esito.tipo, esito.indizi
    testo = f"{l.titolo} {l.descrizione}".lower()
    if not l.prezzo or l.prezzo <= 1000:
        return False, "prezzo mancante"
    if l.tipologia and any(t in l.tipologia.lower() for t in TIPOLOGIE_NO):
        return False, f"tipologia {l.tipologia}"
    if not l.mq:
        mq_txt = mq_dal_testo(f"{l.titolo or ''} {l.descrizione or ''}")
        if mq_txt and p.get("mq_dal_testo", True):
            l.mq = mq_txt
            l.flags = sorted(set(l.flags) | {"mq letti dal testo"})
        elif esito.tipo in ("asta", "possibile_asta"):
            # un lotto all'asta senza mq resta nella lista Aste (senza confronto €/mq)
            l.flags = sorted(set(l.flags) | {"mq mancanti"})
            return False, ("asta: " if esito.tipo == "asta" else "possibile asta (da verificare): ") + \
                ", ".join(esito.indizi[:3])
        else:
            return False, "mq mancanti"
    if l.mq < p.get("mq_min", 18) or l.mq > p.get("mq_max", 1000):
        return False, f"mq fuori range ({l.mq:g})"
    for w in p.get("parole_escludi", []):
        if "asta" in w.lower():   # le aste le riconosce tipo_vendita e finiscono nella lista Aste
            continue
        if w.lower() in testo:
            return False, f"esclusione: '{w}'"
    # parole che escludono solo se sono nel titolo o nella tipologia: "box auto" nella descrizione
    # di un appartamento ("con box auto") non deve farlo scartare
    titolo_tip = f"{l.titolo} {l.tipologia or ''}".lower()
    for w in p.get("parole_escludi_titolo", []):
        if w.lower() in titolo_tip:
            return False, f"esclusione: '{w}'"
    ppm = l.prezzo / l.mq
    flags = set(l.flags)
    if ppm < p.get("prezzo_mq_min", 300):
        flags.add(f"€/mq molto basso ({ppm:.0f})")
    if ppm > p.get("prezzo_mq_max", 15000):
        return False, f"€/mq assurdo ({ppm:.0f})"
    for w in p.get("parole_dubbie", []):
        if "asta" in w.lower():
            continue
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
    if esito.tipo == "asta":
        return False, "asta: " + ", ".join(esito.indizi[:3])
    if esito.tipo == "possibile_asta":
        return False, "possibile asta (da verificare): " + ", ".join(esito.indizi[:3])
    return True, None


_MQ_TXT = re.compile(r"(\d{2,4}(?:[.,]\d+)?)\s*(?:mq|m2|m²|metri\s+quadr)", re.I)


def mq_dal_testo(testo: str) -> float | None:
    """Superficie scritta nel testo (molti privati non compilano il campo). Prende la più grande
    tra 25 e 600 mq, per evitare cantine, balconi e giardini."""
    vals = []
    for m in _MQ_TXT.finditer(testo or ""):
        try:
            v = float(m.group(1).replace(".", "").replace(",", ".")) if "," in m.group(1) else float(m.group(1).replace(".", ""))
        except ValueError:
            continue
        prima = testo[max(0, m.start() - 22):m.start()].lower()   # "giardino di 200 mq", "cantina 8 mq"
        if any(w in prima for w in ("giardino", "terrazz", "cantina", "garage", "box", "balcon", "corte", "terreno",
                                    "lotto", "soffitta", "taverna", "magazzino")):
            continue
        if 25 <= v <= 600:
            vals.append(v)
    return max(vals) if vals else None


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


PRIORITA = {"pvp": -1, "immobiliare": 0, "idealista": 1, "casa": 2, "subito": 3, "facebook": 4, "excel": 9}


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
