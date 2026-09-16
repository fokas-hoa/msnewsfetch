#!/usr/bin/env python3
"""Discover EU-funded MS myelin-repair programmes from public CORDIS search/project pages.

Uses the public search interface and official project records. It does not use
the CORDIS Data Extraction API, which requires a registered API key.
"""
from __future__ import annotations

import json
import re
import urllib.parse

import deep_discovery as dd
from discovery_source_utils import merge_source

PROJECT_LINK_RE = re.compile(r"(?:https?://(?:www\.)?cordis\.europa\.eu)?/project/id/(\d+)", re.I)
JSON_PROJECT_RE = re.compile(r'"(?:id|projectId)"\s*:\s*"?(\d{5,})"?', re.I)
MAX_PER_QUERY = 10
MAX_PROJECTS_PER_RUN = 30


def discover_ids(raw: bytes) -> list[str]:
    """Return project IDs in search-result order, without duplicates."""
    text = raw.decode("utf-8", "replace")
    found = PROJECT_LINK_RE.findall(text)
    if not found and ("contenttype" in text.lower() and "project" in text.lower()):
        found = JSON_PROJECT_RE.findall(text)
    out = []
    seen = set()
    for project_id in found:
        if project_id not in seen:
            seen.add(project_id)
            out.append(project_id)
    return out


def main() -> int:
    candidates = []
    warnings = []
    ordered_ids = []
    id_seen = set()

    for query in dd.CONFIG.get("cordis_queries", []):
        if len(ordered_ids) >= MAX_PROJECTS_PER_RUN:
            break
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "p": 1,
                "num": 20,
                "srt": "Relevance:decreasing",
                "format": "json",
            })
            raw = dd.req(
                "https://cordis.europa.eu/search/en?" + params,
                headers={"Accept": "application/json,text/html;q=0.9,*/*;q=0.8"},
                timeout=10,
            )
            for project_id in discover_ids(raw)[:MAX_PER_QUERY]:
                if project_id not in id_seen and len(ordered_ids) < MAX_PROJECTS_PER_RUN:
                    id_seen.add(project_id)
                    ordered_ids.append(project_id)
        except Exception as e:
            warnings.append(f"CORDIS search failed: {query!r} ({type(e).__name__})")

    for project_id in ordered_ids:
        url = f"https://cordis.europa.eu/project/id/{project_id}"
        try:
            raw = dd.req(url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=8)
            text, _links = dd.html_text(raw)
            title = project_id
            m = re.search(r"(?:Project|Fact Sheet|Objective)\s+(.{12,260}?)(?:Objective|CORDIS|Project description|$)", text, re.I)
            if m:
                title = " ".join(m.group(1).split())[:300]
            else:
                title = text[:260] if text else project_id

            c = dd.candidate(
                "CORDIS",
                project_id,
                title,
                url,
                text,
                {
                    "grant": True,
                    "human": any(x in text.lower() for x in (
                        "clinical trial", "patients", "participants", "phase 1", "phase i", "phase 2", "phase ii", "first-in-human"
                    )),
                    "greece": "Greece" in text,
                },
                evidence="EU-funded research and innovation project",
                source_quality="CORDIS — official European Commission project record",
            )
            if c:
                candidates.append(c)
        except Exception as e:
            warnings.append(f"CORDIS project fetch failed: {project_id} ({type(e).__name__})")

    result = merge_source("cordis", candidates, warnings)
    result["project_ids_discovered"] = len(ordered_ids)
    result["project_fetch_cap"] = MAX_PROJECTS_PER_RUN
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
