const monthNames=['Ιαν','Φεβ','Μαρ','Απρ','Μάι','Ιουν','Ιουλ','Αυγ','Σεπ','Οκτ','Νοε','Δεκ'];
const formatDate=s=>{const [y,m,d]=String(s||'').slice(0,10).split('-').map(Number);return y&&m&&d?`${d} ${monthNames[m-1]} ${y}`:'—'};
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const norm=s=>String(s??'').toLowerCase().replace(/[^a-z0-9α-ω]+/g,' ').trim();
const LIVE_FEED_URL='https://raw.githubusercontent.com/fokas-hoa/msnewsfetch/live-data/live-feed.json';
let data;

function category(item){
  if(item.signal==='Αρνητικό') return 'negative';
  if(item.human_data===true) return 'human';
  const population=String(item.study_population||'');
  if(population==='preclinical_models') return 'preclinical';
  const stage=String(item.stage||'').toLowerCase();
  if(stage.includes('προκλιν')||stage.includes('μεταφρα')) return 'preclinical';
  if(stage.includes('προδημο')) return 'unknown';
  if(item.human_data===false||population==='not_established') return 'unknown';
  return 'human';
}
const safeURL=u=>{try{const x=new URL(String(u));return x.protocol==='https:'&&!x.username&&!x.password?x.href:'#'}catch{return '#'}};

function renderSources(sources=[]){
  if(!sources.length) return '';
  return `<div class="source-row">${sources.map(s=>`<a class="source" href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a>`).join('')}</div>`;
}

function renderGreece(){
  const host=document.querySelector('#greece-news');
  if(!host) return;
  const items=data.greece||[];
  host.innerHTML=items.map(item=>`<article class="greece-card${item.featured?' featured':''}">
    <div class="greece-top"><span class="greece-kicker">${esc(item.kicker)}</span><span class="date">${formatDate(item.date)}</span></div>
    <h3>${esc(item.title)}</h3>
    <div class="greece-labels"><span class="badge">${esc(item.status)}</span><span class="evidence-pill">${esc(item.evidence)}</span>${item.auto_published?'<span class="badge">LIVE AUTO</span>':''}</div>
    <p>${esc(item.summary)}</p>
    <p class="meaning"><strong>Τι σημαίνει για ασθενή στην Ελλάδα:</strong> ${esc(item.meaning)}</p>
    <p class="source-quality"><strong>Ποιότητα πηγής:</strong> ${esc(item.sourceQuality)}</p>
    ${renderSources(item.sources)}
  </article>`).join('');
}

function render(filter='all'){
  const host=document.querySelector('#news');
  const items=(data.items||[]).filter(x=>filter==='all'||category(x)===filter).sort((a,b)=>String(b.date).localeCompare(String(a.date)));
  host.innerHTML=items.map(item=>`<article class="news-card" data-category="${category(item)}">
    <div class="meta"><div class="date">${formatDate(item.date)}</div><div class="badge">${esc(item.stage)}</div><div class="badge ${item.signal==='Αρνητικό'?'negative':''}">${esc(item.signal)}</div>${item.auto_published?'<div class="badge">LIVE AUTO</div>':''}<div class="evidence-text">${esc(item.evidence)}</div></div>
    <div><h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p><p class="meaning"><strong>Τι σημαίνει:</strong> ${esc(item.meaning)}</p><p class="source-quality"><strong>Ποιότητα πηγής:</strong> ${esc(item.sourceQuality)}</p><a class="source" href="${esc(safeURL(item.url))}" target="_blank" rel="noopener noreferrer">Πηγή: ${esc(item.source)} ↗</a><div class="tags">${(item.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div>
  </article>`).join('');
}

