"""Analisi: mediana €/mq per microzona e fascia, scostamento, correzioni, OMI."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re

import numpy as np
import pandas as pd

from .cleaning import PRIORITA, _dist_m, _stessa_via, sono_doppioni, unisci_doppioni, valida
from .models import Listing
from .normalize import piano_num
from .storage import CAMPI, Storage
from .tipo_vendita import diritto, occupazione

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


def prepara(storage: Storage, cfg: dict, aste: list | None = None) -> pd.DataFrame:
    """Annunci validi e deduplicati (attivi + rimossi di recente) con metadati storici.

    Se ``aste`` è una lista, ci finiscono gli annunci attivi riconosciuti come aste
    (esclusi dalla valutazione del territorio)."""
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
        storage.aggiorna_campi(l.uid, scartato=int(not ok), motivo_scarto=motivo, flags=l.flags,
                               tipo_vendita=l.tipo_vendita, indizi_vendita=l.indizi_vendita, mq=l.mq)
        if ok:
            tenuti.append(l)
        else:
            scarti[l.uid] = motivo
            if aste is not None and motivo and motivo.startswith(("asta", "possibile asta")) and r["attivo"] == 1:
                aste.append((l, r))
    storage.commit()
    n_aste = sum(1 for m in scarti.values() if m and m.startswith(("asta", "possibile asta")))
    log.info("annunci validi %d, scartati %d (di cui aste o possibili aste: %d)", len(tenuti), len(scarti), n_aste)

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


# ---------------------------------------------------------------------- Aste
_EURO = r"(?:€|euro|eur)?\s*([\d.]{4,}(?:,\d{1,2})?)\s*(?:€|euro)?"
_RX_BASE = re.compile(r"prezzo\s+(?:base|d['’]asta)[^\d€]{0,25}" + _EURO, re.I)
_RX_MIN = re.compile(r"offerta\s+minima[^\d€]{0,25}" + _EURO, re.I)
_RX_DATA = re.compile(r"(?:data\s+(?:dell['’]\s*)?(?:asta|vendita)|asta\s+(?:il|del)|vendita\s+(?:il|del))[^\d]{0,15}(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", re.I)


def dati_asta(testo: str) -> dict:
    """Prezzo base, offerta minima e data dell'asta, se scritti nell'annuncio."""
    from .normalize import num
    out = {"prezzo_base": None, "offerta_minima": None, "data_asta": None}
    m = _RX_BASE.search(testo or "")
    if m:
        out["prezzo_base"] = num(m.group(1).rstrip("."))
    m = _RX_MIN.search(testo or "")
    if m:
        out["offerta_minima"] = num(m.group(1).rstrip("."))
    m = _RX_DATA.search(testo or "")
    if m:
        g, me, a = (int(x) for x in m.groups())
        a = a + 2000 if a < 100 else a
        try:
            out["data_asta"] = dt.date(a, me, g).isoformat()
        except ValueError:
            pass
    return out


def analizza_aste(aste: list, df: pd.DataFrame, med: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Confronta ogni asta con il mercato libero della sua microzona e fascia (le mediane
    calcolate SENZA le aste). Lo sconto è sul prezzo dell'annuncio e, se c'è, sull'offerta minima."""
    if not aste:
        return pd.DataFrame()
    a = cfg.get("analisi", {})
    fasce = a.get("fasce_mq", [[30, 50, "30/50"], [50, 70, "50/70"], [70, 100, "70/100"], [100, 10000, "100+"]])
    corr = a.get("correzioni", {})
    min_n = int(a.get("min_campione", 3))
    usa_norm = corr.get("attive", False)
    righe = []
    for l, r in _unisci_aste(aste, cfg):
        d = {**l.to_dict(), "flags": l.flags, "indizi_vendita": l.indizi_vendita, "doppioni": l.doppioni,
             "first_seen": r.get("first_seen"), "last_seen": r.get("last_seen"), "attivo": 1}
        d["fascia"] = fascia(l.mq, fasce) if l.mq else "mq mancanti"
        d["coeff"] = coefficiente(d, corr)
        testo = f"{l.titolo or ''} {l.descrizione or ''}"
        d.update(dati_asta(testo))
        d["diritto"] = diritto(testo) or "da verificare"
        d["occupazione"] = occupazione(testo)
        rif, base = np.nan, "senza zona"
        if l.microzona and not med.empty:
            m = med[(med["microzona"] == l.microzona) & (med["fascia"] == d["fascia"])]
            mz = med[med["microzona"] == l.microzona]
            if len(m) and m.iloc[0]["n"] >= min_n:
                rif = m.iloc[0]["mediana_mq_norm" if usa_norm else "mediana_mq"]
                base = f"fascia (n={int(m.iloc[0]['n'])})"
            elif len(mz) and (mz.iloc[0]["n_zona"] or 0) >= min_n:
                rif = mz.iloc[0]["mediana_zona_norm" if usa_norm else "mediana_zona"]
                base = f"zona intera (n={int(mz.iloc[0]['n_zona'])})"
            else:
                base = "campione scarso"
        d["riferimento_mq"], d["base_confronto"] = rif, base
        if not l.mq:
            rif, base = np.nan, "mq mancanti"
            d["riferimento_mq"], d["base_confronto"] = rif, base
        valore = (d["prezzo_mq"] / d["coeff"] if usa_norm else d["prezzo_mq"]) if l.mq else np.nan
        d["scostamento_pct"] = (valore / rif - 1) * 100 if rif == rif else np.nan
        if d["offerta_minima"] and l.mq and rif == rif:
            d["scostamento_minima_pct"] = (d["offerta_minima"] / l.mq / d["coeff"] / rif - 1) * 100 if usa_norm \
                else (d["offerta_minima"] / l.mq / rif - 1) * 100
        else:
            d["scostamento_minima_pct"] = np.nan
        d["valore_mercato"] = rif * l.mq * d["coeff"] if usa_norm and rif == rif else (rif * l.mq if rif == rif else np.nan)
        righe.append(d)
    out = pd.DataFrame(righe)
    return out.sort_values(["tipo_vendita", "scostamento_pct"], na_position="last").reset_index(drop=True)


