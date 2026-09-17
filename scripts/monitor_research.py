#!/usr/bin/env python3
"""Deterministic watcher for high-signal MS remyelination/myelin-repair developments.

It never edits the public site. It creates a review report only for substantive registry,
regulatory/page, or strongly relevant literature changes. First run establishes baseline.
"""
from __future__ import annotations
import copy, hashlib, html, json, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from research_contract import (POLICY_VERSION, CTG_STATUSES, source_record, record_ids,
                               primary_registry_url, evidence_context, now_iso)
from program_identity import match_programme

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / 'monitor'
WATCH = json.loads((MON / 'watchlist.json').read_text(encoding='utf-8'))
STATE_PATH = MON / 'state.json'
REPORT_PATH = MON / 'report.json'
UA = 'MSNewsFetch/1.0 (+https://github.com/fokas-hoa/msnewsfetch)'

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self, data):
        x=' '.join(data.split())
        if x: self.parts.append(x)
    def text(self): return ' '.join(self.parts)


def fetch(url: str, accept='*/*') -> bytes:
    req=urllib.request.Request(url, headers={'User-Agent':UA,'Accept':accept})
    with urllib.request.urlopen(req, timeout=40) as r: return r.read()

def fetch_json(url: str): return json.loads(fetch(url,'application/json').decode('utf-8'))

def clean_text(raw: bytes) -> str:
    p=TextParser(); p.feed(raw.decode('utf-8','replace'))
    return re.sub(r'\s+',' ',html.unescape(p.text())).strip()

def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def load_state():
    if not STATE_PATH.exists(): return {'version':1,'clinicaltrials':{},'ctis':{},'pages':{},'pubmed_ids':[]}
    return json.loads(STATE_PATH.read_text(encoding='utf-8'))

def save_state(state):
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def ctg_snapshot(nct: str):
    data = fetch_json(f'https://clinicaltrials.gov/api/v2/studies/{nct}')
    p = data.get('protocolSection', {})
    ident = p.get('identificationModule', {})
    status = p.get('statusModule', {})
    design = p.get('designModule', {})
    contacts = p.get('contactsLocationsModule', {})
    outcomes = p.get('outcomesModule', {})
    # An HTTP 200 with an error/empty/other study payload is not a good observation.
    if ident.get('nctId', '').upper() != nct.upper() or status.get('overallStatus') not in CTG_STATUSES:
        raise ValueError('Missing/mismatched registry ID or unsupported status')
    locations = contacts.get('locations')
    if locations is not None and not isinstance(locations, list):
        raise ValueError('Malformed locations')
    countries = sorted({x.get('country') for x in (locations or []) if x.get('country')}) if locations is not None else None
    greek = None
    if locations is not None:
        greek = []
        for x in locations:
            if (x.get('country') or '').lower() != 'greece':
                continue
            site = {k: x.get(k) for k in ('facility', 'city', 'zip', 'status')}
            site['id'] = digest({k: site[k] for k in ('facility', 'city', 'zip')})[:20]
            site['contacts'] = sorted(
                [{k: y.get(k) for k in ('name', 'role', 'email', 'phone')} for y in x.get('contacts', [])],
                key=lambda y: str(y.get('name')))
            greek.append(site)
        greek.sort(key=lambda x: x['id'])
    primary = outcomes.get('primaryOutcomes')
    if primary is not None and not isinstance(primary, list):
        raise ValueError('Malformed primary outcomes')
    url = f'https://clinicaltrials.gov/study/{nct}'
    snapshot = {
        'id': nct.upper(), 'title': ident.get('briefTitle') or ident.get('officialTitle') or nct,
        'status': status['overallStatus'],
        'start': (status.get('startDateStruct') or {}).get('date'),
        'primary_completion': (status.get('primaryCompletionDateStruct') or {}).get('date'),
        'completion': (status.get('completionDateStruct') or {}).get('date'),
        'enrollment': (design.get('enrollmentInfo') or {}).get('count'),
        'enrollment_type': (design.get('enrollmentInfo') or {}).get('type'),
        'phases': design.get('phases') or [], 'countries': countries,
        'greece_sites': len(greek) if greek is not None else None,
        'greece_locations': greek, 'locations_complete': locations is not None,
        'primary_outcomes': primary,
        'has_results': bool(data.get('hasResults') or data.get('resultsSection')),
        'source_updated_at': (status.get('lastUpdatePostDateStruct') or {}).get('date'),
        'url': url, 'observation_valid': True,
    }
    snapshot['provenance'] = source_record(nct, url, snapshot)
    return snapshot

