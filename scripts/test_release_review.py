#!/usr/bin/env python3
"""Independent offline release-contract tests for PR2 at 13fd743.
All trial statuses/content below are synthetic fixtures, not research news.
No network calls, tokens, live-data writes or production deploys are performed.
Run: python scripts/restore_data.py && python scripts/test_release_review.py
"""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import deep_discovery as dd
import monitor_research as mr
import publish_live_feed as pub
from filter_discovery_report import issue_worthy
from program_identity import review_confidence
ROOT = Path(__file__).resolve().parents[1]
WHEN = '2026-09-17T00:00:00+00:00'

def empty_feed():
    return {'version':1,'events':[],'programme_overrides':{},'programmes':[],'quarantine':[]}

def collect(title='Lucid-MS Phase 2 remyelination in multiple sclerosis', meta=None):
    return dd.candidate('ClinicalTrials.gov','NCT09999998',title,
        'https://clinicaltrials.gov/study/NCT09999998',
        title+' clinical trial in multiple sclerosis patients',
        {'human':True,'status':'RECRUITING','phases':['PHASE2'],**(meta or {})},
        evidence='Human trial registration',source_quality='Primary trial registry')

def change(program='MODIF-MS / ifenprodil',after='RECRUITING',source='ClinicalTrials.gov'):
    return mr.change(program,source,'Human trial','Primary registry','status',
        'NOT_YET_RECRUITING',after,'https://clinicaltrials.gov/study/NCT06330077',
        'Synthetic operational-status fixture; not an efficacy result.')

def browser(payload,expression):
    script=r'''
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const ctx=vm.createContext({console:{warn(){}},fetch:()=>new Promise(()=>{}),input:input.payload});
vm.runInContext(fs.readFileSync('app.js','utf8'),ctx);
try{process.stdout.write(JSON.stringify({ok:true,value:vm.runInContext(input.expression,ctx)}));}
catch(e){process.stdout.write(JSON.stringify({ok:false,error:String(e)}));}
'''
    run=subprocess.run(['node','-e',script],input=json.dumps({'payload':payload,'expression':expression}),
        cwd=ROOT,text=True,capture_output=True,check=True,timeout=10)
    return json.loads(run.stdout)

class ReleaseReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads((ROOT/'news.json').read_text())

    def test_control_normal_status_event_and_idempotent_replay(self):
        feed=empty_feed(); report={'generated_at':WHEN,'substantive_changes':[change()]}
        pub.apply_daily(feed,report); pub.apply_daily(feed,report)
        self.assertEqual(len(feed['events']),1)
        self.assertIn('RECRUITING',feed['events'][0]['summary'])

    def test_control_novel_lucid_registry_record_survives(self):
        c=collect(); self.assertIsNotNone(c)
        self.assertEqual(c['identity_status'],'known_program_new_record')

    def test_novel_metformin_registry_record_survives_generic_known_alias(self):
        c=collect('Metformin with RX-TEST Phase 2 remyelination in multiple sclerosis')
        self.assertIsNotNone(c,'New registry ID was discarded by generic metformin watchlist alias')

    def test_novel_registry_record_referencing_previous_trial_survives(self):
        c=collect(meta={'previous_trial':'NCT06595706'})
        self.assertIsNotNone(c,'A cited prior trial ID must not make this new registry ID an old mention')

    def test_canonical_identity_is_preserved_in_public_programme(self):
        c=collect(); c.update(review_confidence(c)); p=pub.programme_from_candidate(c)
        self.assertEqual(p['canonical_id'],c['canonical_program_id'])

    def test_actual_modif_card_receives_its_status_override(self):
        feed=empty_feed()
        pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':[change(after='Ongoing, recruiting',source='EU CTIS')]})
        result=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed).pipeline.find(x=>x.name==="MODIF-MS").status')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['value'],'Ongoing, recruiting','Watcher name and real baseline card name do not join')

    def test_terminal_trial_is_not_left_in_active_upcoming_category(self):
        feed=empty_feed(); pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':[change('ReVIVE','TERMINATED')]})
        result=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed).pipeline.filter(x=>x.name==="ReVIVE")')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['value'],[],'A terminated trial is still in active/upcoming trials')

    def test_live_added_programme_receives_subsequent_status_override(self):
        c=collect('RX-TEST remyelination Phase 2 in multiple sclerosis')
        feed=empty_feed(); pub.apply_weekly(feed,{'generated_at':WHEN,'candidates':[c]})
        name=feed['programmes'][0]['name']
        pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':[change(name,'SUSPENDED')]})
        result=browser({'base':self.base,'feed':feed,'name':name},'mergeLiveData(input.base,input.feed).pipeline.find(x=>x.name===input.name).status')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['value'],'SUSPENDED','Overrides run before live programmes are appended')

    def test_registry_status_does_not_destroy_existing_readout(self):
        old=next(x for x in self.base['readouts'] if x['name']=='CCMR Two')['status']
        feed=empty_feed(); pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':[change('CCMR Two','COMPLETED')]})
        result=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed).readouts.find(x=>x.name==="CCMR Two")')
        self.assertTrue(result['ok'],result)
        self.assertIn(old,json.dumps(result['value'],ensure_ascii=False),'Operational status erased the existing Greek readout summary field')

    def test_ctis_network_failure_does_not_publish_halt_lift(self):
        old={'id':'2023-507874-42-00','status':'Temporarily halted','official_status':'Temporarily halted',
            'mirror_status':'Temporarily halted','temporary_halt':True,'greece_mentioned':True,'status_conflict':False}
        try:
            with patch.object(mr,'fetch',side_effect=OSError('synthetic network failure')):
                new=mr.ctis_snapshot(old['id'])
        except (OSError,ValueError):
            return
        updates=mr.compare_ctis('MODIF-MS / ifenprodil',old,new)
        feed=empty_feed(); pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':updates})
        factual=[x for x in feed['events'] if any(k in x['title'] for k in ('status','Greece mention','temporary halt'))]
        self.assertEqual(factual,[],'Source outage became public status=null / halt=false / Greece=false')

    def test_ctis_conflicting_mirror_cannot_override_official_status(self):
        old={'status':'Authorised','temporary_halt':False,'greece_mentioned':False,'status_conflict':False}
        def fetch(url,*args):
            return b'<p>Ongoing, recruiting</p>' if 'euclinicaltrials.eu' in url else b'<p>Temporarily halted</p>'
        with patch.object(mr,'fetch',side_effect=fetch): new=mr.ctis_snapshot('2025-522922-11-00')
        feed=empty_feed(); pub.apply_daily(feed,{'generated_at':WHEN,'substantive_changes':mr.compare_ctis('ACT-1004-1239',old,new)})
        result=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed).pipeline.find(x=>x.name==="ACT-1004-1239").status')
        self.assertTrue(result['ok'],result)
        self.assertNotEqual(result['value'],'Temporarily halted','Mirror halt silently overrode the official recruiting observation')

    def test_failed_daily_fetch_retains_last_good_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            state=Path(tmp)/'state.json'; report=Path(tmp)/'report.json'
            prior={'version':1,'clinicaltrials':{'NCT09999998':{'status':'RECRUITING'}},'ctis':{},'pages':{},'pubmed_ids':[]}
            state.write_text(json.dumps(prior))
            stack.enter_context(patch.object(mr,'STATE_PATH',state)); stack.enter_context(patch.object(mr,'REPORT_PATH',report))
            stack.enter_context(patch.object(mr,'WATCH',{'clinicaltrials':[{'id':'NCT09999998','name':'RX-TEST'}],'ctis':[],'official_pages':[],'program_aliases':[]}))
            stack.enter_context(patch.object(mr,'ctg_snapshot',side_effect=OSError('synthetic timeout')))
            stack.enter_context(patch.object(mr,'pubmed_search',return_value=[]))
            mr.main()
            self.assertIn('NCT09999998',json.loads(state.read_text())['clinicaltrials'],'Transient outage erased comparison baseline')

    def test_greek_site_recruitment_change_detected_without_count_change(self):
        api={'protocolSection':{'identificationModule':{'briefTitle':'RX-TEST'},'statusModule':{'overallStatus':'RECRUITING'},
            'contactsLocationsModule':{'locations':[{'country':'Greece','city':'Athens','facility':'TEST centre','status':'RECRUITING'}]}}}
        with patch.object(mr,'fetch_json',return_value=api): old=mr.ctg_snapshot('NCT09999998')
        api['protocolSection']['contactsLocationsModule']['locations'][0]['status']='COMPLETED'
        with patch.object(mr,'fetch_json',return_value=api): new=mr.ctg_snapshot('NCT09999998')
        changes=mr.compare_ctg('RX-TEST',old,new)
        self.assertTrue(any(x.get('priority')=='greece' for x in changes),'Greek recruitment closed but identical site count hid the change')

    def test_patient_derived_cells_do_not_become_human_clinical_context(self):
        record={'id':'TEST-PAPER','title':'RX-TEST remyelination in multiple sclerosis models',
            'abstractText':'Patient-derived oligodendrocytes and mice show myelin repair; an ind-enabling development project.',
            'pubTypeList':{'pubType':['Journal Article']},'source':'MED'}
        with patch.object(dd,'get_json',return_value={'resultList':{'result':[record]}}),patch.object(dd,'KNOWN_ALIASES',[]):
            found=dd.scan_europepmc([])
        self.assertTrue(found,'Fixture must reach the collector')
        self.assertFalse(found[0]['human_data'],'Substring patient in patient-derived cells was treated as human study context')

    def test_invalid_live_feed_shape_falls_back_to_baseline(self):
        result=browser({'base':self.base,'feed':{'version':1,'events':{}}},'mergeLiveData(input.base,input.feed)')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['value']['items'],self.base['items'])

    def test_human_preprint_is_not_biologically_preclinical(self):
        result=browser({},'category({stage:"Προδημοσίευση",evidence:"Human preprint",human_data:true})')
        self.assertTrue(result['ok'],result)
        self.assertNotEqual(result['value'],'preclinical','Publication status and study population are separate dimensions')

    def test_unqualified_candidate_is_not_published_by_final_boundary(self):
        c={'id':'TEST-LOW','title':'Speculative research lead','url':'https://example.invalid/lead',
            'source':'News discovery','source_quality':'Secondary discovery','evidence':'Unverified',
            'score':1,'review_confidence':1,'source_class':'secondary_news','human_data':False,'translation_hits':[]}
        self.assertFalse(issue_worthy(c))
        feed=empty_feed(); pub.apply_weekly(feed,{'generated_at':WHEN,'candidates':[c]})
        self.assertEqual(feed['events'],[],'Final publishing boundary trusts upstream candidates without validation/gate')

    def test_netlify_uncached_build_is_not_skipped_when_refs_are_equal(self):
        run=subprocess.run(['node','scripts/netlify_ignore.js'],cwd=ROOT,
            env={**os.environ,'CACHED_COMMIT_REF':'HEAD','COMMIT_REF':'HEAD'},text=True,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,1,'An uncached/manual rebuild must continue, not exit 0: '+run.stdout)

    def test_rejected_record_can_be_reconsidered_when_its_evidence_changes(self):
        c={'id':'TEST-RETRY','title':'RX-TEST remyelination development','url':'https://example.invalid/test',
            'source':'Europe PMC','source_quality':'Europe PMC bibliographic record','evidence':'Research paper',
            'greece_priority':False,'human_data':False,'score':8,'review_confidence':70,
            'source_class':'peer_reviewed_index','translation_hits':[]}
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            state=Path(tmp)/'state.json'; report=Path(tmp)/'report.json'
            state.write_text(json.dumps({'version':1,'seen':{'europepmc':[]}}))
            stack.enter_context(patch.object(dd,'STATE_PATH',state)); stack.enter_context(patch.object(dd,'REPORT_PATH',report))
            for name in ['scan_clinicaltrials','scan_ctis','scan_preprints','scan_reporter','scan_anzctr','scan_conferences','scan_news_rss']:
                stack.enter_context(patch.object(dd,name,return_value=[]))
            scanner=stack.enter_context(patch.object(dd,'scan_europepmc',return_value=[c]))
            dd.main(); first=json.loads(report.read_text())['candidates']
            self.assertEqual(len(first),1); self.assertFalse(issue_worthy(first[0]))
            improved={**c,'human_data':True,'score':11,'review_confidence':91,'translation_hits':['phase 2']}
            self.assertTrue(issue_worthy(improved)); scanner.return_value=[improved]
            dd.main()
            self.assertTrue(json.loads(report.read_text())['candidates'],'Seen-ID state permanently suppressed a formerly rejected record')

if __name__=='__main__':
    unittest.main(verbosity=2)
