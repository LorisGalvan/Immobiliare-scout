"""Orchestrazione: acquisizione -> microzona -> storico -> analisi -> output -> alert."""
from __future__ import annotations

import datetime as dt
import logging
import os
from concurrent.futures import ThreadPoolExecutor
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
from .scrapers import apify_facebook, apify_immobiliare, apify_portali, apify_wikicasa, idealista, immobiliare, pvp, subito
from .scrapers.base import PoliteClient
from .storage import Storage
from .territori import comuni_hinterland, file_zone, nome_breve, norm, principale, tutti_i_comuni, variante

log = logging.getLogger(__name__)


def carica_zone(cfg) -> MicrozoneSet:
    """Microzone del comune principale + quelle di ogni comune dell'hinterland (un file ciascuno).
    Un nome già usato prende davanti il nome del comune, così due zone non si confondono mai."""
    zone = MicrozoneSet.load(resolve(cfg, cfg["microzone"]["file"])).zone
    for z in zone:
        z.props.setdefault("comune", principale(cfg))
    nomi = {z.nome for z in zone}
    for c in comuni_hinterland(cfg):
        for z in MicrozoneSet.load(resolve(cfg, file_zone(c))).zone:
            z.props["comune"] = c["nome"]
            if z.nome in nomi:
                z.nome = f"{nome_breve(c)} {z.nome}"
            nomi.add(z.nome)
            zone.append(z)
    return MicrozoneSet(zone)


def assegna_zone(listings: list[Listing], zone: MicrozoneSet, cfg: dict, geocoder: Geocoder | None):
    tol = float(get(cfg, "microzone.tolleranza_confine_m", 0))
    comune = cfg["territorio"]["comune"]
    prov = cfg["territorio"].get("provincia", "")
    geocodificati = 0
    for l in listings:
        if (l.lat is None or not l.coord_precise) and l.indirizzo and geocoder is not None:
            res = geocoder.geocode(l.indirizzo, l.comune or comune, prov)
            if res:
                l.lat, l.lon = res
                l.coord_precise = True
                geocodificati += 1
        if l.microzona is None:
            l.microzona = zone.assign(l.lat, l.lon, tol)
    log.info("geocodificati %d annunci; senza zona %d/%d", geocodificati,
             sum(1 for l in listings if l.microzona is None), len(listings))


def ingest(cfg, storage: Storage, listings: list[Listing], zone: MicrozoneSet,
           fonte: str, completa: bool | dict[str, bool]) -> dict:
    """``completa``: vero/falso per il comune principale, oppure {comune: completa} quando la ricerca
    ha toccato più comuni. Gli annunci non più visti si segnano come rimossi solo nei comuni
    letti per intero, così un giro su un solo comune non tocca gli altri."""
    princ = principale(cfg)
    for l in listings:
        l.comune = l.comune or princ
    per_comune = completa if isinstance(completa, dict) else {princ: bool(completa)}
    geo = None
    if get(cfg, "geocoding.attivo", True):
        geo = Geocoder(storage.path, get(cfg, "scraping.user_agent", "scout-immobili"),
                       float(get(cfg, "geocoding.pausa_s", 1.1)))
    assegna_zone(listings, zone, cfg, geo)
    stats = storage.upsert(listings)
    rimossi = []
    for comune, ok in per_comune.items():
        visti = {l.uid for l in listings if norm(l.comune) == norm(comune)}
        if ok and visti:
            rimossi += storage.segna_rimossi(fonte, visti, comune=comune, principale=princ)
    tutto = bool(per_comune) and all(per_comune.values())
    storage.log_esecuzione(fonte, len(listings), len(stats["nuovi"]), len(stats["ribassi"]),
                           len(rimossi), tutto)
    log.info("%s: %d annunci, %d nuovi, %d ribassi, %d rimossi", fonte, len(listings),
             len(stats["nuovi"]), len(stats["ribassi"]), len(rimossi))
    return {**stats, "rimossi": rimossi}