def date_shift_days(a,b):
    def parse(x):
        if not x:return None
        for fmt in ('%Y-%m-%d','%Y-%m','%Y'):
            try:return datetime.strptime(x,fmt)
            except ValueError:pass
        return None
    da,db=parse(a),parse(b)
    return abs((db-da).days) if da and db else 0

def compare_ctg(name, old, new):
    if not old or new.get('observation_valid') is not True:
        return []
    out = []
    def add(field, before, after, meaning, priority='normal'):
        out.append(change(name, 'ClinicalTrials.gov', 'Human trial registration', 'Primary registry',
                          field, before, after, new['url'], meaning, priority,
                          observation=new))
    if old.get('status') and new.get('status') and old['status'] != new['status']:
        add('status', old['status'], new['status'], 'Registry operational status changed; no efficacy conclusion follows.')
    if old.get('greece_sites') is not None and new.get('greece_sites') is not None and old['greece_sites'] != new['greece_sites']:
        add('Greece sites', old['greece_sites'], new['greece_sites'],
            'The number of listed Greek centres changed. Listing is not proof of open recruitment.', 'greece')
    if old.get('greece_locations') is not None and new.get('greece_locations') is not None and old['greece_locations'] != new['greece_locations']:
        add('Greece site details', old['greece_locations'], new['greece_locations'],
            'A listed Greek centre or its local recruitment/contact information changed. Verify eligibility with the centre.', 'greece')
    if old.get('has_results') is False and new.get('has_results') is True:
        add('results posted', False, True, 'A registry results section is available; its presence does not establish clinical benefit.')
    for key, label in [('start', 'start date'), ('primary_completion', 'primary completion'), ('completion', 'completion date')]:
        if old.get(key) != new.get(key) and date_shift_days(old.get(key), new.get(key)) >= 60:
            add(label, old.get(key), new.get(key), 'A schedule estimate changed by at least 60 days; no efficacy inference is made.')
    # Migrating legacy list-of-strings to structured outcomes is not a protocol amendment.
    before, after = old.get('primary_outcomes'), new.get('primary_outcomes')
    if before is not None and after is not None and before != after:
        if not (any(isinstance(x, str) for x in before) and [x.get('measure', '') for x in after] == before):
            add('primary outcomes', before, after, 'Registry primary-outcome fields changed; this is not a finding of benefit.')
    return out

def change(program, source, evidence, quality, field, before, after, url, meaning, priority='normal', *, observation=None):
    ids = record_ids(url)
    ident = match_programme({'source': source, 'id': ids[0] if ids else '', 'title': program, 'url': url})
    c = {'program': program, 'source': source, 'evidence': evidence, 'source_quality': quality,
         'field': field, 'before': before, 'after': after, 'url': url, 'meaning': meaning,
         'priority': priority, 'policy_version': POLICY_VERSION, **ident,
         'record_ids': ids, 'trial_id': ids[0] if len(ids) == 1 else None}
    # Callers must supply an actually parsed observation for publication. The low-
    # level change builder alone is intentionally not a source-verification oracle.
    if observation is not None:
        c['observation_valid'] = observation.get('observation_valid') is True
        c['provenance'] = observation.get('provenance')
        c['observation'] = observation
    return c

CTIS_STATUSES=['Temporarily halted','Ongoing, recruiting','Ongoing, not recruiting','Ended','Early terminated','Authorised','Not authorised']

