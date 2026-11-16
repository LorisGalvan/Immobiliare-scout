"""Interfaccia a riga di comando: ``python -m scout <comando>``."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import get, load_config, resolve


def _setup_log(cfg, verbose: bool):
    logdir = resolve(cfg, "data/log")
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(logdir / "scout.log", encoding="utf-8")],
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scout", description="Scouting immobili sottoprezzo per microzona")
    ap.add_argument("-c", "--config", default=None, help="file YAML (default: config.yaml)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("zone-importa-excel", help="importa i poligoni (e gli annunci storici) dai tuoi Excel")
    p.add_argument("files", nargs="+")
    p.add_argument("--aggiungi", action="store_true", help="aggiunge alle zone esistenti invece di sostituirle")
    p.add_argument("--no-annunci", action="store_true", help="non importare le righe annuncio storiche")

    p = sub.add_parser("zone-auto", help="propone microzone da OpenStreetMap")
    p.add_argument("--livello", choices=["base", "medio", "fine"], default="medio",
                   help="quali strade usare come confine")
    p.add_argument("--area-min", type=float, default=150_000, help="area minima zona in m² (default 150000)")
    p.add_argument("--solo-scoperto", action="store_true",
                   help="genera solo nelle parti del comune non coperte dalle tue zone")
    p.add_argument("--output", help="file GeoJSON di destinazione (default: quello in config)")

    p = sub.add_parser("zone-importa-geojson", help="sostituisce le zone con un GeoJSON (es. export dell'editor)")
    p.add_argument("file")

    p = sub.add_parser("zone-rinomina", help="rinomina una microzona")
    p.add_argument("vecchio")
    p.add_argument("nuovo")

    sub.add_parser("zone-elenco", help="elenca le microzone")
    sub.add_parser("editor", help="crea la mappa HTML per modificare le microzone")

    p = sub.add_parser("scrape", help="scarica gli annunci dai siti attivi")
    p.add_argument("--siti", help="es. immobiliare,subito")

    p = sub.add_parser("importa-html", help="importa pagine di ricerca salvate dal browser")
    p.add_argument("cartella")
    p.add_argument("--archivia", action="store_true",
                   help="sposta i file letti in importate/<data>/ (usato da AVVIA.bat)")
    p.add_argument("--fonte-completa", action="store_true",
                   help="le pagine coprono tutta la ricerca: segna come rimossi gli annunci non presenti")

    p = sub.add_parser("importa-csv", help="importa annunci da CSV (es. Facebook Marketplace)")
    p.add_argument("file")
    p.add_argument("--fonte", default="facebook")

    p = sub.add_parser("analizza", help="calcola mediane/scostamenti e genera Excel + mappa")
    p.add_argument("--no-alert", action="store_true")
    p.add_argument("--prova-alert", action="store_true", help="mostra gli alert senza inviarli")

    p = sub.add_parser("run", help="esecuzione giornaliera completa: scrape + analisi + alert")
    p.add_argument("--siti")

    p = sub.add_parser("esporta-json", help="esporta i risultati in JSON (dati demo per il sito web)")
    p.add_argument("file", nargs="?", default="web/public/demo.json")

    sub.add_parser("stato", help="statistiche del database")
    p = sub.add_parser("test-alert", help="invia un messaggio di prova su Telegram/email")

    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    _setup_log(cfg, a.verbose)
    log = logging.getLogger("scout")

    from .geo.microzones import MicrozoneSet
    from .pipeline import analizza_e_esporta, carica_zone, ingest, scrape_tutto
    from .storage import Storage

    zone_path = resolve(cfg, cfg["microzone"]["file"])

    if a.cmd == "zone-importa-excel":
        from .excel_import import importa_annunci_storici, importa_poligoni
        nuove, avvisi = importa_poligoni(a.files, cfg["territorio"]["comune"])
        for w in avvisi:
            log.warning(w)
        zone = nuove
        if a.aggiungi:
            vecchie = carica_zone(cfg)
            zone = MicrozoneSet(vecchie.zone + [z for z in nuove.zone if z.nome not in vecchie.names()])
        zone.save(zone_path)
        log.info("salvate %d microzone in %s", len(zone), zone_path)
        if not a.no_annunci:
            mappa = {(z.props.get("file"), z.props.get("foglio")): z.nome for z in nuove.zone}
            storici = importa_annunci_storici(a.files, mappa)
            st = Storage(resolve(cfg, cfg["database"]))
            st.upsert(storici)
            for l in storici:   # dati storici: non attivi, "rimossi" alla data dell'annuncio
                st.aggiorna_campi(l.uid, attivo=0, removed_at=l.data_pubblicazione or "2000-01-01",
                                  first_seen=l.data_pubblicazione or "2000-01-01")
            st.commit()
            log.info("importati %d annunci storici dagli Excel (non attivi, solo consultazione)", len(storici))

    elif a.cmd == "zone-auto":
        from .geo.osm_zoning import proponi_microzone
        esistenti = carica_zone(cfg) if a.solo_scoperto else None
        zs = proponi_microzone(cfg["territorio"]["comune"], get(cfg, "scraping.user_agent"),
                               a.livello, a.area_min, esistenti=esistenti)
        out = Path(a.output) if a.output else zone_path
        if out.exists() and not a.output and not a.solo_scoperto:
            backup = out.with_suffix(".backup.geojson")
            out.replace(backup)
            log.info("zone precedenti salvate in %s", backup)
        zs.save(out)
        log.info("proposte %d microzone -> %s (rivedile con 'scout editor')", len(zs), out)

    elif a.cmd == "zone-importa-geojson":
        zs = MicrozoneSet.load(a.file)
        nomi = set()
        for i, z in enumerate(zs.zone, 1):
            if not z.props.get("nome") or z.nome in nomi:
                z.nome = f"Nuova zona {i}"
            nomi.add(z.nome)
        zs.save(zone_path)
        log.info("salvate %d microzone", len(zs))

    elif a.cmd == "zone-rinomina":
        zs = carica_zone(cfg)
        z = zs.get(a.vecchio)
        if not z:
            sys.exit(f"zona '{a.vecchio}' non trovata")
        z.nome = a.nuovo
        zs.save(zone_path)
        st = Storage(resolve(cfg, cfg["database"]))
        st.conn.execute("UPDATE annunci SET microzona=? WHERE microzona=?", (a.nuovo, a.vecchio))
        st.commit()

    elif a.cmd == "zone-elenco":
        zs = carica_zone(cfg)
        for z in zs.zone:
            print(f"{z.nome:40s} {zs.area_m2(z.nome) / 1e6:6.2f} km²  {z.props.get('fonte', '')}")
        for x, y, pct in zs.overlaps_report():
            print(f"ATTENZIONE sovrapposizione {pct}%: {x} / {y}")

    elif a.cmd == "editor":
        from .mappa import editor_microzone
        out = resolve(cfg, cfg.get("cartella_output", "output")) / "editor_microzone.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        print(editor_microzone(out, carica_zone(cfg)))

    elif a.cmd == "scrape":
        st = Storage(resolve(cfg, cfg["database"]))
        scrape_tutto(cfg, st, carica_zone(cfg), a.siti.split(",") if a.siti else None)

    elif a.cmd == "importa-html":
        from .importa import importa_html
        st = Storage(resolve(cfg, cfg["database"]))
        if not Path(a.cartella).exists():
            Path(a.cartella).mkdir(parents=True)
        res = importa_html(a.cartella, archivia=a.archivia)
        log.info("pagine salvate: %d annunci importati", len(res))
        per_fonte = {}
        for l in res:
            per_fonte.setdefault(l.source, []).append(l)
        for fonte, ls in per_fonte.items():
            ingest(cfg, st, ls, carica_zone(cfg), fonte, a.fonte_completa)

    elif a.cmd == "importa-csv":
        from .importa import importa_csv
        st = Storage(resolve(cfg, cfg["database"]))
        ingest(cfg, st, importa_csv(a.file, a.fonte), carica_zone(cfg), a.fonte, False)

    elif a.cmd == "analizza":
        st = Storage(resolve(cfg, cfg["database"]))
        r = analizza_e_esporta(cfg, st, carica_zone(cfg), alert=not a.no_alert, dry_run_alert=a.prova_alert)
        if r.get("pubblicato"):
            print("Risultati pubblicati sul sito (Supabase).")
        if a.prova_alert:
            print("\n\n".join(r["segnalazioni"]) or "nessuna nuova segnalazione")
        print(f"Excel: {r['excel']}\nMappa: {r['mappa']}\nOccasioni: {r['occasioni']} - Frazionabili: {r['frazionabili']}")

    elif a.cmd == "run":
        st = Storage(resolve(cfg, cfg["database"]))
        zone = carica_zone(cfg)
        scrape_tutto(cfg, st, zone, a.siti.split(",") if a.siti else None)
        r = analizza_e_esporta(cfg, st, zone)
        print(f"Excel: {r['excel']}\nMappa: {r['mappa']}\nOccasioni: {r['occasioni']} - Frazionabili: {r['frazionabili']}")

    elif a.cmd == "esporta-json":
        from .supabase_sync import costruisci_payload, esporta_json
        st = Storage(resolve(cfg, cfg["database"]))
        zone = carica_zone(cfg)
        r = analizza_e_esporta(cfg, st, zone, alert=False)
        print(esporta_json(a.file, costruisci_payload(cfg, st, r, zone, "demo")))

    elif a.cmd == "stato":
        st = Storage(resolve(cfg, cfg["database"]))
        for row in st.conn.execute("SELECT source, SUM(attivo) attivi, COUNT(*) totali, "
                                   "SUM(microzona IS NULL) senza_zona FROM annunci GROUP BY source"):
            print(dict(row))
        for row in st.conn.execute("SELECT * FROM esecuzioni ORDER BY id DESC LIMIT 10"):
            print(dict(row))

    elif a.cmd == "test-alert":
        from .alerts import invia_email, invia_telegram
        t = invia_telegram(cfg, ["✅ Scout immobili: test alert Telegram"])
        e = invia_email(cfg, "Scout immobili: test", ["Test alert email"])
        print(f"Telegram inviati: {t} - Email: {'ok' if e else 'non inviata/non attiva'}")


if __name__ == "__main__":
    main()
