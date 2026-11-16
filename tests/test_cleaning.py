from scout.cleaning import unisci_doppioni, valida
from scout.config import load_config
from scout.models import Listing

CFG = load_config()


def L(src, sid, prezzo, mq, **kw):
    return Listing(source=src, source_id=sid, prezzo=prezzo, mq=mq, lat=45.44, lon=10.98, **kw)


def test_valida():
    assert valida(L("x", "1", 100000, None), CFG) == (False, "mq mancanti")
    assert valida(L("x", "2", 100000, 5), CFG)[0] is False
    assert valida(L("x", "3", 100000, 60, descrizione="vendesi nuda proprietà"), CFG)[0] is False
    l = L("x", "4", 100000, 60, descrizione="appartamento attualmente affittato, 90 mq")
    ok, _ = valida(l, CFG)
    assert ok and any("affittato" in f for f in l.flags) and any("mq nel testo" in f for f in l.flags)


def test_doppioni_tra_siti():
    a = L("immobiliare", "1", 150000, 60, agenzia="A", piano="2")
    b = L("subito", "2", 152000, 61, agenzia="B")
    c = L("immobiliare", "3", 150000, 95)
    reps = unisci_doppioni([a, b, c], CFG)
    assert len(reps) == 2
    r = next(x for x in reps if x.mq < 90)
    assert r.uid == "immobiliare:1" and len(r.doppioni) == 1
    assert any("inserzionisti" in f for f in r.flags)
