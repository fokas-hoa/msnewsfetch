#!/usr/bin/env python3
"""Offline multi-run, final-boundary and optimistic-transaction regressions.
All observations and identities used here are synthetic. No live writes occur.
"""
import base64
import copy
import json
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import deep_discovery as dd
import monitor_research as mr
import publish_live_feed as pub
import live_store as store
import discovery_source_utils as journal
from research_contract import (POLICY_VERSION, source_record, evidence_context,
                                primary_registry_url, fingerprint, validate_feed)
from test_release_review import browser

ROOT=Path(__file__).resolve().parents[1]
RID='NCT09999998'
URL='https://clinicaltrials.gov/study/'+RID
WHEN='2026-09-17T06:00:00+00:00'


def snapshot(status='RECRUITING', when=WHEN, sites=None):
    s={'id':RID,'url':URL,'title':'RX-TEST','status':status,'observation_valid':True,
       'greece_sites':len(sites) if sites is not None else None,
       'greece_locations':sites,'locations_complete':sites is not None,'has_results':False,
       'primary_outcomes':[],'source':'ClinicalTrials.gov'}
    s['provenance']=source_record(RID,URL,{'status':status,'sites':sites})
    s['provenance']['fetched_at']=when
    return s


def candidate(rid=RID, title='RX-TEST Phase 2 remyelination in multiple sclerosis'):
    return dd.candidate('ClinicalTrials.gov',rid,title,'https://clinicaltrials.gov/study/'+rid,
        title+' clinical trial in multiple sclerosis',
        {'human':True,'status':'RECRUITING','phases':['PHASE2'],'countries':['France']},
        evidence='Human trial registration',source_quality='Primary trial registry')


class Hardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base=json.loads((ROOT/'news.json').read_text())

    def test_success_failure_success_keeps_transition(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as st:
            state,report=Path(tmp)/'state.json',Path(tmp)/'report.json'
            st.enter_context(patch.object(mr,'STATE_PATH',state)); st.enter_context(patch.object(mr,'REPORT_PATH',report))
            st.enter_context(patch.object(mr,'MON',Path(tmp)))
            st.enter_context(patch.object(mr,'WATCH',{'clinicaltrials':[{'id':RID,'name':'RX-TEST'}]}))
            st.enter_context(patch.object(mr,'pubmed_search',return_value=[]))
            scan=st.enter_context(patch.object(mr,'ctg_snapshot',return_value=snapshot()))
            mr.main(); first=json.loads(state.read_text())['clinicaltrials'][RID]
            scan.side_effect=TimeoutError('synthetic');mr.main()
            self.assertEqual(json.loads(state.read_text())['clinicaltrials'][RID],first)
            self.assertEqual(json.loads(report.read_text())['substantive_changes'],[])
            scan.side_effect=None;scan.return_value=snapshot('SUSPENDED','2026-09-18T06:00:00+00:00');mr.main()
            last=json.loads(report.read_text());self.assertEqual(len(last['substantive_changes']),1)
            feed=pub.empty_feed();pub.apply_daily(feed,last)
            self.assertEqual(feed['trial_overrides'][RID]['status'],'SUSPENDED')

    def test_http_200_empty_or_wrong_id_is_not_success(self):
        for payload in ({}, {'protocolSection':{'identificationModule':{'nctId':'NCT00000000'},'statusModule':{'overallStatus':'RECRUITING'}}}):
            with patch.object(mr,'fetch_json',return_value=payload),self.assertRaises(ValueError):mr.ctg_snapshot(RID)

    def test_ctis_multiple_historical_statuses_stay_unknown(self):
        self.assertIsNone(mr.parse_status('History: Authorised. Ongoing, recruiting. Ended.'))
        self.assertEqual(mr.parse_status('Trial status: Ongoing, recruiting | History: Authorised'),'Ongoing, recruiting')
        self.assertEqual(mr.parse_status('Not authorised'),'Not authorised')

    def test_ctis_mirror_only_is_not_authoritative(self):
        def get(url,*a):
            if 'euclinicaltrials.eu' in url: raise TimeoutError()
            return b'<p>Ongoing, recruiting</p>'
        with patch.object(mr,'fetch',side_effect=get):s=mr.ctis_snapshot('2025-522922-11-00')
        self.assertIsNone(s['status']);self.assertIsNone(s['temporary_halt'])
        self.assertFalse(pub.valid_observation(s))

    def test_missing_location_fields_do_not_refresh_old_access(self):
        feed=pub.empty_feed()
        old=snapshot(sites=[{'id':'TEST','facility':'TEST centre','status':'RECRUITING'}])
        pub.apply_daily(feed,{'observations':[old]})
        new=snapshot(when='2026-09-18T06:00:00+00:00')
        pub.apply_daily(feed,{'observations':[new]})
        o=feed['trial_overrides'][RID]
        self.assertEqual(o['field_observed_at']['greece_locations'],WHEN)
        self.assertFalse(o['locations_complete'])
        answer=browser(feed,'accessCard(input)')
        self.assertTrue(answer['ok']);self.assertNotIn('1 καταχωρισμένα ελληνικά',answer['value']['title'])

    def test_invalid_status_or_null_after_is_never_published(self):
        for value in (None,False,'MAGIC_REMYELINATION'):
            obs=snapshot(value)
            c=mr.change('RX-TEST','ClinicalTrials.gov','Human trial registration','Primary registry','status',
                        'RECRUITING',value,URL,'Synthetic',observation=obs)
            feed=pub.empty_feed();pub.apply_daily(feed,{'substantive_changes':[c]})
            self.assertEqual(feed['events'],[])

    def test_final_boundary_rejects_tampered_observation(self):
        s=snapshot('SUSPENDED')
        c=mr.change('RX-TEST','ClinicalTrials.gov','Human trial registration','Primary registry','status',
                     'RECRUITING','COMPLETED',URL,'Synthetic',observation=s)
        self.assertFalse(pub.validated_change(c))
        s['provenance']['id']='NCT00000000';self.assertFalse(pub.valid_observation(s))

    def test_stale_policy_or_missing_provenance_rejected(self):
        for mutate in (lambda c:c.pop('source_record'),lambda c:c.update(policy_version='old'),lambda c:c.update(score='100')):
            c=candidate();mutate(c);self.assertIsNone(pub.validated_candidate(c))
        self.assertIsNotNone(pub.validated_candidate(candidate()))

    def test_secondary_mirror_link_cannot_claim_primary_authority(self):
        c=candidate();c.update(source='EU CTIS discovery',source_quality='Discovery via CTIS.eu; official record linked')
        self.assertIsNone(pub.validated_candidate(c))

    def test_primary_url_identity_uses_path_not_query_spoof(self):
        self.assertTrue(primary_registry_url(RID,URL))
        for url in ('https://clinicaltrials.gov.evil.test/study/'+RID,
                    'https://clinicaltrials.gov/study/NCT00000000?ref='+RID,
                    'https://evil.test/'+RID):self.assertFalse(primary_registry_url(RID,url))

    def test_human_cells_randomized_mouse_trial_stays_preclinical(self):
        x=evidence_context('Patient-derived cells in mice; randomized controlled trial in mouse models.')
        self.assertFalse(x['human_data']);self.assertEqual(x['study_population'],'preclinical_models')
        x=evidence_context('We enrolled 40 patients with multiple sclerosis.',preprint=True)
        self.assertTrue(x['human_data']);self.assertEqual(x['publication_status'],'preprint')

    def test_review_is_not_original_clinical_data(self):
        x=evidence_context('The trials enrolled 200 patients with multiple sclerosis.', ['Systematic Review'])
        self.assertFalse(x['human_data']);self.assertEqual(x['study_population'],'secondary_literature')

    def test_novel_registry_targets_adopted_without_code_change(self):
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[candidate()]})
        watch=mr.adopt_targets({'clinicaltrials':[]},feed['watch_targets'])
        self.assertEqual(watch['clinicaltrials'][0]['id'],RID)
        self.assertEqual(watch['clinicaltrials'][0]['initial_snapshot']['status'],'RECRUITING')
        again=mr.adopt_targets(watch,feed['watch_targets']);self.assertEqual(len(again['clinicaltrials']),1)
        mr.adopt_targets(watch,{'NCT00000001':{'verified':True,'url':'https://evil.test'}})
        self.assertEqual(len(watch['clinicaltrials']),1)

    def test_adopted_first_poll_detects_immediate_transition(self):
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[candidate()]})
        initial=feed['watch_targets'][RID]['initial_snapshot']
        changes=mr.compare_ctg('RX-TEST',initial,snapshot('SUSPENDED'))
        self.assertTrue(any(c['field']=='status' for c in changes))

    def test_different_trials_same_programme_not_collapsed_in_public_cards(self):
        a=candidate('NCT09999991','Lucid-MS Phase 2 remyelination in multiple sclerosis')
        b=candidate('NCT09999992','Lucid-MS Phase 3 remyelination in multiple sclerosis')
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[a,b]})
        self.assertEqual(len(feed['programmes']),2)
        out=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed).pipeline.filter(x=>x.live_id)')
        self.assertTrue(out['ok']);self.assertEqual(len(out['value']),2)

    def test_rejected_pending_and_changed_published_journal(self):
        state={'seen':{'test':[]},'records':{}}
        c=candidate();first=journal.collect_source(state,'test',[c]);self.assertEqual(len(first),1)
        journal.set_disposition(state,first[0],'quarantined')
        again=journal.collect_source(state,'test',[c]);self.assertEqual(len(again),1)
        journal.set_disposition(state,again[0],'published')
        self.assertEqual(journal.collect_source(state,'test',[c]),[])
        changed=copy.deepcopy(c);changed['meta']['status']='SUSPENDED'
        self.assertEqual(len(journal.collect_source(state,'test',[changed])),1)

    def test_empty_failed_source_is_not_baseline(self):
        state={'seen':{}}
        journal.collect_source(state,'test',[],healthy=False)
        self.assertNotIn('test',state['seen'])
        self.assertEqual(journal.collect_source(state,'test',[candidate()]),[])
        self.assertIn('test',state['seen'])

    def test_legacy_seen_migration_is_silent_once(self):
        c=candidate();key=c['source']+'::'+c['id'];state={'seen':{'test':[key]}}
        self.assertEqual(journal.collect_source(state,'test',[c]),[])
        c['meta']['status']='SUSPENDED';self.assertEqual(len(journal.collect_source(state,'test',[c])),1)

    def test_policy_change_reconsiders_without_flooding_same_events(self):
        c=candidate();state={'seen':{'test':[]}};out=journal.collect_source(state,'test',[c])
        journal.set_disposition(state,out[0],'published')
        state['records'][out[0]['_record_key']]['policy_version']='previous'
        self.assertEqual(len(journal.collect_source(state,'test',[c])),1)
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[c]})
        first=copy.deepcopy(feed['events'])
        c['source_record']['fetched_at']='2026-09-18T06:00:00+00:00'
        pub.apply_weekly(feed,{'candidates':[c]});self.assertEqual(feed['events'],first)

    def test_warning_does_not_change_scientific_freshness(self):
        feed=pub.empty_feed();feed['latest_event_at']=WHEN
        pub.quarantine_warnings(feed,{'generated_at':'2026-09-19','warnings':['Synthetic timeout']},'daily')
        self.assertEqual(feed['latest_event_at'],WHEN);self.assertEqual(feed['events'],[])

    def test_out_of_order_snapshot_cannot_revert_current_status(self):
        feed=pub.empty_feed();pub.apply_daily(feed,{'observations':[snapshot('SUSPENDED','2026-09-19T06:00:00+00:00')]})
        pub.apply_daily(feed,{'observations':[snapshot('RECRUITING',WHEN)]})
        self.assertEqual(feed['trial_overrides'][RID]['status'],'SUSPENDED')

    def test_invalid_feed_child_and_unsupported_version_fallback_unchanged(self):
        for feed in ({'version':2,'events':[None]}, {'version':3,'events':[]}, {'version':2,'programmes':{}},
                     {'version':2,'events':[{'id':'x','title':'x','date':'2026-09-17','url':'javascript:alert(1)'}]}):
            out=browser({'base':self.base,'feed':feed},'mergeLiveData(input.base,input.feed)')
            self.assertTrue(out['ok']);self.assertEqual(out['value']['items'],self.base['items'])

    def test_merge_does_not_mutate_base(self):
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[candidate()]})
        out=browser({'base':self.base,'feed':feed},'(()=>{const before=JSON.stringify(input.base);mergeLiveData(input.base,input.feed);return before===JSON.stringify(input.base)})()')
        self.assertTrue(out['value'])

    def test_bad_existing_override_rejected_before_store(self):
        feed=pub.empty_feed();feed['trial_overrides'][RID]={'status':None}
        with self.assertRaises(ValueError):validate_feed(feed)

    def test_rss_contains_live_metadata_and_xml_escapes(self):
        c=candidate(title='RX-TEST & <myelin> Phase 2 remyelination in multiple sclerosis')
        feed=pub.empty_feed();pub.apply_weekly(feed,{'candidates':[c]})
        rss=store.rss_for_feed(feed)
        self.assertIn('&amp;',rss);self.assertIn('&lt;myelin&gt;',rss)
        self.assertIn(feed['events'][0]['id'],rss)
        import xml.etree.ElementTree as ET
        self.assertEqual(ET.fromstring(rss).tag,'rss')

    def test_concurrent_other_writer_reloads_and_merges_atomically(self):
        report={'policy_version':POLICY_VERSION,'generated_at':WHEN,'candidates':[candidate()]}
        initial=pub.empty_feed();other=pub.empty_feed()
        pub.apply_weekly(other,{'candidates':[candidate('NCT09999997')]})
        bundles=[{'sha':'base1','tree':'tree1','feed':initial},{'sha':'base2','tree':'tree2','feed':other}]
        posts=[];patch_count=0
        def api(url,token,method='GET',body=None):
            nonlocal patch_count
            if method=='POST' and url.endswith('/git/trees'):
                posts.append(copy.deepcopy(body));return {'sha':'merged-tree'}
            if method=='POST' and url.endswith('/git/commits'):return {'sha':'candidate-commit'}
            if method=='PATCH':
                patch_count+=1
                if patch_count==1:raise urllib.error.HTTPError(url,409,'race',{},None)
                self.assertFalse(body['force']);return {}
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as st:
            tmp=Path(tmp);(tmp/'monitor').mkdir()
            st.enter_context(patch.object(store,'ROOT',tmp))
            st.enter_context(patch.object(store,'read_bundle',side_effect=bundles))
            st.enter_context(patch.object(store,'read_json_at',return_value=None))
            st.enter_context(patch.object(store,'rss_for_feed',side_effect=lambda d:json.dumps([x['id'] for x in d['events']])))
            st.enter_context(patch.object(store,'api_request',side_effect=api))
            store.publish_transaction('test/repo','DUMMY','weekly',report,{'version':2,'seen':{}},sleeper=lambda _:None)
        files={x['path']:x['content'] for x in posts[-1]['tree']}
        feed=json.loads(files['live-feed.json'])
        self.assertEqual(len(feed['events']),2)
        self.assertEqual(set(json.loads(files['rss.xml'])),{x['id'] for x in feed['events']})
        self.assertIn('discovery-state.json',files)

    def test_same_mode_journal_race_is_not_overwritten(self):
        with patch.object(store,'read_bundle',return_value={'sha':'x','tree':'t','feed':pub.empty_feed()}),\
             patch.object(store,'read_json_at',return_value={'version':2,'newer':True}),\
             patch.object(store,'api_request') as api,self.assertRaises(RuntimeError):
            store.publish_transaction('test/repo','DUMMY','daily',{'observations':[]},{'_journal_base':'older'})
        api.assert_not_called()

    def test_network_error_does_not_acknowledge_local_journal(self):
        state={'version':2,'seen':{},'records':{}}
        original=copy.deepcopy(state)
        with patch.object(store,'read_bundle',return_value={'sha':'x','tree':'t','feed':pub.empty_feed()}),\
             patch.object(store,'read_json_at',return_value=None),\
             patch.object(store,'api_request',side_effect=TimeoutError()),\
             self.assertRaises(TimeoutError):
            store.publish_transaction('test/repo','DUMMY','weekly',{'candidates':[candidate()]},state,sleeper=lambda _:None)
        self.assertEqual(state,original)

    def test_development_cannot_publish_production_feed(self):
        with patch.dict('os.environ',{'GITHUB_REF':'refs/heads/development','MSNEWS_PUBLISH_MODE':'daily'}),self.assertRaises(SystemExit):pub.main()


if __name__=='__main__': unittest.main(verbosity=2)
