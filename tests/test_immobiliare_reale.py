"""Regressione su una pagina reale di Immobiliare (novembre 2026), ridotta a 4 annunci."""
from pathlib import Path

from scout.cleaning import valida
from scout.config import load_config
from scout.importa import parse_html_file

FIX = Path(__file__).parent / "fixtures" / "immobiliare_reale_2026-11.html"


def test_pagina_reale():
    ls = {l.source_id: l for l in parse_html_file(FIX)}   # la pagina inizia con ~400 KB di CSS
    assert set(ls) == {"133598104", "134002849", "97472412", "129133554"}
    a = ls["133598104"]
    assert (a.prezzo, a.mq, a.piano, a.bagni) == (400000, 110, "R", 2)
    assert a.ascensore is False                       # "No Ascensore" non è un ascensore
    assert a.stato == "ottimo" and a.lat and a.coord_precise
    assert ls["134002849"].ascensore is True and ls["134002849"].piano == "5"
    assert ls["97472412"].tipologia == "Progetto"
    assert valida(ls["97472412"], load_config())[0] is False   # i progetti (range di prezzo) sono esclusi
