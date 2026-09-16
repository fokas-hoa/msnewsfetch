#!/usr/bin/env python3
"""Discover EU-funded MS myelin-repair programmes from public CORDIS search/project pages.

Uses CORDIS public search with the official `contenttype=project` filter, then
verifies candidates on official project records. It does not use the CORDIS
Data Extraction API, which requires a registered API key.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse

import deep_discovery as dd
from discovery_source_utils import merge_source

PROJECT_LINK_RE = re.compile(r"(?:https?://(?:www\.)?cordis\.europa\.eu)?/project/id/(\d+)", re.I)
MAX_PER_QUERY = 10
MAX_PROJECTS_PER_RUN = 30


def discover_ids(raw: bytes) -> list[str]:
    """Extract only project IDs with explicit project context, preserving order."""
    text = raw.decode("utf-8", "replace")
    found: list[str] = []

    # Canonical project links are always safe project identifiers.
    found.extend(PROJECT_LINK_RE.findall(text))

    try:
        data = json.loads(text)
    except Exception:
        data = None

    def add(value):
        if value is None:
            return
        s = str(value).strip()
        if s.isdigit() and 5 <= len(s) <= 12:
            found.append(s)

    def walk(obj):
        if isinstance(obj, dict):
            ctype = str(obj.get("contenttype") or obj.get("contentType") or obj.get("type") or "").lower()
            project = obj.get("project")
            if isinstance(project, dict):
                add(project.get("id") or project.get("projectId") or project.get("grantAgreementId"))
            elif isinstance(project, str):
                for m in PROJECT_LINK_RE.findall(project):
                    add(m)
            if ctype == "project":
                add(obj.get("id") or obj.get("projectId") or obj.get("grantAgreementId"))
            for value in obj.values():
                if isinstance(value, str):
                    for m in PROJECT_LINK_RE.findall(value):
                        add(m)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    if data is not None:
        walk(data)

    out = []
    seen = set()
    for project_id in found:
        if project_id not in seen:
            seen.add(project_id)
            out.append(project_id)
    return out


def page_title(raw: bytes, fallback: str) -> str:
    source = raw.decode("utf-8", "replace")
    m = re.search(r"<title[^>]*>(.*?)</title>", source, re.I | re.S)
    if not m:
        return fallback
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
    title = re.sub(r"\s*\|\s*CORDIS\s*\|.*$", "", title, flags=re.I)
    return title[:300] or fallback


def main() -> int:
    candidates = []
    warnings = []
    ordered_ids = []
    id_seen = set()

    for query in dd.CONFIG.get("cordis_queries", []):
        if len(ordered_ids) >= MAX_PROJECTS_PER_RUN:
            break
        try:
            # CORDIS documents `contenttype=project` as the official project
            # collection filter. Keeping it in q prevents article/org IDs from
            # contaminating the project discovery set.
            cordis_q = f"({query}) AND contenttype=project"
            params = urllib.parse.urlencode({
                "q": cordis_q,
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
            title = page_title(raw, project_id)
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

    # New state key creates one silent baseline after replacing the unsafe generic
    # numeric-ID extraction with project-context-only extraction.
    result = merge_source("cordis_public_v2", candidates, warnings)
    result["project_ids_discovered"] = len(ordered_ids)
    result["project_fetch_cap"] = MAX_PROJECTS_PER_RUN
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
