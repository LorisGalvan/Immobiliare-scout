"""Idealista e Casa.it via Apify: conversione delle righe dei due actor."""
from scout.config import load_config
from scout.scrapers import apify_portali as ap

IDEALISTA = {"id": "33012345", "propertyCode": "33012345", "url": "https://www.idealista.it/immobile/33012345/",
             "price": 215000, "size": 85, "rooms": 3, "bathrooms": 1, "floor": "2", "hasLift": True,
             "address": "via Roma 5", "latitude": 45.44, "longitude": 10.99, "description": "Trilocale luminoso",
             "contactInfo": {"userType": "private", "commercialName": None}}
CASA = {"adId": "82715349", "detailUrl": "https://www.casa.it/immobili/82715349.html", "price": "395000",
        "areaSqm": "80", "floor": "3", "latitude": "45.43", "longitude": "11.0", "description": "Bilocale",
        "publisherType": "Agency", "agencyName": "Agenzia Adige"}


def test_idealista_privato():
    l = ap.a_listing(IDEALISTA, "idealista")
    assert l.uid == "idealista:33012345" and l.prezzo == 215000 and l.mq == 85 and l.privato is True
    assert l.piano == "2" and l.ascensore is True and l.lat == 45.44


def test_casa_agenzia_e_righe_scartate():
    l = ap.a_listing(CASA, "casa")
    assert l.uid == "casa:82715349" and l.prezzo == 395000 and l.mq == 80 and l.privato is False
    assert l.agenzia == "Agenzia Adige" and l.lon == 11.0
    assert ap.a_listing({**CASA, "price": None}, "casa") is None
    assert ap.a_listing({**CASA, "transaction": "rent"}, "casa") is None


def test_input():
    cfg = load_config()
    i = ap.input_actor(cfg, "idealista")
    assert i["locationQuery"] == "Verona" and i["operation"] == "sale" and i["maxResults"] == 3000
    c = ap.input_actor(cfg, "casa")
    assert c["locationSlugs"] == ["verona"] and c["transaction"] == "sale" and c["priceMin"] == 30000
