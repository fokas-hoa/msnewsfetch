#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish_live_feed", ROOT / "scripts" / "publish_live_feed.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)

change = {
    "program": "ReINFORCE",
    "source": "ClinicalTrials.gov",
    "evidence": "Human trial",
    "source_quality": "Primary registry",
    "field": "status",
    "before": "NOT_YET_RECRUITING",
    "after": "RECRUITING",
    "url": "https://clinicaltrials.gov/study/NCT06065670",
    "meaning": "Operational status changed; this does not itself establish efficacy.",
    "priority": "normal",
}
e = mod.event_from_change(change, "2026-09-16 18:00 UTC")
assert e["stage"] == "Ανθρώπινα δεδομένα"
assert e["auto_published"] is True
assert "NOT_YET_RECRUITING" in e["summary"] and "RECRUITING" in e["summary"]

candidate = {
    "id": "X1",
    "title": "A remyelination programme",
    "source": "Europe PMC",
    "source_quality": "Bibliographic record",
    "evidence": "Preclinical / translational paper",
    "human_data": False,
    "translation_hits": ["first-in-human"],
    "repair_hits": ["remyelination"],
    "clinical_note": "Preclinical/translational candidate only; no proven clinical benefit in people.",
    "url": "https://example.test/x1",
}
e2 = mod.event_from_candidate(candidate, "2026-09-16T18:00:00+00:00")
assert e2["stage"] == "Μεταφραστικό"
assert "no proven clinical benefit" in e2["meaning"]
p = mod.programme_from_candidate(candidate)
assert p and p["human"] is False

feed = {"events": [], "programme_overrides": {}, "programmes": []}
mod.apply_daily(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "substantive_changes": [change]})
assert len(feed["events"]) == 1
assert feed["programme_overrides"]["ReINFORCE"]["status"] == "RECRUITING"
mod.apply_daily(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "substantive_changes": [change]})
assert len(feed["events"]) == 1, "same event must dedupe"

print("live feed tests: OK")
