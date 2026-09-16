#!/usr/bin/env python3
"""Publish deterministic MSNewsFetch updates to the dedicated live-data branch.

The publisher never writes free-form medical conclusions. It converts structured
monitor/discovery reports into conservative public entries and updates
`live-feed.json` through the GitHub Contents API. The website fetches that file
directly, so research updates do not require a Netlify production deploy.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / "monitor"
API = "https://api.github.com"
DATA_BRANCH = os.environ.get("MSNEWS_LIVE_BRANCH", "live-data")
DATA_PATH = os.environ.get("MSNEWS_LIVE_PATH", "live-feed.json")
MAX_EVENTS = 250
MAX_PROGRAMMES = 100
MAX_QUARANTINE = 100

PROGRAMME_SOURCES = {
    "ClinicalTrials.gov",
    "EU CTIS discovery",
    "EU CTIS",
    "ANZCTR",
    "ISRCTN",
    "NIH RePORTER",
    "UKRI Gateway to Research",
    "CORDIS",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stable_id(*parts: object) -> str:
    raw = "\u241f".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def api_request(url: str, token: str, *, method: str = "GET", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "MSNewsFetch-live-publisher",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def load_remote(repo: str, token: str):
    encoded_path = "/".join(urllib.parse.quote(x, safe="") for x in DATA_PATH.split("/"))
    url = f"{API}/repos/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(DATA_BRANCH, safe='')}"
    try:
        obj = api_request(url, token)
        raw = base64.b64decode(obj["content"]).decode("utf-8")
        return json.loads(raw), obj.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        return {
            "version": 1,
            "updated_at": now_iso(),
            "events": [],
            "programme_overrides": {},
            "programmes": [],
            "quarantine": [],
        }, None


def save_remote(repo: str, token: str, data: dict, sha: str | None):
    encoded_path = "/".join(urllib.parse.quote(x, safe="") for x in DATA_PATH.split("/"))
    url = f"{API}/repos/{repo}/contents/{encoded_path}"
    payload = {
        "message": "Update live MS research feed",
        "content": base64.b64encode((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        "branch": DATA_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    return api_request(url, token, method="PUT", body=payload)


def stage_from_evidence(evidence: str) -> str:
    low = (evidence or "").lower()
    if "preprint" in low:
        return "Προδημοσίευση"
    if "human" in low or "trial" in low:
        return "Ανθρώπινα δεδομένα"
    if "grant" in low or "programme" in low or "program" in low or "project" in low:
        return "Μεταφραστικό"
    return "Προκλινικό"


def event_from_change(change: dict, generated_at: str) -> dict:
    before = change.get("before")
    after = change.get("after")
    field = str(change.get("field") or "ενημέρωση")
    program = str(change.get("program") or "MS research update")
    summary = f"{field}: {after}." if before is None else f"{field}: {before} → {after}."
    greece = change.get("priority") == "greece"
    return {
        "id": stable_id("daily", program, change.get("source"), field, after, change.get("url")),
        "date": generated_at[:10] if generated_at else today(),
        "kind": "registry-update" if change.get("source") in {"ClinicalTrials.gov", "EU CTIS"} else "research-update",
        "source": change.get("source") or "Primary source",
        "sourceQuality": change.get("source_quality") or "Source requires contextual interpretation",
        "evidence": change.get("evidence") or "Research update",
        "stage": stage_from_evidence(change.get("evidence") or ""),
        "signal": "Ενημέρωση",
        "title": f"{program} — {field}",
        "summary": summary,
        "meaning": change.get("meaning") or "Καταγράφηκε νέα πηγή ή μεταβολή. Δεν αποτελεί από μόνη της απόδειξη κλινικού οφέλους.",
        "url": change.get("url") or "",
        "tags": [x for x in [program, change.get("source"), "Greece" if greece else None] if x],
        "greece_priority": greece,
        "canonical_program": change.get("canonical_name") or program,
        "confidence": change.get("review_confidence"),
        "auto_published": True,
    }


def event_from_candidate(c: dict, generated_at: str) -> dict:
    evidence = c.get("evidence") or "Research discovery"
    stage = stage_from_evidence(evidence)
    source = c.get("source") or "Research discovery"
    title = c.get("title") or c.get("canonical_name") or c.get("id") or "New MS research signal"
    note = c.get("clinical_note") or "Νέο ερευνητικό σήμα. Η καταχώριση δεν αποτελεί από μόνη της απόδειξη κλινικού οφέλους."
    return {
        "id": stable_id("weekly", c.get("id"), c.get("url"), title),
        "date": generated_at[:10] if generated_at else today(),
        "kind": "new-programme" if c.get("human_data") or c.get("translation_hits") else "new-research",
        "source": source,
        "sourceQuality": c.get("source_quality") or "Source requires verification",
        "evidence": evidence,
        "stage": stage,
        "signal": "Νέο εύρημα",
        "title": title,
        "summary": f"Αυτόματα εντοπισμένο νέο ερευνητικό σήμα από {source}. Evidence: {evidence}.",
        "meaning": note,
        "url": c.get("url") or "",
        "tags": list(dict.fromkeys([str(x) for x in ([c.get("canonical_name")] + (c.get("repair_hits") or []) + (c.get("translation_hits") or [])) if x]))[:8],
        "greece_priority": bool(c.get("greece_priority")),
        "canonical_program": c.get("canonical_name"),
        "confidence": c.get("review_confidence"),
        "confidence_level": c.get("review_confidence_level"),
        "auto_published": True,
    }


def programme_from_candidate(c: dict) -> dict | None:
    """Promote only programme-like sources to pipeline cards.

    Papers/preprints remain visible in Latest Updates but are not invented into
    development programmes merely because their abstract contains a translation
    keyword.
    """
    source = str(c.get("source") or "")
    evidence = str(c.get("evidence") or "")
    quality = str(c.get("source_quality") or "")
    context = f"{evidence} {quality}".lower()
    programme_like = (
        source in PROGRAMME_SOURCES
        or "trial registry" in context
        or "clinical-trial registry" in context
        or "grant database" in context
        or "project record" in context
        or "funded research" in context
    )
    if not programme_like:
        return None
    if not (c.get("human_data") or c.get("translation_hits") or c.get("meta", {}).get("grant")):
        return None

    meta = c.get("meta") or {}
    phases = meta.get("phases") or []
    if isinstance(phases, str):
        phases = [phases]
    countries = meta.get("countries") or []
    if isinstance(countries, str):
        countries = [countries]
    human = bool(c.get("human_data"))
    return {
        "id": stable_id("programme", c.get("canonical_id") or c.get("id"), c.get("title")),
        "canonical_id": c.get("canonical_id"),
        "name": c.get("canonical_name") or c.get("title") or c.get("id"),
        "candidate": c.get("title") if c.get("canonical_name") else (source or "Automated discovery"),
        "phase": ", ".join(phases) if phases else ("Human trial" if human else "Translational"),
        "status": meta.get("status") or ("Automatically discovered" if human else "Translational signal"),
        "geography": ", ".join(countries[:8]) if countries else "",
        "evidence": evidence or "Research discovery",
        "nextLabel": "Auto watch",
        "next": "Παρακολουθείται αυτόματα για ουσιαστικές αλλαγές και νέα πρωτογενή δεδομένα.",
        "url": c.get("url") or "",
        "human": human,
        "updated_at": now_iso(),
    }


def merge_by_id(existing: list[dict], incoming: list[dict], limit: int) -> list[dict]:
    merged = {str(x.get("id")): x for x in existing if x.get("id")}
    for item in incoming:
        if item.get("id"):
            merged[str(item["id"])] = item
    values = list(merged.values())
    values.sort(key=lambda x: (x.get("date") or x.get("updated_at") or "", x.get("id") or ""), reverse=True)
    return values[:limit]


def quarantine_warnings(data: dict, report: dict, mode: str):
    generated = report.get("generated_at") or now_iso()
    incoming = []
    for warning in report.get("warnings") or []:
        incoming.append({
            "id": stable_id("quarantine", mode, warning),
            "updated_at": generated,
            "mode": mode,
            "reason": "source/parser warning",
            "detail": str(warning)[:1000],
            "published": False,
        })
    data["quarantine"] = merge_by_id(data.get("quarantine") or [], incoming, MAX_QUARANTINE)


def apply_daily(data: dict, report: dict):
    generated = report.get("generated_at") or now_iso()
    events = [event_from_change(c, generated) for c in report.get("substantive_changes") or []]
    data["events"] = merge_by_id(data.get("events") or [], events, MAX_EVENTS)

    overrides = dict(data.get("programme_overrides") or {})
    for c in report.get("substantive_changes") or []:
        program = c.get("canonical_name") or c.get("program")
        if not program:
            continue
        entry = dict(overrides.get(program) or {})
        entry["updated_at"] = generated
        if c.get("field") == "status":
            entry["status"] = c.get("after")
        elif c.get("field") == "Greece sites":
            entry["greece_sites"] = c.get("after")
        elif c.get("field") == "Greece mention":
            entry["greece_mentioned"] = c.get("after")
        elif c.get("field") == "temporary halt":
            entry["temporary_halt"] = c.get("after")
        overrides[program] = entry
    data["programme_overrides"] = overrides


def apply_weekly(data: dict, report: dict):
    generated = report.get("generated_at") or now_iso()
    candidates = report.get("candidates") or []
    events = [event_from_candidate(c, generated) for c in candidates]
    programmes = [p for p in (programme_from_candidate(c) for c in candidates) if p]
    data["events"] = merge_by_id(data.get("events") or [], events, MAX_EVENTS)
    data["programmes"] = merge_by_id(data.get("programmes") or [], programmes, MAX_PROGRAMMES)


def main() -> int:
    mode = os.environ.get("MSNEWS_PUBLISH_MODE", "daily").strip().lower()
    report_path = MON / ("report.json" if mode == "daily" else "discovery_report.json")
    if not report_path.exists():
        print(f"No {report_path.name}; nothing to publish.")
        return 0
    if mode not in {"daily", "weekly"}:
        raise SystemExit(f"Unknown MSNEWS_PUBLISH_MODE={mode!r}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    data, sha = load_remote(repo, token)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)

    # Baseline runs establish source state but do not publish historical items.
    if not report.get("baseline"):
        if mode == "daily":
            apply_daily(data, report)
        else:
            apply_weekly(data, report)
    quarantine_warnings(data, report, mode)

    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before == after:
        print("No new live-feed content; no live-data commit created.")
        return 0

    data["version"] = 1
    data["updated_at"] = now_iso()
    result = save_remote(repo, token, data, sha)
    print(f"Live feed updated on {DATA_BRANCH}: {result.get('commit', {}).get('sha', 'ok')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
