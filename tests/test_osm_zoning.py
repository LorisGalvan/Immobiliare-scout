from shapely.geometry import LineString, box

from scout.geo.osm_zoning import build_zones


def test_taglio_e_fusione():
    terr = box(10.95, 45.42, 11.03, 45.47)
    tagli = [LineString([(10.99, 45.40), (10.99, 45.50)]),    # "strada" verticale
             LineString([(10.90, 45.445), (11.10, 45.445)]),  # "fiume" orizzontale
             LineString([(11.025, 45.40), (11.025, 45.50)])]  # taglio che crea strisce piccole
    zone = build_zones(terr, tagli, [], area_min_m2=2_000_000)
    assert 2 <= len(zone) <= 4
    tot = sum(z.geom.area for z in zone)
    assert abs(tot - terr.area) / terr.area < 0.01


def test_ritagli_sottili_scartati():
    # territorio scoperto = grande area libera + striscia larga ~10 m tra due zone esistenti
    libero = box(10.95, 45.42, 10.99, 45.45)
    striscia = box(11.00, 45.42, 11.00013, 45.45)
    zone = build_zones(libero.union(striscia), [LineString([(10.97, 45.40), (10.97, 45.50)])], [], area_min_m2=150_000)
    assert len(zone) == 2 and all(z.geom.bounds[2] < 10.995 for z in zone)


def test_overpass_prova_altri_server(monkeypatch, tmp_path):
    import scout.geo.osm_zoning as oz

    monkeypatch.chdir(tmp_path)               # la cache delle risposte va in una cartella temporanea

    chiamate = []

    class R:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {"elements": []}

    def finto_post(url, data, headers, timeout):
        chiamate.append((url, headers["User-Agent"]))
        return R(406 if len(chiamate) == 1 else 200)

    monkeypatch.setattr(oz.requests, "post", finto_post)
    assert oz.overpass("[out:json];", "Mozilla/5.0") == {"elements": []}
    assert len(chiamate) == 2 and chiamate[1][0] != chiamate[0][0]
    assert all("ScoutImmobili" in ua for _, ua in chiamate)      # mai lo User-Agent da browser
    assert oz.overpass("[out:json];", None) == {"elements": []} and len(chiamate) == 2   # seconda volta: dalla cache
