"""Small, shared contracts. Unknown is never False and a registry record is not a result.

Policy changes intentionally cause retained discovery candidates to be reassessed.
This is a deterministic publication policy, not an estimate of treatment efficacy.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs

POLICY_VERSION = '2026-09-17.2'
FEED_VERSION = 2
CTG_STATUSES = {
    'NOT_YET_RECRUITING', 'RECRUITING', 'ENROLLING_BY_INVITATION',
    'ACTIVE_NOT_RECRUITING', 'SUSPENDED', 'TERMINATED', 'COMPLETED',
    'WITHDRAWN', 'UNKNOWN', 'AVAILABLE', 'NO_LONGER_AVAILABLE',
    'TEMPORARILY_NOT_AVAILABLE', 'APPROVED_FOR_MARKETING',
}
CTIS_STATUSES = {
    'Temporarily halted', 'Ongoing, recruiting', 'Ongoing, not recruiting',
    'Ended', 'Early terminated', 'Authorised', 'Not authorised',
}
REGISTRY_ID = re.compile(r'^(NCT\d{8}|20\d{2}-\d{6}-\d{2}-\d{2}|ACTRN\d{14}[A-Z]?|ISRCTN\d{8})$', re.I)
REGISTRY_FIND = re.compile(r'\b(?:NCT\d{8}|20\d{2}-\d{6}-\d{2}-\d{2}|ACTRN\d{14}[A-Z]?|ISRCTN\d{8})\b', re.I)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def https_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def record_ids(value):
    return sorted({x.upper() for x in REGISTRY_FIND.findall(str(value or ''))})


def primary_registry_url(identifier, url):
    """Check an identity against the real host/path; a linked official URL isn't verification."""
    if not REGISTRY_ID.fullmatch(str(identifier)) or not https_url(url):
        return False
    host = (urlsplit(url).hostname or '').lower()
    identifier = identifier.upper()
    hosts = ('clinicaltrials.gov',) if identifier.startswith('NCT') else (
        ('www.anzctr.org.au', 'anzctr.org.au') if identifier.startswith('ACTRN') else (
            ('www.isrctn.com', 'isrctn.com') if identifier.startswith('ISRCTN') else ('euclinicaltrials.eu',)
        )
    )
    if host not in hosts:
        return False
    parsed = urlsplit(url)
    if identifier.startswith('NCT'):
        return parsed.path.rstrip('/').upper() == '/STUDY/' + identifier
    if identifier.startswith('ISRCTN'):
        return parsed.path.rstrip('/').upper() == '/' + identifier
    if identifier.startswith('ACTRN'):
        params = {k.upper(): [v.upper() for v in values] for k, values in parse_qs(parsed.query).items()}
        return parsed.path.lower().endswith('/trial/registration/trialreview.aspx') and params.get('ACTRN') == [identifier]
    return parsed.path.rstrip('/').upper() == '/CTIS-PUBLIC/VIEW/' + identifier


def source_record(identifier, url, material, *, verified=True):
    """Called only after successful parsing by a collector, never by the final gate."""
    return {'id': str(identifier), 'url': url, 'fetched_at': now_iso(),
            'fingerprint': fingerprint(material), 'verified': bool(verified)}


