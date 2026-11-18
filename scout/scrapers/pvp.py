"""Portale delle Vendite Pubbliche del Ministero della Giustizia (pvp.giustizia.it).

È l'elenco ufficiale di TUTTE le aste giudiziarie: ogni lotto vi deve essere pubblicato
per legge. I lotti diventano annunci con ``source="pvp"`` e il segnale "portale: asta",
quindi finiscono sempre nella sezione Aste e mai nelle mediane del mercato libero.

Due modi per leggerli:

1. **Automatico** (``scraping.siti.pvp: true``): il bot interroga il servizio di ricerca
   che usa il sito del PVP (``aste_pvp.api_url``), filtrando per tribunale (poi per comune) e solo immobili,
   con lo stesso ritmo lento degli altri siti. Il servizio non è documentato: se il
   Ministero lo cambia, il bot lo segnala nel log e si usa il modo 2.
2. **Pagine salvate**: si apre la ricerca sul PVP nel browser e si salva la pagina
   (Ctrl+S, "Pagina web completa") in ``pagine_salvate/``. Va bene anche la risposta JSON
   del servizio salvata dagli strumenti per sviluppatori (file ``.json``).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re

from ..cleaning import mq_dal_testo
from ..models import Listing
from ..normalize import num
from ..tipo_vendita import diritto, occupazione
from .base import BloccatoError, PoliteClient

log = logging.getLogger(__name__)

BASE = "https://pvp.giustizia.it"
DETTAGLIO = BASE + "/pvp/it/detail_annuncio.page?idAnnuncio={id}"

# chiavi che identificano un lotto nel JSON del PVP (i nomi esatti cambiano tra versioni del sito)
_K_BASE = r"prezzo.?base|base.?d.?asta|prezzovalorebase|valore.?base"
_K_MIN = r"offerta.?minima|prezzo.?minimo|offertaMin"
_K_DATA = r"data.?(?:ora.?)?(?:vendita|asta|esperimento|udienza)"
_K_ID = r"^id.?annuncio$|^idannuncio$|^id.?lotto$|^id$"


def _find(d: dict, *patterns):
    """Primo valore di ``d`` (appiattito) la cui chiave corrisponde a un pattern."""
    for p in patterns:
        rx = re.compile(p, re.I)
        for k, v in d.items():
            if rx.search(k.split(".")[-1]) and v not in (None, "", [], {}):
                return v
    return None


def _flatten(o, prefix="", out=None) -> dict:
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            _flatten(v, f"{prefix}{k}.", out)
    elif isinstance(o, list):
        if o and not isinstance(o[0], (dict, list)):
            out[prefix[:-1]] = " ".join(map(str, o))
        for i, v in enumerate(o[:5]):
            if isinstance(v, (dict, list)):
                _flatten(v, f"{prefix}{i}.", out)
    else:
        out[prefix[:-1]] = o
    return out


def _walk(obj, pred) -> list[dict]:
    out, stack = [], [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if pred(o):
                out.append(o)
                continue
            stack.extend(reversed(list(o.values())))
        elif isinstance(o, list):
            stack.extend(reversed(o))
    return out


def _data(v) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) and v > 1e9:            # millisecondi o secondi
        return dt.datetime.fromtimestamp(v / (1000 if v > 1e11 else 1)).date().isoformat()
    s = str(v)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        g, me, a = map(int, m.groups())
        try:
            return dt.date(a, me, g).isoformat()
        except ValueError:
            return None
    return None


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return num(str(v)) if v not in (None, "") else None


def _eur(v: float | None) -> str:
    return f"€ {v:,.0f}".replace(",", ".") if v else ""


def _listing(*, sid: str, url: str, titolo: str, testo: str, indirizzo: str | None, comune: str | None,
             base: float | None, minima: float | None, data_asta: str | None, mq: float | None,
             lat: float | None, lon: float | None, tribunale: str | None, procedura: str | None,
             tipo: str | None = None) -> Listing:
    """Lotto PVP -> Listing. Prezzo base, offerta minima e data vanno anche nella descrizione,
    così l'analisi delle aste li legge come per gli altri portali."""
    righe = [titolo, comune or ""]
    if tribunale or procedura:
        righe.append(" ".join(x for x in (f"Tribunale di {tribunale}" if tribunale and "tribunale" not in tribunale.lower()
                                          else tribunale, f"R.G.E. {procedura}" if procedura else None) if x))
    if base:
        righe.append(f"Prezzo base {_eur(base)}")
    if minima:
        righe.append(f"Offerta minima {_eur(minima)}")
    if data_asta:
        a, m, g = data_asta.split("-")
        righe.append(f"Data asta {g}/{m}/{a}")
    righe.append(testo)
    descr = ". ".join(r.strip(" .") for r in righe if r and r.strip(" .")) + "."
    flags = ["portale: asta"]
    dir_ = diritto(descr)
    if dir_ and dir_ != "piena proprietà":
        flags.append(f"diritto: {dir_}")
    occ = occupazione(descr)
    if occ:
        flags.append(f"immobile {occ}")
    return Listing(source="pvp", source_id=sid, url=url, titolo=titolo[:200], descrizione=descr[:6000],
                   prezzo=minima or base, mq=mq, indirizzo=indirizzo or None,   # il comune lo aggiunge il geocoder
                   lat=lat, lon=lon, coord_precise=lat is not None,
                   tipologia=f"Asta giudiziaria - {tipo}" if tipo else "Asta giudiziaria",
                   agenzia=f"Tribunale di {tribunale}" if tribunale and "tribunale" not in tribunale.lower() else tribunale,
                   privato=False, flags=flags)


