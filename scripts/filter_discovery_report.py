#!/usr/bin/env python3
"""Apply the notification threshold to the broad weekly discovery inventory."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"

STRONG_NEWS_MARKERS = {
    "clinical trial", "phase 1", "phase i", "phase 2", "phase ii",
    "first-in-human", "ind-enabling", "investigational new drug", "gmp", "licensing"
}


def issue_worthy(c: dict) -> bool:
    if c.get("greece_priority"):
        return True
    score = int(c.get("score", 0))
    if score < 8:
        return False

    # Secondary news is a lead source, not evidence. Generic phrases such as
    # "remyelination therapy" must not generate review issues by themselves.
    if c.get("source") == "News discovery":
        markers = {str(x).lower() for x in (c.get("translation_hits") or [])}
        return bool(c.get("human_data")) or bool(markers & STRONG_NEWS_MARKERS)

    return True


def main() -> int:
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    raw = data.get("candidates") or []

    # Keep the collection layer sensitive, but only notify on high-signal leads.
    # Greece-related trial access is always review-worthy even if its text score is lower.
    high = [c for c in raw if issue_worthy(c)]
    high.sort(key=lambda x: (not x.get("greece_priority"), not x.get("human_data"), -int(x.get("score", 0)), x.get("source", ""), x.get("title", "")))

    data["broad_new_candidate_count"] = len(raw)
    data["suppressed_lower_signal_count"] = len(raw) - len(high)
    data["candidates"] = high
    data["candidate_count"] = len(high)
    data.setdefault("policy", {})["issue_threshold"] = (
        "score >= 8, or Greece-priority; secondary news additionally requires human-study context "
        "or an explicit development marker (trial/phase/first-in-human/IND/GMP/licensing)"
    )

    REPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Broad new={len(raw)}; issue-worthy={len(high)}; suppressed lower-signal={len(raw)-len(high)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
