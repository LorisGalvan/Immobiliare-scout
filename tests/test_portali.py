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


def test_casa_pagine_max_80():
    cfg = load_config()
    cfg["portali_apify"] = {"casa": {"max_pagine": 200}}
    assert ap.input_actor(cfg, "casa")["maxPagesPerTask"] == 80


def test_casa_tutte_le_tipologie():
    c = ap.input_actor(load_config(), "casa")
    assert c["propertyType"] == "all" and c["maxRetries"] == 10


def test_casa_una_run_per_fascia_di_prezzo(monkeypatch):
    """Casa.it si ferma a ~380 annunci per ricerca: una run per fascia; una fascia al limite = elenco parziale."""
    cfg = load_config()
    cfg["scraping"] = {**cfg["scraping"], "fasce_prezzo": [200000], "filtri": {"prezzo_min": 30000, "prezzo_max": 900000}}
    monkeypatch.setattr(ap, "token", lambda cfg: "x")
    monkeypatch.delenv("SCOUT_APIFY_RUN", raising=False)
    input_ricevuti = []

    def finto(tok, attore, inp, attesa, run_id=None):
        input_ricevuti.append((inp["priceMin"], inp["priceMax"]))
        n = 3 if inp["priceMin"] == 30000 else ap.TETTO_CASA
        return [{**CASA, "adId": f"{inp['priceMin']}-{i}"} for i in range(n)]

    monkeypatch.setattr(ap, "esegui_actor", finto)
    annunci, completa = ap.scrape(cfg, "casa")
    assert input_ricevuti == [(30000, 200000), (200000, 900000)]
    assert len(annunci) == 3 + ap.TETTO_CASA and completa is False     # la seconda fascia è al limite
