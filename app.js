const monthNames=['Ιαν','Φεβ','Μαρ','Απρ','Μάι','Ιουν','Ιουλ','Αυγ','Σεπ','Οκτ','Νοε','Δεκ'];
const formatDate=s=>{const [y,m,d]=String(s||'').slice(0,10).split('-').map(Number);return y&&m&&d?`${d} ${monthNames[m-1]} ${y}`:'—'};
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const norm=s=>String(s??'').toLowerCase().replace(/[^a-z0-9α-ω]+/g,' ').trim();
const LIVE_FEED_URL='https://raw.githubusercontent.com/fokas-hoa/msnewsfetch/live-data/live-feed.json';
let data;

function category(item){
  if(item.signal==='Αρνητικό') return 'negative';
  const stage=String(item.stage||'').toLowerCase();
  if(stage.includes('προκλιν')||stage.includes('μεταφρα')||stage.includes('προδημο')) return 'preclinical';
  return 'human';
}

function renderSources(sources=[]){
  if(!sources.length) return '';
  return `<div class="source-row">${sources.map(s=>`<a class="source" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a>`).join('')}</div>`;
}

function renderGreece(){
  const host=document.querySelector('#greece-news');
  if(!host) return;
  const items=(data.greece||[]).sort((a,b)=>String(b.date).localeCompare(String(a.date)));
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
    <div class="meta"><div class="date">${formatDate(item.date)}</div><div class="badge">${esc(item.stage)}</div><div class="badge ${item.signal==='Αρνητικό'?'negative':'positive'}">${esc(item.signal)}</div>${item.auto_published?'<div class="badge">LIVE AUTO</div>':''}<div class="evidence-text">${esc(item.evidence)}</div></div>
    <div><h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p><p class="meaning"><strong>Τι σημαίνει:</strong> ${esc(item.meaning)}</p><p class="source-quality"><strong>Ποιότητα πηγής:</strong> ${esc(item.sourceQuality)}</p><a class="source" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Πηγή: ${esc(item.source)} ↗</a><div class="tags">${(item.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div>
  </article>`).join('');
}

function mergeUnique(primary=[],secondary=[],keyFn){
  const seen=new Set();
  const out=[];
  for(const item of [...primary,...secondary]){
    const key=keyFn(item);
    if(!key||seen.has(key)) continue;
    seen.add(key);out.push(item);
  }
  return out;
}

function liveEventToItem(x){
  return {
    date:x.date,
    stage:x.stage||'Ερευνητική ενημέρωση',
    signal:x.signal||'Ενημέρωση',
    evidence:x.evidence||'Live research signal',
    title:x.title,
    summary:x.summary,
    meaning:x.meaning,
    sourceQuality:x.sourceQuality,
    url:x.url,
    source:x.source,
    tags:x.tags||[],
    auto_published:true,
    live_id:x.id
  };
}

function liveEventToGreece(x){
  return {
    date:x.date,
    kicker:'LIVE • ΑΥΤΟΜΑΤΗ ΕΝΗΜΕΡΩΣΗ',
    title:x.title,
    status:x.signal||'Ενημέρωση',
    evidence:x.evidence||'Live research signal',
    summary:x.summary,
    meaning:x.meaning,
    sourceQuality:x.sourceQuality,
    sources:x.url?[{label:x.source||'Primary source',url:x.url}]:[],
    auto_published:true,
    featured:true,
    live_id:x.id
  };
}

function programmeKey(x){return norm(x.canonical_id||x.name||x.candidate||x.id)}

function applyOverrides(list,overrides={}){
  const entries=Object.entries(overrides).map(([name,value])=>[norm(name),value]);
  return (list||[]).map(item=>{
    const nk=norm(item.name);
    const match=entries.find(([k])=>k===nk);
    if(!match) return item;
    const ov=match[1]||{};
    const merged={...item};
    if(ov.status!==undefined) merged.status=String(ov.status);
    if(ov.greece_sites!==undefined) merged.geography=`${item.geography?item.geography+' • ':''}Greek trial sites: ${ov.greece_sites}`;
    if(ov.greece_mentioned!==undefined) merged.geography=`${item.geography?item.geography+' • ':''}Greece in EU record: ${ov.greece_mentioned?'yes':'no'}`;
    if(ov.temporary_halt!==undefined) merged.status=ov.temporary_halt?'Temporarily halted':merged.status;
    return merged;
  });
}

function liveProgrammeToCard(p){
  return {
    name:p.name,
    candidate:p.candidate||'Automated discovery',
    phase:p.phase||'Research programme',
    status:p.status||'Automatically discovered',
    geography:p.geography||'',
    evidence:`LIVE AUTO • ${p.evidence||'Research discovery'}`,
    nextLabel:p.nextLabel||'Auto watch',
    next:p.next||'Παρακολουθείται αυτόματα για ουσιαστικές αλλαγές.',
    url:p.url||'',
    canonical_id:p.canonical_id,
    live_id:p.id
  };
}

function mergeLiveData(base,live){
  if(!live||typeof live!=='object') return base;
  const events=(live.events||[]).map(liveEventToItem);
  base.items=mergeUnique(events,base.items||[],x=>x.live_id||`${x.url||''}|${x.title||''}`);

  const greek=(live.events||[]).filter(x=>x.greece_priority).map(liveEventToGreece);
  base.greece=mergeUnique(greek,base.greece||[],x=>x.live_id||`${(x.sources&&x.sources[0]?.url)||''}|${x.title||''}`);

  base.pipeline=applyOverrides(base.pipeline||[],live.programme_overrides||{});
  base.translational=applyOverrides(base.translational||[],live.programme_overrides||{});
  base.readouts=applyOverrides(base.readouts||[],live.programme_overrides||{});

  const known=new Set([...(base.pipeline||[]),...(base.translational||[]),...(base.readouts||[])].map(programmeKey));
  for(const p of live.programmes||[]){
    const card=liveProgrammeToCard(p);const k=programmeKey(card);
    if(!k||known.has(k)) continue;
    known.add(k);
    if(p.human) base.pipeline.push(card); else base.translational.push(card);
  }

  const localDate=String(base.siteUpdated||'');
  const liveDate=String(live.updated_at||'').slice(0,10);
  if(liveDate&&liveDate>localDate) base.siteUpdated=liveDate;
  base.liveFeedUpdated=live.updated_at||null;
  return base;
}

async function fetchJson(url,opts={}){
  const response=await fetch(url,opts);
  if(!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function loadData(){
  const base=await fetchJson('/news.json');
  let live=null;
  try{
    const fiveMinuteBucket=Math.floor(Date.now()/300000);
    live=await fetchJson(`${LIVE_FEED_URL}?v=${fiveMinuteBucket}`,{cache:'no-store'});
  }catch(err){
    console.warn('MSNewsFetch live feed unavailable; using deployed baseline.',err);
  }
  return mergeLiveData(base,live);
}

loadData().then(json=>{
  data=json;
  document.querySelector('#updated').textContent=formatDate(data.siteUpdated);
  const renderTrialCard=x=>`<article class="pipeline-card"><div class="phase">${esc(x.phase)}</div><h3>${esc(x.name)}</h3><div class="candidate">${esc(x.candidate)}</div><div class="status">${esc(x.status)}</div>${x.geography?`<div class="geography">${esc(x.geography)}</div>`:''}${x.evidence?`<div class="card-evidence"><strong>Evidence:</strong> ${esc(x.evidence)}</div>`:''}<div class="next"><strong>${esc(x.nextLabel||'Επόμενο')}:</strong> ${esc(x.next)}</div>${x.url?`<a class="trial-link" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">Registry / source ↗</a>`:''}</article>`;
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
