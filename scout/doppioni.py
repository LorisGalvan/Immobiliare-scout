"""Stesso immobile pubblicato più volte (da più agenzie o su più portali).

Le agenzie raramente scrivono gli stessi numeri: una mette 95 mq e l'altra 100, una chiede
229.000 € e l'altra 235.000 €, le coordinate di Immobiliare sono spesso il centro del quartiere.
Per questo non basta che tutto coincida: ogni indizio dà punti e si decide sul totale.

Indizi a favore: numero di procedura uguale (aste), stessa via e civico, mq e prezzo vicini,
stesso piano e numero di locali, testo della descrizione simile (molte agenzie copiano lo stesso).
Indizi che escludono: procedure o lotti diversi, piani diversi, mq o prezzo troppo lontani,
annunci a più di 1,5 km (con posizioni precise).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .models import Listing
from .normalize import piano_num

# soglia di punti per dire "stesso immobile"
SOGLIA = 5

# ---------------------------------------------------------------------- numero di procedura
# il numero va letto solo vicino a parole da asta, così "rif. 12/2024" di un'agenzia non conta
_PROC_CONTESTO = re.compile(
    r"r\.?\s?g\.?\s?(?:e|es|esec)?\.?|procedur[ae]|proc\.|esecuzion[ei]|esecutiv[ae]|e\.\s?i\.|es\.\s?imm"
    r"|fallimento|fall\.|liquidazione|concordato|tribunale|trib\.|ruolo", re.I)
_PROC_NUM = re.compile(r"(?<![\d/])(?<!\d[.,])(\d{1,5})\s*/\s*((?:19|20)?\d{2})(?![\d/]|[.,]\d|\s*/\s*\d)")
_LOTTO = re.compile(r"\blotto\s*(?:n\.?|nr\.?|n°|numero)?\s*°?\s*(\d{1,3}|unico)\b", re.I)


def numeri_procedura(testo: str | None) -> set[str]:
    """Numeri di procedura scritti nel testo, normalizzati come "264/2025"."""
    out = set()
    for m in _PROC_NUM.finditer(testo or ""):
        prima = testo[max(0, m.start() - 60):m.start()]
        if not _PROC_CONTESTO.search(prima):
            continue
        n, anno = int(m.group(1)), int(m.group(2))
        anno = anno + 2000 if anno < 100 else anno
        if 1990 <= anno <= 2035 and n > 0:
            out.add(f"{n}/{anno}")
    return out


def lotti(testo: str | None) -> set[str]:
    return {m.group(1).lower().lstrip("0") or "0" for m in _LOTTO.finditer(testo or "")}


# ---------------------------------------------------------------------- testo e indirizzo
_PAROLA = re.compile(r"[a-zà-ü0-9]+")


def impronta(testo: str | None) -> frozenset:
    """Gruppi di 3 parole consecutive: due descrizioni copiate ne hanno molti in comune."""
    w = [x for x in _PAROLA.findall((testo or "").lower()) if len(x) > 2]
    return frozenset(" ".join(w[i:i + 3]) for i in range(len(w) - 2))


def somiglianza(a: frozenset, b: frozenset) -> float:
    if len(a) < 8 or len(b) < 8:     # testi troppo corti per dire qualcosa
        return 0.0
    return len(a & b) / min(len(a), len(b))


_TIPO_VIA = re.compile(r"^(?:via|viale|v\.le|corso|c\.so|piazza|p\.za|piazzale|vicolo|vic\.|lungadige|stradone"
                       r"|strada|largo|contr[aà]|localit[aà]|loc\.)\s+", re.I)


def via_civico(indirizzo: str | None) -> tuple[str | None, str | None]:
    if not indirizzo:
        return None, None
    s = indirizzo.lower().split(",")
    via = _TIPO_VIA.sub("", s[0].strip())
    civ = re.search(r"\b(\d{1,4})\s*([a-z])?\b", " ".join(s[:2]))
    nome = re.sub(r"[^a-zà-ü]", "", re.sub(r"\d.*$", "", via))
    if len(nome) < 4:
        return None, None
    return nome, (civ.group(1) + (civ.group(2) or "")) if civ else None


def stessa_via(a: str | None, b: str | None) -> bool:
    """"mameli" e "goffredomameli" sono la stessa via (un'agenzia scrive il nome intero)."""
    if not a or not b:
        return False
    corto, lungo = sorted((a, b), key=len)
    return corto == lungo or (len(corto) >= 5 and lungo.endswith(corto))


def distanza_m(a: Listing, b: Listing) -> float:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return math.inf
    kx = 111_320 * math.cos(math.radians(a.lat))
    return math.hypot((a.lon - b.lon) * kx, (a.lat - b.lat) * 110_540)


# ---------------------------------------------------------------------- confronto
@dataclass
class Scheda:
    """Dati di un annuncio pronti per il confronto (calcolati una volta sola)."""
    l: Listing
    procedure: set
    lotti: set
    via: str | None
    civico: str | None
    testo: frozenset

    @classmethod
    def da(cls, l: Listing) -> "Scheda":
        t = f"{l.titolo or ''} {l.descrizione or ''}"
        via, civ = via_civico(l.indirizzo)
        return cls(l, numeri_procedura(t), lotti(t), via, civ, impronta(l.descrizione))


def confronta(a: Scheda, b: Scheda, asta: bool = False) -> tuple[int, list[str]]:
    """Punteggio "stesso immobile" e motivi. Un punteggio negativo grande vuol dire "sicuramente no"."""
    NO = -100
    x, y = a.l, b.l
    if x.uid == y.uid:
        return NO, ["stesso annuncio"]
    motivi, p = [], 0
    ident = 0      # indizi che dicono "è proprio quello" (procedura, indirizzo, posizione, testo)
    # --- aste: il numero di procedura decide
    stessa_proc = bool(a.procedure & b.procedure)
    if a.procedure and b.procedure and not stessa_proc:
        return NO, ["procedure diverse"]
    if a.lotti and b.lotti and not (a.lotti & b.lotti):
        return NO, ["lotti diversi"]
    if stessa_proc:
        p += 6
        ident += 6
        motivi.append(f"stessa procedura {sorted(a.procedure & b.procedure)[0]}")
    # --- mq
    if x.mq and y.mq:
        d = abs(x.mq - y.mq)
        rel = d / max(x.mq, y.mq)
        if d <= 3 or rel <= 0.03:
            p += 2
            motivi.append("stessi mq")
        elif rel <= 0.08:
            p += 1
            motivi.append("mq simili")
        elif rel > (0.15 if stessa_proc else 0.08):
            return NO, ["mq diversi"]
    # --- prezzo (alle aste un portale mostra il prezzo base, un altro l'offerta minima = -25%)
    if x.prezzo and y.prezzo:
        rel = abs(x.prezzo - y.prezzo) / max(x.prezzo, y.prezzo)
        if rel <= 0.03:
            p += 2
            motivi.append("stesso prezzo")
        elif rel <= 0.10:
            p += 1
            motivi.append("prezzo simile")
        elif rel > (0.30 if asta or stessa_proc else 0.15):
            return NO, ["prezzo troppo diverso"]
    # --- piano, locali, bagni
    if x.piano and y.piano:
        if x.piano != y.piano and piano_num(x.piano) != piano_num(y.piano):
            return NO, ["piano diverso"]
        p += 1
        motivi.append("stesso piano")
    if x.locali and y.locali:
        if abs(x.locali - y.locali) >= 2:
            return NO, ["locali diversi"]
        p += 1 if x.locali == y.locali else -1
    if x.bagni and y.bagni and x.bagni != y.bagni:
        p -= 1
    # --- posizione
    dist = distanza_m(x, y)
    precise = x.coord_precise and y.coord_precise
    if precise and dist != math.inf and dist > 1500 and not stessa_proc:
        return NO, ["troppo lontani"]
    if stessa_via(a.via, b.via):
        if a.civico and b.civico and a.civico != b.civico:
            if not stessa_proc:
                return NO, ["civico diverso"]
        else:
            v = 3 if (a.civico and a.civico == b.civico) else 2
            p, ident = p + v, ident + v
            motivi.append("stesso indirizzo" if a.civico and a.civico == b.civico else "stessa via")
    elif dist <= 150 and not (x.source == y.source and dist < 1):
        # coordinate identiche sullo stesso portale = di solito il centro del quartiere, non l'indirizzo
        v = 2 if precise and dist <= 40 else 1      # stesso edificio
        p, ident = p + v, ident + v
        motivi.append("stessa posizione sulla mappa")
    elif x.microzona and y.microzona and x.microzona != y.microzona:
        p -= 2
    # --- testo copiato
    s = somiglianza(a.testo, b.testo)
    if s >= 0.5:
        p, ident = p + 3, ident + 3
        motivi.append(f"testo quasi uguale ({s:.0%})")
    elif s >= 0.3:
        p, ident = p + 2, ident + 2
        motivi.append(f"testo simile ({s:.0%})")
    elif s >= 0.15:
        p, ident = p + 1, ident + 1
    # la stessa agenzia sullo stesso portale non ripubblica quasi mai lo stesso immobile:
    # due annunci così sono di solito appartamenti diversi dello stesso stabile
    if x.source == y.source and x.agenzia and x.agenzia == y.agenzia:
        p -= 2
    # mq, prezzo e piano uguali da soli non bastano: in una città ci sono tanti trilocali da 90 mq
    # a 250.000 €. Serve almeno un indizio sul "dove" o un testo in comune.
    if ident < 2:
        p = min(p, SOGLIA - 1)
    return p, motivi


def stesso_immobile(a: Listing, b: Listing, asta: bool = False, soglia: int = SOGLIA) -> bool:
    return confronta(Scheda.da(a), Scheda.da(b), asta)[0] >= soglia


def raggruppa(listings: list[Listing], asta: bool = False, puo_unire=None,
              soglia: int = SOGLIA) -> list[list[Listing]]:
    """Gruppi di annunci dello stesso immobile. Un annuncio entra in un gruppo solo se è
    compatibile con tutti quelli già dentro (niente catene A~B~C con A e C diversi)."""
    schede = [Scheda.da(l) for l in listings]
    n = len(schede)
    gruppo = list(range(n))
    membri = {i: [i] for i in range(n)}

    def compatibili(gi, gj) -> bool:
        return all(confronta(schede[i], schede[j], asta)[0] > -100 for i in membri[gi] for j in membri[gj])

    # coppie candidate: ordinate per mq si confrontano solo quelle vicine; chi non ha mq
    # (lotti del PVP) si confronta con tutti
    con_mq = sorted((i for i in range(n) if listings[i].mq), key=lambda i: listings[i].mq)
    senza = [i for i in range(n) if not listings[i].mq]
    coppie = []
    for pos, i in enumerate(con_mq):
        mi = listings[i].mq
        for j in con_mq[pos + 1:]:
            if listings[j].mq - mi > max(5, 0.15 * mi):
                break
            coppie.append((i, j))
    for i in senza:
        coppie += [(i, j) for j in range(n) if j != i and (listings[j].mq or j > i)]
    punteggi = []
    for i, j in coppie:
        if puo_unire is not None and not puo_unire(listings[i], listings[j]):
            continue
        p, _ = confronta(schede[i], schede[j], asta)
        if p >= soglia:
            punteggi.append((p, i, j))
    # prima le coppie più sicure
    for _, i, j in sorted(punteggi, key=lambda t: -t[0]):
        gi, gj = gruppo[i], gruppo[j]
        if gi == gj or not compatibili(gi, gj):
            continue
        for k in membri[gj]:
            gruppo[k] = gi
        membri[gi] += membri.pop(gj)
    return [[listings[i] for i in m] for m in membri.values()]


def descrivi(x: Listing) -> str:
    """Riga di un doppione come la mostra il sito: "fonte: url (inserzionista, prezzo€)"."""
    chi = "privato" if x.privato else (x.agenzia or "?")
    prezzo = f"{x.prezzo:,.0f}€" if x.prezzo else "prezzo ?"
    return f"{x.source}: {x.url} ({chi}, {prezzo})"


def segnala_gruppo(rep: Listing, g: list[Listing]) -> None:
    """Flag sul rappresentante: quanti inserzionisti e, se diversi, la forbice di prezzo."""
    chi = {("privato" if x.privato else (x.agenzia or "").strip().lower()) for x in g} - {""}
    flags = {f for f in rep.flags if not f.startswith(("pubblicato da ", "prezzi diversi tra "))}
    if len(chi) > 1:
        flags.add(f"pubblicato da {len(chi)} inserzionisti")
    prezzi = [x.prezzo for x in g if x.prezzo]
    if len(prezzi) > 1 and max(prezzi) - min(prezzi) > 0.01 * max(prezzi):
        flags.add(f"prezzi diversi tra gli annunci: {min(prezzi):,.0f}–{max(prezzi):,.0f} €".replace(",", "."))
    rep.flags = sorted(flags)
