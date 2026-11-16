from pathlib import Path

from scout.importa import importa_html
from scout.normalize import num, piano, stato
from scout.scrapers import idealista, immobiliare, subito

FIX = Path(__file__).parent / "fixtures"


def test_normalize():
    assert num("€ 150.000") == 150000
    assert num("85 m²") == 85
    assert num("1.234,5") == 1234.5
    assert piano("Piano terra") == "T" and piano("3° piano") == "3" and piano("Attico") == "A"
    assert piano("rialzato") == "R"
    assert stato("Ottimo / Ristrutturato") == "ottimo" and stato("Da ristrutturare") == "da_ristrutturare"


def test_immobiliare():
    ls, maxp = immobiliare.parse_search_page((FIX / "immobiliare_lista.html").read_text())
    assert maxp == 1 and len(ls) == 3
    a = {l.source_id: l for l in ls}
    assert a["101"].prezzo == 98000 and a["101"].mq == 39 and a["101"].piano == "T"
    assert a["102"].ascensore is True and a["102"].prezzo_ribassato_da == 175000
    assert a["103"].privato is True and a["103"].bagni == 2 and a["103"].stato == "da_ristrutturare"
    assert a["101"].lat == 45.4462 and a["101"].url.endswith("/101/")


def test_subito():
    ls, tot = subito.parse_search_page((FIX / "subito_lista.html").read_text())
    assert tot == 1 and len(ls) == 2
    a = {l.source_id: l for l in ls}
    assert a["555001"].privato is True and a["555001"].indirizzo.lower().startswith("via mameli")
    assert a["555002"].agenzia == "Agenzia Tre" and a["555002"].piano == "T" and a["555002"].lat == 45.434
    assert a["555001"].ascensore is True and a["555001"].stato == "buono"


def test_idealista():
    ls, nxt = idealista.parse_search_page((FIX / "idealista_lista.html").read_text())
    assert len(ls) == 1 and not nxt
    l = ls[0]
    assert l.prezzo == 139000 and l.mq == 55 and l.piano == "2" and l.ascensore is False
    assert l.indirizzo.startswith("via San Nazaro")


def test_importa_html_cartella():
    ls = importa_html(FIX)
    assert {l.source for l in ls} == {"immobiliare", "subito", "idealista", "casa"}
