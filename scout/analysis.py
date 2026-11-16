"""Analisi: mediana €/mq per microzona e fascia, scostamento, correzioni, OMI."""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from .cleaning import unisci_doppioni, valida
from .models import Listing
from .normalize import piano_num
from .storage import CAMPI, Storage

log = logging.getLogger(__name__)


def fascia(mq: float, fasce: list) -> str:
    for lo, hi, lab in fasce:
        if lo <= mq < hi:
            return lab
    return f"<{fasce[0][0]}" if mq < fasce[0][0] else "altro"


def coefficiente(row, corr: dict) -> float:
    if not corr.get("attive", False):
        return 1.0
    c = 1.0
    p = row.get("piano")
    pn = piano_num(p)
    if p in ("T", "S"):
        c *= corr.get("piano_terra", 1.0)
    elif p == "A":
        c *= corr.get("attico", 1.0)
    elif pn is not None and pn >= 3 and row.get("ascensore") is False:
        c *= corr.get("piano_alto_senza_ascensore", 1.0)
    st = row.get("stato")
    if st:
        c *= (corr.get("stato") or {}).get(st, 1.0)
    return c


def _row_to_listing(r) -> Listing:
    l = Listing(**{c: (None if (isinstance(r[c], float) and np.isnan(r[c])) else r[c]) for c in CAMPI})
    l.flags = json.loads(r["flags"] or "[]") if isinstance(r["flags"], str) else []
    l.ascensore = r["ascensore"] if isinstance(r["ascensore"], bool) else None
    l.privato = r["privato"] if isinstance(r["privato"], bool) else None
    l.coord_precise = bool(r["coord_precise"]) if r["coord_precise"] is not None else False
    return l


def prepara(storage: Storage, cfg: dict) -> pd.DataFrame:
    """Annunci validi e deduplicati (attivi + rimossi di recente) con metadati storici."""
    df = storage.dataframe()
    if df.empty:
        return df
    giorni = int(cfg.get("analisi", {}).get("includi_storico_giorni", 180))
    limite = (dt.date.today() - dt.timedelta(days=giorni)).isoformat()
    df = df[(df["attivo"] == 1) | (df["removed_at"].fillna("") >= limite)].copy()

    tenuti, scarti = [], {}
    for _, r in df.iterrows():
        l = _row_to_listing(r)
        ok, motivo = valida(l, cfg)
        storage.aggiorna_campi(l.uid, scartato=int(not ok), motivo_scarto=motivo, flags=l.flags)
        if ok:
            tenuti.append(l)
        else:
            scarti[l.uid] = motivo
    storage.commit()
    log.info("annunci validi %d, scartati %d", len(tenuti), len(scarti))

    # i doppioni si uniscono separatamente tra attivi e rimossi
    attivi_uid = set(df.loc[df["attivo"] == 1, "uid"])
    reps = unisci_doppioni([l for l in tenuti if l.uid in attivi_uid], cfg) + \
        unisci_doppioni([l for l in tenuti if l.uid not in attivi_uid], cfg)
    rep_df = pd.DataFrame([{**l.to_dict(), "flags": l.flags, "doppioni": l.doppioni} for l in reps])
    meta = df.set_index("uid")[["first_seen", "last_seen", "attivo", "removed_at", "prezzo_iniziale",
                                "n_prezzi", "pmin", "pmax"]]
    rep_df = rep_df.join(meta, on="uid")
    return rep_df


