#!/usr/bin/env python3
"""Restore the canonical structured research dataset from compressed payload parts.

RSS is intentionally not restored from a payload. It is generated deterministically
from news.json by scripts/build_rss.py so there is only one content source of truth.
"""
from __future__ import annotations
import base64
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


def restore(prefix: str, output: str) -> None:
    parts = sorted(DATA.glob(f'{prefix}.part*'))
    if not parts:
        raise SystemExit(f'No payload parts found for {prefix}')
    encoded = ''.join(p.read_text(encoding='ascii').strip() for p in parts)
    raw = gzip.decompress(base64.b64decode(encoded))
    (ROOT / output).write_bytes(raw)
    print(f'Restored {output} from {len(parts)} payload part(s).')


def main() -> int:
    restore('news.json.gz.b64', 'news.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
