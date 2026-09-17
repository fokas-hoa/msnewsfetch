#!/usr/bin/env python3
"""Bounded read-only live source smoke. No publisher, issue, merge or feed write."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    import deep_discovery as dd
    from publish_live_feed import valid_observation, validated_candidate
    subprocess.run([sys.executable,'scripts/monitor_research.py'],check=True,cwd=ROOT,timeout=1100)
    report=json.loads((ROOT/'monitor/report.json').read_text())
    observations=report.get('observations',[])
    valid=[o for o in observations if valid_observation(o)]
    if not any(str(o.get('id','')).startswith('NCT') for o in valid):
        raise RuntimeError('Live-source smoke has no successfully validated NCT observation')
    warnings=[]
    dd.CONFIG['clinicaltrials_queries']=dd.CONFIG['clinicaltrials_queries'][:1]
    dd.CONFIG['europepmc_queries']=dd.CONFIG['europepmc_queries'][:1]
    candidates=dd.scan_clinicaltrials(warnings)+dd.scan_europepmc(warnings)
    eligible=[c for c in candidates if validated_candidate(c)]
    result={'mode':'READ_ONLY_NO_PUBLICATION','observations':len(observations),
            'validated_observations':len(valid),'source_health':report.get('source_health',{}),
            'daily_warnings':report.get('warnings',[]),'sampled_discovery_candidates':len(candidates),
            'sampled_gate_eligible_candidates':len(eligible),'discovery_warnings':warnings,
            'note':'Partial coverage is visible. Source failure is NOT a negative trial-status observation. This is not an exhaustive science audit.'}
    (ROOT/'source-health-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
