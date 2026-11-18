"""Immobiliare.it tramite Apify (servizio a pagamento, pochi euro al mese).

Immobiliare blocca le richieste automatiche del bot (403). Apify fa girare uno "scraper" già pronto
(un *actor*) sui suoi server e restituisce gli annunci. Il bot lancia l'actor, aspetta che finisca e
converte i risultati negli stessi annunci ``immobiliare:<id>`` delle pagine salvate, così storico,
ribassi e doppioni continuano a funzionare.

Actor supportati (``apify.attore`` in config):
- ``crawloop/immobiliare-it-scraper`` (consigliato): coordinate, mq, piano, descrizione completa,
  contratto "auction" per le aste; spezza da solo le ricerche oltre i 2.000 risultati.
- ``igolaizola/immobiliare-it-scraper``: più collaudato, ma senza descrizione.

Serve un token Apify: in ``config.local.yaml`` (``apify: {token: ...}``) o nella variabile
d'ambiente ``SCOUT_APIFY_TOKEN``. Mai in config.yaml, che è su GitHub.
"""
from __future__ import annotations

import logging
import os
import time

import requests

from ..models import Listing
from ..normalize import num, piano, si_no, stato
from . import immobiliare

log = logging.getLogger(__name__)
API = "https://api.apify.com/v2"
FINITI = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyErrore(RuntimeError):
    pass


def token(cfg: dict) -> str | None:
    return os.environ.get("SCOUT_APIFY_TOKEN") or (cfg.get("apify") or {}).get("token") or None


# ---------------------------------------------------------------- chiamate Apify
def esegui_actor(tok: str, attore: str, input_, attesa_max_s: int = 3600,
                 sessione: requests.Session | None = None, pausa_s: float = 15,
                 run_id: str | None = None) -> list[dict]:
    """Avvia l'actor, aspetta la fine e restituisce tutte le righe del dataset.
    Con ``run_id`` non avvia nulla: recupera i risultati di un'esecuzione già fatta (già pagata)."""
    s = sessione or requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if run_id:
        r = s.get(f"{API}/actor-runs/{run_id}", timeout=60)
        if r.status_code == 404:
            raise ApifyErrore(f"esecuzione {run_id} non trovata")
        r.raise_for_status()
        run = r.json()["data"]
        log.info("Apify: recupero l'esecuzione %s (stato %s)", run_id, run["status"])
    else:
        r = s.post(f"{API}/acts/{attore.replace('/', '~')}/runs", json=input_, timeout=60)
        if r.status_code == 401:
            raise ApifyErrore("token Apify non valido")
        if r.status_code == 402:
            raise ApifyErrore("credito Apify esaurito")
        if r.status_code >= 400:
            raise ApifyErrore(f"avvio non riuscito (HTTP {r.status_code}): {r.text[:300]}")
        run = r.json()["data"]
        log.info("Apify: avviato %s (run %s)", attore, run["id"])
    inizio, errori = time.time(), 0
    while run["status"] not in FINITI:
        if time.time() - inizio > attesa_max_s:
            raise ApifyErrore(f"l'esecuzione supera {attesa_max_s // 60} minuti: controlla su console.apify.com "
                              f"(per recuperarla: run {run['id']})")
        time.sleep(pausa_s)
        try:
            run = s.get(f"{API}/actor-runs/{run['id']}", timeout=60).json()["data"]
            errori = 0
        except (requests.RequestException, ValueError, KeyError) as e:
            # la rete di casa può sparire per qualche secondo: l'esecuzione su Apify continua, riprovo
            errori += 1
            if errori >= 20:
                raise ApifyErrore(f"rete assente da troppo tempo ({e}). L'esecuzione su Apify è salva: "
                                  f"recuperala con RECUPERA_APIFY.bat, run {run['id']}") from e
            log.warning("Apify: rete non raggiungibile, riprovo (%d/20)", errori)
    if run["status"] != "SUCCEEDED":
        raise ApifyErrore(f"esecuzione terminata con stato {run['status']}")
    righe, offset = [], 0
    while True:
        for n in range(5):
            try:
                r = s.get(f"{API}/datasets/{run['defaultDatasetId']}/items",
                          params={"clean": "true", "format": "json", "offset": offset, "limit": 1000}, timeout=120)
                r.raise_for_status()
                break
            except requests.RequestException:
                if n == 4:
                    raise
                time.sleep(pausa_s)
        blocco = r.json()
        righe += blocco
        if len(blocco) < 1000:
            break
        offset += 1000
    costo = run.get("usageTotalUsd")
    log.info("Apify: %d risultati%s", len(righe), f", costo {costo:.2f} $" if isinstance(costo, (int, float)) else "")
    return righe


