const monthNames=['Ιαν','Φεβ','Μαρ','Απρ','Μάι','Ιουν','Ιουλ','Αυγ','Σεπ','Οκτ','Νοε','Δεκ'];
const formatDate=s=>{const [y,m,d]=s.split('-').map(Number);return `${d} ${monthNames[m-1]} ${y}`};
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
let data;

function category(item){
  if(item.signal==='Αρνητικό') return 'negative';
  if(item.stage==='Προκλινικό'||item.stage==='Μεταφραστικό') return 'preclinical';
  return 'human';
}

function renderSources(sources=[]){
  if(!sources.length) return '';
  return `<div class="source-row">${sources.map(s=>`<a class="source" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a>`).join('')}</div>`;
}

function renderGreece(){
  const host=document.querySelector('#greece-news');
  if(!host) return;
  const items=(data.greece||[]).sort((a,b)=>b.date.localeCompare(a.date));
  host.innerHTML=items.map(item=>`<article class="greece-card${item.featured?' featured':''}">
    <div class="greece-top"><span class="greece-kicker">${esc(item.kicker)}</span><span class="date">${formatDate(item.date)}</span></div>
    <h3>${esc(item.title)}</h3>
    <div class="greece-labels"><span class="badge">${esc(item.status)}</span><span class="evidence-pill">${esc(item.evidence)}</span></div>
    <p>${esc(item.summary)}</p>
    <p class="meaning"><strong>Τι σημαίνει για ασθενή στην Ελλάδα:</strong> ${esc(item.meaning)}</p>
    <p class="source-quality"><strong>Ποιότητα πηγής:</strong> ${esc(item.sourceQuality)}</p>
    ${renderSources(item.sources)}
  </article>`).join('');
}

function render(filter='all'){
  const host=document.querySelector('#news');
  const items=data.items.filter(x=>filter==='all'||category(x)===filter).sort((a,b)=>b.date.localeCompare(a.date));
  host.innerHTML=items.map(item=>`<article class="news-card" data-category="${category(item)}">
    <div class="meta"><div class="date">${formatDate(item.date)}</div><div class="badge">${esc(item.stage)}</div><div class="badge ${item.signal==='Αρνητικό'?'negative':'positive'}">${esc(item.signal)}</div><div class="evidence-text">${esc(item.evidence)}</div></div>
    <div><h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p><p class="meaning"><strong>Τι σημαίνει:</strong> ${esc(item.meaning)}</p><p class="source-quality"><strong>Ποιότητα πηγής:</strong> ${esc(item.sourceQuality)}</p><a class="source" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Πηγή: ${esc(item.source)} ↗</a><div class="tags">${item.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div>
  </article>`).join('');
}

fetch('/news.json').then(r=>{
  if(!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}).then(json=>{
  data=json;
  document.querySelector('#updated').textContent=formatDate(data.siteUpdated);
  const renderTrialCard=x=>`<article class="pipeline-card"><div class="phase">${esc(x.phase)}</div><h3>${esc(x.name)}</h3><div class="candidate">${esc(x.candidate)}</div><div class="status">${esc(x.status)}</div>${x.geography?`<div class="geography">${esc(x.geography)}</div>`:''}${x.evidence?`<div class="card-evidence"><strong>Evidence:</strong> ${esc(x.evidence)}</div>`:''}<div class="next"><strong>${esc(x.nextLabel||'Επόμενο')}:</strong> ${esc(x.next)}</div>${x.url?`<a class="trial-link" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">Registry / source ↗</a>`:''}</article>`;
  renderGreece();
  document.querySelector('#pipeline').innerHTML=data.pipeline.map(renderTrialCard).join('');
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
