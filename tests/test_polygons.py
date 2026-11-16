from scout.geo.polygons import (decode_any, decode_casa_geopolygon, decode_idealista_shape,
                                decode_immobiliare_vrt, decode_polyline, encode_polyline,
                                idealista_search_url, immobiliare_search_url)


def test_polyline_roundtrip():
    pts = [(45.44415, 10.98272), (45.4452, 10.9851), (45.4431, 10.9905), (45.44415, 10.98272)]
    assert decode_polyline(encode_polyline(pts)) == pts


def test_idealista_reale():
    # link reale dal foglio "1 Borgo Trento m1"
    url = ("https://www.idealista.it/aree/vendita-case/?ordine=area-asc&shape=%28%28%7DxjtG_a%60bAsBKwDwMsE"
           "%7BTtSmIj%40aBjFrFnChGdAjFs%40tGiC~EgCxC%7DEbD_Bp%40%29%29")
    pts = decode_idealista_shape(url)
    assert len(pts) == 14
    assert abs(pts[0][0] - 45.44415) < 1e-5 and abs(pts[0][1] - 10.98272) < 1e-5


def test_vrt_e_casa():
    u = "https://www.immobiliare.it/ricerca.php?idCategoria=1&vrt=45.1,11.0;45.2,11.0;45.2,11.1&pag=1"
    assert decode_immobiliare_vrt(u) == [(45.1, 11.0), (45.2, 11.0), (45.2, 11.1)]
    c = ("https://www.casa.it/srp/?geopolygon={%22polygon%22:[[45.37%2C11.04]%2C[45.38%2C11.05]"
         "%2C[45.39%2C11.04]]}")
    assert decode_casa_geopolygon(c) == [(45.37, 11.04), (45.38, 11.05), (45.39, 11.04)]
    assert decode_any(u)[0] == "immobiliare"


def test_url_builder_roundtrip():
    pts = [(45.44, 10.98), (45.45, 10.99), (45.43, 10.995)]
    assert decode_immobiliare_vrt(immobiliare_search_url(pts))[:3] == pts
    assert decode_idealista_shape(idealista_search_url(pts))[:3] == pts
    assert "/vendita-case/verona/" in immobiliare_search_url(pts)   # non ricerca.php (robots.txt)
