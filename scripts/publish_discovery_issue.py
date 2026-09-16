#!/usr/bin/env python3
"""Open one GitHub audit issue for new weekly discovery candidates."""
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
        "## Weekly deep discovery — audit trail",
        "",
        "This issue records **new high-signal candidates outside ordinary known-programme monitoring**.",
        "The review-confidence value is a **triage score**, not a probability that a treatment works. Animal, cell, imaging, biomarker and preprint findings are **not clinical benefit**.",
        "Publication to the live feed is deterministic and evidence-gated; this issue is an audit/review surface, not a manual approval gate.",
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
            lines.append(f"- **Source class:** {c.get('source_class', 'other')}")
            lines.append(f"- **Evidence level:** {c['evidence']}")
            lines.append(f"- **Human data:** {'Yes / human study context' if c['human_data'] else 'No or not established'}")
            lines.append(f"- **Discovery score:** {c['score']}")
            lines.append(f"- **Review confidence:** {c.get('review_confidence', 'n/a')} / 100 ({c.get('review_confidence_band', 'n/a')})")
            reasons = [str(x) for x in (c.get("review_confidence_reasons") or []) if x]
            if reasons:
                lines.append(f"- **Confidence rationale:** {'; '.join(reasons)}")
            if c.get("canonical_program_name"):
                lines.append(
                    f"- **Canonical identity:** {c['canonical_program_name']} "
                    f"(`{c.get('canonical_program_id')}`; {c.get('identity_status')}; via {c.get('identity_method')}: {c.get('identity_evidence')})"
                )
            else:
                lines.append("- **Canonical identity:** unmatched — candidate may represent a genuinely new programme")
            if c.get("family_id"):
                lines.append(f"- **Programme family:** `{c['family_id']}` (family membership does not imply same programme)")
            if c.get("relations"):
                relation_text = "; ".join(
                    f"{r.get('type')}: {r.get('target') or r.get('label') or ''}".strip()
                    for r in c["relations"]
                )
                lines.append(f"- **Curated relations:** {relation_text}")
            if c.get("repair_hits"):
                lines.append(f"- **Repair terms:** {', '.join(c['repair_hits'])}")
            if c.get("translation_hits"):
                lines.append(f"- **Translation signals:** {', '.join(c['translation_hits'])}")
            if c.get("model_hits"):
                lines.append(f"- **Model terms:** {', '.join(c['model_hits'])}")
            if c.get("also_seen_in"):
                alternate_text = ", ".join(
                    f"{x.get('source', 'source')} ({x.get('source_class', 'other')}, confidence {x.get('review_confidence', 'n/a')})"
                    for x in c["also_seen_in"]
                )
                lines.append(f"- **Cross-source duplicate cluster:** {alternate_text}")
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
        "### Audit checklist",
        "",
        "- [ ] Confirm the candidate is genuinely MS-relevant and not merely mentioning MS as an exclusion criterion.",
        "- [ ] Confirm canonical identity and whether this is a new programme, a new trial record, a trial name, or only another mention of an existing programme.",
        "- [ ] Verify trial status in the primary registry; resolve registry conflicts.",
        "- [ ] For Greece: verify an actual Greek recruiting site/contact, not merely an EU or country mention.",
        "- [ ] Distinguish human efficacy/safety from imaging, biomarker, animal, cell or mechanistic evidence.",
        "- [ ] Prefer primary/official sources when interpreting or manually editing curated baseline data.",
    ])

    payload = json.dumps({
        "title": f"Deep discovery audit — {today} ({len(candidates)} candidate{'s' if len(candidates) != 1 else ''})",
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
    print(f"Created discovery audit issue #{issue['number']}: {issue['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
