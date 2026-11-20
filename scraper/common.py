"""Shared HTTP plumbing: polite, identifiable, robots-aware fetching."""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger("basketwise")

# Identify ourselves honestly. A contact URL lets a retailer reach us instead of just blocking us.
BOT_UA = os.environ.get(
    "BASKETWISE_UA",
    "Mozilla/5.0 (compatible; BasketWiseBot/1.0; +https://github.com/basketwise/basketwise/blob/main/docs/BOT.md)",
)

# Minimum seconds between requests to the same host. PnP's robots.txt asks for 10s.
DEFAULT_DELAY = 3.0
HOST_DELAY = {"www.pnp.co.za": 10.0}
# robots.txt "Visit-time" directives (HHMM UTC). urllib.robotparser ignores these, so we enforce them.
VISIT_WINDOW_UTC = {"www.pnp.co.za": (400, 845)}


def in_visit_window(host: str) -> bool:
    """True if `host` may be crawled now per its robots.txt Visit-time (True when it has none)."""
    w = VISIT_WINDOW_UTC.get(host)
    if not w:
        return True
    hhmm = int(time.strftime("%H%M", time.gmtime()))
    return w[0] <= hhmm <= w[1]


class Fetcher:
    def __init__(self, respect_robots: bool = True):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": BOT_UA, "Accept-Language": "en-ZA,en;q=0.9"})
        self.last: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.respect_robots = respect_robots
        self.requests_made = 0
        self.blocked_hosts: set[str] = set()

    def _robots_ok(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        host = urlparse(url).netloc
        rp = self.robots.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(f"https://{host}/robots.txt", timeout=20)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[host] = rp
        # Check as a generic bot ("*"); we do not borrow another crawler's permissions.
        return rp.can_fetch("*", url)

    def _wait(self, host: str) -> None:
        delay = HOST_DELAY.get(host, DEFAULT_DELAY)
        rp = self.robots.get(host)
        if rp is not None:
            cd = rp.crawl_delay("*")
            if cd:
                delay = max(delay, float(cd))
        elapsed = time.time() - self.last.get(host, 0)
        if elapsed < delay:
            time.sleep(delay - elapsed + random.uniform(0, 0.5))
        self.last[host] = time.time()

    def get(self, url: str, *, accept_json: bool = False, retries: int = 3, check_robots: bool = True) -> requests.Response | None:
        if check_robots and not self._robots_ok(url):
            log.warning("robots.txt disallows %s - skipped", url)
            return None
        host = urlparse(url).netloc
        if host in self.blocked_hosts:
            return None
        window = VISIT_WINDOW_UTC.get(host)
        if window and self.respect_robots:
            hhmm = int(time.strftime("%H%M", time.gmtime()))
            if not (window[0] <= hhmm <= window[1]):
                log.warning("%s only allows visits %04d-%04d UTC (robots.txt) - skipped", host, *window)
                return None
        headers = {"Accept": "application/json"} if accept_json else {}
        for attempt in range(retries):
            self._wait(host)
            try:
                r = self.s.get(url, timeout=45, headers=headers)
                self.requests_made += 1
            except requests.TooManyRedirects:
                log.warning("GET %s redirect loop (bot block page) - not retrying", url)
                self.blocked_hosts.add(host)
                return None
            except requests.RequestException as e:
                log.warning("GET %s failed (%s), attempt %d", url, e, attempt + 1)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r
            if "/400?support_id" in r.url:
                log.warning("GET %s served a WAF block page - not retrying", url)
                self.blocked_hosts.add(host)
                return None
            if r.status_code in (403, 429, 503):
                # Being throttled or blocked: back off hard, never hammer.
                log.warning("GET %s -> %s, backing off", url, r.status_code)
                time.sleep(30 * (attempt + 1))
                continue
            log.warning("GET %s -> %s", url, r.status_code)
            return None
        return None


def extract_json_script(html: str, script_id: str) -> dict | None:
    m = re.search(rf'<script id="{script_id}"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|litre|liter|s|pack|'s)\b", re.I)


def parse_size(name: str) -> tuple[float, str] | None:
    """Return (quantity, base unit) e.g. 'Milk 2L' -> (2000, 'ml'), '6 x 1 L' -> (6000,'ml')."""
    n = name.lower().replace(",", ".")
    multi = re.search(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", n)
    mult = 1.0
    if multi:
        mult = float(multi.group(1))
        qty, unit = float(multi.group(2)), multi.group(3)
    else:
        ms = SIZE_RE.findall(n)
        if not ms:
            return None
        qty, unit = float(ms[-1][0]), ms[-1][1]
    unit = unit.lower()
    if unit in ("kg",):
        return qty * mult * 1000, "g"
    if unit in ("l", "litre", "liter"):
        return qty * mult * 1000, "ml"
    if unit in ("g", "ml"):
        return qty * mult, unit
    return qty * mult, "ea"
