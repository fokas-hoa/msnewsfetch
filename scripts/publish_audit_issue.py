"""Best-effort notification only for successfully published substantive events.
The journal/feed transaction is authoritative; issues are not approval gates.
"""
import json
import os
import urllib.parse
from pathlib import Path
from research_contract import fingerprint
from publish_live_feed import api_request

ROOT=Path(__file__).resolve().parents[1]


def main():
    result_path=ROOT/'monitor'/'publication_result.json'
    if not result_path.exists():
        print('No publication result; no notification.');return 0
    result=json.loads(result_path.read_text())
    events=result.get('events',[])
    if not events:
        print('No newly published substantive events; no notification.');return 0
    token=os.environ['GITHUB_TOKEN'];repo=os.environ['GITHUB_REPOSITORY']
    fp=fingerprint(sorted(x['id'] for x in events))[:20]
    title=f'MS research update [{fp}]'
    query=urllib.parse.quote(f'repo:{repo} in:title {fp}')
    existing=api_request(f'https://api.github.com/search/issues?q={query}',token)
    if existing.get('total_count',0):return 0
    lines=['## Automatic publication audit', '',
           'The entries below passed the publication policy and were committed to live-data. No manual approval is required.',
           'Registration, biomarkers, imaging, animal/cell experiments and preprints are not proof of clinical benefit.', '']
    for e in sorted(events,key=lambda x:not x.get('greece_priority')):
        lines += [f"### {e['title']}",f"- Source: {e['url']}",f"- Quality: {e.get('sourceQuality')}",
                  f"- Evidence: {e.get('evidence')}; population: {e.get('study_population')}; publication: {e.get('publication_status')}",
                  f"- Observation: {e['summary']}",f"- Clinical meaning: {e['meaning']}",
                  f"- Detected: {e.get('observed_at')}; source date: {e.get('source_date') or 'not established'}"]
        if e.get('confidence') is not None:
            lines += [f"- Triage score (not efficacy probability): {e['confidence']}",
                      '- Rationale: '+ '; '.join(e.get('confidence_reasons',[]))]
        lines += ['']
    # GitHub issue bodies have a length limit; never let audit formatting block data publication.
    body='\n'.join(lines)[:60000]
    api_request(f'https://api.github.com/repos/{repo}/issues',token,method='POST',body={'title':title,'body':body})
    return 0

if __name__=='__main__':raise SystemExit(main())
