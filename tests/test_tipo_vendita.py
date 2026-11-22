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


@pytest.mark.parametrize("descr", [
    "IMMOBILE IN PROCEDURA ESECUTIVA\n\nProcedura n. 264/2025.",
    "MMOBILE IN PROCEDURA ESECUTIVA",                       # testo copiato tagliato
    "Appartamento. Procedura n. 264/2025.",
    "Immobile in procedura esecutva, libero.",                # refuso
    "Proc. esec. imm. nr 264/25",
    "E.I. 264/2025 - lotto unico",
    "Es. imm. n° 12/2024",
    "R.G.Es. 264/2025",
    "R.G.E. N° 264/2025",
    "Trib. di Verona, n. 264/2025",
    "Vendita giudizaria, professionista deleagto alla vendita",  # refusi
    "Giudice dell'esecuzione dott. Bianchi",
    "Procedure esecutive riunite",
])
def test_procedura_esecutiva(descr):
    e = classifica("Appartamento", descr)
    assert e.tipo == "asta", e


@pytest.mark.parametrize("descr", [
    "Progetto esecutivo approvato, pratica edilizia n. 12/2024.",
    "Procedura di vendita trasparente, appartamento al civico n. 12/b.",
    "Esecuzione dei lavori a regola d'arte, concessione n. 45/1985.",
    "Vicino al Tribunale di Verona, civico n. 12.",
    "Condono: pratica n. 12/2003 definita.",
    "Procedura di sanatoria n. 12/2003 conclusa.",
])
def test_procedura_falsi_positivi(descr):
    assert classifica("Trilocale", descr).tipo == "compravendita"


def test_annunci_gia_importati_riclassificati(tmp_path):
    """Un annuncio salvato prima come compravendita passa ad asta al ricalcolo (PUBBLICA.bat)."""
    from scout.analysis import prepara
    from scout.models import Listing
    from scout.storage import Storage
    st = Storage(tmp_path / "db.sqlite")
    l = Listing(source="immobiliare", source_id="1", url="u", titolo="Trilocale",
                descrizione="IMMOBILE IN PROCEDURA ESECUTIVA. Procedura n. 264/2025.", prezzo=120000, mq=90)
    st.upsert([l])
    st.aggiorna_campi(l.uid, tipo_vendita="compravendita")
    st.commit()
    aste = []
    prepara(st, {"pulizia": {}, "analisi": {}}, aste=aste)
    assert [a[0].uid for a in aste] == [l.uid]
    r = st.conn.execute("SELECT tipo_vendita FROM annunci WHERE uid=?", (l.uid,)).fetchone()
    assert r["tipo_vendita"] == "asta"
