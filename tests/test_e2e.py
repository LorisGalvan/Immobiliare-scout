"""Test end-to-end su dati simulati dentro le microzone reali di Verona."""
import random
from pathlib import Path

import openpyxl
import yaml

from scout.config import load_config
from scout.geo.microzones import MicrozoneSet
from scout.models import Listing
from scout.pipeline import analizza_e_esporta, ingest
from scout.storage import Storage

ROOT = Path(__file__).resolve().parent.parent


def _punto_in(z, rnd):
    minx, miny, maxx, maxy = z.geom.bounds
    from shapely.geometry import Point
    while True:
        x, y = rnd.uniform(minx, maxx), rnd.uniform(miny, maxy)
        if z.geom.contains(Point(x, y)):
            return y, x


def _cfg(tmp_path):
    cfg = load_config()
    cfg["database"] = str(tmp_path / "t.sqlite")
    cfg["cartella_output"] = str(tmp_path / "out")
    cfg["geocoding"]["attivo"] = False
    cfg["microzone"]["file"] = str(ROOT / "data/zone/verona.geojson")
    return cfg


def _annunci(zone, rnd, fonte="immobiliare"):
    livelli = {z.nome: rnd.uniform(2200, 4200) for z in zone.zone}
    out, k = [], 0
    for z in zone.zone[:6]:
        for mq in [35, 40, 42, 45, 48, 55, 60, 65, 75, 80, 90, 110, 120]:
            lat, lon = _punto_in(z, rnd)
            k += 1
            ppm = livelli[z.nome] * rnd.uniform(0.92, 1.08) * (1.1 if mq < 50 else 1.0)
            out.append(Listing(source=fonte, source_id=str(k), url=f"https://example/{k}", prezzo=round(ppm * mq, -3),
                               mq=mq, lat=lat, lon=lon, piano=str(rnd.randint(1, 4)), ascensore=True,
                               stato="buono", agenzia=f"Ag{k % 5}", indirizzo=f"via Test {k}"))
    z0 = zone.zone[0]
    lat, lon = _punto_in(z0, rnd)
    out.append(Listing(source=fonte, source_id="AFFARE", url="https://example/affare", mq=62, lat=lat, lon=lon,
                       prezzo=round(livelli[z0.nome] * 0.65 * 62, -3), piano="2", stato="buono", agenzia="AgX"))
    lat, lon = _punto_in(z0, rnd)
    out.append(Listing(source=fonte, source_id="GRANDE", url="https://example/grande", mq=150, lat=lat, lon=lon,
                       prezzo=round(livelli[z0.nome] * 0.5 * 150, -3), bagni=2, piano="T",
                       descrizione="Ampio appartamento con doppio ingresso, due bagni, forma regolare"))
    return out


def test_pipeline(tmp_path):
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    rnd = random.Random(42)
    ann = _annunci(zone, rnd)
    # doppione su Subito dello stesso "affare" con prezzo quasi uguale
    aff = next(a for a in ann if a.source_id == "AFFARE")
    dup = Listing(source="subito", source_id="S1", url="https://subito/S1", mq=61, prezzo=aff.prezzo + 1000,
                  lat=aff.lat + 0.0002, lon=aff.lon, piano="2", privato=True)
    ingest(cfg, st, ann, zone, "immobiliare", True)
    ingest(cfg, st, [dup], zone, "subito", True)

    # "giorno 2": un annuncio ribassa, un altro sparisce
    st.conn.execute("UPDATE annunci SET first_seen='2026-10-01'")
    ann[0].prezzo = ann[0].prezzo * 0.9
    sparito = ann.pop(1)
    stats = ingest(cfg, st, ann, zone, "immobiliare", True)
    assert stats["ribassi"] and stats["ribassi"][0][0] == ann[0].uid
    assert sparito.uid in stats["rimossi"]

    r = analizza_e_esporta(cfg, st, zone, alert=True, dry_run_alert=True)
    df = r["df"]
    occ = df[df["occasione"]]
    assert "immobiliare:AFFARE" in set(occ["uid"])
    row = df[df["uid"] == "immobiliare:AFFARE"].iloc[0]
    assert row["scostamento_pct"] < -25 and len(row["doppioni"]) == 1      # doppione unito
    assert "subito:S1" not in set(df["uid"])
    fr = r["fraz"]
    assert not fr.empty and fr.iloc[0]["uid"] == "immobiliare:GRANDE"
    assert "doppio ingresso" in fr.iloc[0]["indizi"] and fr.iloc[0]["n_unita"] == 3
    assert any("AFFARE" in t or "affare" in t for t in r["segnalazioni"])

    wb = openpyxl.load_workbook(r["excel"])
    assert {"Riepilogo", "Occasioni", "Frazionabili", "Ribassi"} <= set(wb.sheetnames)
    assert "1 Borgo Trento m1" in wb.sheetnames
    ws = wb["1 Borgo Trento m1"]
    assert ws["A5"].value == "VIA" and ws["B5"].value == "MQ 30/50" and ws["E5"].value == "%SCOSTAMENTO"
    assert "vrt=" in ws["B1"].value and "shape=" in ws["B2"].value
    assert Path(r["mappa"]).stat().st_size > 10000


def test_campione_fascia_usato(tmp_path):
    """Regressione: con campione sufficiente il riferimento è la fascia, non la zona intera."""
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    ingest(cfg, st, _annunci(zone, random.Random(42)), zone, "immobiliare", True)
    df = analizza_e_esporta(cfg, st, zone, alert=False)["df"]
    z = df[df["microzona"] == zone.zone[0].nome]
    assert (z["base_confronto"].str.startswith("fascia")).mean() > 0.8


def test_giorni_online(tmp_path):
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    ingest(cfg, st, _annunci(zone, random.Random(42)), zone, "immobiliare", True)
    st.conn.execute("UPDATE annunci SET first_seen='2020-01-01'")
    st.commit()
    df = analizza_e_esporta(cfg, st, zone, alert=False)["df"]
    assert df["giorni_online"].notna().all() and (df["giorni_online"] > 300).all()
