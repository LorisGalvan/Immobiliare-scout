"""Portale delle Vendite Pubbliche: lettura dei lotti, pulizia e unione con i portali."""
import json
import random

from scout.cleaning import valida
from scout.config import load_config
from scout.geo.microzones import MicrozoneSet
from scout.importa import parse_html_file
from scout.models import Listing
from scout.pipeline import analizza_e_esporta, ingest
from scout.scrapers import pvp
from scout.storage import Storage
from scout.tipo_vendita import diritto, occupazione

from test_e2e import _annunci, _cfg, _punto_in

# forma simile alla risposta del servizio di ricerca del PVP (i nomi delle chiavi possono cambiare)
RISPOSTA = {"body": {"content": [
    {"idAnnuncio": 123456, "tipologia": "Appartamento", "descLotto": "Appartamento al piano secondo con cantina, "
     "piena proprietà per la quota di 1/1, superficie commerciale 85 mq, libero.",
     "indirizzo": "Via Mazzini 10", "comune": "Verona", "provincia": "VR", "prezzoBase": 120000.0,
     "offertaMinima": 90000.0, "dataOraVendita": "2027-01-20T10:00:00", "tribunale": "Verona",
     "numeroProcedura": "321", "annoProcedura": "2024", "lat": 45.4410, "lng": 10.9975},
    {"idAnnuncio": 123457, "tipologia": "Box", "descLotto": "Autorimessa", "comune": "Verona",
     "prezzoBase": 15000.0, "dataOraVendita": 1800000000000},
    {"idAnnuncio": 123458, "tipologia": "Appartamento", "descLotto": "Quota di 1/2 di appartamento",
     "comune": "San Giovanni Lupatoto", "prezzoBase": 50000.0},
    {"idAnnuncio": 123459, "tipologia": "Villa", "descLotto": "Villa con giardino, quota di 1/2 della piena proprietà",
     "comune": "Verona", "indirizzo": "Via Belluno 3", "prezzoBase": 400000.0, "offertaMinima": 300000.0},
]}, "totalElements": 4}


def test_lotti_da_json():
    lotti = pvp.lotti_da_json(RISPOSTA, comune="Verona")
    assert [l.source_id for l in lotti] == ["123456", "123457", "123459"]      # San Giovanni escluso
    a = lotti[0]
    assert a.source == "pvp" and a.prezzo == 90000 and a.mq == 85 and a.indirizzo == "Via Mazzini 10"
    assert a.url.endswith("idAnnuncio=123456") and a.lat == 45.441 and "portale: asta" in a.flags
    assert "Prezzo base € 120.000" in a.descrizione and "Data asta 20/01/2027" in a.descrizione
    assert "R.G.E. 321/2024" in a.descrizione and a.agenzia == "Tribunale di Verona"
    assert "diritto: quota 1/2" in lotti[2].flags


def test_lotti_pvp_puliti_e_classificati():
    cfg = load_config()
    appartamento, box, villa = pvp.lotti_da_json(RISPOSTA, comune="Verona")
    ok, motivo = valida(appartamento, cfg)
    assert not ok and motivo.startswith("asta") and appartamento.tipo_vendita == "asta"
    ok, motivo = valida(box, cfg)
    assert not ok and motivo.startswith("tipologia")                 # i box non sono abitazioni
    ok, motivo = valida(villa, cfg)                                   # senza mq: resta tra le aste
    assert not ok and motivo.startswith("asta") and "mq mancanti" in villa.flags


def test_diritto_e_occupazione():
    assert diritto("piena proprietà per la quota di 1/1") == "piena proprietà"
    assert diritto("quota di 1/2 della piena proprietà") == "quota 1/2"
    assert diritto("nuda proprietà dell'appartamento") == "nuda proprietà"
    assert diritto("appartamento libero da usufrutto, piena proprietà") == "piena proprietà"
    assert diritto("bel trilocale") is None
    assert occupazione("immobile occupato dal debitore esecutato") == "occupato dal debitore"
    assert occupazione("libero al decreto di trasferimento") == "libero"


