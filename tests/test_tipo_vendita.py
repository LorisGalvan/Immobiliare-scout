import pytest

from scout.tipo_vendita import classifica


@pytest.mark.parametrize("titolo,descr,atteso", [
    ("Trilocale via Mameli", "Luminoso trilocale con balcone, ristrutturato nel 2020.", "compravendita"),
    ("Bilocale", "Vasta zona giorno, vicino al Tribunale di Verona, comodo ai servizi.", "compravendita"),
    ("Appartamento", "Non è un'asta: vendita diretta dal proprietario. No aste.", "compravendita"),
    ("Appartamento all'asta", "Tribunale di Verona, R.G.E. n. 123/2024, prezzo base € 98.000, offerta minima € 73.500.", "asta"),
    ("Bilocale", "Vendita giudiziaria telematica, professionista delegato alla vendita avv. Rossi.", "asta"),
    ("Appartamento in asta", "Ottima occasione.", "asta"),
    ("Appartamento", "Immobile proveniente da procedura fallimentare, vendita competitiva.", "asta"),
    ("Trilocale", "Possibile acquisto anche tramite asta.", "possibile_asta"),
])
def test_classifica(titolo, descr, atteso):
    assert classifica(titolo, descr).tipo == atteso


def test_agenzia_e_portale():
    assert classifica("Appartamento", "Ampio appartamento.", agenzia="Aste Immobili Verona").tipo == "possibile_asta"
    assert classifica("Appartamento", "", flags=["portale: asta"]).tipo == "asta"
    e = classifica("Bilocale", "Prezzo base d'asta 80.000 euro")
    assert e.tipo == "asta" and "prezzo base d'asta" in e.indizi


def test_casa_reale_asta_riconosciuta():
    from pathlib import Path

    from scout.scrapers import casa
    from scout.tipo_vendita import classifica_listing
    html = (Path(__file__).parent / "fixtures/casa_reale_2026-11.html").read_text(encoding="utf-8")
    res, _ = casa.parse_search_page(html)
    tipi = [classifica_listing(l).tipo for l in res]
    assert tipi.count("asta") >= 1 and tipi.count("compravendita") >= len(res) - 2
