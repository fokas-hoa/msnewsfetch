#!/usr/bin/env python3
"""Restore the newest monitor-state artifact from an earlier GitHub Actions run."""
from __future__ import annotations
import io, json, os, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'monitor' / 'state.json'
API = 'https://api.github.com'


def request_json(url: str, token: str):
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'MSNewsFetch-monitor'
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if not token or not repo:
        print('No GitHub runtime context; starting without previous state.')
        return 0
    data = request_json(f'{API}/repos/{repo}/actions/artifacts?name=msnews-monitor-state&per_page=100', token)
    artifacts = [a for a in data.get('artifacts', []) if not a.get('expired')]
    if not artifacts:
        print('No previous monitor-state artifact found; this run will establish baseline.')
        return 0
    artifacts.sort(key=lambda a: a.get('created_at', ''), reverse=True)
    art = artifacts[0]
    req = urllib.request.Request(art['archive_download_url'], headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'MSNewsFetch-monitor'
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = r.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        candidates = [n for n in zf.namelist() if n.endswith('state.json')]
        if not candidates:
            print('Previous artifact did not contain state.json; starting baseline.')
            return 0
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_bytes(zf.read(candidates[0]))
    print(f'Restored previous state from artifact {art["id"]}.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
