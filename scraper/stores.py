"""Weekly: every Checkers, Shoprite, PnP, SPAR and Woolworths store in South Africa, from OpenStreetMap.

OSM data is (c) OpenStreetMap contributors, ODbL - the app must show that attribution.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import requests

from common import BOT_UA

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("basketwise")
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]

QUERY = """
[out:json][timeout:300];
area["ISO3166-1"="ZA"][admin_level=2]->.za;
(
  nwr["shop"~"^(supermarket|convenience|department_store|wholesale|grocery|greengrocer)$"]["brand"~"checkers|shoprite|pick n pay|spar|woolworths|usave|^ok |boxer|food lover|makro",i](area.za);
  nwr["shop"~"^(supermarket|convenience|department_store|wholesale|grocery|greengrocer)$"]["name"~"^(checkers|shoprite|pick n pay|pnp|spar|superspar|kwikspar|woolworths|usave|ok (foods|grocer|minimark|express|value)|boxer|food lover|makro)",i](area.za);
);
out center tags;
"""

CHAINS = [
    ("checkers", re.compile(r"\bcheckers\b", re.I)),
    ("shoprite", re.compile(r"\bshoprite\b", re.I)),
    ("pnp", re.compile(r"pick\s*n\s*pay|\bpnp\b", re.I)),
    ("woolworths", re.compile(r"woolworths", re.I)),
    ("spar", re.compile(r"spar\b", re.I)),
    # Chains without online prices: shown on the map with a link to their weekly specials.
    ("usave", re.compile(r"\busave\b", re.I)),
    ("ok", re.compile(r"^ok\b|\bok (foods|grocer|minimark|express|value)\b", re.I)),
    ("boxer", re.compile(r"\bboxer\b", re.I)),
    ("foodlovers", re.compile(r"food\s*lover", re.I)),
    ("makro", re.compile(r"\bmakro\b", re.I)),
]
EXCLUDE = re.compile(r"liquor|tops|clothing|pharmacy|\bbuild\b|build ?it|\bpet\b|cash ?& ?carry", re.I)


def classify(tags: dict) -> str | None:
    label = " ".join(filter(None, [tags.get("brand"), tags.get("name")]))
    if not label or EXCLUDE.search(label):
        return None
    for chain, rx in CHAINS:
        if rx.search(label):
            return chain
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = None
    for ep in ENDPOINTS:
        try:
            r = requests.post(ep, data={"data": QUERY}, headers={"User-Agent": "BasketWise/1.0 (+https://github.com/Skarrd001/basketwise)", "Accept": "*/*"}, timeout=400)
            if r.ok:
                data = r.json()
                break
            log.warning("%s -> %s", ep, r.status_code)
        except requests.RequestException as e:
            log.warning("%s failed: %s", ep, e)
    if not data:
        log.error("no Overpass endpoint answered; keeping existing stores.json")
        return 1
    stores, seen = [], set()
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        chain = classify(tags)
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not chain or lat is None:
            continue
        key = (chain, round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        stores.append({"chain": chain, "name": tags.get("name") or tags.get("brand"),
                       "lat": round(lat, 5), "lon": round(lon, 5),
                       "suburb": tags.get("addr:suburb") or tags.get("addr:city") or ""})
    counts = {c: sum(1 for s in stores if s["chain"] == c) for c, _ in CHAINS}
    log.info("stores: %s", counts)
    if len(stores) < 500:  # sanity: SA has thousands; a tiny result means a broken query
        log.error("only %d stores - refusing to overwrite", len(stores))
        return 1
    (ROOT / "data" / "stores.json").write_text(json.dumps(
        {"source": "OpenStreetMap contributors (ODbL)", "count": len(stores), "stores": stores},
        separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
