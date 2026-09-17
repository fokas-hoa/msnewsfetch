#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from research_contract import source_record, POLICY_VERSION

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
obs={'id':'NCT06065670','url':change['url'],'status':change['after'],'observation_valid':True}
obs['provenance']=source_record(obs['id'],obs['url'],{'status':obs['status']})
change.update(policy_version=POLICY_VERSION,observation_valid=True,observation=obs,provenance=obs['provenance'],record_ids=[obs['id']],trial_id=obs['id'])
e = mod.event_from_change(change, "2026-09-16 18:00 UTC")
assert e["stage"] == "Ανθρώπινα δεδομένα"
assert e["auto_published"] is True
assert "NOT_YET_RECRUITING" in e["summary"] and "RECRUITING" in e["summary"]

paper = {
    "id": "PAPER1",
    "title": "A remyelination paper",
    "source": "Europe PMC",
    "source_quality": "Bibliographic record",
    "evidence": "Preclinical / translational paper",
    "human_data": False,
    "translation_hits": ["first-in-human"],
    "repair_hits": ["remyelination"],
    "clinical_note": "Preclinical/translational candidate only; no proven clinical benefit in people.",
    "url": "https://example.test/paper1",
}
e2 = mod.event_from_candidate(paper, "2026-09-16T18:00:00+00:00")
assert e2["stage"] == "Προκλινικό"
assert "no proven clinical benefit" in e2["meaning"]
assert mod.programme_from_candidate(paper) is None, "paper must not be invented into a pipeline programme"

trial = {
    "id": "NCT99999999",
    "title": "New remyelination trial",
    "source": "ClinicalTrials.gov",
    "source_quality": "Primary trial registry",
    "evidence": "Human trial registration",
    "human_data": True,
    "translation_hits": ["phase 2"],
    "repair_hits": ["remyelination"],
    "clinical_note": "Human trial registration does not establish clinical benefit.",
    "url": "https://clinicaltrials.gov/study/NCT99999999",
    "meta": {"phases": ["PHASE2"], "status": "RECRUITING", "countries": ["Greece", "France"]},
}
p = mod.programme_from_candidate(trial)
assert p and p["human"] is True
assert p["status"] == "RECRUITING"
assert "Greece" in p["geography"]

feed = {"events": [], "programme_overrides": {}, "programmes": [], "quarantine": []}
mod.apply_daily(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "substantive_changes": [change]})
assert len(feed["events"]) == 1
assert feed["programme_overrides"]["ReINFORCE"]["status"] == "RECRUITING"
mod.apply_daily(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "substantive_changes": [change]})
assert len(feed["events"]) == 1, "same event must dedupe"

mod.quarantine_warnings(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "warnings": ["Example source timeout"]}, "weekly")
assert len(feed["quarantine"]) == 1
assert feed["quarantine"][0]["published"] is False
mod.quarantine_warnings(feed, {"generated_at": "2026-09-16T18:00:00+00:00", "warnings": ["Example source timeout"]}, "weekly")
assert len(feed["quarantine"]) == 1, "same quarantine warning must dedupe"

print("live feed tests: OK")
