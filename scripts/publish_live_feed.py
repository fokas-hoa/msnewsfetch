#!/usr/bin/env python3
"""Final, fail-closed publication boundary for the zero-touch research feed.

Successful authoritative observations may update operational fields. Publications
and announcements never update a trial status or assert clinical effectiveness.
Feed, RSS and collector journal are committed atomically (see live_store.py).
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from research_contract import (POLICY_VERSION, FEED_VERSION, CTG_STATUSES, CTIS_STATUSES,
    REGISTRY_ID, fingerprint, https_url, now_iso, primary_registry_url, record_ids, validate_feed)
from program_identity import match_programme, review_confidence
from filter_discovery_report import issue_worthy

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / 'monitor'
API = 'https://api.github.com'
DATA_BRANCH = os.environ.get('MSNEWS_LIVE_BRANCH', 'live-data')
DATA_PATH = 'live-feed.json'
MAX_EVENTS = 250
MAX_PROGRAMMES = 1000
MAX_QUARANTINE = 100
REGISTRY_SOURCES = {'ClinicalTrials.gov', 'EU CTIS', 'ANZCTR', 'ISRCTN'}


def today():
    return datetime.now(timezone.utc).date().isoformat()


def stable_id(*parts):
    return fingerprint(list(parts))[:24]


def empty_feed():
    return {'version': FEED_VERSION, 'events': [], 'programmes': [], 'programme_overrides': {},
            'trial_overrides': {}, 'watch_targets': {}, 'quarantine': [], 'source_health': {}}


def api_request(url, token, *, method='GET', body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28',
                 'User-Agent': 'MSNewsFetch-live-publisher'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def stage_from_evidence(evidence, human_data=None, population=None):
    low = str(evidence or '').lower()
    if 'registration' in low:
        return 'Καταχώριση κλινικής δοκιμής'
    if 'preprint' in low:
        return 'Προδημοσίευση'
    if human_data is True or 'human trial' in low or 'human clinical' in low:
        return 'Ανθρώπινα δεδομένα'
    if 'preclinical' in low or 'cell' in low or 'animal' in low or population == 'preclinical_models':
        return 'Προκλινικό'
    if any(x in low for x in ('grant', 'programme', 'program', 'project', 'planned', 'announced')):
        return 'Μεταφραστικό'
    return 'Μη προσδιορισμένο επίπεδο'


def valid_provenance(proof, url):
    return bool(isinstance(proof, dict) and proof.get('verified') is True and proof.get('url') == url
                and https_url(url) and re.fullmatch(r'[0-9a-f]{64}', str(proof.get('fingerprint', '')))
                and isinstance(proof.get('fetched_at'), str) and len(proof['fetched_at']) >= 19)


def validated_candidate(raw):
    """Recompute identity and triage at the final boundary; don't trust stale scores.

    Discovery mirrors/news are retained in the journal but are not a primary fact.
    Their linked official URL alone cannot satisfy this gate. The next scan can
    discover/verify the corresponding primary record without human approval.
    """
    if not isinstance(raw, dict) or raw.get('policy_version') != POLICY_VERSION:
        return None
    if not raw.get('id') or not isinstance(raw.get('title'), str) or not raw['title'].strip():
        return None
    if not isinstance(raw.get('meta', {}), dict) or not isinstance(raw.get('human_data'), bool):
        return None
    if not all(isinstance(raw.get(k), str) for k in ('source', 'source_quality', 'evidence')):
        return None
    for key in ('phases', 'countries'):
        val = raw.get('meta', {}).get(key, [])
        if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
            return None
    if not valid_provenance(raw.get('source_record'), raw.get('url')):
        return None
    for key in ('repair_hits', 'translation_hits', 'model_hits'):
        if not isinstance(raw.get(key, []), list) or any(not isinstance(x, str) for x in raw.get(key, [])):
            return None
    if not raw.get('repair_hits') or not isinstance(raw.get('score'), int) or isinstance(raw.get('score'), bool):
        return None
    if raw.get('study_population') == 'secondary_literature':
        return None
    c = copy.deepcopy(raw)
    c.update(match_programme(c))
    c.update(review_confidence(c))
    if c['source_class'] in ('secondary_news', 'other'):
        return None
    if c['source_class'] == 'primary_registry':
        if not primary_registry_url(str(c['id']), c['url']) or c['source_record'].get('id', '').upper() != str(c['id']).upper():
            return None
        if c.get('study_population') != 'human_registered_trial':
            return None
        meta = c.get('meta') or {}
        if c['source'] == 'ClinicalTrials.gov' and meta.get('status') not in CTG_STATUSES:
            return None
        if c['source'] == 'EU CTIS' and meta.get('status') not in CTIS_STATUSES:
            return None
    if c.get('human_data') is True and c.get('study_population') not in (
            'human_registered_trial', 'human_study', 'mixed_human_and_preclinical'):
        return None
    return c if issue_worthy(c) else None


def valid_observation(s):
    if not isinstance(s, dict) or s.get('observation_valid') is not True:
        return False
    url = s.get('official_url') or s.get('url')
    if not valid_provenance(s.get('provenance'), url) or not primary_registry_url(str(s.get('id')), url):
        return False
    if str(s['provenance'].get('id', '')).upper() != str(s['id']).upper():
        return False
    status = s.get('status')
    if str(s['id']).startswith(('NCT', 'ACTRN', 'ISRCTN')):
        return status in CTG_STATUSES
    return status in CTIS_STATUSES and status == s.get('official_status')


def validated_change(c):
    if not isinstance(c, dict) or c.get('policy_version') != POLICY_VERSION or c.get('observation_valid') is not True:
        return False
    if not valid_provenance(c.get('provenance'), c.get('url')) or c.get('after') is None:
        return False
    if c.get('source') in REGISTRY_SOURCES:
        s = c.get('observation')
        if not valid_observation(s) or str(s['id']) not in c.get('record_ids', []):
            return False
        fields = {'status': 'status', 'temporary halt': 'temporary_halt', 'Greece sites': 'greece_sites',
                  'Greece site details': 'greece_locations', 'Greece mention': 'greece_mentioned',
                  'results posted': 'has_results', 'start date': 'start',
                  'primary completion': 'primary_completion', 'completion date': 'completion',
                  'primary outcomes': 'primary_outcomes', 'registry conflict': 'mirror_status'}
        key = fields.get(c.get('field'))
        return key is not None and s.get(key) is not None and c['after'] == s[key]
    # Literature and programme-page events are source observations, never operational overrides.
    host = urllib.parse.urlsplit(c['url']).hostname
    if c.get('source') == 'PubMed':
        return host == 'pubmed.ncbi.nlm.nih.gov' and c.get('field') == 'new paper'
    if c.get('source') == 'Official programme page' and c.get('field') == 'high-signal page text':
        watch = json.loads((MON / 'watchlist.json').read_text())
        return c['url'] in {x['url'] for x in watch.get('official_pages', [])}
    return False


def event_from_change(c, generated_at):
    field, program = str(c.get('field', 'update')), str(c.get('program', 'Research update'))
    observed = (c.get('provenance') or {}).get('fetched_at') or generated_at or now_iso()
    summary = f"{field}: {c.get('before')} → {c.get('after')}."
    if field == 'Greece site details':
        summary = 'Άλλαξαν στοιχεία ελληνικού κέντρου, τοπικής στρατολόγησης ή επικοινωνίας στο μητρώο.'
    elif field in ('new paper', 'high-signal page text'):
        summary = ('Εντοπίστηκε νέα βιβλιογραφική εγγραφή σχετική με την επιδιόρθωση της μυελίνης.' if field == 'new paper'
                   else 'Εντοπίστηκε μεταβολή σε επίσημη σελίδα ανάπτυξης προγράμματος. Πρόκειται για ανακοίνωση, όχι για αποτέλεσμα θεραπείας.')
    human = c.get('human_data', c.get('source') in REGISTRY_SOURCES)
    # Include before AND observation time: a later genuine return to an earlier
    # status is a different transition, but a retry of this report is idempotent.
    return {
        'id': stable_id('daily', c.get('trial_id'), c.get('url'), field, c.get('before'), c.get('after'), observed),
        'date': observed[:10], 'observed_at': observed,
        'source_date': (c.get('observation') or {}).get('source_updated_at'),
        'date_kind': 'detection_date', 'kind': 'registry-update' if c.get('source') in REGISTRY_SOURCES else 'research-update',
        'source': c.get('source', ''), 'sourceQuality': c.get('source_quality', ''),
        'evidence': c.get('evidence', 'Research observation'),
        'stage': stage_from_evidence(c.get('evidence'), human, c.get('study_population')),
        'signal': 'Ενημέρωση', 'title': f'{program} — {field}', 'summary': summary[:2000],
        'meaning': c.get('meaning') or 'Δεν αποτελεί απόδειξη κλινικού οφέλους.', 'url': c.get('url', ''),
        'tags': [program, c.get('source', '')], 'greece_priority': c.get('priority') == 'greece',
        'canonical_program': c.get('canonical_program_name') or program,
        'canonical_program_id': c.get('canonical_program_id'), 'record_ids': c.get('record_ids', []),
        'field': field, 'human_data': human,
        'study_population': c.get('study_population') or ('human_registered_trial' if human else 'not_established'),
        'publication_status': c.get('publication_status') or ('registration' if c.get('source') in REGISTRY_SOURCES else 'announcement'),
        'endpoint_classes': c.get('endpoint_classes', ['not_established']),
        'human_results_available': (c.get('observation') or {}).get('has_results') if c.get('source') in REGISTRY_SOURCES else None,
        'clinical_benefit_proven': False, 'provenance': c.get('provenance'), 'auto_published': True,
    }


def event_from_candidate(c, generated_at):
    evidence = c.get('evidence', 'Research discovery')
    observed = (c.get('source_record') or {}).get('fetched_at') or generated_at or now_iso()
    publication_date = (c.get('meta') or {}).get('pub_date') or (c.get('meta') or {}).get('date')
    return {
        'id': stable_id('weekly', c.get('source'), c.get('id'), c.get('_fingerprint') or (c.get('source_record') or {}).get('fingerprint') or c.get('title')),
        'date': observed[:10], 'observed_at': observed, 'source_date': publication_date, 'date_kind': 'detection_date',
        'kind': 'new-programme' if c.get('source_class') in ('primary_registry', 'official_funding_or_project') else 'new-research',
        'source': c.get('source', ''), 'sourceQuality': c.get('source_quality', ''), 'evidence': evidence,
        'stage': stage_from_evidence(evidence, c.get('human_data'), c.get('study_population')),
        'signal': 'Νέο εύρημα', 'title': c.get('title') or c.get('id'),
        'summary': f"Νέα ή μεταβληθείσα ερευνητική εγγραφή από {c.get('source')}. Επίπεδο: {evidence}.",
        'meaning': c.get('clinical_note') or 'Δεν αποτελεί απόδειξη κλινικού οφέλους.', 'url': c.get('url', ''),
        'tags': list(dict.fromkeys([str(x) for x in [c.get('canonical_program_name'), *(c.get('repair_hits') or [])] if x]))[:8],
        'greece_priority': bool(c.get('greece_priority')),
        'canonical_program': c.get('canonical_program_name'), 'canonical_program_id': c.get('canonical_program_id'),
        'record_ids': [str(c['id']).upper()] if REGISTRY_ID.fullmatch(str(c.get('id'))) else [],
        'confidence': c.get('review_confidence'), 'confidence_level': c.get('review_confidence_band'),
        'confidence_reasons': c.get('review_confidence_reasons', []),
        'human_data': c.get('human_data') is True, 'human_results_available': False if c.get('publication_status') == 'registration' else None, 'study_population': c.get('study_population', 'not_established'),
        'publication_status': c.get('publication_status', 'not_established'),
        'endpoint_classes': c.get('endpoint_classes', ['not_established']), 'clinical_benefit_proven': False,
        'provenance': c.get('source_record'), 'auto_published': True,
    }


def programme_from_candidate(c):
    from program_identity import source_class
    cls = c.get('source_class') or source_class(c.get('source', ''), c.get('source_quality', ''))[0]
    if cls not in ('primary_registry', 'official_funding_or_project'):
        return None
    meta = c.get('meta') or {}
    human = cls == 'primary_registry'
    if not (c.get('human_data') or c.get('translation_hits') or meta.get('grant')):
        return None
    rid = str(c.get('id', '')).upper() if human else None
    phases, countries = meta.get('phases') or [], meta.get('countries') or []
    canonical = c.get('canonical_program_id')
    return {
        'id': 'trial:' + rid if rid else 'programme:' + stable_id(c.get('source'), c.get('id')),
        'canonical_id': canonical, 'record_ids': [rid] if rid else [],
        'name': c.get('title') or c.get('canonical_program_name') or str(c.get('id')),
        'candidate': c.get('canonical_program_name') or c.get('source', ''),
        'phase': ', '.join(phases) if phases else ('Human trial registration' if human else 'Translational'),
        'status': meta.get('status') or ('Registered; status not established' if human else 'Funded programme; no registered trial established'),
        'operational_status': meta.get('status') if human else None,
        'geography': ', '.join(countries), 'evidence': c.get('evidence', ''),
        'nextLabel': 'Παρακολούθηση',
        'next': 'Αυτόματος έλεγχος της πρωτογενούς καταχώρισης. Η πρόσβαση και η επιλεξιμότητα απαιτούν επιβεβαίωση από το κέντρο.' if human else 'Αυτόματη επανεξέταση αλλαγών στην πηγή. Δεν τεκμηριώνεται έναρξη κλινικής δοκιμής.',
        'url': c.get('url'), 'human': human,
        'updated_at': (c.get('source_record') or {}).get('fetched_at') or now_iso(),
        'provenance': c.get('source_record'),
    }


def merge_by_id(existing, incoming, limit):
    merged = {str(x['id']): x for x in existing if isinstance(x, dict) and x.get('id')}
    for item in incoming:
        if item.get('id'):
            merged[str(item['id'])] = item
    return sorted(merged.values(), key=lambda x: (x.get('date') or x.get('updated_at') or '', x['id']), reverse=True)[:limit]


def quarantine_warnings(data, report, mode):
    generated = report.get('generated_at') or now_iso()
    warnings = [{'id': stable_id('quarantine', mode, w), 'updated_at': generated,
                 'mode': mode, 'reason': 'source/parser warning', 'detail': str(w)[:1000], 'published': False}
                for w in report.get('warnings', [])]
    data['quarantine'] = merge_by_id(data.get('quarantine', []), warnings, MAX_QUARANTINE)


def observation_override(s):
    """Never let null optional fields erase a last-good observation."""
    out = {'status': s['status'], 'operational_status': s['status'],
           'record_id': s['id'], 'updated_at': s['provenance']['fetched_at'],
           'source_updated_at': s.get('source_updated_at'), 'source': s.get('source'),
           'url': s.get('official_url') or s['url'], 'provenance': s['provenance']}
    out['field_observed_at'] = {'status': s['provenance']['fetched_at']}
    for key in ('greece_sites', 'greece_locations', 'countries', 'locations_complete', 'temporary_halt',
                'greece_mentioned', 'official_status', 'mirror_status', 'status_conflict',
                'has_results', 'start', 'primary_completion', 'completion'):
        if s.get(key) is not None:
            out[key] = s[key]
            out['field_observed_at'][key] = s['provenance']['fetched_at']
    return out


def apply_daily(data, report):
    data['version'] = FEED_VERSION
    generated = report.get('generated_at') or now_iso()
    changes = [c for c in report.get('substantive_changes', []) if validated_change(c)]
    events = [] if report.get('baseline') else [event_from_change(c, generated) for c in changes]
    data['events'] = merge_by_id(data.get('events', []), [e for e in events if e['id'] not in {x['id'] for x in data.get('events', [])}], MAX_EVENTS)
    overrides = data.setdefault('trial_overrides', {})
    snapshots = list(report.get('observations', [])) + [c['observation'] for c in changes if c.get('source') in REGISTRY_SOURCES]
    for s in snapshots:
        if not valid_observation(s):
            continue
        rid = s['id'].upper()
        entry = observation_override(s)
        prior = overrides.get(rid, {})
        if prior.get('updated_at', '') <= entry['updated_at']:
            entry['field_observed_at'] = {**prior.get('field_observed_at', {}), **entry['field_observed_at']}
            overrides[rid] = {**prior, **entry}
    # Name-keyed overrides kept only for backwards-readable diagnostics. Browser
    # projection deliberately uses trial_overrides and IDs, never these names.
    for c in changes:
        if c.get('source') in REGISTRY_SOURCES:
            rid = c.get('trial_id')
            if rid in overrides:
                data.setdefault('programme_overrides', {})[c['program']] = overrides[rid]
    data['source_health'] = report.get('source_health') or data.get('source_health', {})
    return changes


def apply_weekly(data, report):
    data['version'] = FEED_VERSION
    generated = report.get('generated_at') or now_iso()
    accepted = []; events = []; programmes = []
    for raw in report.get('candidates', []):
        c = validated_candidate(raw)
        if c is None:
            continue
        accepted.append(c)
        if report.get('baseline'):
            continue
        events.append(event_from_candidate(c, generated))
        programme = programme_from_candidate(c)
        if programme:
            programmes.append(programme)
            if programme['human'] and primary_registry_url(str(c['id']), c['url']):
                rid = str(c['id']).upper()
                data.setdefault('watch_targets', {})[rid] = {
                    'id': rid, 'name': programme['name'], 'url': c['url'], 'source': c['source'],
                    'verified': True, 'provenance': c['source_record'],
                }
                # Store the first verified record as a polling baseline. This
                # prevents losing a transition before the first daily adoption.
                data['watch_targets'][rid]['initial_snapshot'] = {
                    **(c.get('meta') or {}), 'id': rid, 'url': c['url'],
                    'status': (c.get('meta') or {}).get('status'), 'observation_valid': True,
                    'provenance': c['source_record'],
                }
    data['events'] = merge_by_id(data.get('events', []), [e for e in events if e['id'] not in {x['id'] for x in data.get('events', [])}], MAX_EVENTS)
    data['programmes'] = merge_by_id(data.get('programmes', []), programmes, MAX_PROGRAMMES)
    return accepted


def apply_report(data, report, mode):
    validate_feed(data)
    # Only the known empty pre-release v1 feed may migrate automatically.
    if data.get('version', 1) == 1 and any(data.get(k) for k in ('events', 'programmes', 'programme_overrides')):
        raise ValueError('Non-empty legacy feed requires explicit validated migration')
    data['version'] = FEED_VERSION
    before = fingerprint({k: data.get(k) for k in ('events', 'programmes', 'trial_overrides')})
    accepted = apply_daily(data, report) if mode == 'daily' else apply_weekly(data, report)
    quarantine_warnings(data, report, mode)
    if before != fingerprint({k: data.get(k) for k in ('events', 'programmes', 'trial_overrides')}):
        data['updated_at'] = report.get('generated_at') or now_iso()
    # Scientific news freshness is different from polling/technical freshness.
    data['latest_event_at'] = max((e.get('observed_at', '') for e in data.get('events', [])), default=None)
    validate_feed(data)
    return accepted


def main():
    mode = os.environ.get('MSNEWS_PUBLISH_MODE', 'daily')
    if mode not in ('daily', 'weekly'):
        raise SystemExit('Invalid publishing mode')
    # A workflow dispatched on a development/audit ref must never write production data.
    if os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Production publication is allowed only from main; use offline tests on other refs')
    report_path = MON / ('report.json' if mode == 'daily' else 'discovery_report.json')
    state_path = MON / ('state.json' if mode == 'daily' else 'discovery_state.json')
    report = json.loads(report_path.read_text())
    if report.get('policy_version') != POLICY_VERSION:
        raise SystemExit('Missing/current-policy mismatch on report')
    state = json.loads(state_path.read_text())
    from live_store import publish_transaction
    result = publish_transaction(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'], mode, report, state)
    print('Atomic live-data transaction:', result or 'no changes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
