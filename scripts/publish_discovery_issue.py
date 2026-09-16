#!/usr/bin/env python3
"""Open one GitHub review issue for new weekly discovery candidates."""
from __future__ import annotations
import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "monitor" / "discovery_report.json"


def main() -> int:
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    if data.get("baseline"):
        print("Baseline run; no discovery issue created.")
        return 0
    candidates = data.get("candidates") or []
    if not candidates:
        print("No new high-signal discovery candidates; no issue created.")
        return 0

    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    today = datetime.now(timezone.utc).date().isoformat()

    lines = [
        "## Weekly deep discovery — human review required",
        "",
        "This issue contains **new candidates outside the known watchlist**. Nothing here has been published to the site.",
        "Animal, cell, imaging, biomarker and preprint findings are **not clinical benefit**. Verify primary sources before adding anything to `news.json`.",
        "",
    ]
    greece = [c for c in candidates if c.get("greece_priority")]
    others = [c for c in candidates if not c.get("greece_priority")]

    def add_group(title, items):
        if not items:
            return
        lines.extend([f"### {title}", ""])
        for c in items:
            lines.append(f"#### [{c['title']}]({c['url']})")
            lines.append(f"- **Source:** {c['source']} — {c['source_quality']}")
            lines.append(f"- **Evidence level:** {c['evidence']}")
            lines.append(f"- **Human data:** {'Yes / human study context' if c['human_data'] else 'No or not established'}")
            lines.append(f"- **Discovery score:** {c['score']}")
            if c.get("repair_hits"):
                lines.append(f"- **Repair terms:** {', '.join(c['repair_hits'])}")
            if c.get("translation_hits"):
                lines.append(f"- **Translation signals:** {', '.join(c['translation_hits'])}")
            if c.get("model_hits"):
                lines.append(f"- **Model terms:** {', '.join(c['model_hits'])}")
            lines.append(f"- **Clinical meaning:** {c['clinical_note']}")
            lines.append("")

    add_group("Greece-priority candidates", greece)
    add_group("Other new candidates", others)

    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["### Source-health notes", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend([
        "### Review checklist",
        "",
        "- [ ] Confirm the candidate is genuinely MS-relevant and not merely mentioning MS as an exclusion criterion.",
        "- [ ] Confirm the programme is not already represented under another name/successor.",
        "- [ ] Verify trial status in the primary registry; resolve registry conflicts.",
        "- [ ] For Greece: verify an actual Greek recruiting site/contact, not merely an EU or country mention.",
        "- [ ] Distinguish human efficacy/safety from imaging, biomarker, animal, cell or mechanistic evidence.",
        "- [ ] Prefer primary/official sources before publication.",
    ])

    payload = json.dumps({
        "title": f"Deep discovery review — {today} ({len(candidates)} candidate{'s' if len(candidates) != 1 else ''})",
        "body": "\n".join(lines),
    }).encode("utf-8")

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "MSNewsFetch-deep-discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        issue = json.load(response)
    print(f"Created discovery review issue #{issue['number']}: {issue['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
