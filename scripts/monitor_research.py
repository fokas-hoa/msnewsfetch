#!/usr/bin/env python3
"""Deterministic watcher for high-signal MS remyelination/myelin-repair developments.

It never edits the public site. It creates a review report only for substantive registry,
regulatory/page, or strongly relevant literature changes. First run establishes baseline.
"""
from __future__ import annotations
import hashlib, html, json, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

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
    data=fetch_json(f'https://clinicaltrials.gov/api/v2/studies/{nct}')
    p=data.get('protocolSection',{})
    ident=p.get('identificationModule',{})
    status=p.get('statusModule',{})
    design=p.get('designModule',{})
    contacts=p.get('contactsLocationsModule',{})
    outcomes=p.get('outcomesModule',{})
    locations=contacts.get('locations') or []
    countries=sorted({x.get('country') for x in locations if x.get('country')})
    greek=[x for x in locations if (x.get('country') or '').lower()=='greece']
    primary=[o.get('measure','') for o in (outcomes.get('primaryOutcomes') or [])]
    phases=design.get('phases') or []
    return {
      'id':nct,'title':ident.get('briefTitle') or ident.get('officialTitle') or nct,
      'status':status.get('overallStatus'),
      'start':(status.get('startDateStruct') or {}).get('date'),
      'primary_completion':(status.get('primaryCompletionDateStruct') or {}).get('date'),
      'completion':(status.get('completionDateStruct') or {}).get('date'),
      'enrollment':(design.get('enrollmentInfo') or {}).get('count'),
      'enrollment_type':(design.get('enrollmentInfo') or {}).get('type'),
      'phases':phases,'countries':countries,'greece_sites':len(greek),
      'primary_outcomes':primary,
      'has_results':bool(data.get('hasResults') or data.get('resultsSection')),
      'url':f'https://clinicaltrials.gov/study/{nct}'
    }

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
    if not old:return []
    out=[]
    if old.get('status') != new.get('status'):
        out.append(change(name,'ClinicalTrials.gov','Human trial','Primary registry','status',old.get('status'),new.get('status'),new['url'],
          'Recruitment/operational status changed; this does not itself establish efficacy.'))
    if old.get('greece_sites') != new.get('greece_sites'):
        out.append(change(name,'ClinicalTrials.gov','Human trial','Primary registry','Greece sites',old.get('greece_sites'),new.get('greece_sites'),new['url'],
          'Directly relevant to trial access in Greece; eligibility still depends on the site and protocol.','greece'))
    if not old.get('has_results') and new.get('has_results'):
        out.append(change(name,'ClinicalTrials.gov','Human trial results posted','Primary registry','results posted',False,True,new['url'],
          'Results are now posted and need scientific review before any efficacy or safety conclusion.'))
    for key,label in [('start','start date'),('primary_completion','primary completion'),('completion','completion date')]:
        if old.get(key) != new.get(key) and date_shift_days(old.get(key),new.get(key)) >= 60:
            out.append(change(name,'ClinicalTrials.gov','Human trial','Primary registry',label,old.get(key),new.get(key),new['url'],
              'A ≥60-day schedule change may indicate a meaningful delay/acceleration; it is not an efficacy signal.'))
    if old.get('primary_outcomes') != new.get('primary_outcomes'):
        out.append(change(name,'ClinicalTrials.gov','Human trial','Primary registry','primary outcomes',old.get('primary_outcomes'),new.get('primary_outcomes'),new['url'],
          'Primary outcome wording changed; protocol/history review is required to interpret significance.'))
    return out

def change(program,source,evidence,quality,field,before,after,url,meaning,priority='normal'):
    return {'program':program,'source':source,'evidence':evidence,'source_quality':quality,'field':field,'before':before,'after':after,'url':url,'meaning':meaning,'priority':priority}

CTIS_STATUSES=['Temporarily halted','Ongoing, recruiting','Ongoing, not recruiting','Ended','Early terminated','Authorised','Not authorised']

def parse_status(text):
    for s in CTIS_STATUSES:
        if re.search(r'\b'+re.escape(s)+r'\b',text,re.I): return s
    return None