def parse_status(text):
    # Accept one unambiguous current label, not the first status word in a history,
    # status dropdown or a JavaScript application shell. Missing is unknown.
    found = {s for s in CTIS_STATUSES if re.search(r'\b' + re.escape(s) + r'\b', text, re.I)}
    # 'Authorised' must not be selected from inside 'Not authorised'.
    if 'Not authorised' in found:
        found.discard('Authorised')
    labelled = re.findall(r'(?:Current trial status|Trial status|Overall trial status)\s*[:\-]?\s*([^|;]{1,100})', text, re.I)
    if labelled:
        values = {s for value in labelled for s in CTIS_STATUSES if value.lower().startswith(s.lower())}
        if 'Not authorised' in values:
            values.discard('Authorised')
        return next(iter(values)) if len(values) == 1 else None
    return next(iter(found)) if len(found) == 1 else None

def ctis_snapshot(euct: str):
    official = f'https://euclinicaltrials.eu/ctis-public/view/{euct}?lang=en'
    mirror = f'https://ctis.eu/trial/{euct}'
    observations = {}; errors = []
    for label, url in [('official', official), ('mirror', mirror)]:
        try:
            text = clean_text(fetch(url))
            status = parse_status(text)
            observations[label] = {'status': status, 'greece_mentioned': True if re.search(r'\bGreece\b', text) else None,
                                   'provenance': source_record(euct, url, text, verified=label == 'official' and status is not None)}
            if status is None:
                errors.append(label + ':no unambiguous current status (possibly a JS shell)')
        except Exception as e:
            observations[label] = {'status': None, 'greece_mentioned': None}
            errors.append(label + ':' + type(e).__name__)
    o, m = observations['official'], observations['mirror']
    os, ms = o['status'], m['status']
    return {'id': euct, 'status': os, 'official_status': os, 'mirror_status': ms,
            'status_conflict': None if not (os and ms) else os.lower() != ms.lower(),
            'greece_mentioned': o['greece_mentioned'],
            'temporary_halt': None if os is None else os == 'Temporarily halted',
            'official_url': official, 'mirror_url': mirror, 'url': official,
            'observations': observations, 'errors': errors, 'observation_valid': os is not None,
            'provenance': o.get('provenance')}

def compare_ctis(name, old, new):
    if not old or new.get('observation_valid') is not True:
        return []
    out = []
    def add(field, before, after, meaning, priority='normal'):
        out.append(change(name, 'EU CTIS', 'Human trial registration', 'Official EU registry; mirror only as cross-check',
                          field, before, after, new['official_url'], meaning, priority, observation=new))
    # Only official observations drive factual transitions. Unknown cannot restart
    # a trial or remove Greece. Mirror observations are retained as a conflict.
    for field, label in [('status', 'status'), ('temporary_halt', 'temporary halt'), ('greece_mentioned', 'Greece mention')]:
        before, after = old.get(field), new.get(field)
        if before is not None and after is not None and before != after:
            add(label, before, after, 'Official EU observation changed; this is not evidence of clinical benefit or guaranteed Greek access.',
                'greece' if field == 'greece_mentioned' else 'normal')
    if new.get('status_conflict') and (not old.get('status_conflict') or old.get('mirror_status') != new.get('mirror_status')):
        add('registry conflict', old.get('mirror_status'), new.get('mirror_status'),
            'Official and mirror disagree. The official status is displayed with the disagreement; the mirror cannot silently override it.')
    return out

def page_snapshot(item):
    text=clean_text(fetch(item['url']))
    low=text.lower(); hits=[]
    for kw in item['keywords']:
        pos=low.find(kw.lower())
        if pos>=0:
            hits.append(re.sub(r'\s+',' ',text[max(0,pos-140):pos+260]).strip())
    material='\n'.join(sorted(set(hits)))
    return {'url':item['url'],'hash':hashlib.sha256(material.encode()).hexdigest(),'material':material[:5000], 'observation_valid': True, 'provenance': source_record(item['name'],item['url'],material)}

