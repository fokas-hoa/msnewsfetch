/* Offline tests of the real app.js startup, render and fallback paths. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync('app.js','utf8');
const baseline=JSON.parse(fs.readFileSync('news.json','utf8'));
const clone=x=>JSON.parse(JSON.stringify(x));
const empty={version:2,events:[],programmes:[],trial_overrides:{},source_health:{}};
async function startup(live, {cache=null,never=false}={}){
  const nodes=new Map();
  const doc={querySelector:s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:''});return nodes.get(s)},querySelectorAll:()=>[]};
  const values=new Map(cache?[['msnews-validated-feed-v2',JSON.stringify(cache)]]:[]);
  const context={URL,AbortController,console:{warn(){}},document:doc,localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},
    setTimeout:(fn,ms)=>setTimeout(fn,Math.min(ms,20)),clearTimeout,
    fetch:async url=>{
      if(url==='/news.json')return{ok:true,text:async()=>JSON.stringify(baseline)};
      if(never)return new Promise(()=>{});
      if(live instanceof Error)throw live;
      return{ok:true,text:async()=>JSON.stringify(live)};
    }};
  vm.createContext(context);vm.runInContext(code,context);
  await new Promise(resolve=>setTimeout(resolve,55));
  return {nodes,context};
}
(async()=>{
  let result=await startup(empty);
  assert.match(result.nodes.get('#pipeline').innerHTML,/ReVIVE/);
  assert.match(result.nodes.get('#greece-news').innerHTML,/δεν αποδεικνύει/);
  assert.doesNotMatch(result.nodes.get('#greece-news').innerHTML,/καμία μελέτη myelin-repair του watchlist δεν στρατολογεί/);
  assert.match(result.nodes.get('#feed-health').textContent,/Ζωντανό feed/);
  result=await startup({version:2,events:{}});
  assert.match(result.nodes.get('#pipeline').innerHTML,/ReVIVE/);
  assert.match(result.nodes.get('#feed-health').textContent,/αρχικό/);
  result=await startup(new Error('synthetic outage'),{cache:empty});
  assert.match(result.nodes.get('#feed-health').textContent,/αποθηκευμένο/);
  result=await startup(null,{never:true});
  assert.match(result.nodes.get('#pipeline').innerHTML,/ReVIVE/);
  assert.match(result.nodes.get('#feed-health').textContent,/αρχικό/);
  const context=result.context;
  assert.equal(vm.runInContext('safeURL("javascript:alert(1)")',context),'#');
  assert.equal(vm.runInContext('category({publication_status:"preprint",stage:"Προδημοσίευση",human_data:true})',context),'human');
  assert.equal(vm.runInContext('category({publication_status:"preprint",stage:"Προδημοσίευση",human_data:false,study_population:"not_established"})',context),'unknown');
  console.log('Browser contract: 4 startup/fallback scenarios and URL/evidence checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
