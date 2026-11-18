"""Scraper Immobiliare.it.

Le pagine di ricerca sono costruite con Next.js: i risultati sono nel JSON
``__NEXT_DATA__`` (oggetti con chiave ``realEstate``). Il parser cerca gli
oggetti in modo ricorsivo, così resiste a piccoli cambi di struttura.
"""
from __future__ import annotations

import logging
import re
import urllib.parse

from ..geo.polygons import immobiliare_search_url
from ..models import Listing
from ..normalize import num, piano, si_no, stato
from .base import BloccatoError, PoliteClient, fasce_prezzo, next_data, walk

log = logging.getLogger(__name__)
SOURCE = "immobiliare"
BASE = "https://www.immobiliare.it"


# ------------------------------------------------------------------ URL
def search_url(cfg: dict, page: int = 1, poligono=None, fascia: tuple | None = None) -> str:
    t = cfg["territorio"]
    f = cfg.get("scraping", {}).get("filtri", {})
    if poligono:
        url = immobiliare_search_url(poligono, t.get("slug_immobiliare", "verona"), page)
        sep = "&"
    else:
        q = {"criterio": "dataModifica", "ordine": "desc"}
        if page > 1:
            q["pag"] = page
        url = f"{BASE}/vendita-case/{t.get('slug_immobiliare', 'verona')}/?" + urllib.parse.urlencode(q)
        sep = "&"
    extra = {}
    pmin, pmax = fascia if fascia else (f.get("prezzo_min"), f.get("prezzo_max"))
    if pmin:
        extra["prezzoMinimo"] = int(pmin)
    if pmax:
        extra["prezzoMassimo"] = int(pmax)
    if f.get("mq_min"):
        extra["superficieMinima"] = int(f["mq_min"])
    return url + (sep + urllib.parse.urlencode(extra) if extra else "")


# ------------------------------------------------------------------ parsing
def _agency(re_: dict) -> tuple[str | None, bool | None]:
    adv = re_.get("advertiser") or {}
    ag = adv.get("agency") or {}
    if ag:
        if (ag.get("type") or "").lower() in ("private", "privato", "user"):
            return None, True
        return ag.get("displayName") or ag.get("name"), False
    sup = adv.get("supervisor") or {}
    if sup and (sup.get("type") or "").lower() in ("user", "private"):
        return None, True
    return None, None


def _features_text(p: dict) -> str:
    bits = []
    for key in ("ga4features", "features", "featureList"):
        v = p.get(key)
        if isinstance(v, list):
            bits += [x if isinstance(x, str) else str(x.get("label") or x.get("name") or "") for x in v]
    return " | ".join(bits).lower()


def parse_real_estate(re_: dict, seo: dict | None = None) -> Listing | None:
    rid = re_.get("id")
    if rid is None:
        return None
    props = re_.get("properties") or [{}]
    p = props[0] if props else {}
    price = re_.get("price") or {}
    prezzo = num(price.get("value")) if price.get("visible", True) else None
    if prezzo is None:
        prezzo = num(price.get("formattedValue"))
    ribasso = None
    lp = price.get("loweredPrice") or {}
    if lp.get("originalPrice"):
        ribasso = num(lp.get("originalPrice"))

    mq = num(p.get("surfaceValue")) or num(p.get("surface"))
    loc = p.get("location") or {}
    floor = p.get("floor") or {}
    piano_raw = floor.get("abbreviation") or floor.get("value") if isinstance(floor, dict) else floor
    # featureList: [{"type": "elevator", "label": "No Ascensore", "compactLabel": "No"}, ...]
    fl = {f.get("type"): f for f in (p.get("featureList") or []) if isinstance(f, dict)}
    asc = si_no(p.get("elevator"))
    if asc is None and "elevator" in fl:
        cl = str(fl["elevator"].get("compactLabel") or fl["elevator"].get("label") or "").strip().lower()
        asc = False if cl.startswith("no") else True if cl.startswith(("s", "ascensore")) else None
    if asc is None:
        feats = _features_text(p)
        if re.search(r"(?<!no )\bascensore\b", feats) and "no ascensore" not in feats and "senza ascensore" not in feats:
            asc = True
    if not piano_raw and "floor" in fl:
        piano_raw = fl["floor"].get("compactLabel") or fl["floor"].get("label")
    condizione = p.get("condition") or p.get("ga4Condition")
    agenzia, privato = _agency(re_)
    url = (seo or {}).get("url") or f"{BASE}/annunci/{rid}/"
    indirizzo = loc.get("address")
    if indirizzo and loc.get("streetNumber"):
        indirizzo = f"{indirizzo} {loc['streetNumber']}"

    # vendite all'asta segnalate dal portale (contratto "auction" o campi *auction*)
    flags = []
    contratto = str(re_.get("contract") or "").lower()
    if "auction" in contratto or "asta" in contratto or any(
            "auction" in k.lower() and v not in (None, False, "", [], {}) for k, v in re_.items()):
        flags.append("portale: asta")
    return Listing(
        flags=flags,
        source=SOURCE, source_id=str(rid), url=url,
        titolo=re_.get("title") or (seo or {}).get("title") or "",
        descrizione=p.get("description") or p.get("caption") or "",
        prezzo=prezzo, mq=mq, piano=piano(piano_raw), ascensore=asc,
        bagni=int(num(p.get("bathrooms"))) if num(p.get("bathrooms")) else None,
        locali=int(num(p.get("rooms"))) if num(p.get("rooms")) else None,
        stato=stato(condizione), stato_raw=condizione,
        agenzia=agenzia, privato=privato,
        indirizzo=indirizzo,
        lat=num(loc.get("latitude")), lon=num(loc.get("longitude")),
        coord_precise=bool((loc.get("marker") or "") != "zone") if loc else False,
        tipologia=("Progetto" if re_.get("isProjectLike") else
                   (p.get("typologyGA4Translation") or (re_.get("typology") or {}).get("name"))),
        prezzo_ribassato_da=ribasso,
    )