def compare_page(name, old, new):
    if not old or old.get('hash')==new.get('hash'):return []
    oldm=(old.get('material') or '').lower(); newm=(new.get('material') or '').lower()
    triggers=['phase 2','phase ii','phase 1','phase i','first-in-human','first patient','dosing','recruit','ind clear','fda','mhra','bfarm','clinical trial','gmp','completed','halt','paused','terminated']
    added=[t for t in triggers if t in newm and t not in oldm]
    if not added:return []
    return [change(name,'Official programme page','Announced/planned development','Official company/university page','high-signal page text',old.get('material','')[-700:],new.get('material','')[-1000:],new['url'],
      'A high-signal development term appeared on an official programme page. This is an announcement, not evidence of clinical efficacy; verify against a registry/regulator before updating trial status.', observation=new)]

PUBMED_QUERY='''("multiple sclerosis"[Title/Abstract]) AND (remyelination[Title/Abstract] OR "myelin repair"[Title/Abstract] OR "myelin regeneration"[Title/Abstract] OR promyelination[Title/Abstract] OR "oligodendrocyte progenitor"[Title/Abstract] OR "OPC differentiation"[Title/Abstract] OR "oligodendrocyte differentiation"[Title/Abstract] OR "oligodendrocyte maturation"[Title/Abstract] OR "myelin water fraction"[Title/Abstract] OR "magnetization transfer ratio"[Title/Abstract] OR "myelin PET"[Title/Abstract] OR neurorepair[Title/Abstract] OR "neural stem cell"[Title/Abstract] OR "glial progenitor"[Title/Abstract])'''

