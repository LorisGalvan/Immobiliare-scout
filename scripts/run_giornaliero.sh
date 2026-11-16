#!/usr/bin/env bash
# Esecuzione giornaliera: aggiungi a crontab (es. 30 7 * * *)
cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate
python -m scout run
# altri territori:
# python -m scout -c config_sgl.yaml run
