"""Modulo FRAZIONAMENTO: stima del margine dividendo un immobile grande in unità piccole."""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

# (etichetta, regex, peso nel punteggio)
INDIZI = [
    ("doppio ingresso", r"doppio ingresso|due ingressi|2 ingressi|ingresso indipendente|ingressi separati|doppio accesso", 3),
    ("già frazionabile", r"frazionabil|divisibil|facilmente dividibile|possibilit[aà] di (ricavare|dividere|frazionare)|ricavare due", 3),
    ("più utenze", r"doppi[ae]? (utenze|contatori|impianti)|due contatori|utenze separate|predispost[oa] per (due|2)", 2),
    ("più bagni", r"(due|2|tre|3|doppi) (bagni|servizi)|doppi servizi|secondo bagno", 2),
    ("piano terra / indipendente", r"piano terra|indipendente|terra[- ]cielo|cielo[- ]terra|rialzato", 1),
    ("forma regolare", r"forma regolare|pianta regolare|rettangolare|squadrat|open space|ben distribuit", 1),
    ("due cucine/angoli cottura", r"due cucine|doppia cucina|2 cucine|angolo cottura", 1),
]


def indizi_testo(testo: str, bagni) -> tuple[list[str], int]:
    t = (testo or "").lower()
    trovati, score = [], 0
    for lab, rx, peso in INDIZI:
        if re.search(rx, t):
            trovati.append(lab)
            score += peso
    if bagni and bagni >= 2 and "più bagni" not in trovati:
        trovati.append(f"{int(bagni)} bagni")
        score += 2
    return trovati, score


def analizza_frazionamento(df: pd.DataFrame, med: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    f = cfg.get("frazionamento", {})
    if not f.get("attivo", True) or df.empty:
        return pd.DataFrame()
    c = f.get("costi", {})
    mq_min = float(f.get("mq_min", 100))
    target = float(f.get("mq_unita_target", 45))
    perdita = float(f.get("perdita_superficie_pct", 8)) / 100
    fascia_rif = f.get("fascia_riferimento", "30/50")
    sconto = float(f.get("sconto_prudenziale_pct", 5)) / 100
    min_n = int(cfg.get("analisi", {}).get("min_campione", 3))

    piccole = med[med["fascia"] == fascia_rif].set_index("microzona")
    cand = df[(df["mq"] >= mq_min) & (df["attivo"] == 1) & df["microzona"].notna()].copy()
    if "indirizzo_agenzia" in cand.columns:     # posizione falsa: la microzona non è quella vera
        cand = cand[~cand["indirizzo_agenzia"].fillna(False).astype(bool)]
    righe = []
    for _, r in cand.iterrows():
        if r["microzona"] not in piccole.index:
            continue
        rif = piccole.loc[r["microzona"]]
        if rif["n"] < min_n:
            continue
        mq_utili = r["mq"] * (1 - perdita)
        n_unita = int(math.floor(mq_utili / target))
        if n_unita < 2:
            continue
        mq_unita = mq_utili / n_unita
        valore_post = mq_utili * rif["mediana_mq"] * (1 - sconto)
        lavori = r["mq"] * c.get("lavori_mq", 650)
        tecniche = lavori * c.get("spese_tecniche_pct", 8) / 100
        impianti = n_unita * c.get("impianti_per_unita", 9000)
        oneri = n_unita * c.get("oneri_per_unita", 3500)
        acquisto = r["prezzo"] * c.get("acquisto_pct", 4) / 100
        vendita = valore_post * c.get("vendita_pct", 3) / 100
        costi = lavori + tecniche + impianti + oneri + acquisto + vendita
        investimento = r["prezzo"] + costi
        margine = valore_post - investimento
        indizi, score = indizi_testo(f"{r.get('titolo', '')} {r.get('descrizione', '')}", r.get("bagni"))
        if r.get("piano") in ("T", "R") and "piano terra / indipendente" not in indizi:
            indizi.append("piano terra/rialzato")
            score += 1
        righe.append({
            **r.to_dict(),
            "n_unita": n_unita, "mq_unita": round(mq_unita, 1),
            "mediana_piccole_mq": rif["mediana_mq"], "n_campione_piccole": int(rif["n"]),
            "valore_post": valore_post, "costi_totali": costi, "costo_lavori": lavori + tecniche,
            "costo_impianti_oneri": impianti + oneri, "costi_transazione": acquisto + vendita,
            "margine": margine, "margine_pct": margine / investimento * 100,
            "indizi": ", ".join(indizi), "punteggio_indizi": score,
        })
    out = pd.DataFrame(righe)
    if out.empty:
        return out
    out = out[out["margine_pct"] >= float(f.get("margine_min_pct", 10))]
    return out.sort_values(["margine_pct", "punteggio_indizi"], ascending=False).reset_index(drop=True)


__all__ = ["analizza_frazionamento", "indizi_testo", "np"]
