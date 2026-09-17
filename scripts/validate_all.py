#!/usr/bin/env python3
"""Single offline release gate shared by GitHub CI and the Netlify build."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    python_tests=['validate_site.py','test_program_identity.py','test_discovery_policy.py',
                  'test_live_feed.py','test_release_review.py','test_hardening.py']
    commands=[[sys.executable,'scripts/'+name] for name in python_tests]
    commands += [[sys.executable,'scripts/build_rss.py','--check'],['node','--check','app.js'],
                 ['node','scripts/test_netlify_ignore.js'],['node','scripts/test_browser_contract.js']]
    for command in commands:
        print('+',' '.join(command),flush=True)
        subprocess.run(command,cwd=ROOT,check=True,timeout=90)
    print('Release gate: all offline suites passed.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
