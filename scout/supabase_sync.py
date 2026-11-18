"""Pubblicazione dei risultati su Supabase (database + storage) per il sito web.

Usa direttamente le API REST di Supabase (PostgREST e Storage): nessuna
dipendenza aggiuntiva. Serve la chiave ``service_role`` del progetto, da tenere
SOLO sul PC che esegue il bot (config.local.yaml o variabile d'ambiente
SCOUT_SUPABASE_SERVICE_KEY), mai nel sito o su GitHub.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

log = logging.getLogger(__name__)

COL_ANNUNCI = ["uid", "source", "url", "titolo", "descrizione", "prezzo", "mq", "prezzo_mq", "piano",
               "ascensore", "bagni", "locali", "stato", "agenzia", "privato", "data_pubblicazione",
               "indirizzo", "lat", "lon", "microzona", "fascia", "riferimento_mq", "scostamento_pct",
               "scostamento_grezzo_pct", "base_confronto", "coeff", "occasione", "giorni_online",
               "ribasso_pct", "prezzo_iniziale", "first_seen", "last_seen", "attivo", "removed_at",
               "flags", "doppioni", "zona_omi", "omi_min", "omi_max"]
# colonne della migrazione 003 (aste): se il database non le ha ancora, si pubblica senza
COL_ASTE = ["tipo_vendita", "indizi_vendita", "prezzo_base", "offerta_minima", "data_asta",
            "scostamento_minima_pct", "valore_mercato", "diritto", "occupazione"]
COL_MEDIANE = ["microzona", "fascia", "n", "mediana_mq", "media_mq", "mediana_zona", "n_zona"]
COL_FRAZ = ["uid", "n_unita", "mq_unita", "mediana_piccole_mq", "n_campione_piccole", "valore_post",
            "costo_lavori", "costo_impianti_oneri", "costi_transazione", "costi_totali", "margine",
            "margine_pct", "indizi", "punteggio_indizi"]
INTERI = {"bagni", "locali", "giorni_online", "n", "n_zona", "n_unita", "n_campione_piccole", "punteggio_indizi"}
BOOL = {"ascensore", "privato", "occasione", "attivo"}
DATE = {"data_pubblicazione", "first_seen", "last_seen", "removed_at", "data_asta"}


def _clean(v, col=None):
    if isinstance(v, (list, dict)):
        return v
    if v is None:
        return None
    if isinstance(v, (np.generic,)):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NaT:
        return None
    if col in BOOL:
        return None if v is None else bool(v)
    if col in INTERI:
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None
    if col in DATE:
        s = str(v)[:10]
        try:
            dt.date.fromisoformat(s)
            return s
        except ValueError:
            return None
    if isinstance(v, float):
        return round(v, 4)
    return v


def righe(df: pd.DataFrame, cols: list[str], extra: dict) -> list[dict]:
    if df is None or df.empty:
        return []
    out = []
    for rec in df.to_dict("records"):
        r = {c: _clean(rec.get(c), c) for c in cols}
        for k in ("flags", "doppioni", "indizi_vendita"):
            if k in r and not isinstance(r[k], list):
                r[k] = []
        r.update(extra)
        out.append(r)
    return out


def costruisci_payload(cfg, storage, risultato: dict, zone, run_id: str) -> dict:
    terr = cfg["territorio"]["nome"]
    df, med, fraz = risultato["df"], risultato["med"], risultato["fraz"]
    ann = righe(df, COL_ANNUNCI + COL_ASTE, {"territorio": terr, "run_id": run_id})
    for a in ann:
        a["tipo_vendita"] = a.get("tipo_vendita") or "compravendita"
    aste = risultato.get("aste")
    if aste is not None and not aste.empty:
        # le aste vanno nella stessa tabella ma non sono mai "occasioni" del mercato libero
        ann += [{**a, "occasione": False} for a in righe(aste, COL_ANNUNCI + COL_ASTE, {"territorio": terr, "run_id": run_id})]
    uids = {a["uid"] for a in ann}
    prezzi = [{"uid": r["uid"], "data": r["data"], "prezzo": r["prezzo"]}
              for r in storage.conn.execute("SELECT uid, data, prezzo FROM prezzi").fetchall()
              if r["uid"] in uids]
    from shapely.geometry import mapping
    zone_rows = [{"territorio": terr, "nome": z.nome, "geojson": mapping(z.geom), "ordine": i,
                  "props": {k: v for k, v in z.props.items() if isinstance(v, (str, int, float))}}
                 for i, z in enumerate(zone.zone)]
    return {
        "territorio": terr,
        "run_id": run_id,
        "generato": dt.datetime.now().isoformat(timespec="seconds"),
        "soglia_occasione_pct": cfg.get("analisi", {}).get("soglia_occasione_pct", -15),
        "fasce": [f[2] for f in cfg.get("analisi", {}).get("fasce_mq", [])],
        "zone": zone_rows,
        "annunci": ann,
        "prezzi": prezzi,
        "mediane": righe(med, COL_MEDIANE, {"territorio": terr, "run_id": run_id}),
        "frazionabili": righe(fraz, COL_FRAZ, {"territorio": terr, "run_id": run_id}),
    }


def esporta_json(path, payload: dict) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path)


class Supabase:
    def __init__(self, url: str, key: str, timeout: int = 60):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"apikey": key})
        # le chiavi "legacy" sono JWT (eyJ...) e vanno anche in Authorization;
        # le nuove chiavi segrete (sb_secret_...) vanno SOLO in apikey
        if key.startswith("eyJ"):
            self.s.headers["Authorization"] = f"Bearer {key}"
        self.timeout = timeout

    def upsert(self, table: str, rows: list[dict], on_conflict: str, batch: int = 500):
        for i in range(0, len(rows), batch):
            r = self.s.post(f"{self.url}/rest/v1/{table}", params={"on_conflict": on_conflict},
                            json=rows[i:i + batch], timeout=self.timeout,
                            headers={"Prefer": "resolution=merge-duplicates,return=minimal",
                                     "Content-Type": "application/json"})
            if r.status_code >= 300:
                raise RuntimeError(f"Supabase upsert {table}: HTTP {r.status_code} {r.text[:300]}")

    def delete(self, table: str, filters: dict):
        r = self.s.delete(f"{self.url}/rest/v1/{table}", params=filters, timeout=self.timeout)
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase delete {table}: HTTP {r.status_code} {r.text[:300]}")

    def insert(self, table: str, row: dict):
        r = self.s.post(f"{self.url}/rest/v1/{table}", json=row, timeout=self.timeout,
                        headers={"Prefer": "return=minimal"})
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase insert {table}: HTTP {r.status_code} {r.text[:300]}")

    def upload(self, bucket: str, path: str, file: Path, content_type: str):
        with open(file, "rb") as f:
            r = self.s.post(f"{self.url}/storage/v1/object/{bucket}/{path}", data=f, timeout=180,
                            headers={"Content-Type": content_type, "x-upsert": "true"})
        if r.status_code >= 300:
            raise RuntimeError(f"Supabase upload {path}: HTTP {r.status_code} {r.text[:300]}")


def credenziali(cfg) -> tuple[str | None, str | None]:
    s = cfg.get("supabase", {}) or {}
    url = os.environ.get("SCOUT_SUPABASE_URL") or s.get("url")
    key = os.environ.get("SCOUT_SUPABASE_SERVICE_KEY") or s.get("service_key")
    return url, key


def pubblica(cfg, storage, risultato: dict, zone) -> bool:
    s = cfg.get("supabase", {}) or {}
    url, key = credenziali(cfg)
    if not (s.get("attivo") and url and key):
        log.info("Supabase non configurato: pubblicazione saltata")
        return False
    run_id = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    p = costruisci_payload(cfg, storage, risultato, zone, run_id)
    terr = p["territorio"]
    sb = Supabase(url, key)
    sb.upsert("zone", p["zone"], "territorio,nome")
    sb.delete("zone", {"territorio": f"eq.{terr}", "nome": "not.in.(" + ",".join(
        '"' + z["nome"].replace('"', '""') + '"' for z in p["zone"]) + ")"} if p["zone"] else
        {"territorio": f"eq.{terr}"})
    try:
        sb.upsert("annunci", p["annunci"], "uid")
    except RuntimeError as e:
        if not any(c in str(e) for c in COL_ASTE):
            raise
        log.warning("Il database del sito non ha ancora le colonne delle aste: esegui una volta "
                    "supabase/migrazione_003_aste.sql nel SQL Editor di Supabase. Per ora pubblico senza le aste.")
        p["annunci"] = [{k: v for k, v in a.items() if k not in COL_ASTE} for a in p["annunci"]
                        if (a.get("tipo_vendita") or "compravendita") == "compravendita"]
        sb.upsert("annunci", p["annunci"], "uid")
    sb.delete("annunci", {"territorio": f"eq.{terr}", "run_id": f"neq.{run_id}"})
    sb.upsert("prezzi", p["prezzi"], "uid,data")
    sb.upsert("mediane", p["mediane"], "territorio,microzona,fascia")
    sb.delete("mediane", {"territorio": f"eq.{terr}", "run_id": f"neq.{run_id}"})
    sb.upsert("frazionabili", p["frazionabili"], "uid")
    sb.delete("frazionabili", {"territorio": f"eq.{terr}", "run_id": f"neq.{run_id}"})
    report = None
    if risultato.get("excel") and Path(risultato["excel"]).exists():
        report = f"{terr}/{Path(risultato['excel']).name}"
        sb.upload("report", report, Path(risultato["excel"]),
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    sb.insert("esecuzioni", {"territorio": terr, "run_id": run_id, "annunci": len(p["annunci"]),
                             "occasioni": int(sum(1 for a in p["annunci"] if a.get("occasione"))),
                             "frazionabili": len(p["frazionabili"]), "report_xlsx": report})
    log.info("pubblicati su Supabase: %d annunci, %d mediane, %d frazionabili",
             len(p["annunci"]), len(p["mediane"]), len(p["frazionabili"]))
    return True