def evidence_context(text, pubtypes=(), *, registered=False, preprint=False, grant=False):
    """Conservative human-context classification; 'patient-derived' is a cell model.

    A positive human flag requires an explicit study design or participation signal,
    not the word 'patient' or a preprint-server name. Ambiguity remains unknown.
    """
    low = re.sub(r'<[^>]+>', ' ', str(text or '')).lower()
    types = ' '.join(pubtypes).lower()
    model = bool(re.search(r'\b(mice|mouse|murine|rats?|in vitro|organoids?|cuprizone|eae)\b|patient[- ]derived|cell cultur|oligodendrocytes? derived', low))
    clinical_type = any(t in types for t in ('clinical trial', 'randomized controlled trial', 'observational study'))
    participation = bool(re.search(
        r'\b(?:enrolled|recruited|randomi[sz]ed|treated|evaluated|followed|assessed)\s+(?:a total of\s+)?\d+\s+(?:adult\s+)?(?:patients|participants|people)\b|'
        r'\b\d+\s+(?:patients|participants)\s+(?:were\s+)?(?:enrolled|recruited|randomi[sz]ed|treated|evaluated)\b', low))
    secondary = any(x in types for x in ('review', 'editorial', 'comment'))
    human = bool(registered or (not secondary and (clinical_type or participation)))
    population = 'human_registered_trial' if registered else ('mixed_human_and_preclinical' if human and model else (
        'human_study' if human else ('secondary_literature' if secondary else ('preclinical_models' if model else ('translational_programme' if grant else 'not_established')))))
    endpoints = []
    if re.search(r'\b(vep|mtr|mri|pet|myelin water|biomarker|latency|magnetization transfer)\b', low):
        endpoints.append('imaging_or_biomarker')
    if re.search(r'\b(edss|disability|walking|quality of life|relapse)\b', low):
        endpoints.append('clinical_endpoint_mentioned')
    return {'human_data': human, 'study_population': population,
            'publication_status': 'preprint' if preprint else ('registration' if registered else ('funding_or_announcement' if grant else 'indexed_publication')),
            'endpoint_classes': endpoints or ['not_established'], 'clinical_benefit_proven': False}


def validate_feed(data):
    if not isinstance(data, dict) or data.get('version', 1) not in (1, FEED_VERSION):
        raise ValueError('Unsupported live-feed schema')
    for name in ('events', 'programmes', 'quarantine'):
        if name in data and not isinstance(data[name], list):
            raise ValueError(f'{name} must be a list')
    for name in ('programme_overrides', 'trial_overrides', 'watch_targets', 'source_health'):
        if name in data and not isinstance(data[name], dict):
            raise ValueError(f'{name} must be an object')
    for rid, o in data.get('trial_overrides', {}).items():
        if (not isinstance(o, dict) or o.get('record_id') != rid or not primary_registry_url(rid, o.get('url'))
                or o.get('status') not in CTG_STATUSES | CTIS_STATUSES):
            raise ValueError('Malformed trial observation')
        proof = o.get('provenance')
        if not isinstance(proof, dict) or proof.get('verified') is not True or proof.get('url') != o.get('url'):
            raise ValueError('Unverified trial observation')
        if 'greece_locations' in o and (not isinstance(o['greece_locations'], list) or any(not isinstance(x, dict) for x in o['greece_locations'])):
            raise ValueError('Malformed Greek locations')
        if 'countries' in o and (not isinstance(o['countries'], list) or any(not isinstance(x, str) for x in o['countries'])):
            raise ValueError('Malformed country list')
    for rid, target in data.get('watch_targets', {}).items():
        if not isinstance(target, dict) or target.get('id') != rid or target.get('verified') is not True or not primary_registry_url(rid, target.get('url')):
            raise ValueError('Malformed polling target')
    if len(data.get('events', [])) > 1000 or len(data.get('programmes', [])) > 2000:
        raise ValueError('Live feed exceeds item bound')
    for x in data.get('events', []):
        if not isinstance(x, dict) or not x.get('id') or not isinstance(x.get('title'), str) or not https_url(x.get('url')):
            raise ValueError('Malformed live event')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(x.get('date', ''))):
            raise ValueError('Malformed event date')
        if not all(isinstance(x.get(k), str) for k in ('summary', 'meaning', 'stage', 'evidence', 'sourceQuality', 'source')):
            raise ValueError('Malformed event metadata')
        if not isinstance(x.get('tags', []), list) or any(not isinstance(t,str) for t in x.get('tags',[])):
            raise ValueError('Malformed live tags')
    for x in data.get('programmes', []):
        if not isinstance(x, dict) or not x.get('id') or not isinstance(x.get('name'), str) or not https_url(x.get('url')):
            raise ValueError('Malformed live programme')
    return data
