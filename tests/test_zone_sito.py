import json
import random

from shapely.geometry import mapping
from shapely.affinity import translate

from scout import pipeline, supabase_sync
from scout.geo.microzones import MicrozoneSet
from scout.pipeline import carica_zone, ingest, riassegna_zone
from scout.storage import Storage

from test_e2e import _annunci, _cfg


def test_riassegna_e_manuali(tmp_path):
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    ann = _annunci(zone, random.Random(3))
    ingest(cfg, st, ann, zone, "immobiliare", True)
    z0 = zone.zone[0].nome
    conta = lambda: st.conn.execute("SELECT COUNT(*) FROM annunci WHERE microzona=?", (z0,)).fetchone()[0]  # noqa: E731
    assert conta() > 0
    # sposto il poligono della prima zona lontano: i suoi annunci restano senza zona
    zone.zone[0].geom = translate(zone.zone[0].geom, xoff=1)
    zone = MicrozoneSet(zone.zone)
    cambi = riassegna_zone(cfg, st, zone, {"immobiliare:AFFARE": zone.zone[5].nome})
    assert cambi > 0
    righe = dict(st.conn.execute("SELECT uid, microzona FROM annunci").fetchall())
    assert conta() == 0                                              # nessuno resta nella zona spostata
    assert righe["immobiliare:AFFARE"] == zone.zone[5].nome          # assegnazione manuale vince
    assert riassegna_zone(cfg, st, zone, {"immobiliare:AFFARE": zone.zone[5].nome}) == 0


def test_zone_scaricate_dal_sito(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    locale = MicrozoneSet.load(cfg["microzone"]["file"])
    cfg["microzone"]["file"] = str(tmp_path / "zone.geojson")
    locale.save(cfg["microzone"]["file"])
    cfg["microzone"]["sorgente"] = "sito"
    cfg["supabase"] = {"attivo": True, "url": "https://x.supabase.co", "service_key": "k"}
    remote = [{"nome": "Zona nuova dal sito", "geojson": mapping(locale.zone[0].geom), "props": {}, "ordine": 0}]
    monkeypatch.setattr(supabase_sync.Supabase, "select", lambda self, t, p: remote if t == "zone" else [])
    pipeline._ZONE_SINCRONIZZATE.clear()
    zs = carica_zone(cfg)
    assert zs.names() == ["Zona nuova dal sito"]
    assert (tmp_path / "zone.prima_del_sito.geojson").exists()       # backup del file precedente
    assert json.loads((tmp_path / "zone.geojson").read_text())["features"][0]["properties"]["nome"] == "Zona nuova dal sito"
