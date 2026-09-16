#!/usr/bin/env python3
"""Small CI validator for MSNewsFetch structured research data."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'news.json').read_text(encoding='utf-8'))
errors=[]


def require(obj, fields, where):
    for f in fields:
        if not obj.get(f): errors.append(f'{where}: missing {f}')


def valid_url(url):
    try:
        p=urlparse(url)
        return p.scheme == 'https' and bool(p.netloc)
    except Exception:
        return False

try:
    date.fromisoformat(DATA['siteUpdated'])
except Exception:
    errors.append('siteUpdated must be YYYY-MM-DD')

ids=set()
for i,item in enumerate(DATA.get('items', [])):
    where=f'items[{i}]'
    require(item,['id','date','title','stage','signal','evidence','sourceQuality','summary','meaning','source','url','tags'],where)
    if item.get('id') in ids: errors.append(f"duplicate item id: {item.get('id')}")
    ids.add(item.get('id'))
    try: date.fromisoformat(item.get('date',''))
    except Exception: errors.append(f'{where}: invalid date')
    if item.get('url') and not valid_url(item['url']): errors.append(f'{where}: url must be https')

for section in ('pipeline','translational','readouts'):
    names=set()
    for i,item in enumerate(DATA.get(section, [])):
        where=f'{section}[{i}]'
        require(item,['name','candidate','phase','status','evidence','next','url'],where)
        if item.get('name') in names: errors.append(f'{section}: duplicate name {item.get("name")}')
        names.add(item.get('name'))
        if item.get('url') and not valid_url(item['url']): errors.append(f'{where}: url must be https')

for i,item in enumerate(DATA.get('greece', [])):
    where=f'greece[{i}]'
    require(item,['date','kicker','title','status','evidence','summary','meaning','sourceQuality','sources'],where)
    try: date.fromisoformat(item.get('date',''))
    except Exception: errors.append(f'{where}: invalid date')
    if not isinstance(item.get('sources'),list) or not item.get('sources'):
        errors.append(f'{where}: at least one source required')
    else:
        for j,s in enumerate(item['sources']):
            require(s,['label','url'],f'{where}.sources[{j}]')
            if s.get('url') and not valid_url(s['url']): errors.append(f'{where}.sources[{j}]: url must be https')

joined=json.dumps(DATA,ensure_ascii=False).lower()
for phrase in ('θεραπεύει τη σκλήρυνση κατά πλάκας','αποδεδειγμένη επαναμυελίνωση στους ασθενείς','cures multiple sclerosis'):
    if phrase in joined: errors.append(f'potential clinical overclaim found: {phrase}')

if not DATA.get('greece'):
    errors.append('greece-first section must not be empty')

if errors:
    print('VALIDATION FAILED')
    for e in errors: print(f'- {e}')
    raise SystemExit(1)
print(f"Validation OK: {len(DATA.get('items',[]))} updates, {len(DATA.get('pipeline',[]))} human programmes, {len(DATA.get('translational',[]))} translational programmes, {len(DATA.get('greece',[]))} Greece-priority cards.")
