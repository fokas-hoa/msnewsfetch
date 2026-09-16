#!/usr/bin/env python3
"""Enrich weekly discovery candidates with canonical identity and review confidence.

The output remains advisory. It does not publish to news.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from program_identity import load_registry, match_programme, review_confidence, title_similarity

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"


def candidate_rank(candidate: dict) -> tuple:
    return (
        bool(candidate.get("greece_priority")),
        bool(candidate.get("human_data")),
        int(candidate.get("review_confidence", 0)),
        int(candidate.get("score", 0)),
    )


def distinct_primary_registry_records(a: dict, b: dict) -> bool:
    """Return True when two candidates are separate primary-registry records.

    Similar titles are not enough to collapse two registry records. Different
    stable registry IDs remain distinct unless a curated canonical identity
    explicitly proves that they are the same tracked record/programme.
    """
    if a.get("source_class") != "primary_registry" or b.get("source_class") != "primary_registry":
        return False
    aid = str(a.get("id") or "").strip().upper()
    bid = str(b.get("id") or "").strip().upper()
    return bool(aid and bid and aid != bid)


def dedupe_candidates(candidates: list[dict]) -> tuple[list[dict], int]:
    """Deterministic cross-source dedupe.

    1. Exact canonical programme matches collapse ordinary mentions.
    2. New registry records for an already-known programme remain separate.
    3. Distinct unmatched primary-registry IDs remain separate even with near-identical titles.
    4. Other unmatched records with highly similar informative title tokens can collapse.
    """
    kept: list[dict] = []
    suppressed = 0

    for candidate in sorted(candidates, key=candidate_rank, reverse=True):
        merged = False
        cid = candidate.get("canonical_program_id")
        identity_status = candidate.get("identity_status")

        for existing in kept:
            # Preserve distinct newly registered trial records even when they belong to
            # an existing programme family.
            if identity_status == "known_program_new_record" or existing.get("identity_status") == "known_program_new_record":
                continue

            # Never use title similarity alone to collapse two different primary
            # registry IDs. Phase 2 and Phase 3 records can have almost identical
            # titles while being operationally distinct trials.
            if distinct_primary_registry_records(candidate, existing):
                continue

            same_programme = bool(cid and cid == existing.get("canonical_program_id"))
            lexical_duplicate = (
                not cid
                and not existing.get("canonical_program_id")
                and title_similarity(str(candidate.get("title") or ""), str(existing.get("title") or "")) >= 0.84
            )
            if same_programme or lexical_duplicate:
                existing.setdefault("also_seen_in", []).append({
                    "source": candidate.get("source"),
                    "url": candidate.get("url"),
                    "id": candidate.get("id"),
                    "title": candidate.get("title"),
                    "review_confidence": candidate.get("review_confidence"),
                })
                suppressed += 1
                merged = True
                break

        if not merged:
            kept.append(candidate)

    kept.sort(key=candidate_rank, reverse=True)
    return kept, suppressed


def main() -> int:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    registry = load_registry()
    enriched: list[dict] = []

    for raw in report.get("candidates") or []:
        candidate = dict(raw)
        candidate.update(match_programme(candidate, registry))
        candidate.update(review_confidence(candidate))
        enriched.append(candidate)

    deduped, suppressed = dedupe_candidates(enriched)
    report["identity_registry_version"] = registry.get("version")
    report["pre_identity_candidate_count"] = len(enriched)
    report["identity_dedup_suppressed_count"] = suppressed
    report["candidates"] = deduped
    report["candidate_count"] = len(deduped)
    report.setdefault("policy", {})["identity_model"] = (
        "deterministic identifiers + curated aliases + explicit programme families; "
        "no opaque embeddings"
    )
    report.setdefault("policy", {})["review_confidence"] = (
        "review-priority score, not a probability of scientific truth or clinical benefit"
    )

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched={len(enriched)}; deduped={len(deduped)}; suppressed={suppressed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
