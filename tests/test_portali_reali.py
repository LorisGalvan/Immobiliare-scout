"""Regressione su pagine reali di Idealista e Casa.it (novembre 2026), ridotte."""
from pathlib import Path

from scout.cleaning import valida
from scout.config import load_config
from scout.importa import parse_html_file

FIX = Path(__file__).parent / "fixtures"
CFG = load_config()


def test_idealista_reale():
    ls = parse_html_file(FIX / "idealista_reale_2026-11.html")
    assert len(ls) == 3                                   # il quarto è "promosso" senza link: escluso
    a = {l.source_id: l for l in ls}["37035300"]
    assert (a.prezzo, a.mq, a.piano) == (195000, 80, "2")
    assert a.ascensore is True and a.agenzia == "Idea Casa"
    assert a.indirizzo == "Via Lazzaro Spallanzani"      # senza "s.n.c" e senza quartiere
    assert a.url == "https://www.idealista.it/immobile/37035300/"


def test_casa_reale():
    ls = {l.source_id: l for l in parse_html_file(FIX / "casa_reale_2026-11.html")}
    assert len(ls) == 4
    a = ls["55228766"]
    assert (a.prezzo, a.mq, a.piano, a.bagni) == (570000, 130, "4", 2)
    assert a.indirizzo == "Viale della Repubblica 49" and a.coord_precise
    assert abs(a.lat - 45.444447) < 1e-6 and a.privato is False
    assert a.url == "https://www.casa.it/immobili/55228766/"
    assert ls["54973390"].tipologia == "Asta" and not valida(ls["54973390"], CFG)[0]
    assert ls["54465066"].tipologia == "Progetto" and not valida(ls["54465066"], CFG)[0]