# ---------------------------------------------------------------- input per actor
def input_actor(cfg: dict, attore: str) -> list[dict]:
    """Una o più esecuzioni (compravendite e, se attivo, aste) nel formato dell'actor scelto."""
    t, a = cfg["territorio"], cfg.get("apify") or {}
    f = cfg.get("scraping", {}).get("filtri", {})
    max_ = int(a.get("max_annunci", 200))
    aste = a.get("includi_aste", True)
    if attore.startswith("igolaizola/"):
        base = {"maxItems": max_, "municipality": t["comune"], "province": t.get("provincia", ""),
                "sortType": "mostRecent", "minPrice": int(f.get("prezzo_min") or 0),
                "maxPrice": int(f.get("prezzo_max") or 0), "minSize": int(f.get("mq_min") or 0)}
        out = [{**base, "operation": "buy", "excludeAuctions": True}]
        if aste:
            out.append({**base, "operation": "auction"})
        return out
    # crawloop (e actor simili che accettano gli URL di ricerca di Immobiliare)
    # aste in un'esecuzione separata: con un solo limite maxItems le compravendite (prima URL)
    # lo esaurirebbero e le aste non verrebbero mai lette
    def run(url: str, n: int) -> dict:
        return {"startUrls": [{"url": url}], "maxItems": n, "includeDetails": bool(a.get("descrizione", True)),
                "includePhones": False, "monitorMode": False,
                "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"],
                                       "apifyProxyCountry": "IT"}}
    out = [run(immobiliare.search_url(cfg, 1), max_)]
    if aste:
        out.append(run(f"{immobiliare.BASE}/aste-immobiliari/{t.get('slug_immobiliare', 'verona')}/",
                       int(a.get("max_aste", 300))))
    return out


# ---------------------------------------------------------------- conversione
def _g(d, *percorsi):
    """Primo valore non vuoto tra i percorsi ("a.b.c") di un dizionario annidato."""
    for p in percorsi:
        cur = d
        for k in p.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}):
            return cur
    return None


def a_listing(r: dict) -> Listing | None:
    """Riga di un actor (crawloop piatto o igolaizola annidato) -> Listing ``immobiliare:<id>``."""
    rid = _g(r, "id", "listingId")
    if rid is None:
        return None
    url = _g(r, "url", "seo.url") or f"{immobiliare.BASE}/annunci/{rid}/"
    contratto = str(_g(r, "contract", "analytics.contract") or "").lower()
    tipologia = _g(r, "typology", "analytics.typology", "topology.typology.name")
    agenzia = _g(r, "agencyName", "analytics.agencyName")
    privato = _g(r, "isPrivate")
    if privato is None:
        adv = str(_g(r, "advertiserType", "analytics.advertiser") or "").lower()
        privato = adv in ("privato", "private", "user") if adv else None
    prezzo = _g(r, "price.raw", "priceValue", "price")
    flags = ["portale: asta"] if contratto in ("auction", "asta") or "asta" in contratto else []
    return Listing(
        source=immobiliare.SOURCE, source_id=str(rid), url=str(url),
        titolo=str(_g(r, "title") or ""), descrizione=str(_g(r, "description") or ""),
        prezzo=prezzo if isinstance(prezzo, (int, float)) else num(prezzo),
        mq=num(_g(r, "surfaceValue", "surface", "topology.surface.size")),
        piano=piano(_g(r, "floor", "topology.floor", "analytics.floor")),
        ascensore=si_no(_g(r, "elevator", "topology.lift", "analytics.elevator")),
        bagni=int(num(_g(r, "bathroomsValue", "topology.bathrooms")) or 0) or None,
        locali=int(num(_g(r, "roomsValue", "topology.rooms")) or 0) or None,
        stato=stato(_g(r, "condition")), stato_raw=_g(r, "condition"),
        agenzia=None if privato else agenzia, privato=privato,
        indirizzo=_g(r, "address", "geography.street"),
        lat=num(_g(r, "latitude", "geography.geolocation.latitude")),
        lon=num(_g(r, "longitude", "geography.geolocation.longitude")),
        tipologia=str(tipologia) if tipologia else None,
        flags=flags,
    )


def scrape(cfg: dict) -> tuple[list[Listing], bool]:
    """Restituisce (annunci, completa). ``completa`` è False se il limite max_annunci è stato raggiunto
    o un'esecuzione è fallita: in quel caso il bot non segna come rimossi gli annunci non visti."""
    tok = token(cfg)
    if not tok:
        log.error("Apify: manca il token (apify.token in config.local.yaml o SCOUT_APIFY_TOKEN)")
        return [], False
    a = cfg.get("apify") or {}
    attore = a.get("attore", "crawloop/immobiliare-it-scraper")
    max_ = int(a.get("max_annunci", 200))
    tutti: dict[str, Listing] = {}
    completa = True
    run_id = os.environ.get("SCOUT_APIFY_RUN")          # recupero di un'esecuzione già fatta
    for inp in input_actor(cfg, attore)[:1 if run_id else None]:
        try:
            righe = esegui_actor(tok, attore, inp, int(a.get("attesa_max_min", 60)) * 60, run_id=run_id)
        except (ApifyErrore, requests.RequestException) as e:
            log.error("Apify: %s", e)
            completa = False
            continue
        if len(righe) >= inp.get("maxItems", max_):
            completa = False
            log.info("Apify: raggiunto il limite di %d annunci (apify.max_annunci / max_aste): elenco parziale",
                     inp.get("maxItems", max_))
        for r in righe:
            l = a_listing(r)
            if l and l.prezzo:
                tutti[l.uid] = l
    res = list(tutti.values())
    log.info("Apify: %d annunci Immobiliare (di cui aste segnalate dal portale: %d)",
             len(res), sum("portale: asta" in l.flags for l in res))
    return res, completa and bool(res)
