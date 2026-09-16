#!/usr/bin/env python3
"""Apply the notification threshold to the enriched weekly discovery inventory."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"

STRONG_DEVELOPMENT_MARKERS = {
    "clinical trial", "phase 1", "phase i", "phase 2", "phase ii",
    "first-in-human", "ind-enabling", "investigational new drug", "gmp", "licensing"
}


def issue_worthy(c: dict) -> bool:
    identity_status = c.get("identity_status")
    source_class = c.get("source_class") or "other"
    score = int(c.get("score", 0))
    confidence = int(c.get("review_confidence", 0))
    translation = {str(x).lower() for x in (c.get("translation_hits") or [])}

    # Weekly discovery finds NEW programmes. Ordinary mentions of already-known
    # programmes belong to the daily monitor, not to discovery issues.
    if identity_status in {"known_record", "known_program_mention"}:
        return False

    # A newly registered human-trial record under an existing canonical programme
    # is still worth review because it may represent a new phase/arm/registration.
    if identity_status == "known_program_new_record":
        return bool(c.get("human_data")) and source_class == "primary_registry" and confidence >= 85

    if c.get("greece_priority"):
        return confidence >= 65

    if score < 8 or confidence < 68:
        return False

    if source_class == "primary_registry":
        return bool(c.get("human_data"))

    if source_class == "official_funding_or_project":
        return bool(translation) and score >= 8

    if source_class == "peer_reviewed_index":
        return bool(c.get("human_data") or translation) and score >= 9

    if source_class == "preprint":
        return bool(translation & STRONG_DEVELOPMENT_MARKERS) and score >= 10

    if source_class == "official_conference":
        return bool(c.get("human_data") or translation) and score >= 9

    if source_class == "secondary_news":
        return bool(c.get("human_data")) or bool(translation & STRONG_DEVELOPMENT_MARKERS)

    return bool(c.get("human_data") or translation) and confidence >= 72


def main() -> int:
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    raw = data.get("candidates") or []

    high = [c for c in raw if issue_worthy(c)]
    high.sort(key=lambda x: (
        not x.get("greece_priority"),
        not x.get("human_data"),
        -int(x.get("review_confidence", 0)),
        -int(x.get("score", 0)),
        x.get("source", ""),
        x.get("title", ""),
    ))

    data["broad_new_candidate_count"] = len(raw)
    data["suppressed_lower_signal_count"] = len(raw) - len(high)
    data["candidates"] = high
    data["candidate_count"] = len(high)
    data.setdefault("policy", {})["issue_threshold"] = (
        "source-aware gate using canonical identity + review-confidence + development evidence; "
        "known-program mentions are routed away from weekly discovery"
    )

    REPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Broad new={len(raw)}; issue-worthy={len(high)}; suppressed={len(raw)-len(high)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
