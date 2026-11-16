"""Genera web/public/demo.json: annunci SIMULATI nelle microzone reali, per provare il sito
senza Supabase. I livelli di prezzo partono dalle mediane dei tuoi Excel storici (se il DB
locale le contiene) rivalutate del 25%, altrimenti da valori plausibili per Verona.

    python scripts/genera_demo.py
"""
from __future__ import annotations

import datetime as dt
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import Point  # noqa: E402

from scout.config import load_config, resolve  # noqa: E402
from scout.geo.microzones import MicrozoneSet  # noqa: E402
from scout.models import Listing  # noqa: E402
from scout.pipeline import analizza_e_esporta, ingest  # noqa: E402
from scout.storage import Storage  # noqa: E402
from scout.supabase_sync import costruisci_payload, esporta_json  # noqa: E402

VIE = ["via Mameli", "via Cesare Abba", "via Ca' di Cozzi", "corso Milano", "via Albere", "via Roma",
       "via XX Settembre", "via San Nazaro", "via Giolfino", "via Torbido", "via Scuderlando",
       "via Tombetta", "viale Venezia", "via Trento", "via Mantovana", "via Fincato", "via Valpolicella"]
AGENZIE = ["Tecnocasa", "Gabetti", "Tempocasa", "Remax", "Immobiliare Adige", "Studio Arena", "Engel & Völkers"]
STATI = ["buono", "buono", "ottimo", "da_ristrutturare", "nuovo"]


def livelli(cfg, zone) -> dict[str, float]:
    base = {}
    db = resolve(cfg, cfg["database"])
    if db.exists():
        st = Storage(db)
        for r in st.conn.execute("SELECT microzona, prezzo/mq AS ppm FROM annunci WHERE source='excel' AND mq>0"):
            base.setdefault(r["microzona"], []).append(r["ppm"])
    out = {}
    for z in zone.zone:
        v = sorted(base.get(z.nome, []))
        out[z.nome] = (v[len(v) // 2] * 1.25) if len(v) >= 5 else random.uniform(2300, 3600)
    return out


def punto(z, rnd):
    minx, miny, maxx, maxy = z.geom.bounds
    while True:
        x, y = rnd.uniform(minx, maxx), rnd.uniform(miny, maxy)
        if z.geom.contains(Point(x, y)):
            return y, x


def main():
    rnd = random.Random(7)
    cfg = load_config()
    zone = MicrozoneSet.load(resolve(cfg, cfg["microzone"]["file"]))
    lv = livelli(cfg, zone)
    tmp = Path(tempfile.mkdtemp())
    cfg["database"] = str(tmp / "demo.sqlite")
    cfg["cartella_output"] = str(tmp / "out")
    cfg["geocoding"]["attivo"] = False
    st = Storage(cfg["database"])
    oggi = dt.date.today()
    ann, k = [], 0
    for z in zone.zone:
        for _ in range(rnd.randint(8, 22)):
            k += 1
            mq = rnd.choice([rnd.randint(32, 49), rnd.randint(50, 69), rnd.randint(70, 99), rnd.randint(100, 180)])
            stato = rnd.choice(STATI)
            ppm = lv[z.nome] * rnd.gauss(1, 0.07) * (1.08 if mq < 50 else 1) * \
                {"nuovo": 1.15, "ottimo": 1.05, "buono": 1, "da_ristrutturare": 0.8}[stato]
            if rnd.random() < 0.05:
                ppm *= rnd.uniform(0.62, 0.8)      # qualche vera occasione
            lat, lon = punto(z, rnd)
            src = rnd.choice(["immobiliare", "immobiliare", "subito"])
            priv = rnd.random() < (0.35 if src == "subito" else 0.08)
            via = f"{rnd.choice(VIE)} {rnd.randint(1, 90)}"
            desc = "Appartamento luminoso, cantina, riscaldamento autonomo."
            if mq >= 100 and rnd.random() < 0.12:
                desc += rnd.choice([" Doppio ingresso, due bagni.", " Facilmente frazionabile in due unità.",
                                    " Forma regolare, predisposto per doppie utenze."])
                ppm *= rnd.uniform(0.5, 0.75)      # grandi da sistemare: potenziale frazionamento
            ann.append(Listing(
                source=src, source_id=f"demo{k}", url=f"https://www.{src}.it/", titolo=f"[DEMO] {mq} mq {via}",
                descrizione=desc, prezzo=round(ppm * mq, -3), mq=mq, piano=rnd.choice(["T", "R", "1", "2", "3", "4", "A"]),
                ascensore=rnd.random() < 0.6, bagni=2 if mq > 95 else 1, locali=max(1, mq // 30), stato=stato,
                agenzia=None if priv else rnd.choice(AGENZIE), privato=priv,
                data_pubblicazione=(oggi - dt.timedelta(days=rnd.randint(1, 150))).isoformat(),
                indirizzo=via, lat=lat, lon=lon, tipologia="Appartamento"))
    # primo passaggio "60 giorni fa", poi ribassi e rimozioni
    ingest(cfg, st, ann, zone, "immobiliare", False)
    st.conn.execute("UPDATE prezzi SET data=?", ((oggi - dt.timedelta(days=60)).isoformat(),))
    st.conn.execute("UPDATE annunci SET first_seen=data_pubblicazione")
    st.commit()
    for a in ann:
        if rnd.random() < 0.15:
            a.prezzo = round(a.prezzo * rnd.uniform(0.88, 0.97), -3)
    rimossi = set(rnd.sample(range(len(ann)), len(ann) // 12))
    vivi = [a for i, a in enumerate(ann) if i not in rimossi]
    ingest(cfg, st, vivi, zone, "immobiliare", False)
    for i in rimossi:
        st.aggiorna_campi(ann[i].uid, attivo=0, removed_at=(oggi - dt.timedelta(days=rnd.randint(1, 50))).isoformat())
    st.commit()
    r = analizza_e_esporta(cfg, st, zone, alert=False)
    p = costruisci_payload(cfg, st, r, zone, "demo")
    p["demo"] = True
    out = esporta_json(ROOT / "web/public/demo.json", p)
    print(out, len(p["annunci"]), "annunci,", sum(a["occasione"] for a in p["annunci"]), "occasioni,",
          len(p["frazionabili"]), "frazionabili")


if __name__ == "__main__":
    main()