function mergeUnique(primary=[],secondary=[],keyFn){
  const seen=new Set(),out=[];
  for(const item of [...primary,...secondary]){const key=keyFn(item);if(key&&!seen.has(key)){seen.add(key);out.push(item)}}
  return out;
}
const idsFrom=x=>Array.from(new Set(String(x||'').match(/\b(?:NCT\d{8}|20\d{2}-\d{6}-\d{2}-\d{2}|ACTRN\d{14}[A-Z]?|ISRCTN\d{8})\b/gi)||[])).map(x=>x.toUpperCase());
const cardIDs=x=>(Array.isArray(x.record_ids)?x.record_ids:idsFrom(x.url));
const terminal=s=>['COMPLETED','TERMINATED','WITHDRAWN','ENDED','EARLY TERMINATED'].includes(String(s||'').toUpperCase());
const object=x=>!!x&&typeof x==='object'&&!Array.isArray(x);
const str=x=>typeof x==='string';
const urlOK=x=>str(x)&&/^https:\/\//i.test(x)&&!/[\s<>]/.test(x)&&!/^https:\/\/[^/]*@/.test(x);
const listStrings=x=>Array.isArray(x)&&x.every(str);
function validLive(live){
  if(!object(live)||![1,2].includes(live.version)) return false;
  for(const k of ['events','programmes','quarantine']) if(live[k]!==undefined&&!Array.isArray(live[k])) return false;
  for(const k of ['trial_overrides','programme_overrides','watch_targets','source_health']) if(live[k]!==undefined&&!object(live[k])) return false;
  if(live.version===1) return !['events','programmes','programme_overrides'].some(k=>Object.keys(live[k]||{}).length);
  if((live.events||[]).length>1000||(live.programmes||[]).length>2000) return false;
  for(const e of live.events||[]){
    if(!object(e)||!str(e.id)||!str(e.title)||!urlOK(e.url)||!/^\d{4}-\d{2}-\d{2}$/.test(e.date)||!listStrings(e.tags||[])||!listStrings(e.record_ids||[])) return false;
    for(const k of ['summary','meaning','stage','evidence','sourceQuality','source']) if(!str(e[k])) return false;
  }
  for(const p of live.programmes||[]){
    if(!object(p)||!str(p.id)||!str(p.name)||!urlOK(p.url)||!listStrings(p.record_ids||[])) return false;
  }
  for(const [rid,o] of Object.entries(live.trial_overrides||{})){
    if(!object(o)||!str(o.status)||!str(o.updated_at)||!urlOK(o.url)||o.record_id!==rid) return false;
    if(!object(o.provenance)||o.provenance.verified!==true||o.provenance.url!==o.url) return false;
    if(o.greece_locations!==undefined&&(!Array.isArray(o.greece_locations)||o.greece_locations.some(x=>!object(x)))) return false;
    if(o.countries!==undefined&&!listStrings(o.countries)) return false;
  }
  return true;
}
function liveEventToItem(x){return {...x,auto_published:true,live_id:x.id}}
function liveEventToGreece(x){return {...x,kicker:'LIVE • ΑΥΤΟΜΑΤΗ ΕΝΗΜΕΡΩΣΗ',status:x.signal||'Ενημέρωση',sources:[{label:x.source,url:x.url}],featured:true,auto_published:true,live_id:x.id}}
function programmeKey(x){const ids=cardIDs(x);return ids.length?'trial:'+ids.join('|'):'programme:'+(x.id||x.canonical_id||norm(x.name))}
function liveProgrammeToCard(p){return {...p,live_id:p.id,auto_published:true}}
function applyOverrides(list,overrides={},sourceHealth={}){
  return (list||[]).map(item=>{
    const identities=cardIDs(item);
    const matches=identities.map(id=>overrides[id]).filter(Boolean);
    if(!matches.length) return {...item};
    // Respect the registry scope of the baseline card URL. Keep other registry
    // observations visible; different global/EU scopes are not silently equated.
    const preferred=idsFrom(item.url)[0];
    const selected=matches.find(x=>x.record_id===preferred)||matches[0];
    const out={...item,status:selected.status,operational_status:selected.status,
      registry_observations:matches,registry_updated_at:selected.updated_at,
      source_unavailable:sourceHealth[selected.record_id]?.state==='unavailable'};
    out.baseline_status=item.baseline_status||item.status;
    out.baseline_evidence=item.baseline_evidence||item.evidence;
    if(item.readout_summary) out.readout_summary=item.readout_summary;
    out.evidence='Πρωτογενής καταχώριση δοκιμής • η λειτουργική κατάσταση δεν αποτελεί απόδειξη αποτελεσματικότητας.';
    out.nextLabel='Παρακολούθηση';
    out.next=terminal(selected.status)?'Η μελέτη δεν εμφανίζεται ως ενεργή. Η ολοκλήρωση ή διακοπή δεν είναι από μόνη της επιστημονικό αποτέλεσμα.':
      'Η πρόσβαση εξαρτάται από την τοπική στρατολόγηση και το πρωτόκολλο. Δεν συνάγεται δυνατότητα συμμετοχής από το γενικό status.';
    if(Array.isArray(selected.countries)) out.geography=selected.countries.join(', ');
    if(selected.greece_locations&&selected.locations_complete===true){
      const recruiting=selected.greece_locations.filter(x=>x.status==='RECRUITING').length;
      out.geography=(out.geography?out.geography+' • ':'')+`Ελληνικά κέντρα στη λίστα: ${selected.greece_locations.length}, με τοπική ένδειξη Recruiting: ${recruiting}`;
    }
    if(selected.status_conflict) out.registry_conflict=`Επίσημο CTIS: ${selected.official_status}. Mirror (τελευταία διαθέσιμη παρατήρηση ${formatDate(selected.field_observed_at?.mirror_status)}): ${selected.mirror_status}. Διαφωνία πηγών — το mirror δεν αντικαθιστά την επίσημη παρατήρηση.`;
    return out;
  });
}
function accessCard(live){
  const observations=Object.values(live.trial_overrides||{});
  const checked=observations.filter(x=>x.locations_complete===true&&Array.isArray(x.greece_locations));
  const fresh=x=>Date.now()-Date.parse(x.field_observed_at?.greece_locations||x.updated_at)<7*86400000&&live.source_health?.[x.record_id]?.state!=='unavailable';
  const sites=checked.flatMap(x=>(fresh(x)&&x.status==='RECRUITING')?x.greece_locations.filter(y=>y.status==='RECRUITING').map(y=>({...y,trial:x})):[]);
  const seenDate=checked.map(x=>x.updated_at).sort().pop()||'';
  return {date:seenDate.slice(0,10),kicker:'ΠΡΟΣΒΑΣΗ ΣΤΗΝ ΕΛΛΑΔΑ',featured:true,
    title:sites.length?`${sites.length} καταχωρισμένα ελληνικά κέντρα φέρουν ένδειξη Recruiting`:'Η διαθέσιμη πληροφόρηση για συμμετοχή από την Ελλάδα',
    status:'Μόνο επιβεβαιωμένες παρατηρήσεις μητρώων',evidence:'Καταχωρίσεις ανθρώπινων δοκιμών — όχι κλινικό όφελος',
    summary:sites.length?sites.map(s=>`${s.facility||s.city||'Ελληνικό κέντρο'} (${s.trial.record_id})`).join(' • '):
      'Δεν έχει επιβεβαιωθεί από τις πρόσφατες επιτυχείς αναγνώσεις ενεργό ελληνικό κέντρο. Αυτό δεν αποδεικνύει ότι δεν υπάρχει διαθέσιμη μελέτη.',
    meaning:'Το συνολικό Recruiting, η έγκριση στην ΕΕ ή η αναφορά Greece δεν εγγυώνται ελληνική στρατολόγηση. Επιβεβαίωσε διαθεσιμότητα και επιλεξιμότητα με το κέντρο. '+
      `Δοκιμές με δομημένη λίστα κέντρων στον αυτόματο έλεγχο: ${checked.length}. Μη προσδιορισμένη ή μη διαθέσιμη πληροφορία: ${observations.length-checked.length}.`,
    sourceQuality:'Πρωτογενείς καταχωρίσεις, με ημερομηνία ανάγνωσης. Ελλιπής κάλυψη πηγών δεν αντιμετωπίζεται ως απουσία μελετών.',
    sources:sites.slice(0,6).map(s=>({label:s.trial.record_id,url:s.trial.url}))};
}
function mergeLiveData(base,live){
  if(!validLive(live)) return base;
  const out=JSON.parse(JSON.stringify(base));
  out.items=mergeUnique((live.events||[]).map(liveEventToItem),out.items||[],x=>x.live_id||`${x.url}|${x.title}`);
  out.greeceArchive=(out.greece||[]).filter(x=>x.historical_access_snapshot);
  let greek=(out.greece||[]).filter(x=>!x.historical_access_snapshot);
  const liveGreek=(live.events||[]).filter(x=>x.greece_priority);
  // Only the latest observation for a given trial/field appears as current Greek
  // news. Older observations remain in the chronological history, not as advice.
  const latest=mergeUnique([...liveGreek].sort((a,b)=>String(b.observed_at).localeCompare(String(a.observed_at))),[],x=>(x.record_ids||[]).join('|')+'|'+(x.field||x.id));
  out.greece=[accessCard(live),...latest.map(liveEventToGreece),...greek];
  const groups=['pipeline','translational','readouts'];
  for(const g of groups) out[g]=out[g]||[];
  for(const p of live.programmes||[]){
    const ids=cardIDs(p);
    let exists=false;
    for(const group of groups){
      const index=out[group].findIndex(x=>ids.length?cardIDs(x).some(id=>ids.includes(id)):programmeKey(x)===programmeKey(p));
      if(index>=0){exists=true;break;}
    }
    if(!exists) out[p.human?'pipeline':'translational'].push(liveProgrammeToCard(p));
  }
  for(const g of groups) out[g]=applyOverrides(out[g],live.trial_overrides||{},live.source_health||{});
  const ended=out.pipeline.filter(x=>terminal(x.operational_status));
  out.pipeline=out.pipeline.filter(x=>!terminal(x.operational_status));
  out.readouts=mergeUnique(out.readouts,ended,programmeKey);
  out.sourceHealth=live.source_health||{};
  out.liveFeedUpdated=live.updated_at||null;
  out.latestEventAt=live.latest_event_at||null;
  if(live.latest_event_at&&live.latest_event_at.slice(0,10)>String(out.siteUpdated||'')) out.siteUpdated=live.latest_event_at.slice(0,10);
  return out;
}
async function fetchJson(url,opts={}){
  // A hard promise deadline also protects against a fetch mock/connection that
  // never resolves; abort releases the request in a real browser.
  const controller=typeof AbortController!=='undefined'?new AbortController():null;
  let timer;
  const request=(async()=>{const response=await fetch(url,{...opts,...(controller?{signal:controller.signal}:{})});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const text=await response.text();if(text.length>5000000) throw new Error('Feed exceeds size bound');return JSON.parse(text)})();
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller?.abort();reject(new Error('Feed timeout'))},8000)});
  try{return await Promise.race([request,deadline])}finally{clearTimeout(timer)}
}
async function loadData(){
  const base=await fetchJson('/news.json');
  let live=null,health='baseline';
  try{
    live=await fetchJson(`${LIVE_FEED_URL}?v=${Math.floor(Date.now()/300000)}`,{cache:'no-store'});
    if(!validLive(live)) throw new Error('Invalid live feed');
    health='live';
    try{localStorage.setItem('msnews-validated-feed-v2',JSON.stringify(live))}catch{}
  }catch(err){
    console.warn('MSNewsFetch: preserving last validated data.',err);
    try{const cached=JSON.parse(localStorage.getItem('msnews-validated-feed-v2'));if(validLive(cached)){live=cached;health='cached'}}catch{}
  }
  let result;
  try{result=mergeLiveData(base,live)}catch(err){console.warn('Invalid feed projection; baseline retained.',err);result=base;health='baseline'}
  // Baseline access snapshots are historical even before the first v2 publication.
  if(!result.greeceArchive){result={...result,greeceArchive:(result.greece||[]).filter(x=>x.historical_access_snapshot),greece:[accessCard({}),...(result.greece||[]).filter(x=>!x.historical_access_snapshot)]}}
  result.feedHealth=health;
  return result;
}

