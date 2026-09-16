#!/usr/bin/env python3
"""Discover additional MS myelin-repair trials through the official ISRCTN XML API."""
from __future__ import annotations

import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

import deep_discovery as dd
from discovery_source_utils import merge_source

ISRCTN_RE = re.compile(r"\bISRCTN\d{8}\b", re.I)
TITLE_TAGS = {"publictitle", "public_title", "scientifictitle", "scientific_title", "title", "trialname", "trial_name"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower().replace("-", "_")


def element_text(el) -> str:
    return " ".join(" ".join(el.itertext()).split())


def record_elements(root):
    """Pick the smallest useful XML element containing each ISRCTN identifier."""
    best = {}
    for el in root.iter():
        text = element_text(el)
        if len(text) < 120:
            continue
        ids = {x.upper() for x in ISRCTN_RE.findall(text)}
        if len(ids) != 1:
            continue
        rid = next(iter(ids))
        if rid not in best or len(text) < best[rid][0]:
            best[rid] = (len(text), el, text)
    return [(rid, el, text) for rid, (_n, el, text) in best.items()]


def pick_title(el, fallback: str) -> str:
    for child in el.iter():
        if local(child.tag) in TITLE_TAGS:
            text = " ".join(" ".join(child.itertext()).split())
            if len(text) >= 8:
                return text[:300]
    return fallback


def main() -> int:
    candidates = []
    warnings = []
    seen = set()
    # ISRCTN's own API documentation recommends the default XML format for
    # general consumers; `internal` is a legacy/deprecated compatibility format.
    endpoint = "https://www.isrctn.com/api/query/format/default"

    for query in dd.CONFIG.get("isrctn_queries", []):
        try:
            url = endpoint + "?" + urllib.parse.urlencode({"q": query, "limit": 100})
            raw = dd.req(url, headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"}, timeout=30)
            root = ET.fromstring(raw)
            for rid, el, text in record_elements(root):
                if rid in seen:
                    continue
                seen.add(rid)
                title = pick_title(el, rid)
                c = dd.candidate(
                    "ISRCTN",
                    rid,
                    title,
                    f"https://www.isrctn.com/{rid}",
                    text,
                    {"human": True, "greece": "Greece" in text},
                    evidence="Human trial registry record",
                    source_quality="ISRCTN — WHO primary clinical-trial registry; official public XML API",
                )
                if c:
                    candidates.append(c)
        except Exception as e:
            warnings.append(f"ISRCTN query failed: {query!r} ({type(e).__name__})")

    # New source-state key forces one clean silent baseline after moving away
    # from the deprecated internal endpoint.
    result = merge_source("isrctn_default_v1", candidates, warnings)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
