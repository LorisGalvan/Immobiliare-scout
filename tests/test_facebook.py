"""Facebook Marketplace via Apify: conversione delle righe e riconoscimento dei privati."""
from scout.config import load_config
from scout.scrapers import apify_facebook as fb

RIGA = {"id": "1234567890", "url": "https://www.facebook.com/marketplace/item/1234567890/",
        "title": "Trilocale 95 mq Borgo Trento", "description": "Vendo da privato, no agenzie. Terzo piano con ascensore.",
        "final_price": 230000, "currency": "EUR", "address": "Verona, VR", "latitude": 45.45, "longitude": 10.99,
        "listingIntent": "sale", "bathrooms": 1, "beds": 2, "seller": {"name": "Mario Rossi"}}


def test_conversione_e_privato():
    l = fb.a_listing(RIGA)
    assert l.uid == "facebook:1234567890" and l.prezzo == 230000 and l.privato is True and l.agenzia is None
    assert l.lat == 45.45 and l.bagni == 1 and l.locali == 2


def test_agenzia_e_affitti():
    ag = fb.a_listing({**RIGA, "description": "Bel trilocale", "seller": {"name": "Immobiliare Adige srl"}})
    assert ag.privato is False and ag.agenzia == "Immobiliare Adige srl"
    assert fb.a_listing({**RIGA, "listingIntent": "rent"}) is None
    assert fb.a_listing({**RIGA, "final_price": None}) is None


def test_input():
    i = fb.input_actor(load_config())
    assert "propertyforsale" in i["startUrls"][0]["url"] and i["forSaleOnly"] and i["maxItems"] == 100
