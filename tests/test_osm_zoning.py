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
