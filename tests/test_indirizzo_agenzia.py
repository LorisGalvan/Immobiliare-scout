import pandas as pd

from scout.analysis import analizza
from scout.indirizzo_agenzia import FLAG, controlla, nome_agenzia, sedi_nel_testo, segnalato
from scout.models import Listing

CFG = {"controllo_agenzia": {"raggio_m": 30, "min_immobili": 3}}
UFFICIO = (45.4400, 10.9900)


def L(sid, prezzo, mq, agenzia="Tecnocasa Borgo Roma", lat=None, lon=None, **kw):
    return Listing(source="immobiliare", source_id=sid, prezzo=prezzo, mq=mq, agenzia=agenzia,
                   privato=agenzia is None, lat=lat, lon=lon, **kw)


def test_nome_agenzia():
    assert nome_agenzia("Tecnocasa - Studio Borgo Roma S.r.l.") == nome_agenzia("TECNOCASA BORGO ROMA")


def test_tanti_immobili_della_stessa_agenzia_nello_stesso_punto():
    ufficio = [L(str(i), 150000 + i * 40000, 60 + i * 20, lat=UFFICIO[0], lon=UFFICIO[1] + i * 0.00005)
               for i in range(4)]
    altrove = L("9", 200000, 90, lat=45.45, lon=10.97)
    trovati = controlla(ufficio + [altrove], CFG)
    assert set(trovati) == {l.uid for l in ufficio}
    assert all(segnalato(l.flags) for l in ufficio) and not segnalato(altrove.flags)


def test_due_soli_immobili_non_bastano():
    ls = [L(str(i), 150000 + i * 40000, 60 + i * 20, lat=UFFICIO[0], lon=UFFICIO[1]) for i in range(2)]
    assert controlla(ls, CFG) == {}


def test_stesso_immobile_ripetuto_conta_una_volta():
    ls = [L(str(i), 150000, 60, lat=UFFICIO[0], lon=UFFICIO[1]) for i in range(4)]
    assert controlla(ls, CFG) == {}


def test_cantiere_di_nuova_costruzione_non_e_l_ufficio():
    ls = [L(str(i), 250000 + i * 30000, 60 + i * 15, lat=UFFICIO[0], lon=UFFICIO[1],
            descrizione="Nuova costruzione in classe A4, consegna prevista 2027") for i in range(5)]
    assert controlla(ls, CFG) == {}


def test_punto_generico_con_altri_inserzionisti():
    ls = [L(str(i), 150000 + i * 40000, 60 + i * 20, lat=UFFICIO[0], lon=UFFICIO[1]) for i in range(3)]
    ls += [L("p1", 99000, 45, agenzia=None, lat=UFFICIO[0], lon=UFFICIO[1]),
           L("p2", 310000, 140, agenzia="Altra Agenzia", lat=UFFICIO[0], lon=UFFICIO[1])]
    assert controlla(ls, CFG) == {}


def test_posizioni_approssimative_ignorate():
    ls = [L(str(i), 150000 + i * 40000, 60 + i * 20, lat=UFFICIO[0], lon=UFFICIO[1], coord_precise=False)
          for i in range(4)]
    assert controlla(ls, CFG) == {}


def test_sede_scritta_nell_annuncio():
    assert sedi_nel_testo("Per info vieni a trovarci nella nostra sede in Via Mazzini 12, Verona.") == ["Via Mazzini 12"]
    l = L("1", 180000, 80, indirizzo="Via Mazzini 12",
          descrizione="Trilocale luminoso. Ci trovi in via Mazzini, 12 dal lunedì al sabato.")
    ok = L("2", 180000, 80, indirizzo="Via Roma 3",
           descrizione="Trilocale luminoso. Ci trovi in via Mazzini, 12 dal lunedì al sabato.")
    assert set(controlla([l, ok], CFG)) == {l.uid}


def test_sede_scritta_in_config():
    cfg = {"controllo_agenzia": {"sedi": [
        {"agenzia": "Tecnocasa Borgo Roma", "indirizzo": "Via Centro 10"},
        {"agenzia": "Casa Bella", "lat": UFFICIO[0], "lon": UFFICIO[1]}]}}
    a = L("1", 180000, 80, indirizzo="via Centro, 10")
    b = L("2", 180000, 80, agenzia="CASA BELLA IMMOBILIARE srl", lat=UFFICIO[0] + 0.0001, lon=UFFICIO[1])
    c = L("3", 180000, 80, agenzia="Altra", lat=UFFICIO[0], lon=UFFICIO[1])     # altra agenzia: ok
    d = L("4", 180000, 80, indirizzo="via Centro 22")                            # altro civico: ok
    assert set(controlla([a, b, c, d], cfg)) == {a.uid, b.uid}


def test_ignorati_mai_segnalati():
    cfg = {"controllo_agenzia": {"sedi": [{"agenzia": "Tecnocasa Borgo Roma", "indirizzo": "Via Centro 10"}],
                                 "ignora": ["immobiliare:1"]}}
    a = L("1", 180000, 80, indirizzo="Via Centro 10")
    assert controlla([a], cfg) == {}


def test_fuori_dalle_mediane():
    righe = []
    for i, ppm in enumerate([2000, 2100, 2200]):
        righe.append({"uid": f"x:{i}", "prezzo": ppm * 80, "mq": 80, "microzona": "Centro", "attivo": 1,
                      "indirizzo_agenzia": False})
    righe.append({"uid": "x:agenzia", "prezzo": 6000 * 80, "mq": 80, "microzona": "Centro", "attivo": 1,
                  "indirizzo_agenzia": True, "flags": [f"{FLAG}: prova"]})
    df = pd.DataFrame(righe)
    for c in ("first_seen", "removed_at", "prezzo_iniziale", "piano", "ascensore", "stato"):
        df[c] = None
    out, med = analizza(df, {"analisi": {"fasce_mq": [[30, 1000, "tutte"]], "min_campione": 3}})
    assert med.iloc[0]["n"] == 3 and med.iloc[0]["mediana_mq"] == 2100
    r = out.set_index("uid").loc["x:agenzia"]
    assert pd.isna(r["scostamento_pct"]) and not r["occasione"] and "agenzia" in r["base_confronto"]
