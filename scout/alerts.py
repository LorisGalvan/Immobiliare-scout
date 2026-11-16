"""Alert via Telegram ed email per nuove occasioni e frazionabili."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

import pandas as pd
import requests

log = logging.getLogger(__name__)


def _riga_occasione(r) -> str:
    return (f"🏠 {r.get('microzona')} ({r.get('fascia')})\n"
            f"{r.get('indirizzo') or r.get('titolo') or ''}\n"
            f"{r['mq']:.0f} mq - {r['prezzo']:,.0f} € = {r['prezzo_mq']:,.0f} €/mq\n"
            f"Scostamento {r['scostamento_pct']:+.1f}% vs mediana {r['riferimento_mq']:,.0f} €/mq\n"
            f"{'Privato' if r.get('privato') else (r.get('agenzia') or '')} - {r.get('source')}\n"
            f"{r.get('url')}").replace(",", ".")


def _riga_fraz(r) -> str:
    return (f"✂️ FRAZIONABILE {r.get('microzona')}\n{r.get('indirizzo') or r.get('titolo') or ''}\n"
            f"{r['mq']:.0f} mq - {r['prezzo']:,.0f} € -> {r['n_unita']} unità da {r['mq_unita']:.0f} mq\n"
            f"Margine stimato {r['margine']:,.0f} € ({r['margine_pct']:.0f}%)\n"
            f"Indizi: {r.get('indizi') or '-'}\n{r.get('url')}").replace(",", ".")


def invia_telegram(cfg: dict, testi: list[str]) -> int:
    t = cfg.get("alert", {}).get("telegram", {})
    token = os.environ.get("SCOUT_TELEGRAM_TOKEN") or t.get("token")
    chat = os.environ.get("SCOUT_TELEGRAM_CHAT_ID") or t.get("chat_id")
    if not (t.get("attivo") and token and chat):
        return 0
    n = 0
    for testo in testi:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              data={"chat_id": chat, "text": testo[:4000], "disable_web_page_preview": "true"},
                              timeout=20)
            r.raise_for_status()
            n += 1
        except requests.RequestException as e:
            log.error("Telegram: %s", e)
    return n


def invia_email(cfg: dict, oggetto: str, testi: list[str]) -> bool:
    e = cfg.get("alert", {}).get("email", {})
    pwd = os.environ.get("SCOUT_SMTP_PASSWORD") or e.get("password")
    if not (e.get("attivo") and e.get("destinatari") and e.get("utente") and pwd):
        return False
    msg = MIMEText("\n\n".join(testi), "plain", "utf-8")
    msg["Subject"] = oggetto
    msg["From"] = e["utente"]
    msg["To"] = ", ".join(e["destinatari"])
    try:
        with smtplib.SMTP(e.get("smtp_host", "smtp.gmail.com"), int(e.get("smtp_port", 587)), timeout=30) as s:
            s.starttls()
            s.login(e["utente"], pwd)
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as ex:
        log.error("email: %s", ex)
        return False


def notifica(cfg: dict, storage, df: pd.DataFrame, fraz: pd.DataFrame | None, dry_run: bool = False) -> list[str]:
    """Invia solo le occasioni non ancora segnalate. Restituisce i testi."""
    testi, da_segnare = [], []
    if not df.empty:
        for _, r in df[df["occasione"]].sort_values("scostamento_pct").iterrows():
            if not storage.gia_avvisato(r["uid"], "occasione"):
                testi.append(_riga_occasione(r))
                da_segnare.append((r["uid"], "occasione"))
    if cfg.get("alert", {}).get("includi_frazionabili", True) and fraz is not None and not fraz.empty:
        for _, r in fraz.iterrows():
            if not storage.gia_avvisato(r["uid"], "frazionabile"):
                testi.append(_riga_fraz(r))
                da_segnare.append((r["uid"], "frazionabile"))
    if not testi or dry_run:
        return testi
    inviati_tg = invia_telegram(cfg, testi)
    inviata_mail = invia_email(cfg, f"Scout immobili: {len(testi)} nuove segnalazioni", testi)
    if inviati_tg or inviata_mail:
        for uid, tipo in da_segnare:
            storage.segna_avvisato(uid, tipo)
    else:
        log.info("nessun canale di alert attivo: %d segnalazioni non inviate", len(testi))
    return testi