def lotti_da_json(data, comune: str | None = None) -> list[Listing]:
    """Trova nel JSON del PVP gli oggetti che sono lotti (hanno un prezzo base) e li converte."""
    cand = _walk(data, lambda o: any(re.search(_K_BASE, k, re.I) for k in o))
    out = []
    for o in cand:
        f = _flatten(o)
        base = _num(_find(f, _K_BASE))
        if not base:
            continue
        idv = _find(f, _K_ID) or hashlib.md5(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()[:12]
        url = _find(f, r"^url|link|href")
        url = str(url) if url else DETTAGLIO.format(id=idv)
        if not url.startswith("http"):
            url = BASE + "/" + url.lstrip("/")
        com = _find(f, r"^comune$|citt[aà]|^city$|descComune")
        testo = " ".join(str(v) for v in f.values() if isinstance(v, str) and len(v) > 25)
        if comune and comune.lower() not in (str(com) if com else testo).lower():
            continue                     # senza città nel lotto si guarda la descrizione
        tipo = _find(f, r"tipologia|categoria|descTipo|tipo.?bene")
        titolo = " ".join(str(x) for x in (tipo, _find(f, r"descrizione.?breve|titolo|descLotto")) if x) or "Lotto in asta"
        lat, lon = _num(_find(f, r"^lat(?:itudine)?$")), _num(_find(f, r"^(?:lon|lng|longitudine)$"))
        out.append(_listing(
            sid=str(idv), url=url, titolo=titolo, testo=testo,
            indirizzo=str(_find(f, r"^indirizzo|^via$|address") or "") or None, comune=str(com) if com else None,
            base=base, minima=_num(_find(f, _K_MIN)), data_asta=_data(_find(f, _K_DATA)),
            mq=_num(_find(f, r"superficie|^mq$|metri.?quadr")) or mq_dal_testo(testo),
            lat=lat if lat and 30 < lat < 50 else None, lon=lon if lon and 5 < lon < 20 else None,
            tribunale=str(_find(f, r"tribunale|ufficio.?giudiziario") or "") or None,
            procedura=_procedura(f), tipo=str(tipo) if tipo else None,
        ))
    return out


def _procedura(f: dict) -> str | None:
    n, a = _find(f, r"numero.?procedura|^rge$|numProcedura|^numero$"), _find(f, r"anno.?procedura|annoProcedura|^anno$")
    if n and a and "/" not in str(n):
        return f"{n}/{a}"
    return str(n) if n else None


# ---------------------------------------------------------------- pagina salvata (HTML)
_CARD_BASE = re.compile(r"prezzo\s*base[^0-9€]{0,30}€?\s*([\d.]+(?:,\d+)?)", re.I)
_CARD_MIN = re.compile(r"offerta\s*minima[^0-9€]{0,30}€?\s*([\d.]+(?:,\d+)?)", re.I)
_CARD_DATA = re.compile(r"(?:data\s*(?:e\s*ora\s*)?(?:vendita|asta|esperimento)|vendita\s*del|asta\s*del)[^0-9]{0,20}"
                        r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", re.I)
_CARD_VIA = re.compile(r"\b(?:via|viale|piazza|corso|vicolo|strada|lungadige|largo|localit[aà]|stradone)\s+[^,\n]{2,50}"
                       r"(?:,\s*\d+\w?)?", re.I)


def parse_search_page(html: str, comune: str | None = None) -> list[Listing]:
    """Schede dei lotti in una ricerca del PVP salvata dal browser."""
    from bs4 import BeautifulSoup

    # se nella pagina c'è il JSON dei risultati, è più affidabile delle schede
    for m in re.finditer(r"<script[^>]*>\s*(\{.*?\}|\[.*?\])\s*</script>", html, re.S):
        try:
            res = lotti_da_json(json.loads(m.group(1)), comune)
        except ValueError:
            continue
        if res:
            return res
    soup = BeautifulSoup(html, "lxml")
    out, visti = [], set()
    for el in soup.find_all(["article", "li", "div", "tr"]):
        txt = el.get_text(" ", strip=True)
        if not (60 < len(txt) < 3000) or len(_CARD_BASE.findall(txt)) != 1:
            continue
        # la scheda più interna che contiene il prezzo base
        if any(len(_CARD_BASE.findall(c.get_text(" ", strip=True))) == 1 and len(c.get_text(strip=True)) > 60
               for c in el.find_all(["article", "li", "div", "tr"])):
            continue
        if comune and comune.lower() not in txt.lower():
            continue
        a = el.find("a", href=re.compile(r"idAnnuncio|detail|dettaglio", re.I)) or el.find("a", href=True)
        url = a["href"] if a else ""
        if url and not url.startswith("http"):
            url = BASE + "/" + url.lstrip("/")
        mid = re.search(r"idAnnuncio=(\d+)", url) or re.search(r"(\d{5,})", url)
        sid = mid.group(1) if mid else hashlib.md5(txt[:300].encode()).hexdigest()[:12]
        if sid in visti:
            continue
        visti.add(sid)
        md, via = _CARD_DATA.search(txt), _CARD_VIA.search(txt)
        out.append(_listing(
            sid=sid, url=url or BASE, titolo=txt[:120], testo=txt, indirizzo=via.group(0) if via else None,
            comune=comune, base=num(_CARD_BASE.search(txt).group(1).rstrip(".")),
            minima=num(_CARD_MIN.search(txt).group(1).rstrip(".")) if _CARD_MIN.search(txt) else None,
            data_asta=_data(md.group(1)) if md else None, mq=mq_dal_testo(txt),
            lat=None, lon=None, tribunale=None, procedura=None,
        ))
    return out


# ---------------------------------------------------------------- automatico
def tribunale(cfg: dict) -> str:
    """Il servizio ignora il comune ma filtra per tribunale, scritto come sul sito: "Tribunale di VERONA".
    ``aste_pvp.tribunale`` serve quando il comune non è sede di tribunale (es. San Giovanni Lupatoto)."""
    t, p = cfg.get("territorio", {}), cfg.get("aste_pvp", {})
    nome = str(p.get("tribunale") or t.get("comune") or "").strip()
    nome = re.sub(r"^tribunale\s+di\s+", "", nome, flags=re.I)
    return f"Tribunale di {nome.upper()}"


def corpo_ricerca(cfg: dict, pagina: int) -> dict:
    t, p = cfg.get("territorio", {}), cfg.get("aste_pvp", {})
    corpo = {"tipoLotto": "IMMOBILI", "categoriaBene": p.get("categorie", []), "flagRicerca": 0,
             "tribunale": tribunale(cfg),
             "comune": t.get("comune"), "provincia": t.get("provincia"), "coordIndirizzo": "",
             "raggioIndirizzo": str(p.get("raggio_km", 0) or "")}
    corpo.update(p.get("filtri_extra") or {})
    return corpo


_DATA_ASTA = re.compile(r"Data asta (\d{2})/(\d{2})/(\d{4})")


def data_asta(l: Listing) -> dt.date | None:
    m = _DATA_ASTA.search(l.descrizione or "")
    return dt.date(int(m[3]), int(m[2]), int(m[1])) if m else None


def _salva_risposta(cfg: dict, pagina: int, data) -> None:
    """Copia della risposta in data/log/pvp/ per capire cosa restituisce il servizio (non documentato)."""
    try:
        from ..config import resolve
        cartella = resolve(cfg, "data/log/pvp")
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / f"pagina_{pagina + 1}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1)[:5_000_000],
                                                            encoding="utf-8")
    except OSError as e:
        log.debug("PVP: risposta non salvata (%s)", e)


def _totale(data) -> int | None:
    """Numero totale di risultati, se il servizio lo dice (totalElements, totale...)."""
    for o in _walk(data, lambda o: any(re.search(r"^total(?:Elements|e|Count)?$|^numeroRisultati$", k, re.I) for k in o)):
        for k, v in o.items():
            if re.search(r"^total(?:Elements|e|Count)?$|^numeroRisultati$", k, re.I) and isinstance(v, (int, float)):
                return int(v)
    return None


def _ultima_pagina(data, n_lotti: int, per_pagina: int) -> bool:
    """Il servizio dice se è l'ultima pagina ("last"); i lotti letti possono essere meno di quelli
    ricevuti (alcuni senza prezzo base), quindi contarli non basta."""
    corpo = data.get("body") if isinstance(data, dict) else None
    if isinstance(corpo, dict):
        if isinstance(corpo.get("last"), bool):
            return corpo["last"]
        if isinstance(corpo.get("content"), list):
            return len(corpo["content"]) < per_pagina
    return n_lotti < per_pagina


def _nel_comune(l: Listing, comune: str | None) -> bool:
    if not comune:
        return True
    return comune.lower() in f"{l.titolo} {l.descrizione} {l.indirizzo or ''}".lower()


def scrape(cfg: dict, client: PoliteClient) -> list[Listing]:
    p = cfg.get("aste_pvp", {})
    api = p.get("api_url")
    if not api:
        log.warning("PVP: manca aste_pvp.api_url in config; salva la ricerca dal browser in pagine_salvate/")
        return []
    comune = cfg.get("territorio", {}).get("comune")
    per_pagina = int(p.get("per_pagina", 50))
    # le aste già passate da più di N giorni non servono; si parte dalle più lontane nel futuro
    limite = dt.date.today() - dt.timedelta(days=int(p.get("giorni_passati", 60)))
    tutti: dict[str, Listing] = {}
    for pagina in range(int(p.get("max_pagine", 20))):
        url = f"{api}?language=it&page={pagina}&size={per_pagina}&sort=dataOraVendita,desc"
        try:
            r = client.post_json(url, corpo_ricerca(cfg, pagina))
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()
        except BloccatoError as e:
            log.error("PVP: %s", e)
            break
        except (PermissionError, RuntimeError, ValueError) as e:
            log.error("PVP: il servizio di ricerca non risponde come previsto (%s). "
                      "Salva la ricerca dal browser in pagine_salvate/ e usa 'importa-html'.", e)
            break
        _salva_risposta(cfg, pagina, data)
        grezzi = lotti_da_json(data)                       # tutti i lotti della risposta
        vecchi = [l for l in grezzi if (d := data_asta(l)) and d < limite]
        # comune letto dal campo città del lotto (nel testo c'è anche "Tribunale di Verona", che non basta)
        del_comune = {l.source_id for l in lotti_da_json(data, comune)}
        lotti = [l for l in grezzi if l.source_id in del_comune and _nel_comune(l, comune) and l not in vecchi]
        nuovi = [l for l in lotti if l.source_id not in tutti]
        for l in nuovi:
            tutti[l.source_id] = l
        totale = _totale(data)
        log.info("PVP pagina %d: %d lotti nella risposta%s, %d nel comune di %s",
                 pagina + 1, len(grezzi), f" (su {totale} totali)" if totale else "", len(nuovi), comune)
        altri = [l for l in grezzi if l.agenzia and tribunale(cfg).lower() not in l.agenzia.lower()]
        if grezzi and len(altri) > len(grezzi) / 2:
            log.warning("PVP: la maggior parte dei lotti ricevuti non è del %s: il servizio sembra ignorare il "
                        "filtro. Risposta salvata in data/log/pvp/ per controllarla.", tribunale(cfg))
        # si continua finché il servizio restituisce pagine piene (contando i lotti ricevuti, non quelli filtrati)
        # e finché nella pagina ci sono aste recenti (sono in ordine dalla più lontana nel futuro)
        if not grezzi or _ultima_pagina(data, len(grezzi), per_pagina) or len(vecchi) == len(grezzi):
            break
    return list(tutti.values())