def test_pagina_salvata(tmp_path):
    html = """<html><head><title>Portale delle Vendite Pubbliche</title></head><body>
    <div class="risultati">
      <div class="card"><a href="/pvp/it/detail_annuncio.page?idAnnuncio=777">Dettaglio</a>
        <p>Appartamento - Via Roma 5, Verona (VR)</p><p>Prezzo base € 150.000,00</p>
        <p>Offerta minima € 112.500,00</p><p>Data vendita 03/02/2027 ore 10:00</p><p>Superficie 70 mq</p></div>
      <div class="card"><a href="/pvp/it/detail_annuncio.page?idAnnuncio=778">Dettaglio</a>
        <p>Negozio - Corso Porta Nuova 2, Verona (VR)</p><p>Prezzo base € 90.000,00</p></div>
    </div><footer>pvp.giustizia.it</footer></body></html>"""
    f = tmp_path / "pvp.html"
    f.write_text(html, encoding="utf-8")
    lotti = parse_html_file(f, "Verona")
    assert [l.source_id for l in lotti] == ["777", "778"]
    a = lotti[0]
    assert a.prezzo == 112500 and a.mq == 70 and a.indirizzo.startswith("Via Roma 5")
    assert "Data asta 03/02/2027" in a.descrizione
    j = tmp_path / "risposta.json"
    j.write_text(json.dumps(RISPOSTA), encoding="utf-8")
    assert len(parse_html_file(j, "Verona")) == 3


def test_pvp_nella_sezione_aste_e_unito_al_portale(tmp_path):
    """Lo stesso lotto sul PVP e su Immobiliare diventa una riga sola nelle Aste (vince il PVP);
    nessun lotto PVP entra nella valutazione del mercato libero."""
    cfg = _cfg(tmp_path)
    zone = MicrozoneSet.load(cfg["microzone"]["file"])
    st = Storage(cfg["database"])
    rnd = random.Random(5)
    z0 = zone.zone[0]
    lat, lon = _punto_in(z0, rnd)
    risposta = json.loads(json.dumps(RISPOSTA))
    lotto = risposta["body"]["content"][0]
    lotto["lat"], lotto["lng"] = lat, lon
    lotti = pvp.lotti_da_json(risposta, comune="Verona")
    portale = Listing(source="immobiliare", source_id="A9", url="https://example/a9", mq=84, lat=lat + 0.0003, lon=lon,
                      prezzo=120000, titolo="Appartamento all'asta",
                      descrizione="Asta giudiziaria. Prezzo base € 120.000, offerta minima € 90.000.")
    ingest(cfg, st, _annunci(zone, rnd) + [portale], zone, "immobiliare", True)
    ingest(cfg, st, lotti, zone, "pvp", True)
    r = analizza_e_esporta(cfg, st, zone, alert=False)
    df, aste = r["df"], r["aste"]
    assert not any(u.startswith("pvp:") for u in df["uid"])
    uids = set(aste["uid"])
    assert "pvp:123456" in uids and "immobiliare:A9" not in uids
    a = aste.set_index("uid").loc["pvp:123456"]
    assert a["microzona"] == z0.nome and a["diritto"] == "piena proprietà" and a["occupazione"] == "libero"
    assert len(a["doppioni"]) == 1 and "immobiliare" in a["doppioni"][0]
    assert a["prezzo_base"] == 120000 and a["offerta_minima"] == 90000 and a["data_asta"] == "2027-01-20"
    villa = aste.set_index("uid").loc["pvp:123459"]
    assert villa["base_confronto"] == "mq mancanti" and villa["diritto"] == "quota 1/2"


def test_box_nella_descrizione_non_scarta():
    cfg = load_config()
    l = Listing(source="subito", source_id="B", prezzo=200000, mq=80, lat=45.44, lon=10.98,
                titolo="Trilocale luminoso", descrizione="Trilocale con cantina e box auto doppio.")
    assert valida(l, cfg)[0]
    l2 = Listing(source="subito", source_id="C", prezzo=20000, mq=20, lat=45.44, lon=10.98, titolo="Box auto in vendita")
    assert valida(l2, cfg) == (False, "esclusione: 'box auto'")