def ctis_snapshot(euct: str):
    official=f'https://euclinicaltrials.eu/ctis-public/view/{euct}?lang=en'
    mirror=f'https://ctis.eu/trial/{euct}'
    otext=''; mtext=''; errors=[]
    try: otext=clean_text(fetch(official))
    except Exception as e: errors.append('official:'+type(e).__name__)
    try: mtext=clean_text(fetch(mirror))
    except Exception as e: errors.append('mirror:'+type(e).__name__)
    os=parse_status(otext); ms=parse_status(mtext)
    status=os or ms
    conflict=bool(os and ms and os.lower()!=ms.lower())
    greece=('Greece' in otext and 'Greece' in mtext) if otext and mtext else ('Greece' in (otext or mtext))
    halt=bool(re.search(r'Temporary Halt|Temporarily halted',otext+' '+mtext,re.I))
    return {'id':euct,'status':status,'official_status':os,'mirror_status':ms,'status_conflict':conflict,
            'greece_mentioned':greece,'temporary_halt':halt,
            'official_url':official,'mirror_url':mirror,'errors':errors}

def compare_ctis(name, old, new):
    if not old:return []
    out=[]
    if old.get('status') != new.get('status'):
        out.append(change(name,'EU CTIS','Human trial','Official EU registry + independent mirror cross-check','status',old.get('status'),new.get('status'),new['official_url'],
          'EU trial status changed; this affects trial availability/operations, not proven clinical benefit.'))
    if old.get('greece_mentioned') != new.get('greece_mentioned'):
        out.append(change(name,'EU CTIS','Human trial','Official EU registry + mirror','Greece mention',old.get('greece_mentioned'),new.get('greece_mentioned'),new['official_url'],
          'Potential change relevant to Greek access; the exact Greek site/contact must be independently verified before publication.','greece'))
    if old.get('temporary_halt') != new.get('temporary_halt'):
        out.append(change(name,'EU CTIS','Human trial','Official EU registry + mirror','temporary halt',old.get('temporary_halt'),new.get('temporary_halt'),new['official_url'],
          'A halt/restart is a substantive regulatory/operational development; it does not indicate efficacy.'))
    if new.get('status_conflict') and not old.get('status_conflict'):
        out.append(change(name,'EU CTIS','Human trial','Source conflict','registry conflict',old.get('mirror_status'),new.get('mirror_status'),new['official_url'],
          'Official and mirror statuses disagree. Use the official EU record as primary and flag the conflict rather than silently resolving it.'))
    return out

def page_snapshot(item):
    text=clean_text(fetch(item['url']))
    low=text.lower(); hits=[]
    for kw in item['keywords']:
        pos=low.find(kw.lower())
        if pos>=0:
            hits.append(re.sub(r'\s+',' ',text[max(0,pos-140):pos+260]).strip())
    material='\n'.join(sorted(set(hits)))
    return {'url':item['url'],'hash':hashlib.sha256(material.encode()).hexdigest(),'material':material[:5000]}

def compare_page(name, old, new):
    if not old or old.get('hash')==new.get('hash'):return []
    oldm=(old.get('material') or '').lower(); newm=(new.get('material') or '').lower()
    triggers=['phase 2','phase ii','phase 1','phase i','first-in-human','first patient','dosing','recruit','ind clear','fda','mhra','bfarm','clinical trial','gmp','completed','halt','paused','terminated']
    added=[t for t in triggers if t in newm and t not in oldm]
    if not added:return []
    return [change(name,'Official programme page','Announced/planned development','Official company/university page','high-signal page text',old.get('material','')[-700:],new.get('material','')[-1000:],new['url'],
      'A high-signal development term appeared on an official programme page. This is an announcement, not evidence of clinical efficacy; verify against a registry/regulator before updating trial status.')]

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
        human_words=bool(re.search(r'\b(patient|patients|participant|participants|people with multiple sclerosis|phase [123])\b',text))
        preclinical_words=bool(re.search(r'\b(mouse|mice|murine|rat|rats|in vitro|cell culture|cuprizone|eae)\b',text))
        strong_title=bool(re.search(r'remyelin|myelin repair|myelin regeneration|oligodendrocyte|neural stem',title,re.I))
        substantive=human_trial or (human_words and not preclinical_words) or bool(aliases and strong_title)
        evidence='Human clinical paper' if human_trial else ('Human-associated paper' if human_words and not preclinical_words else 'Preclinical / translational paper')
        out.append({'pmid':pmid,'title':title,'aliases':aliases,'substantive':substantive,'evidence':evidence,'url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'})
    return out

