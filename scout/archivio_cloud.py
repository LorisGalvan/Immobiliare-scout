"""Archivio degli annunci (il file SQLite) conservato online, in uno spazio PRIVATO di Supabase Storage.

Così il bot non dipende più da un solo PC: prima di ogni comando che usa l'archivio si scarica
l'ultima copia, alla fine si ricarica quella aggiornata. Lo usano sia GitHub Actions sia i .bat del PC.

Modalità (sezione ``archivio_cloud`` della configurazione, facoltativa):
- ``attivo: auto`` (predefinito): se ci sono le credenziali Supabase E l'archivio online esiste già,
  lo si usa; altrimenti il bot lavora sul file locale come sempre. Così, dopo CARICA_ARCHIVIO.bat,
  il PC passa da solo all'archivio condiviso senza modificare alcun file.
- ``attivo: true``: archivio online obbligatorio (GitHub Actions). Se manca, ci si ferma con un errore
  invece di ripartire da un archivio vuoto.
- ``attivo: false``: solo file locale.

Un piccolo "lucchetto" (file lock.json) evita che due giri (es. PC e GitHub) lavorino insieme
sull'archivio e che uno cancelli il lavoro dell'altro.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import logging
import os
import shutil
import socket
from pathlib import Path

import requests

from .supabase_sync import Supabase, credenziali

log = logging.getLogger(__name__)

BUCKET = "archivio"
OGGETTO = "scout.sqlite.gz"
LUCCHETTO = "lock.json"
LUCCHETTO_SCADENZA_ORE = 4        # un giro interrotto di colpo non blocca per sempre
LIMITE_MB = 45                    # il piano gratuito di Supabase accetta file fino a 50 MB


class ArchivioError(RuntimeError):
    """Errore da mostrare così com'è a Loris (messaggio già in italiano semplice)."""


def _impostazioni(cfg) -> dict:
    a = cfg.get("archivio_cloud") or {}
    modo = os.environ.get("SCOUT_ARCHIVIO_CLOUD", a.get("attivo", "auto"))
    modo = {"1": True, "true": True, "0": False, "false": False}.get(str(modo).lower(), modo)
    if modo not in (True, False, "auto"):
        modo = "auto"
    return {"modo": modo, "bucket": a.get("bucket", BUCKET), "oggetto": a.get("file", OGGETTO)}


def _chi() -> str:
    if os.environ.get("GITHUB_ACTIONS"):
        return f"GitHub (giro {os.environ.get('GITHUB_RUN_NUMBER', '?')})"
    return f"PC {socket.gethostname()}"


def _mancante(r) -> bool:
    # Supabase Storage risponde 404, oppure 400 con "not found", per file o bucket inesistenti
    return r.status_code == 404 or (r.status_code == 400 and "not found" in r.text.lower())


