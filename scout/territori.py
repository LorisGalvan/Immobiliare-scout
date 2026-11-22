"""Comuni dell'hinterland: stesso archivio, stesso sito, stesse regole del comune principale.

Il comune principale è quello di ``territorio`` (Verona). Gli altri si elencano in ``hinterland.comuni``
di config.yaml: per ognuno il bot ricava da solo i nomi usati dai portali (``san-giovanni-lupatoto``)
e il file delle microzone (``data/zone/san_giovanni_lupatoto.geojson``). Ogni ricerca si fa comune per
comune con una copia della configurazione in cui ``territorio`` è quel comune: così gli scraper
non cambiano.
"""
from __future__ import annotations

import copy
import re
import unicodedata

# Riquadro largo attorno a Verona e provincia (lon/lat): serve per cercare i confini comunali
# su OpenStreetMap senza interrogare tutta Italia.
RIQUADRO_VR = (10.55, 45.05, 11.55, 45.75)


def slug(nome: str, sep: str = "-") -> str:
    """"Castel d'Azzano" -> "castel-d-azzano" (come negli indirizzi di Immobiliare, Subito, Casa.it, Wikicasa)."""
    s = unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", sep, s).strip(sep)


def norm(nome: str | None) -> str:
    """Nome di comune confrontabile: senza accenti, apostrofi, maiuscole, "(VR)" finale."""
    s = re.sub(r"\(.*?\)", " ", str(nome or ""))
    s = re.sub(r"\b(vr|verona provincia)\s*$", " ", slug(s, " "))
    return re.sub(r"\s+", " ", s).strip()


def principale(cfg: dict) -> str:
    return (cfg.get("territorio") or {}).get("comune") or "Verona"


def comuni_hinterland(cfg: dict) -> list[dict]:
    """Elenco dei comuni dell'hinterland (dizionari con almeno ``nome``), se la sezione è attiva."""
    h = cfg.get("hinterland") or {}
    if not h.get("attivo", True):
        return []
    out = []
    for c in h.get("comuni") or []:
        c = {"nome": c} if isinstance(c, str) else dict(c or {})
        if c.get("nome") and norm(c["nome"]) != norm(principale(cfg)):
            out.append(c)
    return out


def nome_breve(c: dict) -> str:
    """Nome corto per le microzone: "Villafranca di Verona" -> "Villafranca"."""
    if c.get("breve"):
        return c["breve"]
    n = re.sub(r"\s+di\s+(Verona|Valpolicella)$", "", c["nome"]).strip()
    return re.sub(r"^San(ta)?\s+", lambda m: "S. " if not m.group(1) else "S.ta ", n)


def file_zone(c: dict) -> str:
    return c.get("zone") or f"data/zone/{slug(c['nome'], '_')}.geojson"


def tutti_i_comuni(cfg: dict) -> list[str]:
    return [principale(cfg)] + [c["nome"] for c in comuni_hinterland(cfg)]


def scegli(cfg: dict, quali: str | None) -> list[str]:
    """``quali``: "tutti" (o vuoto), "verona"/"principale", "hinterland", oppure nomi separati da virgola."""
    q = (quali or "tutti").strip().lower()
    if q in ("tutti", "tutto", "all"):
        return tutti_i_comuni(cfg)
    if q in ("principale", norm(principale(cfg)), "solo verona"):
        return [principale(cfg)]
    if q in ("hinterland", "solo hinterland"):
        return [c["nome"] for c in comuni_hinterland(cfg)]
    noti = {norm(n): n for n in tutti_i_comuni(cfg)}
    scelti = []
    for pezzo in quali.split(","):
        n = norm(pezzo)
        if not n:
            continue
        trovato = noti.get(n) or next((v for k, v in noti.items() if k.startswith(n)), None)
        if not trovato:
            raise ValueError(f"comune {pezzo.strip()!r} non presente in config.yaml (territorio o hinterland.comuni)")
        scelti.append(trovato)
    return scelti


def variante(cfg: dict, nome: str) -> dict:
    """Copia della configurazione con ``territorio`` = quel comune (per gli scraper).
    Per il comune principale restituisce la configurazione così com'è."""
    if norm(nome) == norm(principale(cfg)):
        return cfg
    c = next(x for x in comuni_hinterland(cfg) if norm(x["nome"]) == norm(nome))
    h = cfg.get("hinterland") or {}
    s = c.get("slug") or slug(c["nome"])
    v = copy.deepcopy(cfg)
    t = v.setdefault("territorio", {})
    # la provincia di Subito resta quella del comune principale (prima del cambio di comune)
    t["subito_provincia"] = c.get("subito_provincia") or t.get("subito_provincia") or t.get("subito_comune") or "verona"
    t.update(nome=c["nome"], comune=c["nome"],
             slug_immobiliare=c.get("slug_immobiliare", s), subito_comune=c.get("subito_comune", s),
             idealista_slug=c.get("idealista_slug", f"{s}-verona"))
    sc = v.setdefault("scraping", {})
    # comuni piccoli: di solito basta una ricerca unica (senza fasce di prezzo)
    sc["fasce_prezzo"] = c.get("fasce_prezzo", h.get("fasce_prezzo", []))
    sc["modalita"] = "comune"
    a = v.setdefault("apify", {})
    a["max_annunci"] = int(c.get("max_annunci", h.get("max_annunci", 1000)))
    a["max_aste"] = int(c.get("max_aste", h.get("max_aste", 100)))
    w = v.setdefault("wikicasa", {})
    w["slug"] = s
    w["pagine"] = int(c.get("wikicasa_pagine", h.get("wikicasa_pagine", 0)))
    pa = v.setdefault("portali_apify", {})
    for portale in ("idealista", "casa"):
        pa[portale] = {**(pa.get(portale) or {}), "luogo": c.get("idealista_luogo", c["nome"]),
                       "slug": c.get("casa_slug", s),
                       "max_annunci": int(c.get("max_annunci", h.get("max_annunci", 1000)))}
    return v