# siti letti tramite Apify: i comuni partono in parallelo (ognuno è un'esecuzione separata su Apify)
SITI_APIFY = {"immobiliare_apify": "immobiliare", "idealista_apify": "idealista", "casa_apify": "casa",
              "wikicasa_apify": "wikicasa", "facebook_apify": "facebook"}


def _scrape_comune(sito: str, c: dict, client: PoliteClient, zone: MicrozoneSet,
                   poligoni, principale_: bool) -> tuple[list[Listing], bool] | None:
    """Un sito su un comune (``c`` è la configurazione con territorio = quel comune).
    None = sito non usato per quel comune."""
    if sito == "immobiliare_apify":
        return apify_immobiliare.scrape(c)
    if sito in ("idealista_apify", "casa_apify"):
        return apify_portali.scrape(c, sito.removesuffix("_apify"))
    if sito == "wikicasa_apify":
        if int(get(c, "wikicasa.pagine", 8)) <= 0:
            return None
        return apify_wikicasa.scrape(c)
    if sito == "facebook_apify":
        return apify_facebook.scrape(c) if principale_ else None
    blocchi_prima = sum(client.blocchi.values())
    if sito == "immobiliare":
        res = immobiliare.scrape(c, client, poligoni if principale_ else None)
    elif sito == "subito":
        res = subito.scrape(c, client)
    elif sito == "idealista":
        if not principale_:
            return None
        res = idealista.scrape(c, client, {z.nome: z.latlon for z in zone.zone})
    else:
        log.warning("sito sconosciuto: %s", sito)
        return None
    return res, sum(client.blocchi.values()) == blocchi_prima and len(res) > 0


def scrape_tutto(cfg, storage: Storage, zone: MicrozoneSet, siti: list[str] | None = None,
                 comuni: list[str] | None = None) -> dict:
    """``comuni``: quali comuni leggere (default: il principale e tutto l'hinterland)."""
    client = PoliteClient(cfg)
    attivi = siti or [s for s, on in (get(cfg, "scraping.siti", {}) or {}).items() if on]
    comuni = comuni or tutti_i_comuni(cfg)
    if os.environ.get("SCOUT_APIFY_RUN") and len(comuni) > 1:
        # recupero di un'esecuzione Apify già pagata: riguarda un solo comune
        log.warning("recupero di un'esecuzione Apify: uso solo il comune %s (scegline un altro con --comuni)", comuni[0])
        comuni = comuni[:1]
    princ = principale(cfg)
    per_zona = get(cfg, "scraping.modalita", "comune") == "microzone"
    poligoni = {z.nome: z.latlon for z in zone.zone if z.props.get("comune", princ) == princ} if per_zona else None
    if len(comuni) > 1 or comuni[0] != princ:
        log.info("comuni di questo giro: %s", ", ".join(comuni))
    risultati = {}
    for sito in attivi:
        if sito == "pvp":
            # il PVP si interroga una volta sola per tribunale: i lotti si dividono poi per comune
            blocchi_prima = sum(client.blocchi.values())
            res = pvp.scrape(cfg, client, comuni)
            ok = sum(client.blocchi.values()) == blocchi_prima and len(res) > 0
            risultati[sito] = ingest(cfg, storage, res, zone, "pvp", {n: ok for n in comuni})
            continue

        def uno(nome: str):
            r = _scrape_comune(sito, variante(cfg, nome), client, zone, poligoni, norm(nome) == norm(princ))
            if r is not None:
                for l in r[0]:
                    l.comune = nome
            return nome, r

        if sito in SITI_APIFY and len(comuni) > 1:
            with ThreadPoolExecutor(max_workers=int(get(cfg, "hinterland.apify_in_parallelo", 3))) as ex:
                esiti = list(ex.map(uno, comuni))
        else:
            esiti = [uno(n) for n in comuni]
        res_tutti: list[Listing] = []
        per_comune: dict[str, bool] = {}
        for nome, r in esiti:
            if r is None:
                continue
            res_tutti += r[0]
            per_comune[nome] = r[1]
            if len(comuni) > 1:
                log.info("%s - %s: %d annunci%s", sito, nome, len(r[0]), "" if r[1] else " (elenco parziale)")
        if not per_comune:
            continue
        risultati[sito] = ingest(cfg, storage, res_tutti, zone, SITI_APIFY.get(sito, sito), per_comune)
        if sito == "immobiliare" and get(cfg, "scraping.scarica_dettaglio", True):
            _dettagli_immobiliare(cfg, storage, client, res_tutti)
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