def paper_change(p):
    return {'program':', '.join(p['aliases'][:4]) or p['title'],'source':'PubMed','evidence':p['evidence'],'source_quality':'Peer-reviewed/indexed literature','field':'new paper','before':None,'after':p['title'],'url':p['url'],'meaning':('New human clinical literature requires endpoint/safety review before any claim of benefit.' if p['evidence'].startswith('Human') else 'New translational/preclinical evidence only; animal, cell or biomarker findings are not clinical benefit.'),'priority':'normal'}

def markdown(changes, now):
    g=[c for c in changes if c.get('priority')=='greece']; rest=[c for c in changes if c.get('priority')!='greece']
    lines=['# MS remyelination / myelin-repair monitor',f'Run: **{now}**','','This issue is a **review queue**, not an automatic site update. No animal, cell, imaging or biomarker finding should be presented as proven clinical benefit.']
    if g:
        lines += ['','## Ελλάδα — άμεση προτεραιότητα']
        for c in g: lines += fmt_change(c)
    if rest:
        lines += ['','## Substantive developments to review']
        for c in rest: lines += fmt_change(c)
    lines += ['','## Publication gate','Update `news.json` only after checking the primary source, resolving registry conflicts, and writing explicit evidence level / human-data / source-quality / clinical-meaning fields.']
    return '\n'.join(lines)

def fmt_change(c):
    return ['',f'### {c["program"]}',f'- **Source:** {c["source"]} — {c["source_quality"]}',f'- **Evidence:** {c["evidence"]}',f'- **Change:** `{c["field"]}` — `{c["before"]}` → `{c["after"]}`',f'- **Clinical meaning:** {c["meaning"]}',f'- **Primary link:** {c["url"]}']

def main() -> int:
    baseline=not STATE_PATH.exists(); old=load_state()
    new={'version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'clinicaltrials':{},'ctis':{},'pages':{},'pubmed_ids':[]}
    changes=[]; errors=[]
    for item in WATCH['clinicaltrials']:
        try:
            s=ctg_snapshot(item['id']); new['clinicaltrials'][item['id']]=s
            changes += compare_ctg(item['name'],old.get('clinicaltrials',{}).get(item['id']),s)
        except Exception as e: errors.append(f'ClinicalTrials.gov {item["id"]}: {type(e).__name__}: {e}')
    for item in WATCH['ctis']:
        try:
            s=ctis_snapshot(item['id']); new['ctis'][item['id']]=s
            changes += compare_ctis(item['name'],old.get('ctis',{}).get(item['id']),s)
        except Exception as e: errors.append(f'CTIS {item["id"]}: {type(e).__name__}: {e}')
    for item in WATCH['official_pages']:
        try:
            s=page_snapshot(item); new['pages'][item['name']]=s
            changes += compare_page(item['name'],old.get('pages',{}).get(item['name']),s)
        except Exception as e: errors.append(f'Page {item["name"]}: {type(e).__name__}: {e}')
    try:
        ids=pubmed_search(); oldids=set(old.get('pubmed_ids',[])); papers=pubmed_fetch(ids)
        for p in papers:
            if p['pmid'] not in oldids and p['substantive']: changes.append(paper_change(p))
        new['pubmed_ids']=sorted(set(old.get('pubmed_ids',[])) | set(ids))[-500:]
    except Exception as e:
        errors.append(f'PubMed: {type(e).__name__}: {e}'); new['pubmed_ids']=old.get('pubmed_ids',[])
    save_state(new)
    if baseline: changes=[]
    now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    canonical=sorted(changes,key=lambda x:(0 if x.get('priority')=='greece' else 1,x['program'],x['field']))
    fp=digest(canonical); md=markdown(canonical,now)
    if errors: md += '\n\n## Monitor warnings\n' + '\n'.join(f'- {e}' for e in errors)
    report={'generated_at':now,'baseline':baseline,'substantive_changes':canonical,'warnings':errors,'fingerprint':fp,'markdown':md}
    REPORT_PATH.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Baseline={baseline}; substantive changes={len(canonical)}; warnings={len(errors)}')
    for e in errors: print('WARNING:',e,file=sys.stderr)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
