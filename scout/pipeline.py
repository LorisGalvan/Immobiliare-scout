"""Orchestrazione: acquisizione -> microzona -> storico -> analisi -> output -> alert."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from .alerts import notifica
from .analysis import OMI, analizza, prepara
from .config import get, resolve
from .export_excel import esporta
from .frazionamento import analizza_frazionamento
from .geo.geocode import Geocoder
from .geo.microzones import MicrozoneSet
from .mappa import mappa_analisi
from .models import Listing
from .scrapers import idealista, immobiliare, subito
from .scrapers.base import PoliteClient
from .storage import Storage

log = logging.getLogger(__name__)


_ZONE_SINCRONIZZATE: set[str] = set()


def carica_zone(cfg) -> MicrozoneSet:
    """Microzone dal file GeoJSON; con sorgente "sito" prima le aggiorna da Supabase
    (una volta per esecuzione), così le modifiche fatte nell'editor arrivano al bot."""
    path = resolve(cfg, cfg["microzone"]["file"])
    chiave = str(path)
    if chiave not in _ZONE_SINCRONIZZATE:
        _ZONE_SINCRONIZZATE.add(chiave)
        try:
            from .supabase_sync import scarica_zone, zone_dal_sito
            if zone_dal_sito(cfg):
                righe = scarica_zone(cfg)
                if righe:
                    _salva_zone_scaricate(path, righe)
                    log.info("microzone aggiornate dal sito: %d", len(righe))
        except Exception as e:  # noqa: BLE001 - senza rete si usa il file locale
            log.warning("microzone dal sito non scaricate (uso il file locale): %s", e)
    return MicrozoneSet.load(path)


