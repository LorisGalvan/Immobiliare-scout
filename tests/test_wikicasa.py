"""Wikicasa via Apify: conversione delle righe dell'actor e riconoscimento dei privati."""
from scout.config import load_config
from scout.scrapers import apify_wikicasa as wk

RIGA = {"real_estate_id": None, "price": 209000, "price_sale": 209000, "sale": True, "rent": False, "sqm": 95,
        "rooms": 4, "bathrooms": 2, "address": "Via Mazzini", "city_name": "Verona", "zone_name": "Centro",
        "description": "Appartamento luminoso", "place_dto": {"latitude": 45.44, "longitude": 10.99},
        "agency": {"id": 44783, "name": "Agenzia Centro"}, "url": "/annuncio/30059065"}


def test_conversione_agenzia():
    l = wk.a_listing(RIGA)
    assert l.uid == "wikicasa:30059065" and l.url == "https://www.wikicasa.it/annuncio/30059065"
    assert l.prezzo == 209000 and l.mq == 95 and l.lat == 45.44 and l.privato is False and l.agenzia == "Agenzia Centro"


def test_privato_e_affitti():
    p = wk.a_listing({**RIGA, "agency": None})
    assert p.privato is True and p.agenzia is None
    assert wk.a_listing({**RIGA, "rent": True}) is None
    assert wk.a_listing({**RIGA, "price": None, "price_sale": None}) is None


def test_input():
    i = wk.input_actor(load_config())
    assert i["urls"][0] == "https://www.wikicasa.it/vendita-case/verona/" and i["urls"][1].endswith("?p=2")
    assert len(i["urls"]) == 8
