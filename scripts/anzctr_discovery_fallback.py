#!/usr/bin/env python3
"""Retry ANZCTR discovery with a browser-like user agent and merge into weekly report/state.

ANZCTR's public crawler pages can reject non-browser user agents from CI hosts.
This fallback keeps ANZCTR as a best-effort primary-registry source without
making a source outage fail the whole weekly discovery job.
"""
from __future__ import annotations

import json
from pathlib import Path

import deep_discovery as dd

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "monitor" / "discovery_state.json"
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

_original_req = dd.req


def browser_req(url, *, data=None, headers=None, timeout=45):
    h = dict(headers or {})
    if "anzctr.org.au" in url.lower():
        h["User-Agent"] = BROWSER_UA
        h.setdefault("Accept-Language", "en-AU,en;q=0.9")
    return _original_req(url, data=data, headers=h, timeout=timeout)


def main() -> int:
    from discovery_source_utils import merge_source
    warnings = []
    try:
        dd.req = browser_req
        candidates = dd.scan_anzctr(warnings)
    finally:
        dd.req = _original_req
    print(json.dumps(merge_source('anzctr', candidates, warnings)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