def _salva_zone_scaricate(path: Path, righe: list[dict]):
    import json
    feats = [{"type": "Feature", "properties": {**(r.get("props") or {}), "nome": r["nome"]},
              "geometry": r["geojson"]} for r in righe]
    nuovo = json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=1)
    if path.exists():
        vecchio = path.read_text(encoding="utf-8")
        if vecchio == nuovo:
            return
        path.with_suffix(".prima_del_sito.geojson").write_text(vecchio, encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(nuovo, encoding="utf-8")


def riassegna_zone(cfg, storage: Storage, zone: MicrozoneSet, manuali: dict[str, str] | None = None) -> int:
    """Ricalcola la microzona di tutti gli annunci con coordinate (dopo una modifica
    dei confini) e applica le assegnazioni manuali fatte dal sito. Restituisce i cambi."""
    tol = float(get(cfg, "microzone.tolleranza_confine_m", 0))
    manuali = manuali or {}
    nomi = set(zone.names())
    cambi = 0
    rows = storage.conn.execute("SELECT uid, lat, lon, microzona FROM annunci WHERE source != 'excel'").fetchall()
    for r in rows:
        nuova = r["microzona"]
        if r["lat"] is not None and r["lon"] is not None:
            nuova = zone.assign(r["lat"], r["lon"], tol)
        elif nuova is not None and nuova not in nomi:
            nuova = None                     # zona eliminata o rinominata
        if r["uid"] in manuali and manuali[r["uid"]] in nomi:
            nuova = manuali[r["uid"]]
        if nuova != r["microzona"]:
            storage.conn.execute("UPDATE annunci SET microzona=? WHERE uid=?", (nuova, r["uid"]))
            cambi += 1
    storage.commit()
    if cambi:
        log.info("microzona aggiornata per %d annunci (confini modificati o assegnazioni manuali)", cambi)
    return cambi


def assegna_zone(listings: list[Listing], zone: MicrozoneSet, cfg: dict, geocoder: Geocoder | None):
    tol = float(get(cfg, "microzone.tolleranza_confine_m", 0))
    comune = cfg["territorio"]["comune"]
    prov = cfg["territorio"].get("provincia", "")
    geocodificati = 0
    for l in listings:
        if (l.lat is None or not l.coord_precise) and l.indirizzo and geocoder is not None:
            res = geocoder.geocode(l.indirizzo, comune, prov)
            if res:
                l.lat, l.lon = res
                l.coord_precise = True
                geocodificati += 1
        if l.microzona is None:
            l.microzona = zone.assign(l.lat, l.lon, tol)
    log.info("geocodificati %d annunci; senza zona %d/%d", geocodificati,
             sum(1 for l in listings if l.microzona is None), len(listings))


def ingest(cfg, storage: Storage, listings: list[Listing], zone: MicrozoneSet,
           fonte: str, completa: bool) -> dict:
    geo = None
    if get(cfg, "geocoding.attivo", True):
        geo = Geocoder(storage.path, get(cfg, "scraping.user_agent", "scout-immobili"),
                       float(get(cfg, "geocoding.pausa_s", 1.1)))
    assegna_zone(listings, zone, cfg, geo)
    stats = storage.upsert(listings)
    rimossi = []
    if completa and listings:
        rimossi = storage.segna_rimossi(fonte, {l.uid for l in listings})
    storage.log_esecuzione(fonte, len(listings), len(stats["nuovi"]), len(stats["ribassi"]),
                           len(rimossi), completa)
    log.info("%s: %d annunci, %d nuovi, %d ribassi, %d rimossi", fonte, len(listings),
             len(stats["nuovi"]), len(stats["ribassi"]), len(rimossi))
    return {**stats, "rimossi": rimossi}


def scrape_tutto(cfg, storage: Storage, zone: MicrozoneSet, siti: list[str] | None = None) -> dict:
    client = PoliteClient(cfg)
    attivi = siti or [s for s, on in (get(cfg, "scraping.siti", {}) or {}).items() if on]
    per_zona = get(cfg, "scraping.modalita", "comune") == "microzone"
    poligoni = {z.nome: z.latlon for z in zone.zone} if per_zona else None
    risultati = {}
    for sito in attivi:
        blocchi_prima = sum(client.blocchi.values())
        if sito == "immobiliare":
            res = immobiliare.scrape(cfg, client, poligoni)
        elif sito == "subito":
            res = subito.scrape(cfg, client)
        elif sito == "idealista":
            res = idealista.scrape(cfg, client, {z.nome: z.latlon for z in zone.zone})
        else:
            log.warning("sito sconosciuto: %s", sito)
            continue
        completa = sum(client.blocchi.values()) == blocchi_prima and len(res) > 0
        risultati[sito] = ingest(cfg, storage, res, zone, sito, completa)
        if sito == "immobiliare" and get(cfg, "scraping.scarica_dettaglio", True):
            _dettagli_immobiliare(cfg, storage, client, res)
    log.info("richieste HTTP totali: %d", client.richieste)
    return risultati


def _dettagli_immobiliare(cfg, storage, client, res: list[Listing]):
    """Scarica la scheda solo dei candidati interessanti (grandi o con €/mq basso)."""
    maxn = int(get(cfg, "scraping.max_dettagli_per_run", 40))
    mq_fr = float(get(cfg, "frazionamento.mq_min", 100))
    gia = {r["uid"] for r in storage.conn.execute(
        "SELECT uid FROM annunci WHERE length(coalesce(descrizione,''))>400").fetchall()}
    cand = [l for l in res if l.uid not in gia and l.mq and l.prezzo]
    # priorità: grandi (frazionamento) e €/mq più bassi
    cand.sort(key=lambda l: (0 if l.mq >= mq_fr else 1, l.prezzo / l.mq))
    for l in cand[:maxn]:
        immobiliare.arricchisci(client, l)
    if cand:
        storage.upsert(cand[:maxn])


def analizza_e_esporta(cfg, storage: Storage, zone: MicrozoneSet, alert: bool = True,
                       dry_run_alert: bool = False) -> dict:
    manuali = {}
    if get(cfg, "supabase.attivo", False):
        from .supabase_sync import scarica_zone_manuali
        try:
            manuali = scarica_zone_manuali(cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("assegnazioni manuali non scaricate: %s", e)
    riassegna_zone(cfg, storage, zone, manuali)
    df = prepara(storage, cfg)
    omi = None
    if get(cfg, "analisi.omi.attivo", False):
        try:
            omi = OMI(cfg, zone)
        except (OSError, KeyError, ValueError) as e:
            log.warning("OMI non disponibile: %s", e)
    df, med = analizza(df, cfg, omi)
    fraz = analizza_frazionamento(df, med, cfg)
    out = resolve(cfg, cfg.get("cartella_output", "output"))
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    nome = cfg["territorio"]["nome"].replace(" ", "_")
    xlsx = esporta(out / f"scouting_{nome}_{stamp}.xlsx", df, med, fraz, zone, cfg)
    html = mappa_analisi(out / f"mappa_{nome}_{stamp}.html", zone, df, med, fraz,
                         f"Scout immobili {cfg['territorio']['nome']} - {stamp}")
    testi = notifica(cfg, storage, df, fraz, dry_run=dry_run_alert) if alert else []
    risultato = {"excel": xlsx, "df": df, "med": med, "fraz": fraz}
    pubblicato = False
    if get(cfg, "supabase.attivo", False):
        from .supabase_sync import pubblica
        try:
            pubblicato = pubblica(cfg, storage, risultato, zone)
        except Exception as e:  # noqa: BLE001 - il report locale resta valido
            log.error("pubblicazione su Supabase fallita: %s", e)
    n_occ = int(df["occasione"].sum()) if not df.empty else 0
    log.info("Excel: %s | Mappa: %s | occasioni: %d | frazionabili: %d | segnalazioni: %d",
             xlsx, html, n_occ, len(fraz), len(testi))
    return {"excel": xlsx, "mappa": html, "occasioni": n_occ, "frazionabili": len(fraz),
            "segnalazioni": testi, "df": df, "med": med, "fraz": fraz, "pubblicato": pubblicato}


__all__ = ["Path", "carica_zone", "ingest", "scrape_tutto", "analizza_e_esporta"]
