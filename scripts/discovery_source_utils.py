#!/usr/bin/env python3
"""Shared state/report merging for optional weekly discovery sources.

Each newly added source is silently baselined on its first successful run so
historic records do not generate a flood of false "new" alerts.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "monitor" / "discovery_state.json"
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"


def load():
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"version": 1, "seen": {}}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {
        "baseline": True, "warnings": [], "candidates": [], "source_candidate_counts": {}
    }
    state.setdefault("seen", {})
    report.setdefault("warnings", [])
    report.setdefault("candidates", [])
    report.setdefault("source_candidate_counts", {})
    return state, report


def merge_source(source_key: str, candidates: list[dict], warnings: list[str]) -> dict:
    import deep_discovery as dd

    state, report = load()
    had_source_baseline = source_key in state.get("seen", {})
    prior = set(state.get("seen", {}).get(source_key, []))
    dedup = {dd.key(c): c for c in candidates}
    candidates = list(dedup.values())
    current = set(dedup)

    # A brand-new source establishes its own baseline silently, even if the
    # overall weekly discovery system was already stateful.
    new_candidates = [] if not had_source_baseline else [c for c in candidates if dd.key(c) not in prior]

    state["seen"][source_key] = sorted(prior | current)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report["source_candidate_counts"][source_key] = len(candidates)
    existing = {dd.key(c) for c in report.get("candidates", [])}
    for c in new_candidates:
        if dd.key(c) not in existing:
            report["candidates"].append(c)
            existing.add(dd.key(c))

    for warning in warnings:
        if warning not in report["warnings"]:
            report["warnings"].append(warning)

    report.setdefault("source_baselines", {})[source_key] = {
        "was_previously_baselined": had_source_baseline,
        "current_candidate_count": len(candidates),
        "new_candidate_count": len(new_candidates),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "source": source_key,
        "baseline_created": not had_source_baseline,
        "candidates": len(candidates),
        "new": len(new_candidates),
        "warnings": len(warnings),
    }
