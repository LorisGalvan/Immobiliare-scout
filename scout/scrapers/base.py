"""Client HTTP "educato": ritmo lento, retry con backoff, rilevamento blocchi, robots.txt.

Il bot si identifica con lo user-agent configurato e NON tenta di aggirare
protezioni anti-bot: se un sito blocca, lo scraping di quel sito si interrompe
e si può usare l'importazione di pagine salvate dal browser (`scout importa-html`).
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class BloccatoError(Exception):
    """Il sito ha risposto con un blocco (403/429/captcha)."""


BLOCK_MARKERS = ("captcha-delivery", "datadome", "px-captcha", "cf-chl", "Access Denied",
                 "geo.captcha", "Sei un robot", "unusual traffic")


class PoliteClient:
    def __init__(self, cfg: dict):
        s = cfg.get("scraping", {})
        self.ua = s.get("user_agent", "scout-immobili/1.0")
        self.pmin = float(s.get("pausa_min_s", 6))
        self.pmax = float(s.get("pausa_max_s", 14))
        self.tentativi = int(s.get("max_tentativi", 4))
        self.backoff = float(s.get("backoff_base_s", 20))
        self.timeout = float(s.get("timeout_s", 30))
        self.stop_blocchi = int(s.get("stop_dopo_blocchi", 3))
        self.robots = bool(s.get("rispetta_robots_txt", True))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": "it-IT,it;q=0.9",
        })
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.blocchi: dict[str, int] = {}
        self.richieste = 0

    # ------------------------------------------------------------------
    def _robots_ok(self, url: str) -> bool:
        if not self.robots:
            return True
        host = urlparse(url).scheme + "://" + urlparse(url).netloc
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(host + "/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self._robots[host] = rp
            except requests.RequestException:
                self._robots[host] = None
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(self.ua, url)

    def _wait(self, host: str):
        last = self._last.get(host)
        if last is not None:
            target = random.uniform(self.pmin, self.pmax)
            wait = target - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.time()

    @staticmethod
    def is_block(resp: requests.Response) -> bool:
        if resp.status_code in (403, 429, 451):
            return True
        if resp.status_code == 200 and len(resp.text) < 20000:
            return any(m in resp.text for m in BLOCK_MARKERS)
        return False

    def get(self, url: str, **kw) -> requests.Response:
        host = urlparse(url).netloc
        if self.blocchi.get(host, 0) >= self.stop_blocchi:
            raise BloccatoError(f"{host}: troppi blocchi, sito sospeso per questa esecuzione")
        if not self._robots_ok(url):
            raise PermissionError(f"robots.txt non consente {url}")
        err = None
        for i in range(self.tentativi):
            self._wait(host)
            try:
                self.richieste += 1
                r = self.session.get(url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                err = e
                log.warning("errore rete %s (tentativo %d): %s", url, i + 1, e)
                time.sleep(self.backoff * (2 ** i) * random.uniform(0.8, 1.2))
                continue
            if self.is_block(r):
                self.blocchi[host] = self.blocchi.get(host, 0) + 1
                log.warning("BLOCCO da %s (HTTP %s), n.%d", host, r.status_code, self.blocchi[host])
                if self.blocchi[host] >= self.stop_blocchi:
                    raise BloccatoError(f"{host} blocca le richieste (HTTP {r.status_code})")
                time.sleep(self.backoff * (2 ** (i + 1)) * random.uniform(0.8, 1.2))
                continue
            if r.status_code >= 500:
                err = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(self.backoff * (2 ** i))
                continue
            self.blocchi[host] = 0
            return r
        raise RuntimeError(f"richiesta fallita dopo {self.tentativi} tentativi: {url} ({err})")


# ---------------------------------------------------------------------- helpers HTML
def fasce_prezzo(cfg: dict) -> list[tuple[float | None, float | None]]:
    """Fasce di prezzo in cui spezzare una ricerca: i portali mostrano solo un numero massimo
    di pagine, quindi su un comune grande una ricerca unica perde gli annunci oltre il limite.
    Con ``scraping.fasce_prezzo`` (lista di soglie) ogni fascia è una ricerca a sé."""
    s = cfg.get("scraping", {}) or {}
    soglie = s.get("fasce_prezzo") or []
    f = s.get("filtri", {}) or {}
    if not soglie:
        return [(f.get("prezzo_min"), f.get("prezzo_max"))]
    soglie = sorted(float(x) for x in soglie)
    lo, hi = f.get("prezzo_min"), f.get("prezzo_max")
    punti = [lo] + [x for x in soglie if (lo is None or x > lo) and (hi is None or x < hi)] + [hi]
    return [(punti[i], punti[i + 1]) for i in range(len(punti) - 1)]


def next_data(html: str) -> dict | None:
    """Estrae il JSON __NEXT_DATA__ delle pagine Next.js (Immobiliare, Subito)."""
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk(obj):
    """Itera ricorsivamente su tutti i dict contenuti in obj."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
