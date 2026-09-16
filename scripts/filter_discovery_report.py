#!/usr/bin/env python3
"""Apply the publication threshold to the enriched weekly discovery inventory."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"

STRONG_DEVELOPMENT_MARKERS = {
    "clinical trial", "phase 1", "phase i", "phase 2", "phase ii",
    "first-in-human", "ind-enabling", "investigational new drug", "gmp", "licensing"
}


def reaches(confidence: int, threshold: int, greece_priority: bool) -> bool:
    """Greece relevance can modestly raise review priority, never replace evidence."""
    effective = confidence + (5 if greece_priority else 0)
    return effective >= threshold


def issue_worthy(c: dict) -> bool:
    identity_status = c.get("identity_status")
    source_class = c.get("source_class") or "other"
    score = int(c.get("score", 0))
    confidence = int(c.get("review_confidence", 0))
    human = bool(c.get("human_data"))
    greece = bool(c.get("greece_priority"))
    translation = {str(x).lower() for x in (c.get("translation_hits") or [])}
    strong_development = bool(translation & STRONG_DEVELOPMENT_MARKERS)

    # Weekly discovery finds NEW programmes. Ordinary mentions of already-known
    # programmes belong to the daily monitor, not to discovery publication.
    if identity_status in {"known_record", "known_program_mention"}:
        return False

    # A newly registered human-trial record under an existing canonical programme
    # is still important because it may be a new phase, arm or registration.
    if identity_status == "known_program_new_record":
        return human and source_class == "primary_registry" and reaches(confidence, 85, greece)

    # Thresholds are deliberately source-class specific. A single global confidence
    # floor would make the preprint and secondary-news branches unreachable because
    # those classes intentionally start from lower source-confidence baselines.
    if source_class == "primary_registry":
        return human and score >= 7 and reaches(confidence, 85, greece)

    if source_class == "official_funding_or_project":
        return bool(translation) and score >= 8 and reaches(confidence, 70, greece)

    if source_class == "peer_reviewed_index":
        return bool(human or translation) and score >= 9 and reaches(confidence, 72, greece)

    if source_class == "preprint":
        return strong_development and score >= 10 and reaches(confidence, 55, greece)

    if source_class == "official_conference":
        return bool(human or strong_development) and score >= 9 and reaches(confidence, 62, greece)

    if source_class == "secondary_news":
        # Secondary news remains a discovery lead only. It needs an explicit
        # development milestone; generic 'therapy/remyelination' wording is insufficient.
        return strong_development and score >= 8 and reaches(confidence, 38, greece)

    if source_class == "official_programme_page":
        return strong_development and score >= 8 and reaches(confidence, 65, greece)

    return bool(human or translation) and score >= 8 and reaches(confidence, 72, greece)


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
        "source-class-specific evidence/confidence gate using canonical identity, human context, "
        "development signals and Greece priority; known-program mentions route to the daily monitor"
    )

    REPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Broad new={len(raw)}; issue-worthy={len(high)}; suppressed={len(raw)-len(high)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
