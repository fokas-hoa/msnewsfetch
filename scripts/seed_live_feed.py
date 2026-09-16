#!/usr/bin/env python3
"""Create an empty live-feed.json payload for initial branch bootstrap/testing."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "live-feed.json"
data = {
    "version": 1,
    "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "events": [],
    "programme_overrides": {},
    "programmes": [],
    "quarantine": [],
}
out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(out)
