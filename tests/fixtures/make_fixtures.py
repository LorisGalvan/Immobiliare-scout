"""Genera pagine HTML di esempio con la stessa struttura __NEXT_DATA__ dei portali."""
import json
from pathlib import Path

HERE = Path(__file__).parent


def immobiliare_page():
    results = []
    data = [
        (101, 39, 98000, "T", "Via Tunisi", 45.4462, 10.9851, "Buono / Abitabile", "Agenzia Uno", 1, None),
        (102, 45, 165000, "3", "Via Corfù", 45.4442, 10.9858, "Ottimo / Ristrutturato", "Agenzia Due", 1, 175000),
        (103, 130, 330000, "R", "Via Locatelli", 45.4458, 10.9850, "Da ristrutturare", None, 2, None),
    ]
    for rid, mq, prezzo, piano, via, lat, lon, cond, ag, bagni, lowered in data:
        price = {"visible": True, "value": prezzo, "formattedValue": f"€ {prezzo:,}".replace(",", ".")}
        if lowered:
            price["loweredPrice"] = {"originalPrice": f"€ {lowered:,}".replace(",", "."), "discountPercentage": 6}
        results.append({
            "realEstate": {
                "id": rid, "title": f"Bilocale {via}", "contract": "sale",
                "advertiser": {"agency": {"displayName": ag, "type": "agency"}} if ag else
                              {"supervisor": {"type": "user", "displayName": "Privato"}},
                "price": price,
                "properties": [{
                    "surface": f"{mq} m²", "bathrooms": str(bagni), "rooms": "2",
                    "condition": cond, "floor": {"abbreviation": piano, "value": f"{piano}° piano"},
                    "location": {"address": via, "latitude": lat, "longitude": lon, "marker": "pin"},
                    "description": "Ampio appartamento con doppio ingresso e due bagni" if mq > 100 else "Bilocale",
                    "typologyGA4Translation": "Appartamento",
                    "ga4features": ["ascensore", "balcone"] if piano == "3" else ["cantina"],
                }],
            },
            "seo": {"url": f"https://www.immobiliare.it/annunci/{rid}/"},
        })
    nd = {"props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
        "count": 3, "maxPages": 1, "currentPage": 1, "results": results}}}]}}}}
    return ('<html><head><link rel="canonical" href="https://www.immobiliare.it/vendita-case/verona/">'
            '</head><body><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(nd) + "</script></body></html>")


def subito_page():
    items = []
    for sid, mq, prezzo, floor, comp, title, lat in [
        (555001, 48, 120000, "1", False, "Bilocale in via Mameli 12 Borgo Trento", None),
        (555002, 85, 210000, "Piano terra", True, "Trilocale zona stadio", 45.4340),
    ]:
        it = {
            "kind": "AdItem", "urn": f"id:ad:12345:list:{sid}", "subject": title,
            "body": "Vendo appartamento luminoso, 2 camere, cantina.",
            "date": "2026-11-10 09:12:00",
            "urls": {"default": f"https://www.subito.it/appartamenti/x-{sid}.htm"},
            "advertiser": {"company": comp, "name": "Agenzia Tre" if comp else "Mario"},
            "geo": {"town": {"value": "Verona"}, **({"map": {"latitude": lat, "longitude": 10.968}} if lat else {})},
            "features": {
                "/price": {"values": [{"key": str(prezzo), "value": f"{prezzo:,} €".replace(",", ".")}]},
                "/size": {"values": [{"key": str(mq), "value": f"{mq} mq"}]},
                "/floor": {"values": [{"key": "x", "value": floor}]},
                "/bathrooms": {"values": [{"key": "1", "value": "1"}]},
                "/elevator": {"values": [{"key": "1", "value": "Sì"}]},
                "/building_condition": {"values": [{"key": "2", "value": "Buono stato/Abitabile"}]},
            },
        }
        items.append({"item": it})
    nd = {"props": {"pageProps": {"initialState": {"items": {"list": items, "totalPages": 1}}}}}
    return ('<html><head><meta property="og:site_name" content="subito.it"></head><body>'
            '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(nd) + "</script></body></html>")


def idealista_page():
    return """<html><body><main>idealista
<article class="item" data-element-id="3300111"><div class="item-info-container">
<a class="item-link" href="/immobile/3300111/" title="x">Bilocale in via San Nazaro, Veronetta, Verona</a>
<div class="price-row"><span class="item-price h2-simulated">139.000<span class="txt-big">€</span></span></div>
<div class="item-detail-char"><span class="item-detail">2 locali</span><span class="item-detail">55 m²</span>
<span class="item-detail">Piano 2 senza ascensore</span></div>
<div class="item-description description"><p class="ellipsis">Luminoso bilocale</p></div></div></article>
<div class="pagination"><ul><li class="selected">1</li></ul></div></main></body></html>"""


if __name__ == "__main__":
    (HERE / "immobiliare_lista.html").write_text(immobiliare_page(), encoding="utf-8")
    (HERE / "subito_lista.html").write_text(subito_page(), encoding="utf-8")
    (HERE / "idealista_lista.html").write_text(idealista_page(), encoding="utf-8")
