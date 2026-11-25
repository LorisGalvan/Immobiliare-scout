"""Comuni dell'hinterland: nomi per i portali, microzone, rimossi per comune, PVP, giro su più comuni."""
import json

import pytest
from shapely.geometry import LineString, box, mapping

from scout import territori
from scout.models import Listing
from scout.storage import Storage


def cfg_base(tmp_path, comuni=("San Giovanni Lupatoto", "Villafranca di Verona", "Castel d'Azzano")):
    (tmp_path / "data/zone").mkdir(parents=True)
    return {"_root": str(tmp_path),
            "territorio": {"nome": "Verona", "comune": "Verona", "provincia": "VR", "slug_immobiliare": "verona",
                           "subito_comune": "verona"},
            "microzone": {"file": "data/zone/verona.geojson", "tolleranza_confine_m": 0},
            "scraping": {"fasce_prezzo": [100000, 200000], "filtri": {"prezzo_min": 30000, "prezzo_max": 1500000}},
            "apify": {"max_annunci": 4000}, "wikicasa": {"slug": "verona", "pagine": 30},
            "geocoding": {"attivo": False},
            "hinterland": {"comuni": list(comuni), "max_annunci": 800}}


def salva_zone(path, zone):
    feats = [{"type": "Feature", "properties": {"nome": n, **props}, "geometry": mapping(g)} for n, g, props in zone]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")


def test_slug_e_nomi():
    assert territori.slug("Castel d'Azzano") == "castel-d-azzano"
    assert territori.slug("San Martino Buon Albergo", "_") == "san_martino_buon_albergo"
    assert territori.norm("VILLAFRANCA DI VERONA (VR)") == "villafranca di verona"
    assert territori.nome_breve({"nome": "Villafranca di Verona"}) == "Villafranca"
    assert territori.nome_breve({"nome": "San Giovanni Lupatoto"}) == "S. Giovanni Lupatoto"
    assert territori.file_zone({"nome": "San Giovanni Lupatoto"}) == "data/zone/san_giovanni_lupatoto.geojson"


def test_scelta_comuni(tmp_path):
    cfg = cfg_base(tmp_path)
    assert territori.scegli(cfg, None) == ["Verona", "San Giovanni Lupatoto", "Villafranca di Verona", "Castel d'Azzano"]
    assert territori.scegli(cfg, "verona") == ["Verona"]
    assert territori.scegli(cfg, "hinterland")[0] == "San Giovanni Lupatoto"
    assert territori.scegli(cfg, "villafranca,castel d azzano") == ["Villafranca di Verona", "Castel d'Azzano"]
    with pytest.raises(ValueError):
        territori.scegli(cfg, "Milano")
    cfg["hinterland"]["attivo"] = False
    assert territori.scegli(cfg, None) == ["Verona"]


def test_variante_del_comune(tmp_path):
    cfg = cfg_base(tmp_path)
    assert territori.variante(cfg, "Verona") is cfg
    v = territori.variante(cfg, "Castel d'Azzano")
    assert v["territorio"]["comune"] == "Castel d'Azzano" and v["territorio"]["slug_immobiliare"] == "castel-d-azzano"
    assert v["scraping"]["fasce_prezzo"] == [] and v["apify"]["max_annunci"] == 800
    assert v["wikicasa"]["pagine"] == 0                      # Wikicasa solo per Verona
    assert v["portali_apify"]["idealista"]["luogo"] == "Castel d'Azzano"
    assert cfg["territorio"]["comune"] == "Verona"           # l'originale non cambia
    from scout.scrapers import apify_immobiliare, subito
    assert "/vendita-case/castel-d-azzano/" in apify_immobiliare.input_actor(v, "crawloop/x")[0]["startUrls"][0]["url"]
    assert "/aste-immobiliari/castel-d-azzano/" in apify_immobiliare.input_actor(v, "crawloop/x")[1]["startUrls"][0]["url"]
    assert "/verona/castel-d-azzano/" in subito.search_url(v)


def test_carica_zone_di_tutti_i_comuni(tmp_path):
    from scout.pipeline import carica_zone
    cfg = cfg_base(tmp_path)
    z = tmp_path / "data/zone"
    salva_zone(z / "verona.geojson", [("Centro m1", box(10.98, 45.43, 11.0, 45.45), {})])
    salva_zone(z / "villafranca_di_verona.geojson", [("Centro m1", box(10.83, 45.34, 10.85, 45.36), {}),
                                                     ("Villafranca Dossobuono m1", box(10.88, 45.38, 10.9, 45.4), {})])
    zone = carica_zone(cfg)
    assert zone.names() == ["Centro m1", "Villafranca Centro m1", "Villafranca Dossobuono m1"]
    assert zone.get("Villafranca Centro m1").props["comune"] == "Villafranca di Verona"
    assert zone.assign(45.35, 10.84) == "Villafranca Centro m1"


