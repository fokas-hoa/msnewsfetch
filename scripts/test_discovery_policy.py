#!/usr/bin/env python3
"""Dependency-free regression tests for weekly discovery gating and dedupe."""
from __future__ import annotations

from deep_discovery import candidate as collect_candidate
from enrich_discovery_report import dedupe_candidates
from filter_discovery_report import issue_worthy


def base(**overrides):
    item = {
        "source": "ClinicalTrials.gov",
        "source_class": "primary_registry",
        "source_quality": "Primary trial registry",
        "id": "NCT09999999",
        "title": "Novel remyelination Phase 2 study",
        "score": 10,
        "review_confidence": 95,
        "review_confidence_band": "very_high",
        "greece_priority": False,
        "human_data": True,
        "translation_hits": ["phase 2"],
        "repair_hits": ["remyelination"],
        "model_hits": [],
        "identity_status": "unmatched",
        "canonical_program_id": None,
        "canonical_program_name": None,
        "url": "https://example.invalid/",
    }
    item.update(overrides)
    return item


def main() -> int:
    assert issue_worthy(base()) is True

    # Codex P1 regression: a novel registry ID carrying a known programme alias
    # must survive collection so it can become known_program_new_record.
    novel = collect_candidate(
        "ClinicalTrials.gov",
        "NCT09999998",
        "Lucid-MS Phase 2 remyelination study in multiple sclerosis",
        "https://clinicaltrials.gov/study/NCT09999998",
        "Lucid-MS Phase 2 clinical trial remyelination multiple sclerosis patients",
        {
            "human": True,
            "greece": False,
            "status": "NOT_YET_RECRUITING",
            "phases": ["PHASE2"],
            "countries": ["United States"],
        },
        evidence="Human trial registration",
        source_quality="Primary trial registry",
    )
    assert novel is not None
    assert novel["identity_status"] == "known_program_new_record"
    assert novel["canonical_program_id"] == "lucid-ms"

    # The exact already-known registry record remains suppressed.
    existing = collect_candidate(
        "ClinicalTrials.gov",
        "NCT06595706",
        "Lucid-MS remyelination clinical trial in multiple sclerosis",
        "https://clinicaltrials.gov/study/NCT06595706",
        "Lucid-MS clinical trial remyelination multiple sclerosis patients",
        {"human": True, "greece": False},
        evidence="Human trial registration",
        source_quality="Primary trial registry",
    )
    assert existing is None

    # Ordinary re-mentions of known programmes are for the daily monitor.
    assert issue_worthy(base(identity_status="known_program_mention", canonical_program_id="lucid-ms")) is False
    assert issue_worthy(base(identity_status="known_record", canonical_program_id="lucid-ms")) is False

    # A new human registry record under a known programme stays publishable/reviewable.
    assert issue_worthy(base(identity_status="known_program_new_record", canonical_program_id="lucid-ms")) is True

    # Generic secondary-news hype does not pass the publication gate.
    assert issue_worthy(base(
        source="News discovery",
        source_class="secondary_news",
        human_data=False,
        score=8,
        review_confidence=40,
        translation_hits=["therapy"],
    )) is False

    # Codex P1 regression: source-class thresholds must remain reachable.
    # A strong human preprint can pass its deliberately lower preprint confidence floor.
    assert issue_worthy(base(
        source="medRxiv",
        source_class="preprint",
        human_data=True,
        score=10,
        review_confidence=60,
        translation_hits=["first-in-human"],
    )) is True

    # Strong secondary discovery can surface as a lead only with an explicit
    # development milestone; generic 'therapy' wording still cannot pass.
    assert issue_worthy(base(
        source="News discovery",
        source_class="secondary_news",
        human_data=False,
        score=8,
        review_confidence=42,
        translation_hits=["phase 2"],
    )) is True

    assert issue_worthy(base(
        source="medRxiv",
        source_class="preprint",
        human_data=False,
        score=9,
        review_confidence=60,
        translation_hits=["therapy"],
    )) is False

    # Canonical duplicates collapse, but new registry records do not.
    a = base(canonical_program_id="pipe-307", identity_status="known_program_mention", title="PIPE-307 VISTA update")
    b = base(canonical_program_id="pipe-307", identity_status="known_program_mention", title="VISTA study PIPE-307", source="Europe PMC", source_class="peer_reviewed_index", review_confidence=80)
    deduped, suppressed = dedupe_candidates([a, b])
    assert len(deduped) == 1 and suppressed == 1

    c = base(canonical_program_id="lucid-ms", identity_status="known_program_new_record", id="NCT09999991", title="Lucid-MS Phase 2")
    d = base(canonical_program_id="lucid-ms", identity_status="known_program_new_record", id="NCT09999992", title="Lucid-MS extension study")
    deduped, suppressed = dedupe_candidates([c, d])
    assert len(deduped) == 2 and suppressed == 0

    # Codex P2 regression: different unmatched primary-registry IDs remain distinct
    # even when title token similarity is effectively identical (Phase 2 vs Phase 3).
    r1 = base(
        id="NCT09999993",
        title="Novel remyelination Phase 2 study",
        identity_status="unmatched",
        canonical_program_id=None,
    )
    r2 = base(
        id="NCT09999994",
        title="Novel remyelination Phase 3 study",
        identity_status="unmatched",
        canonical_program_id=None,
    )
    deduped, suppressed = dedupe_candidates([r1, r2])
    assert len(deduped) == 2 and suppressed == 0

    print("discovery policy tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
