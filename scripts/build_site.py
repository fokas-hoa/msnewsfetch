#!/usr/bin/env python3
"""Test first; publish only a small static allowlist, never journals or test data."""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=('index.html','app.js','styles.css','favicon.svg','robots.txt','news.json','rss.xml')


def main():
    for script in ('restore_data.py','build_rss.py','validate_all.py'):
        subprocess.run([sys.executable,'scripts/'+script],cwd=ROOT,check=True,timeout=180)
    dest=ROOT/'dist'
    if dest.exists():shutil.rmtree(dest)
    dest.mkdir()
    for name in PUBLIC:shutil.copyfile(ROOT/name,dest/name)
    html=(dest/'index.html').read_text()
    for name in ('app.js','styles.css'):
        digest=hashlib.sha256((dest/name).read_bytes()).hexdigest()[:16]
        html=re.sub(r'(/'+re.escape(name)+r')(?:\?[^"\s]*)?(?=")', r'\1?v='+digest,html)
    (dest/'index.html').write_text(html)
    print('Validated static output: dist/ (7 allowlisted files).')
    return 0

if __name__=='__main__':raise SystemExit(main())
