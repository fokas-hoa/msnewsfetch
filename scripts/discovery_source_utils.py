#!/usr/bin/env python3
"""Durable discovery journal: seen != published; changed/rejected entries are retryable.

The live-data transaction commits this journal only together with its public output.
An upstream failure cannot acknowledge or permanently swallow a candidate.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from research_contract import POLICY_VERSION, fingerprint, now_iso

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / 'monitor' / 'discovery_state.json'
REPORT_PATH = ROOT / 'monitor' / 'discovery_report.json'


def content_fingerprint(candidate):
    c = copy.deepcopy(candidate)
    for name in ('_record_key', '_fingerprint', 'first_seen', 'last_seen', 'policy_version',
                 '_material_change', 'review_confidence', 'review_confidence_band', 'review_confidence_reasons', 'source_class'):
        c.pop(name, None)
    if isinstance(c.get('source_record'), dict):
        c['source_record'].pop('fetched_at', None)
    return fingerprint(c)


def collect_source(state, source, candidates, *, healthy=True):
    """Observe all candidates, return those due for assessment/publication.

    New source baselines are silent. A legacy seen-ID gets an initial fingerprint
    silently once; rejected/pending records remain eligible, and changed content or
    policy can be reconsidered. No record is marked published by this function.
    """
    seen = state.setdefault('seen', {})
    records = state.setdefault('records', {})
    had_baseline = source in seen
    old_keys = set(seen.get(source, []))
    out = []
    unique = {f"{c['source']}::{c['id']}": c for c in candidates}
    for key, candidate in unique.items():
        fp = content_fingerprint(candidate)
        prior = records.get(key)
        silent = (not had_baseline) or (prior is None and key in old_keys)
        changed = prior is not None and (prior.get('fingerprint') != fp or prior.get('policy_version') != POLICY_VERSION)
        disposition = (prior or {}).get('disposition', 'pending')
        ready = not silent and (prior is None or changed or disposition in ('pending', 'rejected', 'quarantined'))
        c = copy.deepcopy(candidate)
        c.update(_record_key=key, _fingerprint=fp)
        if ready and c.get('identity_status') == 'known_program_mention':
            c['_material_change'] = True
        records[key] = {
            'fingerprint': fp, 'policy_version': POLICY_VERSION,
            'disposition': 'baseline' if silent else ('pending' if ready else disposition),
            'candidate': c, 'last_seen': now_iso(),
            'first_seen': (prior or {}).get('first_seen', now_iso()),
        }
        if ready:
            out.append(c)
    # A completely failed first query is NOT a successful empty baseline.
    if healthy or candidates:
        seen[source] = sorted(old_keys | set(unique))
    state['version'] = 2
    state['policy_version'] = POLICY_VERSION
    state['updated_at'] = now_iso()
    return out


def set_disposition(state, candidate, disposition, reason=None):
    key = candidate.get('_record_key') or f"{candidate.get('source')}::{candidate.get('id')}"
    if key not in state.get('records', {}):
        return
    record = state['records'][key]
    record['disposition'] = disposition
    record['policy_version'] = POLICY_VERSION
    if reason:
        record['reason'] = reason


def load():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {'version': 2, 'seen': {}, 'records': {}}
    report = json.loads(REPORT_PATH.read_text()) if REPORT_PATH.exists() else {
        'baseline': True, 'warnings': [], 'candidates': [], 'source_candidate_counts': {}, 'policy_version': POLICY_VERSION}
    return state, report


def merge_source(source_key, candidates, warnings):
    state, report = load()
    had_source = source_key in state.get('seen', {})
    new = collect_source(state, source_key, candidates, healthy=not warnings)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
    report.setdefault('source_candidate_counts', {})[source_key] = len(candidates)
    merged = {f"{c['source']}::{c['id']}": c for c in report.get('candidates', [])}
    merged.update({f"{c['source']}::{c['id']}": c for c in new})
    report['candidates'] = list(merged.values())
    report['candidate_count'] = len(merged)
    report.setdefault('warnings', []).extend(w for w in warnings if w not in report['warnings'])
    report.setdefault('source_baselines', {})[source_key] = {'was_previously_baselined': had_source, 'new_candidate_count': len(new)}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return {'source': source_key, 'baseline_created': not had_source and not warnings,
            'candidates': len(candidates), 'new': len(new), 'warnings': len(warnings)}
