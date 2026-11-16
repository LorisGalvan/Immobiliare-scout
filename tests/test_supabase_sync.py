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
    assert len(p["zone"]) == 50 and p["annunci"] and p["mediane"] and p["frazionabili"]
    a = next(x for x in p["annunci"] if x["uid"] == "immobiliare:AFFARE")
    assert a["occasione"] is True and isinstance(a["flags"], list) and a["run_id"] == "run1"
    assert isinstance(p["zone"][0]["geojson"]["coordinates"], (list, tuple))
    assert "NaN" not in txt