def _unisci_aste(aste: list, cfg: dict) -> list:
    """Lo stesso lotto può comparire sul PVP e su uno o più portali: si tiene una riga sola,
    preferendo il PVP (fonte ufficiale) e completando i dati mancanti dagli altri.
    La tolleranza sul prezzo è larga perché un portale mostra il prezzo base e un altro l'offerta minima."""
    if len(aste) < 2:
        return [(l, r) for l, r in aste]
    c = {**cfg, "pulizia": {**cfg.get("pulizia", {}),
                            "doppioni": {**cfg.get("pulizia", {}).get("doppioni", {}), "tolleranza_prezzo_pct": 30}}}
    n = len(aste)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    basi = [dati_asta(f"{l.titolo or ''} {l.descrizione or ''}")["prezzo_base"] for l, _ in aste]

    def stesso_lotto(i, j):
        a, b = aste[i][0], aste[j][0]
        if a.source == b.source and a.source == "pvp":
            return False                     # sul PVP ogni lotto è già unico
        if sono_doppioni(a, b, c):
            return True
        # stesso prezzo base e stesso posto (i lotti del PVP spesso non hanno i mq)
        return bool(basi[i]) and basi[i] == basi[j] and (_stessa_via(a, b) or _dist_m(a, b) <= 150 or
                                                       (a.microzona is not None and a.microzona == b.microzona))

    for i in range(n):
        for j in range(i + 1, n):
            if stesso_lotto(i, j):
                parent[find(i)] = find(j)
    gruppi: dict[int, list] = {}
    for i in range(n):
        gruppi.setdefault(find(i), []).append(aste[i])
    out = []
    for g in gruppi.values():
        g.sort(key=lambda x: (PRIORITA.get(x[0].source, 5), -len(x[0].descrizione or "")))
        rep, rr = g[0]
        rep.doppioni = [f"{x.source}: {x.url} ({x.agenzia or '?'}, {x.prezzo:,.0f}€)" for x, _ in g[1:]]
        for x, _ in g[1:]:
            for k in ("mq", "piano", "ascensore", "bagni", "stato", "lat", "lon", "indirizzo", "microzona"):
                if getattr(rep, k) in (None, "") and getattr(x, k) not in (None, ""):
                    setattr(rep, k, getattr(x, k))
            rep.descrizione = f"{rep.descrizione or ''} {x.descrizione or ''}".strip()
        out.append((rep, rr))
    return out


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
