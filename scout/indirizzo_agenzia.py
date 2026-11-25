"""Annunci posizionati all'indirizzo dell'agenzia invece che a quello dell'immobile.

Molte agenzie non scrivono il vero indirizzo dell'immobile ma quello del proprio ufficio:
sulla mappa l'annuncio finisce nella microzona dell'agenzia e ne falsa le mediane.
Questi annunci restano sul sito, con una segnalazione ben visibile, ma non entrano nella
valutazione della microzona (niente mediane, niente scostamento, niente occasione).

Tre controlli, dal più sicuro al meno sicuro:

1. **Sede scritta in config** (``controllo_agenzia.sedi``): l'annuncio dell'agenzia è a meno di
   ``raggio_m`` metri dalla sede, oppure ha la stessa via e lo stesso civico.
2. **Sede scritta nell'annuncio**: nel testo c'è "la nostra sede in via Roma 10", "ci trovi in…",
   e l'indirizzo dell'annuncio è proprio quello.
3. **Tanti immobili diversi della stessa agenzia nello stesso punto** (almeno ``min_immobili``):
   è quasi sempre l'ufficio. Non vale se il punto è un cantiere di nuova costruzione (tanti
   appartamenti nuovi nello stesso stabile sono normali) o se nello stesso punto pubblicano anche
   altri inserzionisti (di solito è il centro del paese o della via, non un ufficio).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

from .doppioni import distanza_m, stessa_via, via_civico
from .models import Listing

log = logging.getLogger(__name__)

FLAG = "indirizzo dell'agenzia"

_PAROLE_VUOTE = {"immobiliare", "immobiliari", "agenzia", "agenzie", "srl", "srls", "snc", "sas", "spa",
                 "di", "de", "del", "della", "the", "group", "gruppo", "studio", "real", "estate", "case", "casa"}

_NUOVO = re.compile(r"nuova\s+costruzione|in\s+costruzione|nuova\s+realizzazione|cantiere|nuovo\s+complesso"
                    r"|complesso\s+residenziale|nuova\s+palazzina|consegna\s+prevista|prezzi\s+da\s+capitolato", re.I)

# "la nostra sede in via Roma 10", "ci trovi in Corso Milano, 5", "uffici di Piazza Bra 3"
_SEDE = re.compile(
    r"(?:nostr[aio]\s+(?:sede|uffic[io]|agenzia|filiale)|(?:sede|uffici?o?|filiale)\s+(?:di|in|a|al|sit[oa])"
    r"|ci\s+trovi|vieni\s+a\s+trovarci|ci\s+trovate|venite\s+a\s+trovarci|siamo\s+in|ufficio\s+vendite)"
    r"[^.\n]{0,60}?\b((?:via|viale|v\.le|corso|c\.so|piazza|p\.zza|p\.za|piazzale|vicolo|largo|lungadige|stradone|strada)"
    r"\s+[A-Za-zÀ-ÿ'’. ]{3,40}?,?\s*\d{1,4}\s?[a-zA-Z]?)\b", re.I)


def nome_agenzia(s: str | None) -> str:
    """"Tecnocasa - Studio Borgo Roma S.r.l." -> "tecnocasaborgoroma": per riconoscere la stessa
    agenzia scritta in modi un po' diversi."""
    parole = re.findall(r"[a-z0-9]+", (s or "").lower().replace("s.r.l", "srl").replace("s.n.c", "snc"))
    return "".join(p for p in parole if p not in _PAROLE_VUOTE)


def _stessa_agenzia(a: str, b: str) -> bool:
    if not a or not b:
        return False
    corto, lungo = sorted((a, b), key=len)
    return corto == lungo or (len(corto) >= 5 and corto in lungo)


def _stesso_indirizzo(a: str | None, b: str | None) -> bool:
    va, ca = via_civico(a)
    vb, cb = via_civico(b)
    return bool(va and vb and ca and cb and ca == cb and stessa_via(va, vb))


def sedi_nel_testo(testo: str | None) -> list[str]:
    """Indirizzi della sede dell'agenzia scritti nella descrizione."""
    return [m.group(1).strip() for m in _SEDE.finditer(testo or "")]


def _segna(l: Listing, motivo: str) -> None:
    l.flags = sorted({f for f in l.flags if not f.startswith(FLAG)} | {f"{FLAG}: {motivo}"})


def segnalato(flags) -> bool:
    return any(isinstance(f, str) and f.startswith(FLAG) for f in (flags or []))


