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
    dd.req = browser_req
    warnings: list[str] = []
    candidates = dd.scan_anzctr(warnings)

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"version": 1, "seen": {}}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    previous = set()
    for source_keys in state.get("seen", {}).values():
        previous.update(source_keys)

    candidate_keys = {dd.key(c) for c in candidates}
    new_candidates = [c for c in candidates if dd.key(c) not in previous]

    state.setdefault("seen", {})["anzctr"] = sorted(set(state.get("seen", {}).get("anzctr", [])) | candidate_keys)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Remove the first-pass ANZCTR source warning if the browser-UA retry worked.
    if not warnings:
        report["warnings"] = [w for w in report.get("warnings", []) if not w.startswith("ANZCTR crawler index unavailable")]
        report.setdefault("source_candidate_counts", {})["anzctr"] = len(candidates)
    else:
        report.setdefault("warnings", []).extend(w for w in warnings if w not in report.get("warnings", []))

    if not report.get("baseline"):
        existing = {dd.key(c) for c in report.get("candidates", [])}
        for c in new_candidates:
            if dd.key(c) not in existing:
                report.setdefault("candidates", []).append(c)
                existing.add(dd.key(c))

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ANZCTR fallback candidates={len(candidates)}; new={len(new_candidates)}; warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
