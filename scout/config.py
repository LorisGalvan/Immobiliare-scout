"""Caricamento della configurazione YAML."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg = copy.deepcopy(cfg)
    # impostazioni personali (token, password, percorsi) in un file NON versionato:
    # config.local.yaml accanto al file principale (o <nome>.local.yaml)
    for local in (path.with_name(path.stem + ".local.yaml"), path.with_name("config.local.yaml")):
        if local.exists():
            with open(local, encoding="utf-8") as f:
                _merge(cfg, yaml.safe_load(f) or {})
            break
    cfg["_root"] = str(path.resolve().parent)
    return cfg


def _merge(base: dict, over: dict) -> None:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def resolve(cfg: dict, rel: str) -> Path:
    """Percorso relativo alla cartella del file di configurazione."""
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg.get("_root", ROOT)) / p


def get(cfg: dict, dotted: str, default=None):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
