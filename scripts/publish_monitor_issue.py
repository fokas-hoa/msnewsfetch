#!/usr/bin/env python3
"""Create one GitHub issue when monitor_research.py reports substantive changes."""
from __future__ import annotations
import json, os, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'monitor' / 'report.json'
API = 'https://api.github.com'


def api(url: str, token: str, method='GET', body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'MSNewsFetch-monitor'
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    if not REPORT.exists():
        print('No report.json; nothing to publish.')
        return 0
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    changes = report.get('substantive_changes', [])
    if not changes:
        print('No substantive developments; no GitHub issue created.')
        return 0
    token = os.environ['GITHUB_TOKEN']
    repo = os.environ['GITHUB_REPOSITORY']
    fp = report['fingerprint'][:12]
    query = urllib.parse.quote(f'repo:{repo} in:title {fp}')
    found = api(f'{API}/search/issues?q={query}&per_page=5', token)
    if found.get('total_count', 0):
        print(f'Issue for fingerprint {fp} already exists; skipping duplicate.')
        return 0
    title = f'MS remyelination monitor: substantive update [{fp}]'
    body = report['markdown'] + f'\n\n<!-- monitor-fingerprint:{report["fingerprint"]} -->\n'
    issue = api(f'{API}/repos/{repo}/issues', token, 'POST', {'title': title, 'body': body})
    print(f'Created issue #{issue.get("number")}: {issue.get("html_url")}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
