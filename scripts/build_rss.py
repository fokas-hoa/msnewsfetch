#!/usr/bin/env python3
"""Build rss.xml deterministically from news.json."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / 'news.json'
RSS = ROOT / 'rss.xml'
SITE = 'https://msnewsfetch.netlify.app'


def build() -> str:
    data = json.loads(NEWS.read_text(encoding='utf-8'))
    items = sorted(data.get('items', []), key=lambda x: x['date'], reverse=True)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        '<title>MSNewsFetch</title>',
        f'<link>{SITE}</link>',
        '<description>Τεκμηριωμένες ενημερώσεις για επαναμυελίνωση και myelin repair στη ΣΚΠ.</description>',
        '<language>el</language>',
    ]
    for item in items:
        dt = datetime.strptime(item['date'], '%Y-%m-%d').replace(hour=12, tzinfo=timezone.utc)
        description = f"{item['summary']} Τι σημαίνει: {item['meaning']}"
        out.extend([
            '<item>',
            f"<title>{escape(item['title'])}</title>",
            f"<link>{escape(item['url'], quote=True)}</link>",
            f"<guid isPermaLink=\"false\">{escape(item['id'])}</guid>",
            f"<pubDate>{format_datetime(dt)}</pubDate>",
            f"<description>{escape(description)}</description>",
            '</item>',
        ])
    out.append('</channel></rss>')
    return ''.join(out) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='Fail if rss.xml is not in sync with news.json')
    args = ap.parse_args()
    rendered = build()
    if args.check:
        current = RSS.read_text(encoding='utf-8') if RSS.exists() else ''
        if current != rendered:
            print('rss.xml is out of sync with news.json. Run: python scripts/build_rss.py')
            return 1
        print('rss.xml is in sync.')
        return 0
    RSS.write_text(rendered, encoding='utf-8')
    print(f'Wrote {RSS}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