class ArchivioCloud:
    def __init__(self, cfg, db_path: str | Path, sb: Supabase | None = None):
        imp = _impostazioni(cfg)
        self.modo, self.bucket, self.oggetto = imp["modo"], imp["bucket"], imp["oggetto"]
        self.db = Path(db_path)
        url, key = credenziali(cfg)
        if sb is None and url and key:
            sb = Supabase(url, key)
        self.sb = sb
        self.in_uso = False          # True solo se l'archivio online è stato scaricato (e va ricaricato)
        self._lucchetto_mio = False
        # file vuoto che ricorda "questo PC usa l'archivio online": senza internet ci si ferma
        # invece di lavorare di nascosto su una copia locale che poi non verrebbe condivisa
        self.segnaposto = self.db.with_name(".archivio_online")

    # ------------------------------------------------------------------ utilità
    def _url(self, nome: str) -> str:
        return f"{self.sb.url}/storage/v1/object/{self.bucket}/{nome}"

    def _scarica_oggetto(self, nome: str):
        r = self.sb._richiesta("GET", self._url(nome), timeout=300)
        if _mancante(r):
            return None
        if r.status_code >= 300:
            raise ArchivioError(f"Non riesco a leggere l'archivio online ({nome}): HTTP {r.status_code} {r.text[:200]}")
        return r.content

    def _carica_oggetto(self, nome: str, dati: bytes, tipo: str):
        r = self.sb._richiesta("POST", self._url(nome), data=dati, timeout=300,
                               headers={"Content-Type": tipo, "x-upsert": "true"})
        if r.status_code >= 300:
            raise ArchivioError(f"Non riesco a salvare l'archivio online ({nome}): HTTP {r.status_code} {r.text[:200]}")

    def _crea_bucket(self):
        r = self.sb._richiesta("POST", f"{self.sb.url}/storage/v1/bucket", timeout=60,
                               json={"id": self.bucket, "name": self.bucket, "public": False})
        if r.status_code >= 300 and "exist" not in r.text.lower() and r.status_code != 409:
            raise ArchivioError(f"Non riesco a creare lo spazio privato '{self.bucket}' su Supabase: "
                                f"HTTP {r.status_code} {r.text[:200]}")

    # ------------------------------------------------------------------ lucchetto
    def _prendi_lucchetto(self):
        dati = self._scarica_oggetto(LUCCHETTO)
        if dati and not os.environ.get("SCOUT_IGNORA_LUCCHETTO"):
            try:
                info = json.loads(dati)
                inizio = dt.datetime.fromisoformat(info["inizio"])
            except (ValueError, KeyError, TypeError):
                info, inizio = {}, dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
            eta_ore = (dt.datetime.now(dt.timezone.utc) - inizio).total_seconds() / 3600
            if eta_ore < LUCCHETTO_SCADENZA_ORE:
                raise ArchivioError(
                    f"L'archivio è in uso da {info.get('da', 'un altro giro')} (iniziato {eta_ore * 60:.0f} minuti fa). "
                    f"Aspetta che finisca e riprova. Se sei sicuro che non stia girando nulla, "
                    f"il blocco si toglie da solo dopo {LUCCHETTO_SCADENZA_ORE} ore.")
            log.warning("archivio online: trovato un blocco vecchio (%s), lo ignoro", info.get("da"))
        self._carica_oggetto(LUCCHETTO, json.dumps(
            {"da": _chi(), "inizio": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}).encode(),
            "application/json")
        self._lucchetto_mio = True

    def rilascia(self):
        if not self._lucchetto_mio:
            return
        try:
            self.sb._richiesta("DELETE", self._url(LUCCHETTO), timeout=60)
        except Exception as e:  # noqa: BLE001 - un blocco rimasto scade da solo
            log.warning("archivio online: blocco non tolto (%s), scadrà da solo", e)
        self._lucchetto_mio = False

    # ------------------------------------------------------------------ operazioni
    def scarica(self, modifica: bool = True) -> bool:
        """Prima di un comando: porta in locale l'ultima copia online. True se l'archivio online è in uso."""
        if self.modo is False:
            return False
        if self.sb is None:
            if self.modo is True:
                raise ArchivioError("Archivio online attivo ma mancano le credenziali Supabase "
                                    "(SCOUT_SUPABASE_URL / SCOUT_SUPABASE_SERVICE_KEY).")
            return False
        try:
            dati = self._scarica_oggetto(self.oggetto)
        except (requests.ConnectionError, requests.Timeout) as e:
            if self.modo is True or self.segnaposto.exists():
                raise ArchivioError(f"Supabase non raggiungibile ({type(e).__name__}): senza internet non posso "
                                    "scaricare l'archivio condiviso. Riprova più tardi.") from e
            log.warning("Supabase non raggiungibile: uso l'archivio locale")
            return False
        if dati is None:
            if self.modo is True:
                raise ArchivioError("Non c'è ancora un archivio online. Dal PC di casa lancia una volta "
                                    "CARICA_ARCHIVIO.bat, poi riprova.")
            return False            # auto: si continua col file locale, come prima
        if modifica:
            self._prendi_lucchetto()
            # se nel frattempo un altro giro ha salvato, riscarico la versione più recente
            dati = self._scarica_oggetto(self.oggetto) or dati
        self.db.parent.mkdir(parents=True, exist_ok=True)
        if self.db.exists():
            shutil.copy2(self.db, self.db.with_name(self.db.stem + ".backup" + self.db.suffix))
        tmp = self.db.with_name(self.db.name + ".scaricato")
        tmp.write_bytes(gzip.decompress(dati))
        tmp.replace(self.db)
        self.in_uso = modifica
        self.segnaposto.touch()
        log.info("archivio online scaricato (%.1f MB)", self.db.stat().st_size / 1e6)
        return True

    def carica(self, forza_prima_volta: bool = False):
        """Dopo un comando: salva online la copia aggiornata (più una copia di sicurezza per giorno della settimana)."""
        if not (self.in_uso or forza_prima_volta):
            return
        if not self.db.exists():
            raise ArchivioError(f"Archivio locale non trovato: {self.db}")
        dati = gzip.compress(self.db.read_bytes(), compresslevel=6)
        mb = len(dati) / 1e6
        if mb > LIMITE_MB:
            raise ArchivioError(f"L'archivio compresso pesa {mb:.0f} MB, oltre il limite di {LIMITE_MB} MB "
                                "del piano gratuito di Supabase: avvisa chi gestisce il bot.")
        tipo = "application/gzip"
        self._carica_oggetto(self.oggetto, dati, tipo)
        giorno = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"][dt.date.today().weekday()]
        self._carica_oggetto(f"copie/{giorno}-{self.oggetto}", dati, tipo)
        self.segnaposto.touch()
        log.info("archivio online salvato (%.1f MB compressi)", mb)

    def prima_volta(self, forza: bool = False):
        """CARICA_ARCHIVIO.bat: mette online l'archivio del PC (solo se online non ce n'è già uno)."""
        if self.sb is None:
            raise ArchivioError("Mancano le credenziali Supabase in config.local.yaml (url e service_key).")
        if not self.db.exists():
            raise ArchivioError(f"Archivio locale non trovato: {self.db}")
        self._crea_bucket()
        if self._scarica_oggetto(self.oggetto) is not None and not forza:
            raise ArchivioError("Online c'è già un archivio: non lo sovrascrivo. D'ora in poi i .bat lo "
                                "scaricano da soli. (Per sostituirlo davvero con quello del PC: "
                                "CARICA_ARCHIVIO.bat forza)")
        self._prendi_lucchetto()
        try:
            self.carica(forza_prima_volta=True)
        finally:
            self.rilascia()


# comandi che leggono l'archivio, e quelli che lo modificano (e quindi lo ricaricano online)
COMANDI_LETTURA = {"stato", "esporta-json"}
COMANDI_MODIFICA = {"zone-importa-excel", "zone-rinomina", "scrape", "importa-html", "importa-csv",
                    "analizza", "run"}