def riassegna_zone(storage: Storage, zone: MicrozoneSet, cfg: dict) -> int:
    """Ricalcola la microzona di tutti gli annunci con coordinate in base alle zone attuali,
    così le zone nuove (o annullate) valgono subito anche per gli annunci già in archivio.
    Restituisce quanti annunci attivi restano senza zona."""
    tol = float(get(cfg, "microzone.tolleranza_confine_m", 0))
    righe = storage.conn.execute("SELECT uid, lat, lon, microzona, attivo FROM annunci").fetchall()
    cambiati = senza = 0
    for uid, lat, lon, vecchia, attivo in righe:
        nuova = zone.assign(lat, lon, tol) if lat is not None and lon is not None else vecchia
        if nuova != vecchia:
            storage.aggiorna_campi(uid, microzona=nuova)
            cambiati += 1
        if attivo == 1 and nuova is None:
            senza += 1
    storage.commit()
    attivi = sum(1 for r in righe if r[4] == 1)
    log.info("microzone ricalcolate: %d annunci cambiati di zona; attivi senza zona %d/%d", cambiati, senza, attivi)
    return senza


def analizza_e_esporta(cfg, storage: Storage, zone: MicrozoneSet, alert: bool = True,
                       dry_run_alert: bool = False) -> dict:
    riassegna_zone(storage, zone, cfg)
    aste_grezze: list = []
    df = prepara(storage, cfg, aste_grezze)
    omi = None
    if get(cfg, "analisi.omi.attivo", False):
        try:
            omi = OMI(cfg, zone)
        except (OSError, KeyError, ValueError) as e:
            log.warning("OMI non disponibile: %s", e)
    df, med = analizza(df, cfg, omi)
    from .analysis import analizza_aste
    aste = analizza_aste(aste_grezze, df, med, cfg)
    fraz = analizza_frazionamento(df, med, cfg)
    out = resolve(cfg, cfg.get("cartella_output", "output"))
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    nome = cfg["territorio"]["nome"].replace(" ", "_")
    xlsx = esporta(out / f"scouting_{nome}_{stamp}.xlsx", df, med, fraz, zone, cfg, aste=aste)
    html = mappa_analisi(out / f"mappa_{nome}_{stamp}.html", zone, df, med, fraz,
                         f"Scout immobili {cfg['territorio']['nome']} - {stamp}")
    testi = notifica(cfg, storage, df, fraz, dry_run=dry_run_alert) if alert else []
    risultato = {"excel": xlsx, "df": df, "med": med, "fraz": fraz, "aste": aste}
    pubblicato = False
    if get(cfg, "supabase.attivo", False):
        from .supabase_sync import pubblica
        try:
            pubblicato = pubblica(cfg, storage, risultato, zone)
        except Exception as e:  # noqa: BLE001 - il report locale resta valido
            log.error("pubblicazione su Supabase fallita: %s", e)
    n_occ = int(df["occasione"].sum()) if not df.empty else 0
    log.info("Excel: %s | Mappa: %s | occasioni: %d | frazionabili: %d | aste: %d | segnalazioni: %d",
             xlsx, html, n_occ, len(fraz), len(aste), len(testi))
    return {"excel": xlsx, "mappa": html, "occasioni": n_occ, "frazionabili": len(fraz),
            "segnalazioni": testi, "df": df, "med": med, "fraz": fraz, "aste": aste, "pubblicato": pubblicato}


__all__ = ["Path", "carica_zone", "ingest", "scrape_tutto", "analizza_e_esporta"]
