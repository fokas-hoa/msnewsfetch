#!/usr/bin/env python3
"""Small dependency-free regression suite for deterministic programme identity."""
from __future__ import annotations

from program_identity import load_registry, match_programme, review_confidence, title_similarity, validate_registry


def candidate(source, cid, title, **extra):
    base = {
        "source": source,
        "id": cid,
        "title": title,
        "url": "https://example.invalid/",
        "source_quality": "",
        "human_data": False,
        "greece_priority": False,
        "repair_hits": ["remyelination"],
        "translation_hits": [],
        "model_hits": [],
        "meta": {},
    }
    base.update(extra)
    return base


def main() -> int:
    registry = load_registry()
    errors = validate_registry(registry)
    assert not errors, "registry errors: " + "; ".join(errors)

    lucid = match_programme(candidate("News discovery", "x1", "Quantum BioPharma advances Lucid-21-302"), registry)
    assert lucid["canonical_program_id"] == "lucid-ms", lucid
    assert lucid["identity_status"] == "known_program_mention", lucid

    pipe = match_programme(candidate("Europe PMC", "x2", "PIPE-307 VISTA remyelination results"), registry)
    assert pipe["canonical_program_id"] == "pipe-307", pipe

    vista = match_programme(candidate("Europe PMC", "x3", "VISTA trial of PIPE-307"), registry)
    assert vista["canonical_program_id"] == "pipe-307", vista

    aging = match_programme(candidate("ClinicalTrials.gov", "NCT06463743", "Metformin study"), registry)
    assert aging["canonical_program_id"] == "metformin-aging-ms", aging
    assert aging["identity_status"] == "known_record", aging

    # Generic metformin must not collapse distinct remyelination trials into OCTOPUS.
    generic = match_programme(candidate("Europe PMC", "x4", "Metformin and aging in multiple sclerosis"), registry)
    assert generic["canonical_program_id"] is None, generic

    # Related NeuOrphan programmes are family-linked but intentionally not aliases.
    odyssey = match_programme(candidate("News discovery", "x5", "NeuOrphan Odyssey programme update"), registry)
    ditpa = match_programme(candidate("News discovery", "x6", "NeuOrphan DITPA update"), registry)
    assert odyssey["canonical_program_id"] == "neuorphan-odyssey", odyssey
    assert ditpa["canonical_program_id"] == "neuorphan-ditpa", ditpa
    assert odyssey["canonical_program_id"] != ditpa["canonical_program_id"]
    assert odyssey["family_id"] == ditpa["family_id"] == "neuorphan-remyelination"

    # A new registry record bearing a known alias must remain reviewable rather than
    # being silently collapsed into an existing identifier.
    new_lucid_trial = match_programme(candidate("ClinicalTrials.gov", "NCT09999999", "Lucid-MS Phase 2"), registry)
    assert new_lucid_trial["canonical_program_id"] == "lucid-ms", new_lucid_trial
    assert new_lucid_trial["identity_status"] == "known_program_new_record", new_lucid_trial

    primary = candidate(
        "ClinicalTrials.gov", "NCT09999998", "Novel remyelination Phase 2 trial",
        source_quality="Primary trial registry", human_data=True,
        translation_hits=["phase 2"],
    )
    secondary = candidate(
        "News discovery", "n1", "Novel remyelination therapy announced",
        source_quality="Secondary discovery only", translation_hits=["therapy"],
    )
    assert review_confidence(primary)["review_confidence"] > review_confidence(secondary)["review_confidence"]

    assert title_similarity(
        "A first-in-human study of ABC123 for remyelination in multiple sclerosis",
        "First in human ABC123 study for myelin repair in MS",
    ) >= 0.45

    print("programme identity tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
