#!/usr/bin/env python3
"""Restore the newest weekly deep-discovery state artifact."""
from __future__ import annotations
import io, json, os, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "monitor" / "discovery_state.json"
API = "https://api.github.com"


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("No GitHub runtime context; discovery will establish baseline.")
        return 0

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MSNewsFetch-deep-discovery",
    }
    request = urllib.request.Request(
        f"{API}/repos/{repo}/actions/artifacts?name=msnews-discovery-state&per_page=100",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    artifacts = [a for a in data.get("artifacts", []) if not a.get("expired")]
    if not artifacts:
        print("No previous deep-discovery state artifact; this run will establish baseline.")
        return 0
    artifacts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    artifact = artifacts[0]
    request = urllib.request.Request(artifact["archive_download_url"], headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates = [name for name in archive.namelist() if name.endswith("discovery_state.json")]
        if not candidates:
            print("Previous artifact lacks discovery_state.json; starting baseline.")
            return 0
        DEST.write_bytes(archive.read(candidates[0]))
    print(f"Restored deep-discovery state from artifact {artifact['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