def _diversi(gruppo: list[Listing]) -> int:
    """Quanti immobili diversi: due annunci con mq e prezzo quasi uguali contano una volta."""
    chiavi = set()
    for l in gruppo:
        chiavi.add((round((l.mq or 0) / 5), round((l.prezzo or 0) / 5000)))
    return len(chiavi)


def controlla(listings: list[Listing], cfg: dict) -> dict[str, str]:
    """Segna (flag ``indirizzo dell'agenzia: …``) gli annunci posizionati all'indirizzo
    dell'agenzia. Restituisce {uid: motivo}."""
    c = cfg.get("controllo_agenzia", {}) or {}
    if not c.get("attivo", True):
        return {}
    raggio = float(c.get("raggio_m", 30))
    min_imm = int(c.get("min_immobili", 3))
    ignora = set(c.get("ignora", []) or [])
    trovati: dict[str, str] = {}

    agenzie = [l for l in listings if l.agenzia and not l.privato and l.uid not in ignora
               and l.source not in ("pvp",)]
    nomi = {id(l): nome_agenzia(l.agenzia) for l in agenzie}

    # 1. sedi scritte in config
    for s in c.get("sedi", []) or []:
        nome = nome_agenzia(s.get("agenzia"))
        if not nome:
            continue
        punto = Listing(source="sede", source_id=nome, indirizzo=s.get("indirizzo"),
                        lat=s.get("lat"), lon=s.get("lon"))
        for l in agenzie:
            if l.uid in trovati or not _stessa_agenzia(nomi[id(l)], nome):
                continue
            vicino = punto.lat is not None and l.coord_precise and distanza_m(l, punto) <= raggio
            if vicino or _stesso_indirizzo(l.indirizzo, punto.indirizzo):
                trovati[l.uid] = f"coincide con la sede di {s.get('agenzia')}" + \
                    (f" ({s['indirizzo']})" if s.get("indirizzo") else "")

    # 2. sede scritta nel testo dell'annuncio
    for l in agenzie:
        if l.uid in trovati or not l.indirizzo:
            continue
        for sede in sedi_nel_testo(f"{l.titolo or ''}. {l.descrizione or ''}"):
            if _stesso_indirizzo(l.indirizzo, sede):
                trovati[l.uid] = f"l'annuncio scrive che la sede dell'agenzia è in {sede}"
                break

    # 3. tanti immobili diversi della stessa agenzia nello stesso punto
    precisi = [l for l in listings if l.lat is not None and l.lon is not None and l.coord_precise]
    per_agenzia: dict[str, list[Listing]] = defaultdict(list)
    for l in agenzie:
        if l.lat is not None and l.lon is not None and l.coord_precise and nomi[id(l)]:
            per_agenzia[nomi[id(l)]].append(l)
    for nome, gruppo in per_agenzia.items():
        if len(gruppo) < min_imm:
            continue
        for l in gruppo:
            vicini = [x for x in gruppo if distanza_m(l, x) <= raggio]
            n = _diversi(vicini)
            if n < min_imm:
                continue
            nuovi = sum(1 for x in vicini if x.stato == "nuovo" or _NUOVO.search(f"{x.titolo} {x.descrizione}"))
            if nuovi * 2 >= len(vicini):
                continue        # cantiere: tanti appartamenti nuovi nello stesso stabile
            dentro = {id(x) for x in vicini}
            altri = [x for x in precisi if id(x) not in dentro and distanza_m(l, x) <= raggio
                     and not _stessa_agenzia("" if x.privato else nome_agenzia(x.agenzia), nome)]
            if _diversi(altri) >= 2:
                continue        # punto generico (centro del paese/via), non l'ufficio
            for x in vicini:
                trovati.setdefault(x.uid, f"probabile: {n} immobili diversi di {l.agenzia} nello stesso punto "
                                          f"della mappa{' (' + x.indirizzo + ')' if x.indirizzo else ''}")

    for l in listings:
        if l.uid in trovati:
            _segna(l, trovati[l.uid])
    if trovati:
        log.warning("annunci all'indirizzo dell'agenzia (fuori dalle mediane): %d", len(trovati))
        per_uid = {l.uid: l for l in listings}
        for uid, motivo in sorted(trovati.items(), key=lambda t: (per_uid[t[0]].agenzia or "", t[0]))[:40]:
            l = per_uid[uid]
            log.info("  sede agenzia | %s | %s | %s | %s mq %s € | %s | %s", l.agenzia, l.comune or "",
                     l.indirizzo or "-", f"{l.mq:g}" if l.mq else "?", f"{l.prezzo:,.0f}" if l.prezzo else "?",
                     motivo, l.url)
    return trovati


__all__ = ["FLAG", "controlla", "nome_agenzia", "sedi_nel_testo", "segnalato"]