def test_rimossi_solo_nei_comuni_letti(tmp_path):
    from scout.geo.microzones import MicrozoneSet
    from scout.pipeline import ingest
    cfg = cfg_base(tmp_path)
    st = Storage(tmp_path / "s.sqlite")
    vecchi = [Listing("subito", "1", prezzo=1e5, mq=50),                                   # dato vecchio: Verona
              Listing("subito", "2", prezzo=1e5, mq=50, comune="Villafranca di Verona"),
              Listing("subito", "3", prezzo=1e5, mq=50, comune="Castel d'Azzano")]
    st.upsert(vecchi)
    # giro sul solo hinterland: Villafranca letta per intero (annuncio 2 sparito), Castel d'Azzano parziale
    nuovi = [Listing("subito", "4", prezzo=2e5, mq=70, comune="Villafranca di Verona")]
    r = ingest(cfg, st, nuovi, MicrozoneSet([]), "subito", {"Villafranca di Verona": True, "Castel d'Azzano": False})
    assert r["rimossi"] == ["subito:2"]
    attivi = {x.uid: x.comune for x in st.listings()}
    assert attivi == {"subito:1": None, "subito:3": "Castel d'Azzano", "subito:4": "Villafranca di Verona"}
    # un giro "vecchio stile" (vero/falso) riguarda solo Verona
    r = ingest(cfg, st, [Listing("subito", "5", prezzo=1e5, mq=40)], MicrozoneSet([]), "subito", True)
    assert r["rimossi"] == ["subito:1"]


def test_pvp_divide_i_lotti_per_comune():
    from scout.scrapers.pvp import comune_del_lotto
    comuni = ["Verona", "Villafranca di Verona", "Sona"]
    assert comune_del_lotto("VILLAFRANCA DI VERONA", "", comuni) == "Villafranca di Verona"
    assert comune_del_lotto("Verona", "", comuni) == "Verona"
    assert comune_del_lotto("Cerea", "Tribunale di Verona", comuni) is None
    assert comune_del_lotto(None, "Appartamento a Villafranca di Verona, Tribunale di Verona", comuni) == "Villafranca di Verona"
    # Villafranca non è più contata come Verona quando si cerca solo Verona
    assert comune_del_lotto("Villafranca di Verona", "", ["Verona"]) is None


def test_giro_su_piu_comuni(tmp_path, monkeypatch):
    from scout import pipeline
    from scout.geo.microzones import MicrozoneSet
    cfg = cfg_base(tmp_path, comuni=("Sona", "Castel d'Azzano"))
    st = Storage(tmp_path / "s.sqlite")
    letti = []

    def finto_apify(c):
        com = c["territorio"]["comune"]
        letti.append((com, c["apify"]["max_annunci"]))
        n = {"Verona": 3, "Sona": 2, "Castel d'Azzano": 1}[com]
        return [Listing("immobiliare", f"{com}-{i}", prezzo=1e5, mq=50) for i in range(n)], com != "Sona"

    monkeypatch.setattr(pipeline.apify_immobiliare, "scrape", finto_apify)
    r = pipeline.scrape_tutto(cfg, st, MicrozoneSet([]), ["immobiliare_apify"])
    assert sorted(letti) == [("Castel d'Azzano", 800), ("Sona", 800), ("Verona", 4000)]
    assert len(r["immobiliare_apify"]["nuovi"]) == 6
    per_comune = {}
    for l in st.listings():
        per_comune[l.comune] = per_comune.get(l.comune, 0) + 1
    assert per_comune == {"Verona": 3, "Sona": 2, "Castel d'Azzano": 1}

    letti.clear()
    pipeline.scrape_tutto(cfg, st, MicrozoneSet([]), ["immobiliare_apify"], ["Sona"])
    assert letti == [("Sona", 800)]


def test_disegna_microzone_hinterland(tmp_path, monkeypatch):
    import scout.geo.osm_zoning as oz
    cfg = cfg_base(tmp_path, comuni=("San Giovanni Lupatoto", "Sona"))
    z = tmp_path / "data/zone"
    # SGL ha già una zona fatta a mano: resta, le nuove coprono il resto del comune
    salva_zone(z / "san_giovanni_lupatoto.geojson", [("1 SGL", box(11.0, 45.38, 11.01, 45.39), {"fonte": "excel"})])
    confini = {"San Giovanni Lupatoto": box(11.0, 45.36, 11.06, 45.40), "Sona": box(10.80, 45.42, 10.86, 45.46)}
    monkeypatch.setattr(oz, "fetch_comune_boundary", lambda nome, ua=None, bbox=None: confini[nome])
    monkeypatch.setattr(oz, "fetch_cut_features", lambda poly, ua, livello="medio": {
        "tagli": [LineString([((poly.bounds[0] + poly.bounds[2]) / 2, 0), ((poly.bounds[0] + poly.bounds[2]) / 2, 90)])],
        "quartieri": []})
    monkeypatch.setattr(oz.time, "sleep", lambda s: None)
    righe = oz.disegna_hinterland(cfg)
    assert len(righe) == 2 and "più le tue 1" in righe[0]
    from scout.pipeline import carica_zone
    nomi = carica_zone(cfg).names()
    assert "1 SGL" in nomi and "Sona m1" in nomi and "S. Giovanni Lupatoto m1" in nomi
    # al secondo giro non si ridisegna nulla
    assert all("già presenti" in r for r in oz.disegna_hinterland(cfg))
