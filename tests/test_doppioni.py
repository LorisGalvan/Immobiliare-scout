"""Stesso immobile pubblicato da più agenzie / su più portali."""
from scout.analysis import _unisci_aste
from scout.cleaning import unisci_doppioni
from scout.config import load_config
from scout.doppioni import lotti, numeri_procedura, via_civico
from scout.models import Listing

CFG = load_config()

TESTO = ("Borgo Trento, in palazzina signorile degli anni 70 proponiamo luminoso appartamento al secondo piano "
         "con ascensore composto da ingresso, soggiorno con terrazzo abitabile, cucina abitabile, due camere "
         "matrimoniali, bagno finestrato, ripostiglio. Completano la proprietà cantina e garage singolo. "
         "Riscaldamento centralizzato con contabilizzatori, serramenti in pvc, porta blindata.")


def L(src, sid, prezzo, mq, **kw):
    kw.setdefault("lat", 45.44)
    kw.setdefault("lon", 10.98)
    return Listing(source=src, source_id=sid, url=f"https://{src}.it/{sid}", prezzo=prezzo, mq=mq, **kw)


def test_numero_procedura():
    assert numeri_procedura("Tribunale di Verona, R.G.E. 264/2025, lotto 2") == {"264/2025"}
    assert numeri_procedura("Proc. esec. imm. nr 264/25") == {"264/2025"}
    assert numeri_procedura("Esecuzione immobiliare n° 12 / 2024") == {"12/2024"}
    # numeri che non sono procedure
    assert numeri_procedura("rif. 12/2024, disponibile dal 12/05/2025") == set()
    assert numeri_procedura("asta del 12/05/2025") == set()
    assert lotti("Lotto n. 2 e lotto unico") == {"2", "unico"}


def test_via_civico():
    assert via_civico("Via Mameli 12, Verona") == ("mameli", "12")
    assert via_civico("via Goffredo Mameli, Verona") == ("goffredomameli", None)
    assert via_civico("Verona") == (None, None) or via_civico("Verona")[0] == "verona"


def test_tre_agenzie_stesso_appartamento():
    """Tre agenzie, numeri leggermente diversi, coordinate approssimative: una scheda sola."""
    a = L("immobiliare", "1", 229000, 95, agenzia="Tecnocasa", piano="2", locali=4, descrizione=TESTO,
          coord_precise=False, indirizzo="Via Mameli, Verona")
    b = L("idealista", "2", 235000, 100, agenzia="Gabetti", piano="2", descrizione=TESTO.replace("proponiamo", "vendiamo"),
          lat=45.4415, lon=10.9812, coord_precise=False)
    c = L("casa", "3", 232000, 98, agenzia="Remax", locali=4, indirizzo="Via Goffredo Mameli")
    altro = L("immobiliare", "4", 230000, 96, agenzia="Tecnocasa", piano="5", descrizione="altro testo " * 20)
    reps = unisci_doppioni([a, b, c, altro], CFG)
    assert len(reps) == 2
    r = next(x for x in reps if x.doppioni)
    assert r.uid == "immobiliare:1"            # il prezzo più basso
    assert len(r.doppioni) == 2
    assert any("Gabetti" in d and "235,000€" in d for d in r.doppioni)
    assert "pubblicato da 3 inserzionisti" in r.flags
    assert any(f.startswith("prezzi diversi tra gli annunci: 229.000–235.000") for f in r.flags)


def test_stesso_prezzo_e_testo_senza_posizione():
    """Senza coordinate né indirizzo bastano mq, prezzo e descrizione copiata."""
    a = L("immobiliare", "1", 180000, 80, agenzia="A", descrizione=TESTO, lat=None, lon=None)
    b = L("wikicasa", "2", 180000, 80, agenzia="B", descrizione=TESTO, lat=None, lon=None)
    assert len(unisci_doppioni([a, b], CFG)) == 1


def test_non_unisce_appartamenti_diversi():
    base = dict(agenzia="A", descrizione=TESTO, indirizzo="Via Mameli 12")
    # piani diversi nello stesso stabile
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80, piano="1", **base),
                                L("idealista", "2", 200000, 80, piano="3", **base)], CFG)) == 2
    # prezzo molto diverso
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80, **base),
                                L("idealista", "2", 260000, 80, **base)], CFG)) == 2
    # mq molto diversi
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80, **base),
                                L("idealista", "2", 200000, 95, **base)], CFG)) == 2
    # civici diversi
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80, indirizzo="Via Mameli 12"),
                                L("idealista", "2", 200000, 80, indirizzo="Via Mameli 40")], CFG)) == 2
    # lontani (posizioni precise)
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80),
                                L("idealista", "2", 200000, 80, lat=45.46)], CFG)) == 2
    # solo mq e prezzo uguali, nessun altro indizio: non basta
    assert len(unisci_doppioni([L("immobiliare", "1", 200000, 80, lat=None, lon=None),
                                L("idealista", "2", 200000, 80, lat=None, lon=None)], CFG)) == 2


def test_niente_catene():
    """A~B e B~C ma A e C su piani diversi: C resta fuori."""
    a = L("immobiliare", "1", 200000, 80, piano="1", agenzia="A")
    b = L("idealista", "2", 201000, 80, agenzia="B")
    c = L("casa", "3", 202000, 80, piano="3", agenzia="C")
    reps = unisci_doppioni([a, b, c], CFG)
    assert len(reps) == 2


def _asta(src, sid, prezzo, mq, testo, **kw):
    l = L(src, sid, prezzo, mq, descrizione=testo, tipo_vendita="asta", **kw)
    return l, {"first_seen": "2026-11-01", "last_seen": "2026-11-20"}


def test_aste_stessa_procedura_da_piu_agenzie():
    pvp = _asta("pvp", "9", 120000, None, "Tribunale di Verona R.G.E. 264/2025 - Lotto 1. Prezzo base 120.000",
                lat=None, lon=None)
    a = _asta("immobiliare", "1", 120000, 85, "Asta giudiziaria, procedura n. 264/2025, appartamento con garage",
              agenzia="Aste Verona", coord_precise=False)
    b = _asta("idealista", "2", 90000, 86, "Vendita all'asta, proc. esec. 264/25, offerta minima 90.000",
              agenzia="Gruppo Aste", lat=45.45, coord_precise=False)
    diversa = _asta("casa", "3", 120000, 85, "Asta, R.G.E. 301/2024", agenzia="Aste Verona")
    out = _unisci_aste([pvp, a, b, diversa], CFG)
    assert len(out) == 2
    rep = next(l for l, _ in out if l.doppioni)
    assert rep.source == "pvp" and len(rep.doppioni) == 2 and rep.mq == 85


def test_aste_lotti_diversi_stessa_procedura():
    a = _asta("immobiliare", "1", 120000, 85, "R.G.E. 264/2025 lotto 1", agenzia="X")
    b = _asta("idealista", "2", 120000, 85, "R.G.E. 264/2025 lotto 2", agenzia="Y")
    assert len(_unisci_aste([a, b], CFG)) == 2
