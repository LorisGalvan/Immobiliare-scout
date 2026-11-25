import json
import random

from scout.pipeline import analizza_e_esporta, ingest
from scout.geo.microzones import MicrozoneSet
from scout.storage import Storage
from scout.supabase_sync import costruisci_payload

from test_e2e import _annunci, _cfg


def test_payload_serializzabile(tmp_path):
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    ingest(cfg, st, _annunci(zone, random.Random(42)), zone, "immobiliare", True)
    r = analizza_e_esporta(cfg, st, zone, alert=False)
    p = costruisci_payload(cfg, st, r, zone, "run1")
    txt = json.dumps(p, allow_nan=False)          # niente NaN: PostgREST li rifiuterebbe
    assert len(p["zone"]) == len(zone) > 0 and p["annunci"] and p["mediane"] and p["frazionabili"]
    a = next(x for x in p["annunci"] if x["uid"] == "immobiliare:AFFARE")
    assert a["occasione"] is True and isinstance(a["flags"], list) and a["run_id"] == "run1"
    assert isinstance(p["zone"][0]["geojson"]["coordinates"], (list, tuple))
    assert "NaN" not in txt


def test_payload_con_aste(tmp_path):
    from scout.models import Listing
    from test_e2e import _punto_in
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    rnd = random.Random(3)
    lat, lon = _punto_in(zone.zone[0], rnd)
    asta = Listing(source="immobiliare", source_id="ASTA1", url="https://example/asta", mq=60, lat=lat, lon=lon,
                   prezzo=60000, titolo="Appartamento all'asta",
                   descrizione="R.G.E. 45/2025. Prezzo base € 80.000, offerta minima € 60.000. Data asta 15/01/2027.")
    ingest(cfg, st, _annunci(zone, rnd) + [asta], zone, "immobiliare", True)
    r = analizza_e_esporta(cfg, st, zone, alert=False)
    p = costruisci_payload(cfg, st, r, zone, "run1")
    json.dumps(p, allow_nan=False)
    a = next(x for x in p["annunci"] if x["uid"] == "immobiliare:ASTA1")
    assert a["tipo_vendita"] == "asta" and a["occasione"] is False and a["data_asta"] == "2027-01-15"
    assert isinstance(a["indizi_vendita"], list) and a["indizi_vendita"]
    assert all(x["tipo_vendita"] == "compravendita" for x in p["annunci"] if x["uid"] != "immobiliare:ASTA1")


def test_upsert_riprova_se_la_connessione_cade(monkeypatch):
    import requests
    from scout.supabase_sync import Supabase

    sb = Supabase("https://x.supabase.co", "sb_secret_prova")
    sb.pausa_s = 0
    chiamate = []

    class R:
        status_code = 201
        text = ""

    def finta(metodo, url, **kw):
        chiamate.append(len(kw["json"]))
        if len(chiamate) == 1:
            raise requests.ConnectionError("Remote end closed connection without response")
        return R()

    monkeypatch.setattr(sb.s, "request", finta)
    sb.upsert("annunci", [{"uid": i} for i in range(450)], "uid")
    assert chiamate == [200, 200, 200, 50]      # primo blocco ripetuto, poi a blocchi da 200