def test_scrape_conta_i_lotti_ricevuti_e_salva_la_risposta(tmp_path):
    """Il servizio può ignorare il filtro per comune: si continua a sfogliare finché le pagine sono piene
    (contando i lotti ricevuti) e la risposta resta in data/log/pvp/ per il controllo."""
    class R:
        status_code = 200

        def __init__(self, d):
            self.d = d

        def json(self):
            return self.d

    def pagina(n):
        return {"body": {"content": [
            {"idAnnuncio": n * 10 + i, "comune": "Verona" if i == 0 else "Padova", "prezzoBase": 100000.0 + i}
            for i in range(2)]}, "totalElements": 4}

    chiamate = []

    class Client:
        def post_json(self, url, corpo):
            chiamate.append(url)
            return R(pagina(len(chiamate)) if len(chiamate) <= 2 else {"body": {"content": []}})

    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["aste_pvp"] = {**cfg["aste_pvp"], "per_pagina": 2, "max_pagine": 5}
    lotti = pvp.scrape(cfg, Client())
    assert [l.source_id for l in lotti] == ["10", "20"] and len(chiamate) == 3
    assert (tmp_path / "data/log/pvp/pagina_1.json").exists()


def _lotto_reale(i, citta, data, trib="Tribunale di VERONA"):
    """Forma reale della risposta del PVP (novembre 2026)."""
    return {"id": i, "tipoLotto": "IMMOBILI", "categoriaLotto": "IMMOBILE_RESIDENZIALE", "categoriaBene": ["APPARTAMENTO"],
            "indirizzo": {"via": "Via Roma 1", "cap": "37100", "citta": citta, "provincia": "Verona",
                          "coordinate": {"latitudine": 45.44, "longitudine": 10.99}},
            "procedura": "12", "prezzoBaseAsta": 100000.0, "dataVendita": data, "dataOraVendita": data + "T10:00",
            "offertaMinima": 75000.0, "disponibilita": ["LIBER"], "descLotto": "Appartamento di 80 mq",
            "tribunale": trib, "codiceTribunale": "0"}


def test_pvp_filtra_per_tribunale_e_scarta_le_aste_vecchie(tmp_path):
    import datetime as dt
    oggi = dt.date.today()
    futura, vecchia = str(oggi + dt.timedelta(days=30)), str(oggi - dt.timedelta(days=400))

    class R:
        status_code = 200

        def __init__(self, d):
            self.d = d

        def json(self):
            return self.d

    corpi, urls = [], []

    class Client:
        def post_json(self, url, corpo):
            corpi.append(corpo)
            urls.append(url)
            if len(corpi) == 1:
                return R({"body": {"content": [_lotto_reale(1, "Verona", futura), _lotto_reale(2, "Bussolengo", futura)],
                                   "totalElements": 4}})
            return R({"body": {"content": [_lotto_reale(3, "Verona", vecchia), _lotto_reale(4, "Verona", vecchia)]}})

    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["aste_pvp"] = {**cfg["aste_pvp"], "per_pagina": 2, "max_pagine": 5}
    lotti = pvp.scrape(cfg, Client())
    assert corpi[0]["tribunale"] == "Tribunale di VERONA" and "desc" in urls[0]
    assert [l.source_id for l in lotti] == ["1"] and len(corpi) == 2      # si ferma alla pagina di aste vecchie
    assert lotti[0].lat == 45.44 and lotti[0].prezzo == 75000


def test_tribunale_da_config():
    cfg = load_config()
    cfg["territorio"] = {**cfg["territorio"], "comune": "San Giovanni Lupatoto"}
    cfg["aste_pvp"] = {**cfg["aste_pvp"], "tribunale": "Tribunale di Verona"}
    assert pvp.tribunale(cfg) == "Tribunale di VERONA"


def test_pvp_continua_se_non_e_l_ultima_pagina():
    """Un lotto senza prezzo base non fa credere che la pagina sia l'ultima: conta "last" del servizio."""
    assert not pvp._ultima_pagina({"body": {"content": [{}, {}], "last": False}}, 1, 2)
    assert pvp._ultima_pagina({"body": {"content": [{}], "last": True}}, 1, 2)
    assert not pvp._ultima_pagina({"body": {"content": [{}, {}]}}, 1, 2)
    assert pvp._ultima_pagina({"body": {"content": [{}]}}, 1, 2)
