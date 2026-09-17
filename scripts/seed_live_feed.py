#!/usr/bin/env python3
"""Create the current empty live-feed payload for explicit bootstrap/testing.

This helper mirrors the publisher's single source of truth. It does not update
Git refs or publish anything by itself.
"""
from __future__ import annotations
import json
from pathlib import Path

from publish_live_feed import empty_feed

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "live-feed.json"
out.write_text(json.dumps(empty_feed(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(out)
