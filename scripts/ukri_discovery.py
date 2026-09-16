#!/usr/bin/env python3
"""Discover UK-funded MS myelin-repair programmes via UKRI Gateway to Research."""
from __future__ import annotations

import json
import urllib.parse

import deep_discovery as dd
from discovery_source_utils import merge_source


def flatten_strings(value):
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(flatten_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(flatten_strings(v))
    return out


def main() -> int:
    candidates = []
    warnings = []
    seen = set()
    endpoint = "https://gtr.ukri.org/api/search/project"

    for query in dd.CONFIG.get("ukri_queries", []):
        try:
            params = urllib.parse.urlencode({
                "term": query,
                "page": 1,
                "fetchSize": 100,
                "selectedSortableField": "pro.am",
                "selectedSortOrder": "DESC",
                "fields": "project.abs",
            })
            data = dd.get_json(endpoint + "?" + params)
            for raw in data.get("results", []):
                comp = raw.get("projectComposition") or raw
                project = comp.get("project") or {}
                grant_ref = str(project.get("grantReference") or project.get("grant_reference") or project.get("id") or "").strip()
                title = str(project.get("title") or raw.get("title") or grant_ref).strip()
                if not grant_ref or grant_ref in seen:
                    continue
                seen.add(grant_ref)
                text = " ".join(flatten_strings(raw))
                lead = comp.get("leadResearchOrganisation") or {}
                fund = project.get("fund") or {}
                funder = fund.get("funder") or {}
                c = dd.candidate(
                    "UKRI Gateway to Research",
                    grant_ref,
                    title,
                    "https://gtr.ukri.org/",
                    text,
                    {
                        "grant": True,
                        "human": any(x in text.lower() for x in ("clinical trial", "patients", "participants", "phase 1", "phase i", "phase 2", "phase ii")),
                        "organization": lead.get("name") if isinstance(lead, dict) else None,
                        "funder": funder.get("name") if isinstance(funder, dict) else None,
                        "start": fund.get("start") if isinstance(fund, dict) else None,
                        "end": fund.get("end") if isinstance(fund, dict) else None,
                    },
                    evidence="UK-funded research programme",
                    source_quality="UKRI Gateway to Research — official public grant database",
                )
                if c:
                    candidates.append(c)
        except Exception as e:
            warnings.append(f"UKRI query failed: {query!r} ({type(e).__name__})")

    result = merge_source("ukri", candidates, warnings)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
