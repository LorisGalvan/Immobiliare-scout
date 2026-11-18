"""Storico su SQLite: annunci, variazioni di prezzo, rimozioni, alert inviati."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS annunci (
  uid TEXT PRIMARY KEY, source TEXT, source_id TEXT, url TEXT, titolo TEXT, descrizione TEXT,
  prezzo REAL, mq REAL, piano TEXT, ascensore INTEGER, bagni INTEGER, locali INTEGER,
  stato TEXT, stato_raw TEXT, agenzia TEXT, privato INTEGER, data_pubblicazione TEXT,
  indirizzo TEXT, lat REAL, lon REAL, coord_precise INTEGER, tipologia TEXT,
  prezzo_ribassato_da REAL, microzona TEXT, flags TEXT, doppioni TEXT,
  scartato INTEGER DEFAULT 0, motivo_scarto TEXT, gruppo TEXT,
  prezzo_iniziale REAL, first_seen TEXT, last_seen TEXT, attivo INTEGER DEFAULT 1, removed_at TEXT
);
CREATE TABLE IF NOT EXISTS prezzi (uid TEXT, data TEXT, prezzo REAL, PRIMARY KEY (uid, data));
CREATE TABLE IF NOT EXISTS alert_inviati (uid TEXT, tipo TEXT, data TEXT, PRIMARY KEY (uid, tipo));
CREATE TABLE IF NOT EXISTS esecuzioni (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, fonte TEXT,
  annunci INTEGER, nuovi INTEGER, ribassi INTEGER, rimossi INTEGER, completa INTEGER, note TEXT);
CREATE INDEX IF NOT EXISTS ix_annunci_zona ON annunci(microzona);
"""
# colonne aggiunte dopo la prima versione: create al volo nei database esistenti
COLONNE_NUOVE = {"tipo_vendita": "TEXT", "indizi_vendita": "TEXT"}

CAMPI = ["source", "source_id", "url", "titolo", "descrizione", "prezzo", "mq", "piano", "ascensore",
         "bagni", "locali", "stato", "stato_raw", "agenzia", "privato", "data_pubblicazione",
         "indirizzo", "lat", "lon", "coord_precise", "tipologia", "prezzo_ribassato_da", "microzona"]


def oggi() -> str:
    return dt.date.today().isoformat()


