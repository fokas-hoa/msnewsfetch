"""Atomic live-data store using Git trees/commits and non-force ref updates.

Collector journal + JSON feed + RSS are one transaction. A failed push does not
acknowledge an observation. An optimistic race reloads/remerges; same-mode journal
races fail closed, because a stale collector cannot replace a newer baseline.
"""
from __future__ import annotations
import base64
import copy
import json
import os
import time
import urllib.error
import urllib.parse
from pathlib import Path
from research_contract import fingerprint, validate_feed, POLICY_VERSION
from publish_live_feed import api_request, apply_report, empty_feed, DATA_BRANCH, ROOT

API = 'https://api.github.com'
JOURNALS = {'daily': 'monitor-state.json', 'weekly': 'discovery-state.json'}


def json_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)+'\n'


def read_json_at(repo, token, commit, path, *, absent=None):
    url = f'{API}/repos/{repo}/contents/{path}?ref={urllib.parse.quote(commit, safe="")}'
    try:
        obj = api_request(url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return absent
        raise
    if obj.get('encoding') == 'none' and obj.get('sha'):
        obj = api_request(f'{API}/repos/{repo}/git/blobs/{obj["sha"]}', token)
    if obj.get('encoding') != 'base64':
        raise ValueError('Missing GitHub file payload; refusing to reset data')
    raw = base64.b64decode(obj['content'])
    if len(raw) > 25_000_000:
        raise ValueError('Journal exceeds safety size bound')
    return json.loads(raw.decode('utf-8'))


def read_bundle(repo, token):
    ref = api_request(f'{API}/repos/{repo}/git/ref/heads/{DATA_BRANCH}', token)
    sha = ref['object']['sha']
    commit = api_request(f'{API}/repos/{repo}/git/commits/{sha}', token)
    data = read_json_at(repo, token, sha, 'live-feed.json', absent=None)
    if data is None:
        raise ValueError('Live feed missing; refusing implicit replacement')
    validate_feed(data)
    return {'sha': sha, 'tree': commit['tree']['sha'], 'feed': data}


def rss_for_feed(feed):
    from build_rss import build
    baseline = json.loads((ROOT / 'news.json').read_text())
    records = {x['id']: x for x in baseline.get('items', [])}
    records.update({x['id']: x for x in feed.get('events', [])})
    baseline['items'] = list(records.values())
    return build(baseline)


def publish_transaction(repo, token, mode, report, state, *, attempts=4, sleeper=time.sleep):
    from discovery_source_utils import set_disposition
    journal_path = JOURNALS[mode]
    expected = state.get('_journal_base')
    output_result = None
    for attempt in range(attempts):
        bundle = read_bundle(repo, token)
        remote_state = read_json_at(repo, token, bundle['sha'], journal_path, absent=None)
        actual = fingerprint(remote_state) if remote_state is not None else None
        if actual != expected:
            raise RuntimeError('Same-mode journal advanced or restore missing: rerun collection, do not overwrite newer state')
        data = copy.deepcopy(bundle['feed'])
        previous_events = {x['id'] for x in data.get('events', [])}
        accepted = apply_report(data, report, mode)
        journal = copy.deepcopy(state); journal.pop('_journal_base', None)
        if mode == 'weekly':
            for c in report.get('candidates', []):
                set_disposition(journal, c, 'quarantined', 'Final-boundary policy or source validation failed')
            for c in accepted:
                set_disposition(journal, c, 'baseline' if report.get('baseline') else 'published')
        rss = rss_for_feed(data)
        files = {'live-feed.json': json_text(data), journal_path: json_text(journal), 'rss.xml': rss}
        tree = api_request(f'{API}/repos/{repo}/git/trees', token, method='POST', body={
            'base_tree': bundle['tree'], 'tree': [
                {'path': path, 'mode': '100644', 'type': 'blob', 'content': text}
                for path, text in files.items()]})
        if tree['sha'] == bundle['tree']:
            return None
        commit = api_request(f'{API}/repos/{repo}/git/commits', token, method='POST', body={
            'message': f'Update {mode} research observations and durable journal',
            'tree': tree['sha'], 'parents': [bundle['sha']]})
        try:
            api_request(f'{API}/repos/{repo}/git/refs/heads/{DATA_BRANCH}', token, method='PATCH',
                        body={'sha': commit['sha'], 'force': False})
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == attempts-1:
                raise
            sleeper(min(attempt+1, 3))
            continue
        new_events = [e for e in data.get('events', []) if e['id'] not in previous_events]
        output_result = {'commit': commit['sha'], 'published_event_count': len(new_events),
                         'events': new_events, 'accepted_candidates': accepted if mode == 'weekly' else [],
                         'policy_version': POLICY_VERSION}
        (ROOT / 'monitor' / 'publication_result.json').write_text(json_text(output_result))
        return commit['sha']
    raise RuntimeError('Live-data transaction did not complete')


def restore(mode):
    """Restore both journal and adoption targets at ONE pinned commit.

    Legacy artifacts are a one-time migration only; unavailable/invalid journal
    reads fail the run instead of silently pretending there is no prior state.
    """
    repo, token = os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_TOKEN')
    if not repo or not token:
        raise RuntimeError('State restore requires authenticated GitHub runtime context')
    bundle = read_bundle(repo, token)
    state = read_json_at(repo, token, bundle['sha'], JOURNALS[mode], absent=None)
    dest = ROOT / 'monitor' / ('state.json' if mode == 'daily' else 'discovery_state.json')
    if state is None:
        from restore_legacy_state import restore_legacy
        state = restore_legacy(repo, token, mode)
    else:
        if not isinstance(state, dict) or not isinstance(state.get('version'), int):
            raise ValueError('Invalid durable journal')
    if state is not None:
        remote_state = read_json_at(repo, token, bundle['sha'], JOURNALS[mode], absent=None)
        state['_journal_base'] = fingerprint(remote_state) if remote_state is not None else None
        dest.write_text(json_text(state))
    targets = bundle['feed'].get('watch_targets', {})
    (ROOT / 'monitor' / 'adopted_targets.json').write_text(json_text(targets))
    print(f'Restored {mode} journal/adoption targets from live-data commit {bundle["sha"]}')
    return 0
