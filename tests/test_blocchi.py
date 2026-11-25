import requests

from scout.scrapers.base import BloccatoError, PoliteClient


def _resp(status, testo, server="AkamaiGHost"):
    r = requests.Response()
    r.status_code = status
    r._content = testo.encode()
    r.headers["Server"] = server
    return r


def test_akamai_access_denied_si_ferma_subito(monkeypatch):
    cfg = {"scraping": {"pausa_min_s": 0, "pausa_max_s": 0, "backoff_base_s": 0, "rispetta_robots_txt": False}}
    c = PoliteClient(cfg)
    chiamate = []

    def finto(metodo, url, **kw):
        chiamate.append(url)
        return _resp(403, "<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD></HTML>")

    monkeypatch.setattr(c.session, "request", finto)
    try:
        c.get("https://www.subito.it/annunci-veneto/vendita/appartamenti/verona/verona/")
        assert False, "doveva fermarsi"
    except BloccatoError as e:
        assert "403" in str(e)
    assert len(chiamate) == 1   # nessun nuovo tentativo


def test_altri_403_riprovano():
    assert not PoliteClient.blocco_ip(_resp(403, "Forbidden", server="nginx"))
    assert PoliteClient.blocco_ip(_resp(403, "Access Denied"))
    assert "server=AkamaiGHost" in PoliteClient.descrivi_blocco(_resp(403, "Access Denied"))
