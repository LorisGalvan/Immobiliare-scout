import datetime as dt
import gzip
import json
import sqlite3

import pytest

from scout.archivio_cloud import ArchivioCloud, ArchivioError


class _Risposta:
    def __init__(self, status, content=b"", text=""):
        self.status_code, self.content, self.text = status, content, text or content.decode("latin1")


class FintoStorage:
    """Supabase Storage in memoria: GET/POST/DELETE sugli oggetti, creazione bucket."""
    url = "https://finto.supabase.co"

    def __init__(self):
        self.oggetti, self.bucket = {}, set()

    def _richiesta(self, metodo, url, **kw):
        if url.endswith("/storage/v1/bucket"):
            if kw["json"]["id"] in self.bucket:
                return _Risposta(400, text='{"message":"The resource already exists"}')
            self.bucket.add(kw["json"]["id"])
            return _Risposta(200, b"{}")
        nome = url.split("/storage/v1/object/", 1)[1]
        if metodo == "GET":
            if nome not in self.oggetti:
                return _Risposta(400, text='{"statusCode":"404","error":"not_found","message":"Object not found"}')
            return _Risposta(200, self.oggetti[nome])
        if metodo == "POST":
            self.oggetti[nome] = kw["data"]
            return _Risposta(200, b"{}")
        if metodo == "DELETE":
            self.oggetti.pop(nome, None)
            return _Risposta(200, b"{}")
        raise AssertionError(metodo)


def _db(path, n):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS t (x INT)")
    c.execute("DELETE FROM t")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(n)])
    c.commit()
    c.close()


def _righe(path):
    return sqlite3.connect(path).execute("SELECT COUNT(*) FROM t").fetchone()[0]


def _cfg(modo="auto"):
    return {"archivio_cloud": {"attivo": modo}}


def test_auto_senza_archivio_online_usa_il_file_locale(tmp_path):
    db = tmp_path / "scout.sqlite"
    _db(db, 3)
    fs = FintoStorage()
    a = ArchivioCloud(_cfg(), db, sb=fs)
    assert a.scarica() is False
    a.carica()
    assert fs.oggetti == {}             # niente caricato: come prima della migrazione
    assert _righe(db) == 3


def test_obbligatorio_senza_archivio_online_si_ferma(tmp_path):
    with pytest.raises(ArchivioError, match="CARICA_ARCHIVIO"):
        ArchivioCloud(_cfg(True), tmp_path / "scout.sqlite", sb=FintoStorage()).scarica()


def test_prima_volta_poi_giro_condiviso(tmp_path):
    fs = FintoStorage()
    pc = tmp_path / "pc" / "scout.sqlite"
    pc.parent.mkdir()
    _db(pc, 5)
    ArchivioCloud(_cfg(), pc, sb=fs).prima_volta()
    assert "archivio" in fs.bucket and "archivio/scout.sqlite.gz" in fs.oggetti
    assert "archivio/lock.json" not in fs.oggetti
    assert any(k.startswith("archivio/copie/") for k in fs.oggetti)
    with pytest.raises(ArchivioError, match="già un archivio"):
        ArchivioCloud(_cfg(), pc, sb=fs).prima_volta()

    # GitHub: parte senza file locale, scarica, aggiunge righe, ricarica
    gh = tmp_path / "gh" / "scout.sqlite"
    a = ArchivioCloud(_cfg(True), gh, sb=fs)
    assert a.scarica() is True and _righe(gh) == 5
    assert "archivio/lock.json" in fs.oggetti
    _db(gh, 8)
    a.carica()
    a.rilascia()
    assert "archivio/lock.json" not in fs.oggetti

    # il PC in modalità auto ora riceve la versione aggiornata, e tiene una copia della sua
    b = ArchivioCloud(_cfg(), pc, sb=fs)
    assert b.scarica() is True and _righe(pc) == 8
    assert _righe(pc.with_name("scout.backup.sqlite")) == 5
    b.rilascia()


def test_lucchetto_blocca_un_secondo_giro(tmp_path):
    fs = FintoStorage()
    fs.oggetti["archivio/scout.sqlite.gz"] = gzip.compress(b"")
    fs.oggetti["archivio/lock.json"] = json.dumps(
        {"da": "PC casa", "inizio": dt.datetime.now(dt.timezone.utc).isoformat()}).encode()
    with pytest.raises(ArchivioError, match="in uso da PC casa"):
        ArchivioCloud(_cfg(True), tmp_path / "s.sqlite", sb=fs).scarica()
    # la sola lettura (es. "stato") non prende il lucchetto e non è bloccata
    assert ArchivioCloud(_cfg(True), tmp_path / "s.sqlite", sb=fs).scarica(modifica=False) is True


def test_lucchetto_scaduto_viene_ignorato(tmp_path):
    fs = FintoStorage()
    fs.oggetti["archivio/scout.sqlite.gz"] = gzip.compress(b"")
    vecchio = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)
    fs.oggetti["archivio/lock.json"] = json.dumps({"da": "x", "inizio": vecchio.isoformat()}).encode()
    a = ArchivioCloud(_cfg(True), tmp_path / "s.sqlite", sb=fs)
    assert a.scarica() is True
    assert json.loads(fs.oggetti["archivio/lock.json"])["da"] != "x"


def test_disattivo_non_tocca_nulla(tmp_path):
    fs = FintoStorage()
    fs.oggetti["archivio/scout.sqlite.gz"] = gzip.compress(b"x")
    assert ArchivioCloud(_cfg(False), tmp_path / "s.sqlite", sb=fs).scarica() is False


def test_cli_scarica_e_ricarica(tmp_path, monkeypatch):
    """Il comando 'stato' (sola lettura) e 'analizza' passano dall'archivio online."""
    import scout.archivio_cloud as ac
    from scout import cli

    fs = FintoStorage()
    sorgente = tmp_path / "orig.sqlite"
    from scout.storage import Storage
    Storage(sorgente).conn.close()
    fs.oggetti["archivio/scout.sqlite.gz"] = gzip.compress(sorgente.read_bytes())
    monkeypatch.setattr(ac, "Supabase", lambda url, key: fs)
    cfg = tmp_path / "config.yaml"
    zone = tmp_path / "zone.geojson"
    zone.write_text('{"type": "FeatureCollection", "features": []}')
    cfg.write_text(
        "territorio: {nome: Test, comune: Test}\n"
        f"microzone: {{file: {zone.as_posix()}}}\n"
        "database: data/scout.sqlite\n"
        "archivio_cloud: {attivo: true}\n"
        "supabase: {attivo: false, url: 'https://finto.supabase.co', service_key: k}\n")
    cli.main(["-c", str(cfg), "stato"])
    assert (tmp_path / "data" / "scout.sqlite").exists()
    assert set(fs.oggetti) == {"archivio/scout.sqlite.gz"}      # lettura: niente ricaricato
    cli.main(["-c", str(cfg), "scrape", "--siti", "nessuno"])
    assert "archivio/scout.sqlite.gz" in fs.oggetti and "archivio/lock.json" not in fs.oggetti
    assert any(k.startswith("archivio/copie/") for k in fs.oggetti)   # modifica: ricaricato
