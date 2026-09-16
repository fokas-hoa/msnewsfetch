#!/usr/bin/env python3
"""Restore the newest weekly deep-discovery state artifact."""
from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "monitor" / "discovery_state.json"
API = "https://api.github.com"
UA = "MSNewsFetch-deep-discovery"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": UA,
    }


def download_artifact(archive_url: str, token: str) -> bytes:
    """Follow GitHub's signed-storage redirect without leaking the GitHub auth header."""
    request = urllib.request.Request(archive_url, headers=github_headers(token))
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers.get("Location")
        if not location:
            raise
    # The Location is a signed blob URL. Do not forward Authorization to it.
    request = urllib.request.Request(location, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("No GitHub runtime context; discovery will establish baseline.")
        return 0

    request = urllib.request.Request(
        f"{API}/repos/{repo}/actions/artifacts?name=msnews-discovery-state&per_page=100",
        headers=github_headers(token),
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    artifacts = [a for a in data.get("artifacts", []) if not a.get("expired")]
    if not artifacts:
        print("No previous deep-discovery state artifact; this run will establish baseline.")
        return 0
    artifacts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    artifact = artifacts[0]
    payload = download_artifact(artifact["archive_download_url"], token)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates = [name for name in archive.namelist() if name.endswith("discovery_state.json")]
        if not candidates:
            print("Previous artifact lacks discovery_state.json; starting baseline.")
            return 0
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_bytes(archive.read(candidates[0]))
    print(f"Restored deep-discovery state from artifact {artifact['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
