#!/usr/bin/env python3
"""Restore the newest monitor-state artifact from an earlier GitHub Actions run."""
from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'monitor' / 'state.json'
API = 'https://api.github.com'
UA = 'MSNewsFetch-monitor'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_headers(token: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': UA,
    }


def request_json(url: str, token: str):
    req = urllib.request.Request(url, headers=github_headers(token))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def download_artifact(archive_url: str, token: str) -> bytes:
    """Follow GitHub's signed-storage redirect without leaking the GitHub auth header."""
    req = urllib.request.Request(archive_url, headers=github_headers(token))
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers.get('Location')
        if not location:
            raise
    req = urllib.request.Request(location, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


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
    payload = download_artifact(art['archive_download_url'], token)
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