class Storage:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        esistenti = {r[1] for r in self.conn.execute("PRAGMA table_info(annunci)")}
        for col, tipo in COLONNE_NUOVE.items():
            if col not in esistenti:
                self.conn.execute(f"ALTER TABLE annunci ADD COLUMN {col} {tipo}")
        self.conn.commit()
        self.path = str(path)

    # ------------------------------------------------------------------ scrittura
    def upsert(self, listings: list[Listing], giorno: str | None = None) -> dict:
        giorno = giorno or oggi()
        stats = {"nuovi": [], "ribassi": [], "aggiornati": 0}
        cur = self.conn.cursor()
        for l in listings:
            row = cur.execute("SELECT prezzo, first_seen, attivo FROM annunci WHERE uid=?", (l.uid,)).fetchone()
            vals = [getattr(l, c) for c in CAMPI]
            if row is None:
                cur.execute(
                    f"INSERT INTO annunci (uid,{','.join(CAMPI)},flags,doppioni,prezzo_iniziale,first_seen,last_seen,attivo) "
                    f"VALUES (?,{','.join('?' * len(CAMPI))},?,?,?,?,?,1)",
                    [l.uid, *vals, json.dumps(l.flags), json.dumps(l.doppioni),
                     l.prezzo_ribassato_da or l.prezzo, l.data_pubblicazione or giorno, giorno])
                stats["nuovi"].append(l.uid)
            else:
                # non sovrascrivere campi noti con valori mancanti
                sets, params = [], []
                for c, v in zip(CAMPI, vals):
                    if v not in (None, ""):
                        sets.append(f"{c}=?")
                        params.append(v)
                sets += ["flags=?", "doppioni=?", "last_seen=?", "attivo=1", "removed_at=NULL"]
                params += [json.dumps(l.flags), json.dumps(l.doppioni), giorno]
                cur.execute(f"UPDATE annunci SET {','.join(sets)} WHERE uid=?", [*params, l.uid])
                if l.prezzo and row["prezzo"] and l.prezzo < row["prezzo"] - 1:
                    stats["ribassi"].append((l.uid, row["prezzo"], l.prezzo))
                stats["aggiornati"] += 1
            if l.prezzo:
                cur.execute("INSERT OR REPLACE INTO prezzi VALUES (?,?,?)", (l.uid, giorno, l.prezzo))
        self.conn.commit()
        return stats

    def segna_rimossi(self, source: str, visti: set[str], giorno: str | None = None) -> list[str]:
        """Da chiamare solo se lo scraping della fonte è stato completo."""
        giorno = giorno or oggi()
        rows = self.conn.execute("SELECT uid FROM annunci WHERE source=? AND attivo=1", (source,)).fetchall()
        rimossi = [r["uid"] for r in rows if r["uid"] not in visti]
        self.conn.executemany("UPDATE annunci SET attivo=0, removed_at=? WHERE uid=?",
                              [(giorno, u) for u in rimossi])
        self.conn.commit()
        return rimossi

    def aggiorna_campi(self, uid: str, **campi):
        if not campi:
            return
        for k in ("flags", "doppioni", "indizi_vendita"):
            if k in campi and not isinstance(campi[k], str):
                campi[k] = json.dumps(campi[k])
        sets = ",".join(f"{k}=?" for k in campi)
        self.conn.execute(f"UPDATE annunci SET {sets} WHERE uid=?", [*campi.values(), uid])

    def commit(self):
        self.conn.commit()

    def log_esecuzione(self, fonte, annunci, nuovi, ribassi, rimossi, completa, note=""):
        self.conn.execute("INSERT INTO esecuzioni (ts,fonte,annunci,nuovi,ribassi,rimossi,completa,note) "
                          "VALUES (?,?,?,?,?,?,?,?)",
                          (dt.datetime.now().isoformat(timespec="seconds"), fonte, annunci, nuovi,
                           ribassi, rimossi, int(completa), note))
        self.conn.commit()

    # ------------------------------------------------------------------ alert
    def gia_avvisato(self, uid: str, tipo: str) -> bool:
        return self.conn.execute("SELECT 1 FROM alert_inviati WHERE uid=? AND tipo=?", (uid, tipo)).fetchone() is not None

    def segna_avvisato(self, uid: str, tipo: str):
        self.conn.execute("INSERT OR IGNORE INTO alert_inviati VALUES (?,?,?)", (uid, tipo, oggi()))
        self.conn.commit()

    # ------------------------------------------------------------------ lettura
    def dataframe(self):
        import pandas as pd
        df = pd.read_sql_query("SELECT * FROM annunci", self.conn)
        if df.empty:
            return df
        storia = pd.read_sql_query("SELECT uid, COUNT(*) n_prezzi, MIN(prezzo) pmin, MAX(prezzo) pmax FROM prezzi GROUP BY uid",
                                   self.conn)
        df = df.merge(storia, on="uid", how="left")
        df["ascensore"] = df["ascensore"].map({1: True, 0: False})
        df["privato"] = df["privato"].map({1: True, 0: False})
        return df

    def listings(self, solo_attivi: bool = True) -> list[Listing]:
        q = "SELECT * FROM annunci" + (" WHERE attivo=1" if solo_attivi else "")
        out = []
        for r in self.conn.execute(q).fetchall():
            l = Listing(**{c: r[c] for c in CAMPI})
            l.ascensore = None if r["ascensore"] is None else bool(r["ascensore"])
            l.privato = None if r["privato"] is None else bool(r["privato"])
            l.coord_precise = bool(r["coord_precise"])
            l.flags = json.loads(r["flags"] or "[]")
            l.doppioni = json.loads(r["doppioni"] or "[]")
            out.append(l)
        return out
