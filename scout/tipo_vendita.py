"""Tipo di vendita: compravendita normale o asta giudiziaria.

Legge titolo, descrizione, tipologia e nome dell'inserzionista e assegna un punteggio:
gli indizi "forti" (tribunale, R.G.E., prezzo base, offerta minima, delegato alla vendita...)
bastano da soli, quelli "deboli" (la parola "asta" da sola, agenzie specializzate in aste)
servono in coppia. Le frasi che negano ("non è un'asta", "no aste") vengono tolte prima.

Risultato:
- ``compravendita``: annuncio normale, entra nella valutazione del territorio;
- ``asta``: vendita giudiziaria/fallimentare, esce dalle mediane e va nella lista Aste;
- ``possibile_asta``: un solo indizio debole; esce dalle mediane per prudenza e va
  nella lista Aste come "da verificare".
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache

# (regex, etichetta mostrata all'utente)
FORTI = [
    (r"\baste?\s+giudiziari[ae]\b", "asta giudiziaria"),
    (r"\bvendit[ae]\s+giudiziari[ae]\b", "vendita giudiziaria"),
    (r"\besecuzion[ei]\s+immobiliar[ei]\b|\bprocedur[ae]\s+esecutiv[ae]\b|\besecuzione\s+forzata\b"
     r"|\bproc\.\s*esec\.", "esecuzione immobiliare"),
    (r"\br\.?\s?g\.?\s?(?:e|es|esec)\.?\s*(?:n\.?|nr\.?|n°|num\.?|numero)?\s*°?\s*\d+\s*/\s*\d{2,4}\b", "numero R.G.E."),
    # "Procedura n. 264/2025", "proc. esec. imm. nr 264/25", "E.I. 264/2025", "es. imm. n° 12/2024"
    (r"\b(?:procedur[ae]|proc\.)\s*(?:esecutiv[ae]\s*|esec\.\s*|immobiliar[ei]\s*|imm\.\s*|concorsual[ei]\s*"
     r"|fallimentar[ei]\s*|n\.?\s*r\.?\s*g\.?\s*e?\.?\s*)*(?:n\.?|nr\.?|n°|num\.?|numero)\s*°?\s*\d{1,5}\s*/\s*(?:19|20)?\d{2}\b"
     r"|\b(?:e\.\s?i\.|es\.\s?imm\.|esec\.\s?imm\.)\s*(?:n\.?|nr\.?|n°)?\s*°?\s*\d{1,5}\s*/\s*(?:19|20)?\d{2}\b",
     "numero di procedura"),
    (r"\bgiudice\s+dell['’]?\s?esecuzione\b|\bg\.\s?e\.\s+(?:dott|dr|avv)", "giudice dell'esecuzione"),
    # "Tribunale di Verona ... n. 264/2025" (numero di ruolo vicino al tribunale)
    (r"\btrib(?:unale|\.)\s+(?:di|ordinario)\b[^.\n]{0,80}?\b(?:n\.?|nr\.?|n°)\s*°?\s*\d{1,5}\s*/\s*(?:19|20)\d{2}\b",
     "tribunale + numero di procedura"),
    (r"\b(?:professionista\s+)?delegat[oa]\s+(?:alla|per\s+la)\s+vendita\b", "delegato alla vendita"),
    (r"\bcustode\s+giudiziari[oa]\b|\bistituto\s+vendite\s+giudiziarie\b|\bi\.?v\.?g\.?\b", "custode / IVG"),
    (r"\bprezzo\s+(?:base|d['’]asta)\b|\bbase\s+d['’]asta\b", "prezzo base d'asta"),
    (r"\bofferta\s+minima\b", "offerta minima"),
    (r"\brilancio\s+minimo\b", "rilancio minimo"),
    (r"\bvendita\s+(?:senza|con)\s+incanto\b|\basta\s+(?:telematica|sincrona|asincrona)\b", "modalità d'asta"),
    (r"\b(?:primo|secondo|terzo|quarto|quinto|\d+°?)\s+esperimento\s+di\s+vendita\b|\besperimento\s+d['’]asta\b", "esperimento di vendita"),
    (r"\bportale\s+(?:delle\s+)?vendite\s+pubbliche\b|\bpvp\.giustizia\b|astegiudiziarie\.it|astalegale|\bfallcoaste\b", "portale aste"),
    (r"\bfallimento\b|\bfallimentar[ei]\b|\bprocedura\s+concorsuale\b|\bliquidazione\s+giudiziale\b|\bvendita\s+competitiva\b", "procedura fallimentare"),
    (r"(?<![a-zà-ü])all['’]\s?asta\b|\bin\s+asta\b|\bvendita\s+all['’]asta\b|\bimmobile\s+(?:da|in)\s+asta\b", "\"all'asta\" / \"in asta\""),
    (r"\bdata\s+(?:dell['’]\s*)?asta\b|\bdata\s+(?:della\s+)?vendita\s*:?\s*\d", "data dell'asta"),
    (r"\bcauzione\s+(?:pari\s+al\s+)?10\s?%|\bsaldo\s+prezzo\s+entro\s+\d+\s+giorni", "cauzione / saldo prezzo"),
]
DEBOLI = [
    (r"\basta\b|\baste\b", "parola \"asta\""),
    (r"\bdecreto\s+di\s+trasferimento\b", "decreto di trasferimento"),
    (r"\bpignorat[oa]\b|\bpignoramento\b", "pignoramento"),
    (r"\bperizia\s+(?:di\s+stima|ctu)\b|\bc\.?t\.?u\.?\b", "perizia CTU"),
]
# conta solo se c'è già un altro indizio ("vicino al Tribunale di Verona" da solo non vuol dire nulla)
CONTORNO = [(r"\btribunale\s+(?:di|ordinario)\b", "tribunale")]

# frasi da togliere prima di cercare: non indicano un'asta
NEGAZIONI = [
    r"\bnon\s+(?:è|e['’]|si\s+tratta\s+di)\s+(?:un['’]\s*|una\s+)?(?:asta|vendita\s+giudiziaria)\b",
    r"\bno\s+aste\b|\bniente\s+aste\b|\bnessuna\s+asta\b|\bnon\s+proveniente\s+da\s+asta\b|\bnon\s+da\s+asta\b",
    r"\bevitare\s+l['’]\s?asta\b|\bprima\s+dell['’]\s?asta\b|\bper\s+evitare\s+(?:l['’]\s?)?asta\b",
    r"\bstanchi\s+di\s+aste\b",
    r"\bvasta\b|\bpasta\b|\bcasta\b|\bbasta\b|\bmasta\b",   # parole che contengono "asta"
    r"\basta\s+(?:dell['’]|della|del)\s+(?:bandiera|doccia|tenda)\b",
]
# inserzionisti specializzati in aste (spesso pubblicano lotti giudiziari come annunci normali)
AGENZIA_ASTE = re.compile(r"\baste?\b|\bauction|\bgiudiziari", re.I)


# parole chiave scritte con un refuso ("esecutva", "procedra", "giudizaria", "deleagto"):
# il testo viene cercato anche in una copia dove queste parole sono corrette
VOCABOLARIO = ("esecutiva", "esecutive", "esecuzione", "esecuzioni", "procedura", "procedure", "giudiziaria",
               "giudiziarie", "giudiziario", "delegato", "delegata", "tribunale", "immobiliare", "fallimentare",
               "fallimento", "pignorato", "pignoramento", "concorsuale", "esperimento", "incanto", "custode")
_PAROLA = re.compile(r"[a-zà-ü]{6,16}")


@lru_cache(maxsize=50_000)
def _correggi_parola(w: str) -> str:
    if w in VOCABOLARIO:
        return w
    simili = difflib.get_close_matches(w, VOCABOLARIO, n=1, cutoff=0.84)
    return simili[0] if simili else w


def _correggi_refusi(testo: str) -> str:
    return _PAROLA.sub(lambda m: _correggi_parola(m.group(0)), testo)


@dataclass
class Esito:
    tipo: str = "compravendita"
    punteggio: int = 0
    indizi: list = field(default_factory=list)


def classifica(titolo: str | None = None, descrizione: str | None = None, tipologia: str | None = None,
               agenzia: str | None = None, flags: list | None = None) -> Esito:
    testo = " ".join(x for x in (titolo, descrizione, tipologia) if x).lower()
    testo = re.sub(r"\s+", " ", testo)
    corretto = _correggi_refusi(testo)
    if corretto != testo:
        testo = testo + " \n " + corretto      # cerca sia nel testo originale sia in quello corretto
    for neg in NEGAZIONI:
        testo = re.sub(neg, " ", testo)
    indizi, punti = [], 0
    for rx, lab in FORTI:
        if re.search(rx, testo):
            indizi.append(lab)
            punti += 3
    trovati_deboli = set()
    for rx, lab in DEBOLI:
        if re.search(rx, testo):
            trovati_deboli.add(lab)
    # un indizio forte sulla parola "asta" la contiene già: non la conto due volte
    if any("asta" in i for i in indizi):
        trovati_deboli.discard("parola \"asta\"")
    for lab in sorted(trovati_deboli):
        indizi.append(lab)
        punti += 1
    if tipologia and re.search(r"\basta\b|\baste\b|auction", tipologia.lower()):
        indizi.append("tipologia del portale: asta")
        punti += 3
    for f in flags or []:
        if "portale: asta" in str(f):
            indizi.append("segnalato come asta dal portale")
            punti += 3
    if punti:
        for rx, lab in CONTORNO:
            if re.search(rx, testo):
                indizi.append(lab)
                punti += 1
    if agenzia and AGENZIA_ASTE.search(agenzia):
        indizi.append(f"inserzionista specializzato ({agenzia})")
        punti += 1
    if punti >= 3:
        tipo = "asta"
    elif punti >= 1:
        tipo = "possibile_asta"
    else:
        tipo = "compravendita"
    return Esito(tipo, punti, indizi)


def classifica_listing(l) -> Esito:
    return classifica(l.titolo, l.descrizione, l.tipologia, l.agenzia, l.flags)


# ---------------------------------------------------------------- diritto e occupazione (per le aste)
_FRAZ = re.compile(r"(?:propriet[aà]|quota)[^.;\n]{0,30}?\b(\d{1,4})\s*/\s*(\d{1,4})\b", re.I)


def diritto(testo: str | None) -> str | None:
    """Diritto venduto: "piena proprietà", "quota 1/2", "nuda proprietà", "usufrutto"...
    None se il testo non lo dice (da verificare sulla perizia)."""
    t = (testo or "").lower()
    if not t:
        return None
    if re.search(r"nuda\s+propriet", t):
        return "nuda proprietà"
    if re.search(r"diritto\s+di\s+superficie|propriet[aà]\s+superficiaria", t):
        return "diritto di superficie"
    piena = re.search(r"piena\s+(?:ed\s+esclusiva\s+)?propriet|intera\s+propriet|propriet[aà]\s+esclusiva", t)
    if re.search(r"(?<!libero da )(?<!libera da )(?<!senza )\busufrutto\b", t) and not piena:
        return "usufrutto"
    if re.search(r"diritto\s+di\s+abitazione", t) and not piena:
        return "diritto di abitazione"
    frazioni = [(int(a), int(b)) for a, b in _FRAZ.findall(t) if int(b) > 0]
    parziali = [f"{a}/{b}" for a, b in frazioni if a != b]
    if parziali:
        return "quota " + parziali[0]
    if re.search(r"quota\s+(?:indivisa|parte)\b|pro\s?-?quota", t):
        return "quota"
    if frazioni or piena:
        return "piena proprietà"
    return None


def occupazione(testo: str | None) -> str | None:
    t = (testo or "").lower()
    if re.search(r"\blibero\b|libero da persone|\bliberat[oa]\b|non occupat", t) and "non libero" not in t:
        return "libero"
    if re.search(r"\blocat[oa]\b|contratto di locazione", t):
        return "locato"
    if re.search(r"\boccupat[oa]\b", t):
        return "occupato dal debitore" if re.search(r"debitor|esecutat", t) else "occupato"
    return None