def pubmed_search():
    params=urllib.parse.urlencode({'db':'pubmed','term':PUBMED_QUERY,'retmode':'json','retmax':100,'reldate':14,'datetype':'edat'})
    data=fetch_json('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+params)
    return data.get('esearchresult',{}).get('idlist',[])

def pubmed_fetch(pmids):
    if not pmids:return []
    params=urllib.parse.urlencode({'db':'pubmed','id':','.join(pmids),'retmode':'xml'})
    root=ET.fromstring(fetch('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+params))
    out=[]
    for art in root.findall('.//PubmedArticle'):
        pmid=(art.findtext('.//PMID') or '').strip()
        title=''.join(art.find('.//ArticleTitle').itertext()) if art.find('.//ArticleTitle') is not None else ''
        abst=' '.join(''.join(x.itertext()) for x in art.findall('.//Abstract/AbstractText'))
        pubtypes=[x.text or '' for x in art.findall('.//PublicationType')]
        text=(title+' '+abst).lower()
        aliases=[a for a in WATCH['program_aliases'] if a.lower() in text]
        human_trial=any('clinical trial' in x.lower() or 'randomized controlled trial' in x.lower() for x in pubtypes)
        context=evidence_context(title+' '+abst,pubtypes)
        human_words=context['human_data']
        preclinical_words=bool(re.search(r'\b(mouse|mice|murine|rat|rats|in vitro|cell culture|cuprizone|eae)\b',text))
        strong_title=bool(re.search(r'remyelin|myelin repair|myelin regeneration|oligodendrocyte|neural stem',title,re.I))
        substantive=human_trial or (human_words and not preclinical_words) or bool(aliases and strong_title)
        evidence='Human clinical paper' if human_trial else ('Human-associated paper' if human_words and not preclinical_words else 'Preclinical / translational paper')
        out.append({'pmid':pmid,'title':title,'aliases':aliases,'substantive':substantive,'evidence':evidence,'url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/', **context, 'provenance': source_record(pmid,f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',title+' '+abst)})
    return out

def paper_change(p):
    return {'program':', '.join(p['aliases'][:4]) or p['title'],'source':'PubMed','evidence':p['evidence'],'source_quality':'Peer-reviewed/indexed literature','field':'new paper','before':None,'after':p['title'],'url':p['url'],'meaning':('New human clinical literature requires endpoint/safety review before any claim of benefit.' if p['evidence'].startswith('Human') else 'New translational/preclinical evidence only; animal, cell or biomarker findings are not clinical benefit.'),'priority':'normal', **{k:p.get(k) for k in ('human_data','study_population','publication_status','endpoint_classes','provenance')}, 'observation_valid': True, 'policy_version': POLICY_VERSION}

def markdown(changes, now):
    g=[c for c in changes if c.get('priority')=='greece']; rest=[c for c in changes if c.get('priority')!='greece']
    lines=['# MS remyelination / myelin-repair monitor',f'Run: **{now}**','','This is an **audit trail**, not an approval queue. Only validated source observations can be published automatically. No animal, cell, imaging or biomarker finding should be presented as proven clinical benefit.']
    if g:
        lines += ['','## Ελλάδα — άμεση προτεραιότητα']
        for c in g: lines += fmt_change(c)
    if rest:
        lines += ['','## Substantive developments to review']
        for c in rest: lines += fmt_change(c)
    lines += ['','## Publication policy','Automatic publication uses validated primary observations and conservative evidence labels. Technical failures are not research changes. No manual approval is required.']
    return '\n'.join(lines)

def fmt_change(c):
    return ['',f'### {c["program"]}',f'- **Source:** {c["source"]} — {c["source_quality"]}',f'- **Evidence:** {c["evidence"]}',f'- **Change:** `{c["field"]}` — `{c["before"]}` → `{c["after"]}`',f'- **Clinical meaning:** {c["meaning"]}',f'- **Primary link:** {c["url"]}']

def adopt_targets(watch, targets):
    if not isinstance(targets, dict):
        raise ValueError('Malformed adopted targets')
    for rid, item in targets.items():
        if not isinstance(item, dict) or not primary_registry_url(rid, item.get('url')) or item.get('verified') is not True:
            continue
        section = 'clinicaltrials' if rid.startswith('NCT') else ('ctis' if re.fullmatch(r'20\d{2}-\d{6}-\d{2}-\d{2}', rid) else 'registries')
        records = watch.setdefault(section, [])
        if rid not in {x['id'] for x in records}:
            records.append({**item, 'id': rid, 'name': item.get('name') or rid})
    return watch


def other_registry_snapshot(item):
    """Best-effort explicit status field on primary ISRCTN/ANZCTR records.

    A JS/challenge page or absent/ambiguous status is a source failure. It cannot
    turn recruiting into completed, nor is a country mention Greek-site access.
    """
    if not primary_registry_url(item['id'], item['url']):
        raise ValueError('Invalid registry identity/URL')
    text = clean_text(fetch(item['url']))
    patterns = [('RECRUITING', r'(?:Recruitment status|Overall trial status)\s*:?\s*(?:Recruiting|Ongoing, recruiting)\b'),
                ('NOT_YET_RECRUITING', r'(?:Recruitment status|Overall trial status)\s*:?\s*Not yet recruiting\b'),
                ('COMPLETED', r'(?:Recruitment status|Overall trial status)\s*:?\s*Completed\b'),
                ('SUSPENDED', r'(?:Recruitment status|Overall trial status)\s*:?\s*(?:Suspended|Temporarily halted)\b'),
                ('TERMINATED', r'(?:Recruitment status|Overall trial status)\s*:?\s*(?:Terminated|Stopped)\b')]
    statuses = {status for status, pattern in patterns if re.search(pattern, text, re.I)}
    if len(statuses) != 1:
        raise ValueError('No unambiguous primary recruitment-status field')
    return {'id': item['id'], 'url': item['url'], 'status': statuses.pop(),
            'observation_valid': True, 'provenance': source_record(item['id'], item['url'], text)}


def compare_other_registry(name, old, new):
    if not old or new.get('observation_valid') is not True or old.get('status') == new.get('status'):
        return []
    source = 'ANZCTR' if new['id'].startswith('ACTRN') else 'ISRCTN'
    return [change(name, source, 'Human trial registration', 'Primary registry', 'status',
                   old.get('status'), new.get('status'), new['url'],
                   'The registry operational status changed; no clinical benefit is established.', observation=new)]


def main() -> int:
    baseline = not STATE_PATH.exists(); old = load_state()
    new = copy.deepcopy(old)
    new.update(version=2, generated_at=now_iso(), policy_version=POLICY_VERSION)
    new.setdefault('source_health', {})
    changes = []; errors = []; observations = []
    watch = copy.deepcopy(WATCH)
    # This file is restored from the same live-data commit as the durable journal.
    # No arbitrary remote URLs are accepted as new polling targets.
    adopted_path = MON / 'adopted_targets.json'
    if adopted_path.exists():
        adopt_targets(watch, json.loads(adopted_path.read_text()))
    for section, collector, comparer, label in [
        ('clinicaltrials', ctg_snapshot, compare_ctg, 'ClinicalTrials.gov'),
        ('ctis', ctis_snapshot, compare_ctis, 'EU CTIS'),
        ('registries', other_registry_snapshot, compare_other_registry, 'Primary registry'),
    ]:
        new.setdefault(section, {})
        for item in watch.get(section, []):
            key = item['id']
            try:
                snap = collector(item if section == 'registries' else key)
                if snap.get('observation_valid') is not True:
                    raise ValueError('; '.join(snap.get('errors') or ['No authoritative parsed observation']))
                previous = old.get(section, {}).get(key) or item.get('initial_snapshot')
                changes += comparer(item['name'], previous, snap)
                new[section][key] = snap
                new['source_health'][key] = {'state': 'ok', 'last_success': now_iso()}
                snap = {**snap, 'program': item['name'], 'source': label if section != 'registries' else item['source']}
                observations.append(snap)
                errors.extend(f'{label} {key}: {e}' for e in snap.get('errors', []))
            except Exception as e:
                errors.append(f'{label} {key}: {type(e).__name__}: {e}')
                health = dict(new['source_health'].get(key, {}))
                health.update(state='unavailable', last_attempt=now_iso())
                new['source_health'][key] = health
                # The previous good snapshot stays byte-for-byte intact.
    new.setdefault('pages', {})
    for item in watch.get('official_pages', []):
        try:
            snap = page_snapshot(item)
            changes += compare_page(item['name'], old.get('pages', {}).get(item['name']), snap)
            new['pages'][item['name']] = snap
        except Exception as e:
            errors.append(f'Page {item["name"]}: {type(e).__name__}: {e}')
    try:
        ids = pubmed_search(); oldids = set(old.get('pubmed_ids', [])); papers = pubmed_fetch(ids)
        for paper in papers:
            if paper['pmid'] not in oldids and paper['substantive']:
                changes.append(paper_change(paper))
        # Mark only records actually fetched, not IDs with missing efetch payloads.
        new['pubmed_ids'] = sorted(oldids | {p['pmid'] for p in papers})
    except Exception as e:
        errors.append(f'PubMed: {type(e).__name__}: {e}')
    save_state(new)
    if baseline:
        changes = []
    generated = now_iso()
    canonical = sorted(changes, key=lambda x: (0 if x.get('priority') == 'greece' else 1, x['program'], x['field']))
    md = markdown(canonical, generated)
    if errors:
        md += '\n\n## Source-health warnings (not research developments)\n' + '\n'.join(f'- {e}' for e in errors)
    report = {'generated_at': generated, 'baseline': baseline, 'policy_version': POLICY_VERSION,
              'substantive_changes': canonical, 'observations': observations,
              'source_health': new['source_health'], 'warnings': errors,
              'fingerprint': digest(canonical), 'markdown': md}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Baseline={baseline}; substantive changes={len(canonical)}; warnings={len(errors)}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