def _json_embedded(html: str):
    """Oggetti JSON con "realEstate" sparsi nella pagina, in qualsiasi formato:
    __NEXT_DATA__, flusso React Server Components (self.__next_f.push), JSON
    con escape HTML. Usa raw_decode a partire da ogni '{"realEstate":'."""
    import html as _html
    import json as _json

    testi = [html]
    # payload RSC: self.__next_f.push([1,"...stringa JSON con escape..."])
    rsc = re.findall(r'self\.__next_f\.push\(\[\d+,\s*("(?:[^"\\]|\\.)*")\]\)', html)
    if rsc:
        try:
            testi.append("".join(_json.loads(x) for x in rsc))
        except ValueError:
            pass
    if "&quot;realEstate&quot;" in html:
        testi.append(_html.unescape(html))
    dec = _json.JSONDecoder()
    for t in testi:
        for m in re.finditer(r'\{"realEstate"\s*:', t):
            try:
                obj, _ = dec.raw_decode(t, m.start())
                yield obj
            except ValueError:
                continue
        for m in re.finditer(r'"maxPages"\s*:\s*(\d+)', t):
            yield {"maxPages": int(m.group(1))}


def _da_html(html: str) -> list[Listing]:
    """Ultima risorsa: legge le schede dall'HTML visibile (senza coordinate)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/annunci/(\d+)")):
        sid = re.search(r"/annunci/(\d+)", a["href"]).group(1)
        if sid in seen:
            continue
        card = a
        for _ in range(8):   # risale fino al contenitore della scheda
            if card.parent is None:
                break
            card = card.parent
            if card.name in ("li", "article") or "€" in card.get_text():
                if card.name in ("li", "article"):
                    break
        testo = card.get_text(" ", strip=True)
        prezzo = num(re.search(r"€\s*[\d\.]+", testo).group(0)) if re.search(r"€\s*[\d\.]+", testo) else None
        mq = re.search(r"(\d+(?:[\.,]\d+)?)\s*m²", testo)
        if not prezzo or not mq:
            continue
        seen.add(sid)
        titolo = a.get("title") or a.get_text(" ", strip=True)
        bagni = re.search(r"(\d+)\s*bagn", testo, re.I)
        locali = re.search(r"(\d+)\+?\s*local", testo, re.I)
        pia = re.search(r"(piano\s+\w+|\b\d+°\s*piano|piano terra|rialzato|attico)", testo, re.I)
        from ..geo.geocode import estrai_indirizzo
        indirizzo = estrai_indirizzo(titolo) or estrai_indirizzo(testo)
        out.append(Listing(
            source=SOURCE, source_id=sid,
            url=a["href"] if a["href"].startswith("http") else BASE + a["href"],
            titolo=titolo, prezzo=prezzo, mq=num(mq.group(1)),
            bagni=int(bagni.group(1)) if bagni else None,
            locali=int(locali.group(1)) if locali else None,
            piano=piano(pia.group(1)) if pia else None,
            indirizzo=indirizzo, coord_precise=False,
        ))
    return out


def parse_search_page(html: str) -> tuple[list[Listing], int | None]:
    """Restituisce (annunci, numero_pagine_totali)."""
    out, seen, max_pages = [], set(), None
    sorgenti = []
    data = next_data(html)
    if data:
        sorgenti.append(walk(data))
    sorgenti.append(_json_embedded(html))
    for it in sorgenti:
        for d in it:
            if not isinstance(d, dict):
                continue
            if "maxPages" in d and isinstance(d.get("maxPages"), int):
                max_pages = max(max_pages or 0, d["maxPages"])
            re_ = d.get("realEstate")
            if isinstance(re_, dict) and "properties" in re_:
                l = parse_real_estate(re_, d.get("seo"))
                if l and l.source_id not in seen:
                    seen.add(l.source_id)
                    out.append(l)
    if not out:
        out = _da_html(html)
    return out, max_pages


_DATA_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def parse_detail_page(html: str, base: Listing) -> Listing:
    """Arricchisce un annuncio con descrizione completa, ascensore, data."""
    data = next_data(html)
    if not data:
        return base
    for d in walk(data):
        re_ = d.get("realEstate")
        if isinstance(re_, dict) and re_.get("id") is not None and str(re_["id"]) == base.source_id:
            full = parse_real_estate(re_)
            if full:
                for k, v in full.__dict__.items():
                    if v not in (None, "", []) and getattr(base, k) in (None, "", []):
                        setattr(base, k, v)
                if full.descrizione and len(full.descrizione) > len(base.descrizione or ""):
                    base.descrizione = full.descrizione
        # righe "etichetta/valore" della scheda caratteristiche
        label = d.get("label") or d.get("title")
        value = d.get("value") or d.get("description")
        if isinstance(label, str) and value is not None:
            lab = label.lower()
            if "ascensor" in lab and base.ascensore is None:
                base.ascensore = si_no(value) if si_no(value) is not None else ("sì" in str(value).lower())
            elif ("data" in lab and "annuncio" in lab) or lab.startswith("riferimento e data"):
                m = _DATA_RE.search(str(value))
                if m and not base.data_pubblicazione:
                    base.data_pubblicazione = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            elif lab == "piano" and not base.piano:
                base.piano = piano(value)
            elif "stato" in lab and not base.stato:
                base.stato, base.stato_raw = stato(value), str(value)
    return base


# ------------------------------------------------------------------ scraping
def scrape(cfg: dict, client: PoliteClient, poligoni: dict[str, list] | None = None) -> list[Listing]:
    max_pag = int(cfg.get("scraping", {}).get("max_pagine", 40))
    jobs = [(None, None)] if not poligoni else list(poligoni.items())
    # la ricerca per comune si spezza in fasce di prezzo (il portale mostra un numero massimo di pagine)
    fasce = fasce_prezzo(cfg) if not poligoni else [None]
    tutti: dict[str, Listing] = {}
    for (nome, poly), fascia in ((j, fz) for j in jobs for fz in fasce):
        page, tot = 1, None
        while page <= max_pag and (tot is None or page <= tot):
            url = search_url(cfg, page, poly, fascia)
            try:
                r = client.get(url)
            except BloccatoError as e:
                log.error("Immobiliare: %s", e)
                return list(tutti.values())
            except PermissionError as e:
                log.error("Immobiliare: %s", e)
                break
            except RuntimeError as e:
                log.error("Immobiliare: %s", e)
                break
            if r.status_code == 404:
                break
            annunci, tot_pag = parse_search_page(r.text)
            tot = tot_pag or tot
            log.info("Immobiliare %s%s pag %d/%s: %d annunci", nome or "comune",
                     f" {fascia[0] or 0:.0f}-{fascia[1] or 0:.0f}€" if fascia else "", page, tot, len(annunci))
            if not annunci:
                break
            for a in annunci:
                tutti[a.source_id] = a
            page += 1
    return list(tutti.values())


def arricchisci(client: PoliteClient, l: Listing) -> Listing:
    try:
        r = client.get(l.url)
        return parse_detail_page(r.text, l)
    except Exception as e:  # noqa: BLE001
        log.warning("dettaglio non scaricato %s: %s", l.url, e)
        return l