def analizza(df: pd.DataFrame, cfg: dict, omi: "OMI | None" = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Restituisce (annunci con scostamenti, tabella mediane per zona/fascia)."""
    a = cfg.get("analisi", {})
    fasce = a.get("fasce_mq", [[30, 50, "30/50"], [50, 70, "50/70"], [70, 100, "70/100"], [100, 10000, "100+"]])
    corr = a.get("correzioni", {})
    min_n = int(a.get("min_campione", 3))
    if df.empty:
        return df, pd.DataFrame()
    df = df.copy()
    df["fascia"] = df["mq"].apply(lambda m: fascia(m, fasce))
    df["prezzo_mq"] = df["prezzo"] / df["mq"]
    df["coeff"] = df.apply(lambda r: coefficiente(r, corr), axis=1)
    df["prezzo_mq_norm"] = df["prezzo_mq"] / df["coeff"]
    today = dt.date.today()

    def giorni(r):
        try:
            start = dt.date.fromisoformat(str(r["first_seen"])[:10])
            rem = r.get("removed_at")
            end = dt.date.fromisoformat(str(rem)[:10]) if isinstance(rem, str) and rem else today
            return (end - start).days
        except (ValueError, TypeError):
            return None
    df["giorni_online"] = df.apply(giorni, axis=1)
    df["ribasso_pct"] = np.where(df["prezzo_iniziale"].fillna(0) > df["prezzo"],
                                 (df["prezzo"] / df["prezzo_iniziale"] - 1) * 100, 0.0)

    zonate = df[df["microzona"].notna()]
    g = zonate.groupby(["microzona", "fascia"])
    med = g.agg(n=("uid", "count"), mediana_mq=("prezzo_mq", "median"),
                mediana_mq_norm=("prezzo_mq_norm", "median"), media_mq=("prezzo_mq", "mean")).reset_index()
    zona_tot = zonate.groupby("microzona").agg(n_zona=("uid", "count"), mediana_zona=("prezzo_mq", "median"),
                                               mediana_zona_norm=("prezzo_mq_norm", "median")).reset_index()
    med = med.merge(zona_tot, on="microzona", how="left")

    df = df.merge(med, on=["microzona", "fascia"], how="left").merge(
        zona_tot.rename(columns=lambda c: c if c == "microzona" else c + "_z"), on="microzona", how="left")

    usa_norm = corr.get("attive", False)
    fallback = a.get("fallback_mediana_zona", True)
    # fattore fascia: quanto il €/mq della fascia si discosta dal totale, misurato su tutto il
    # territorio (le unità piccole costano di più al mq). Serve a riscalare la mediana di zona
    # quando la fascia ha pochi annunci, altrimenti i grandi sembrerebbero tutti sottoprezzo.
    col = "prezzo_mq_norm" if corr.get("attive", False) else "prezzo_mq"
    tot = zonate[col].median() if len(zonate) else np.nan
    fattore_fascia = (zonate.groupby("fascia")[col].median() / tot).to_dict() if len(zonate) else {}

    def riferimento(r):
        if pd.isna(r.get("microzona")):
            return np.nan, "senza zona"
        n = r.get("n") or 0
        if n >= min_n:
            return (r["mediana_mq_norm"] if usa_norm else r["mediana_mq"]), f"fascia (n={int(n)})"
        if fallback and (r.get("n_zona_z") or 0) >= min_n:
            f = fattore_fascia.get(r.get("fascia"), 1.0)
            f = 1.0 if pd.isna(f) else f
            base = r["mediana_zona_norm_z"] if usa_norm else r["mediana_zona_z"]
            return base * f, f"zona intera x fattore fascia {f:.2f} (fascia n={int(n)})"
        return np.nan, f"campione scarso (n={int(n)})"

    ref = df.apply(riferimento, axis=1, result_type="expand")
    df["riferimento_mq"], df["base_confronto"] = ref[0], ref[1]
    valore = df["prezzo_mq_norm"] if usa_norm else df["prezzo_mq"]
    df["scostamento_pct"] = (valore / df["riferimento_mq"] - 1) * 100
    df["scostamento_grezzo_pct"] = (df["prezzo_mq"] / df["mediana_mq"] - 1) * 100

    if omi is not None:
        df = omi.arricchisci(df)
    soglia = float(a.get("soglia_occasione_pct", -15))
    df["occasione"] = (df["scostamento_pct"] <= soglia) & (df["attivo"] == 1)
    df = df.drop(columns=[c for c in df.columns if c.endswith("_z")])
    return df, med


# ---------------------------------------------------------------------- OMI
class OMI:
    """Quotazioni OMI (Agenzia delle Entrate) - file CSV 'QI_..._VALORI.csv'.

    Il file si scarica gratuitamente (previa registrazione) da
    https://www.agenziaentrate.gov.it -> Banche dati -> Quotazioni immobiliari.
    """

    def __init__(self, cfg: dict, zone_set=None):
        from .config import resolve
        o = cfg.get("analisi", {}).get("omi", {})
        self.mappa = o.get("mappa_microzone") or {}
        self.tipologia = o.get("tipologia", "Abitazioni civili").lower()
        path = resolve(cfg, o.get("file_valori", "data/omi/QI_VALORI.csv"))
        raw = pd.read_csv(path, sep=";", skiprows=1, dtype=str, encoding="latin-1")
        raw.columns = [c.strip() for c in raw.columns]
        comune = cfg["territorio"]["comune"].upper()
        raw = raw[raw["Comune_descrizione"].str.upper().str.strip() == comune]
        raw = raw[raw["Descr_Tipologia"].str.lower().str.strip() == self.tipologia]
        for c in ("Compr_min", "Compr_max"):
            raw[c] = raw[c].str.replace(",", ".").astype(float)
        normale = raw[raw["Stato"].str.upper().str.strip() == "NORMALE"]
        self.valori = (normale if not normale.empty else raw).groupby("Zona")[["Compr_min", "Compr_max"]].mean()
        self.zone_poly = None
        zf = o.get("file_zone")
        if zf and resolve(cfg, zf).exists():
            from .geo.microzones import MicrozoneSet
            self.zone_poly = MicrozoneSet.load(resolve(cfg, zf))
        self.zone_set = zone_set

    def zona_omi(self, microzona: str) -> str | None:
        if microzona in self.mappa:
            return self.mappa[microzona]
        if self.zone_poly is not None and self.zone_set is not None:
            z = self.zone_set.get(microzona)
            if z is not None:
                c = z.geom.representative_point()
                return self.zone_poly.assign(c.y, c.x)
        return None

    def arricchisci(self, df: pd.DataFrame) -> pd.DataFrame:
        zone = {m: self.zona_omi(m) for m in df["microzona"].dropna().unique()}
        df["zona_omi"] = df["microzona"].map(zone)
        df["omi_min"] = df["zona_omi"].map(self.valori["Compr_min"])
        df["omi_max"] = df["zona_omi"].map(self.valori["Compr_max"])
        mid = (df["omi_min"] + df["omi_max"]) / 2
        df["scostamento_omi_pct"] = (df["prezzo_mq"] / mid - 1) * 100
        return df
