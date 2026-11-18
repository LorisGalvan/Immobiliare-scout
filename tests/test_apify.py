"""Immobiliare tramite Apify: conversione dei risultati dei due actor e gestione dell'esecuzione."""
from scout.cleaning import valida
from scout.config import load_config
from scout.scrapers import apify_immobiliare as ap

CRAWLOOP = {"id": "123456789", "url": "https://www.immobiliare.it/annunci/123456789/", "title": "Trilocale via Mazzini",
            "contract": "sale", "typology": "Appartamento", "price": 245000, "surfaceValue": 92, "floor": "2",
            "elevator": True, "bathroomsValue": 2, "roomsValue": 3, "condition": "Buono / Abitabile",
            "isPrivate": False, "agencyName": "Agenzia Centro", "address": "Via Mazzini 10", "latitude": 45.4410,
            "longitude": 10.9975, "description": "Luminoso trilocale con cantina."}
IGOLAIZOLA = {"id": 120063188, "title": "Apartment",
              "analytics": {"contract": "vendita", "floor": "5", "elevator": True, "advertiser": "agenzia",
                            "agencyName": "Ius Brenta Aste", "typology": "Appartamento"},
              "topology": {"surface": {"size": 86}, "rooms": "5+", "bathrooms": "1", "floor": "5", "lift": True},
              "price": {"value": "€ 202.500", "raw": 202500},
              "geography": {"geolocation": {"latitude": 45.43, "longitude": 10.99}}}


def test_conversione_crawloop():
    l = ap.a_listing(CRAWLOOP)
    assert l.uid == "immobiliare:123456789" and l.prezzo == 245000 and l.mq == 92 and l.piano == "2"
    assert l.lat == 45.441 and l.agenzia == "Agenzia Centro" and l.privato is False and l.bagni == 2
    assert l.descrizione.startswith("Luminoso") and not l.flags


def test_conversione_igolaizola_e_asta():
    l = ap.a_listing(IGOLAIZOLA)
    assert l.uid == "immobiliare:120063188" and l.prezzo == 202500 and l.mq == 86 and l.lon == 10.99
    asta = ap.a_listing({**CRAWLOOP, "id": "9", "contract": "auction"})
    assert asta.flags == ["portale: asta"]
    ok, motivo = valida(asta, load_config())
    assert not ok and motivo.startswith("asta")            # va nella sezione Aste


def test_input_per_actor():
    cfg = load_config()
    c = ap.input_actor(cfg, "crawloop/immobiliare-it-scraper")
    assert len(c) == 2 and "aste-immobiliari/verona" in c[1]["startUrls"][0]["url"] and c[1]["maxItems"] == 300
    i = ap.input_actor(cfg, "igolaizola/immobiliare-it-scraper")
    assert [x["operation"] for x in i] == ["buy", "auction"] and i[0]["municipality"] == "Verona"


class _R:
    def __init__(self, d, code=200):
        self.d, self.status_code, self.text = d, code, ""

    def json(self):
        return self.d

    def raise_for_status(self):
        pass


class _Sessione:
    def __init__(self, righe, stati=("RUNNING", "SUCCEEDED")):
        self.headers, self.righe, self.stati = {}, righe, list(stati)

    def post(self, url, json, timeout, params=None):
        assert params and params["timeout"] > 300          # timeout della run passato ad Apify
        assert "/acts/crawloop~immobiliare-it-scraper/runs" in url
        return _R({"data": {"id": "r1", "status": "READY", "defaultDatasetId": "d1"}})

    def get(self, url, params=None, timeout=None):
        if "/actor-runs/" in url:
            return _R({"data": {"id": "r1", "status": self.stati.pop(0), "defaultDatasetId": "d1", "usageTotalUsd": 0.2}})
        return _R(self.righe[params["offset"]:params["offset"] + params["limit"]])


def test_esecuzione_e_dataset_paginato():
    righe = [{**CRAWLOOP, "id": str(i)} for i in range(1500)]
    out = ap.esegui_actor("tok", "crawloop/immobiliare-it-scraper", {}, sessione=_Sessione(righe), pausa_s=0)
    assert len(out) == 1500


def test_scrape_parziale_se_raggiunge_il_limite(monkeypatch):
    cfg = load_config()
    cfg["apify"] = {**cfg["apify"], "token": "x", "max_annunci": 2, "includi_aste": False}
    monkeypatch.setattr(ap, "esegui_actor", lambda *a, **k: [{**CRAWLOOP, "id": "1"}, {**CRAWLOOP, "id": "2"}])
    res, completa = ap.scrape(cfg)
    assert len(res) == 2 and completa is False             # limite raggiunto: non segna rimossi
    cfg["apify"]["max_annunci"] = 100
    assert ap.scrape(cfg)[1] is True
    cfg["apify"]["token"] = ""
    monkeypatch.delenv("SCOUT_APIFY_TOKEN", raising=False)
    assert ap.scrape(cfg) == ([], False)


class _Sess:
    """Finta sessione: la seconda lettura dello stato fallisce (rete assente), poi va."""
    def __init__(self):
        self.headers, self.n, self.post_fatti = {}, 0, 0

    def post(self, *a, **k):
        self.post_fatti += 1

    def get(self, url, **k):
        import requests
        self.n += 1
        if "actor-runs" in url:
            if self.n == 2:
                raise requests.ConnectionError("getaddrinfo failed")
            return _R({"data": {"id": "R1", "status": "RUNNING" if self.n == 1 else "SUCCEEDED",
                                "defaultDatasetId": "D1"}})
        return _R([{"id": "1"}])


def test_recupero_run_e_rete_che_cade():
    s = _Sess()
    righe = ap.esegui_actor("tok", "x/y", {}, sessione=s, pausa_s=0, run_id="R1")
    assert righe == [{"id": "1"}] and s.post_fatti == 0       # niente nuovo avvio (non si paga di nuovo)


def test_run_in_timeout_tiene_gli_annunci():
    s = _Sessione([{"id": "1"}, {"id": "2"}], stati=("RUNNING", "TIMED-OUT"))
    righe = ap.esegui_actor("tok", "crawloop/immobiliare-it-scraper", {}, sessione=s, pausa_s=0)
    assert len(righe) == 2 and righe.parziale is True
