"""Normalizzazione dei campi eterogenei tra i portali."""
from __future__ import annotations

import re


def num(v) -> float | None:
    """'150.000 €' -> 150000 ; '85 m²' -> 85 ; 1.234,5 -> 1234.5"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v)
    m = re.search(r"\d[\d\.\s]*(?:,\d+)?", s)
    if not m:
        return None
    t = m.group(0).replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def piano(raw) -> str | None:
    """Restituisce 'S' (seminterrato), 'T' (terra), 'R' (rialzato), '1'..'n', 'A' (attico)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in ("nd", "n.d.", "-"):
        return None
    if "attico" in s or "mansard" in s or s == "a":
        return "A"
    if "semi" in s or "interrat" in s or s in ("s", "s1", "-1"):
        return "S"
    if "rialz" in s or s == "r":
        return "R"
    if "terra" in s or s in ("t", "pt", "0") or s.startswith("t "):
        return "T"
    if "ultimo" in s:
        m = re.search(r"\d+", s)
        return m.group(0) if m else "A"
    m = re.search(r"\d+", s)
    return m.group(0) if m else None


def piano_num(p: str | None) -> int | None:
    if p is None:
        return None
    if p in ("T", "R"):
        return 0
    if p == "S":
        return -1
    if p == "A":
        return 99
    try:
        return int(p)
    except ValueError:
        return None


def stato(raw) -> str | None:
    if not raw:
        return None
    s = str(raw).lower()
    if "ristrutturar" in s or "da rimodern" in s:
        return "da_ristrutturare"
    if "nuov" in s or "costruzione" in s:
        return "nuovo"
    if "ottimo" in s or "ristrutturato" in s:
        return "ottimo"
    if "buono" in s or "abitabile" in s:
        return "buono"
    return None


def si_no(raw) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("si", "sì", "yes", "true", "1", "presente"):
        return True
    if s in ("no", "false", "0", "assente"):
        return False
    return None
