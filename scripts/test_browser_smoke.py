#!/usr/bin/env python3
"""Real Chromium smoke tests of dist. Synthetic payloads stay local/route-mocked."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright
    from research_contract import now_iso, source_record
    from publish_live_feed import empty_feed, apply_daily
    from monitor_research import change
    rid='NCT05359653'
    registry_url=f'https://clinicaltrials.gov/study/{rid}'
    snapshot={'id':rid,'name':'ReVIVE','source':'ClinicalTrials.gov','url':registry_url,'status':'TERMINATED',
              'greece_sites':0,'greece_locations':[],'countries':['United States'],'locations_complete':True,
              'observation_valid':True,'provenance':source_record(rid,registry_url,{'status':'TERMINATED'})}
    feed=empty_feed()
    c=change('ReVIVE','ClinicalTrials.gov','Human trial registration','Primary trial registry',
             'status','RECRUITING','TERMINATED',registry_url,
             'Synthetic test only; no efficacy conclusion.',observation=snapshot)
    apply_daily(feed,{'generated_at':now_iso(),'baseline':False,'observations':[snapshot],'substantive_changes':[c]})
    feed['latest_event_at']=now_iso()
    with sync_playwright() as p:
        executable=os.environ.get('MSNEWS_CHROMIUM')
        if not executable and Path('/usr/bin/chromium').exists():executable='/usr/bin/chromium'
        browser=p.chromium.launch(**({'executable_path':executable} if executable else {}),args=['--no-sandbox'])
        scenarios=0
        for viewport in ({'width':1440,'height':900},{'width':390,'height':844}):
            for case in ('baseline','valid-live','malformed','outage'):
                context=browser.new_context(viewport=viewport)
                # Never navigate or make network requests. Render the actual built
                # HTML/CSS/JS in a blank Chromium document with a mocked fetch boundary.
                import re
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                html=(ROOT/'dist/index.html').read_text()
                html=re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S|re.I)
                html=re.sub(r'<link\b[^>]*>', '', html, flags=re.I)
                context.route('**/*',lambda route:route.abort())
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'dist/styles.css').read_text())
                obj=feed if case=='valid-live' else ({'version':2,'events':{}} if case=='malformed' else empty_feed())
                page.evaluate("""({base,live,outage})=>{window.fetch=async url=>{
                    if(url==='/news.json')return {ok:true,text:async()=>JSON.stringify(base)};
                    if(outage)throw new Error('Synthetic local outage');
                    return {ok:true,text:async()=>JSON.stringify(live)};
                }}""", {'base':json.loads((ROOT/'dist/news.json').read_text()),'live':obj,'outage':case=='outage'})
                page.add_script_tag(content=(ROOT/'dist/app.js').read_text())
                page.wait_for_selector('#pipeline .pipeline-card')
                assert not errors,errors
                assert page.locator('#greece-news').inner_text().strip()
                assert 'δεν αποδεικνύει' in page.locator('#greece-news').inner_text()
                if case=='valid-live':
                    assert page.locator('#pipeline h3').filter(has_text='ReVIVE').count()==0
                    assert page.locator('#readouts h3').filter(has_text='ReVIVE').count()==1
                    assert 'TERMINATED' in page.locator('#readouts').inner_text()
                    assert 'Αυτόματη ενημέρωση' in page.locator('#news').inner_text() or 'LIVE AUTO' in page.locator('#news').inner_text()
                else:
                    assert page.locator('#pipeline h3').filter(has_text='ReVIVE').count()==1
                if case in ('outage','malformed'):
                    assert 'αρχικό' in page.locator('#feed-health').inner_text()
                # Header links point to real sections, no malformed in-page navigation.
                for href in page.locator('header a[href^="#"]').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))'):
                    assert href=='#' or page.locator(href).count()==1,href
                # All content/data strings are escaped and untrusted URLs cannot execute code.
                assert page.locator('a[href^="javascript:"]').count()==0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),(viewport,case,'page horizontal overflow')
                scenarios+=1;context.close()
        browser.close()
    print(f'Chromium smoke: {scenarios} desktop/mobile scenarios passed; all external research requests mocked; no public writes.')
    return 0

if __name__=='__main__':raise SystemExit(main())