if(typeof document!=='undefined') loadData().then(json=>{
  data=json;
  document.querySelector('#updated').textContent=formatDate(data.siteUpdated);
  const health=document.querySelector('#feed-health');
  if(health) health.textContent=data.feedHealth==='live'?'Ζωντανό feed · τα νέα διαχωρίζονται από τις τεχνικές ανανεώσεις.':(data.feedHealth==='cached'?'Η ζωντανή πηγή δεν είναι διαθέσιμη. Εμφανίζεται το τελευταίο έγκυρο αποθηκευμένο feed.':'Εμφανίζεται το αρχικό χρονολογημένο στιγμιότυπο. Δεν έχει φορτωθεί έγκυρο ζωντανό feed.');
  const unavailable=Object.entries(data.sourceHealth||{}).filter(([id,h])=>h?.state==='unavailable').map(([id])=>id);
  if(health&&unavailable.length) health.textContent+=` Μη διαθέσιμη πρόσφατη ανάγνωση σε ${unavailable.length} καταχωρίσεις: ${unavailable.join(', ')}. Δεν συνάγεται αλλαγή μελέτης.`;
  const renderTrialCard=x=>`<article class="pipeline-card"><div class="phase">${esc(x.phase)}</div><h3>${esc(x.name)}</h3><div class="candidate">${esc(x.candidate)}</div><div class="status">${esc(x.status)}</div>${x.readout_summary?`<p class="meaning"><strong>Ερευνητικό αποτέλεσμα:</strong> ${esc(x.readout_summary)}</p>`:''}${x.registry_conflict?`<p class="meaning"><strong>Διαφωνία πηγών:</strong> ${esc(x.registry_conflict)}</p>`:''}${x.registry_observations?.length>1?`<details><summary>Καταχωρίσεις ανά μητρώο — διαφορετικό πεδίο κάλυψης</summary>${x.registry_observations.map(o=>`<p>${esc(o.record_id)}: ${esc(o.status)} (${formatDate(o.updated_at)}) <a href="${esc(safeURL(o.url))}" rel="noopener noreferrer" target="_blank">Μητρώο ↗</a></p>`).join('')}</details>`:''}${x.registry_updated_at?`<p class="source-quality">Ανάγνωση μητρώου: ${formatDate(x.registry_updated_at)}${x.source_unavailable?' • Η πιο πρόσφατη προσπάθεια ανάγνωσης απέτυχε — διατηρείται η προηγούμενη παρατήρηση.':''}</p>`:''}${x.geography?`<div class="geography">${esc(x.geography)}</div>`:''}${x.evidence?`<div class="card-evidence"><strong>Evidence:</strong> ${esc(x.evidence)}</div>`:''}<div class="next"><strong>${esc(x.nextLabel||'Επόμενο')}:</strong> ${esc(x.next)}</div>${x.url?`<a class="trial-link" href="${esc(safeURL(x.url))}" target="_blank" rel="noopener noreferrer">Registry / source ↗</a>`:''}</article>`;
  renderGreece();
  document.querySelector('#pipeline').innerHTML=(data.pipeline||[]).map(renderTrialCard).join('');
  document.querySelector('#translational').innerHTML=(data.translational||[]).map(renderTrialCard).join('');
  document.querySelector('#readouts').innerHTML=(data.readouts||[]).map(renderTrialCard).join('');
  render();
  document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.filter').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    render(btn.dataset.filter);
  }));
}).catch(()=>{
  document.querySelector('#news').innerHTML='<p>Δεν ήταν δυνατή η φόρτωση του feed.</p>';
  const gh=document.querySelector('#greece-news');
  if(gh) gh.innerHTML='<p>Δεν ήταν δυνατή η φόρτωση της ενημέρωσης για την Ελλάδα.</p>';
});
