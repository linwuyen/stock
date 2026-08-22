const $=s=>document.querySelector(s);
const fmt=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:2});
const pct=v=>v==null?'—':`${Number(v)>=0?'+':''}${fmt.format(v)}%`;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function badge(text,kind=''){return `<span class="badge ${kind}">${esc(text)}</span>`}
function failed(stock){return (stock.buy_gate?.failed||[]).join(' · ')||'None'}
function topDecision(data){
  const buy=(data.stocks||[]).filter(x=>x.action==='BUY CANDIDATE').sort((a,b)=>(b.alpha_spread_pct??-999)-(a.alpha_spread_pct??-999));
  if(buy.length)return {title:`${buy[0].ticker} ${buy[0].name}`,action:'BUY CANDIDATE',stock:buy[0]};
  const ranked=[...(data.stocks||[])].sort((a,b)=>(b.score??0)-(a.score??0));
  return {title:ranked[0]?`${ranked[0].ticker} ${ranked[0].name}`:'No security',action:'NO BUY',stock:ranked[0]};
}
function renderHero(data){
  const d=topDecision(data),s=d.stock||{},v=s.valuation_metrics||{},rot=data.rotation_review||{};
  $('#decisionTitle').textContent=d.title;
  $('#decisionAction').textContent=d.action;
  $('#decisionAction').className=`decision-action ${d.action==='BUY CANDIDATE'?'buy':'block'}`;
  $('#decisionMeta').innerHTML=[badge(`Alpha ${s.score??'—'}`),badge(`Confidence ${s.confidence_score??'—'}`),badge(`ER ${pct(v.expected_return_pct)}`),badge(`Spread ${pct(s.alpha_spread_pct)}`),badge(`Base upside ${pct(v.base_upside_pct)}`)].join('');
  $('#decisionWhy').textContent=d.action==='BUY CANDIDATE'?'Full Python Buy Gate passed.':`Blocked by: ${failed(s)}`;
  $('#authority').textContent=`${data.meta.decision_engine_version} · ${data.meta.authority}`;
  $('#fingerprint').textContent=data.meta.decision_fingerprint;
  $('#rotation').innerHTML=`${badge(rot.status,rot.status==='READY_FOR_REVIEW'?'good':'')} ${badge(`TSMC 3000 event: ${rot.tsmc_3000_event_triggered?'TRIGGERED':'not triggered'}`)} <strong>Event is not a gate.</strong> Portfolio sizing → Elephant.`;
}
function renderStocks(data){
  $('#stocks').innerHTML=(data.stocks||[]).map(s=>{
    const v=s.valuation_metrics||{},e=s.market_expectation||{};
    return `<article class="card"><div class="row"><div><h3>${esc(s.ticker)} ${esc(s.name)}</h3>${badge(s.action,s.action==='BUY CANDIDATE'?'good':'')}</div><strong class="score">${fmt.format(s.score)}</strong></div><div class="metrics"><span>Confidence <b>${fmt.format(s.confidence_score)}</b></span><span>ER <b>${pct(v.expected_return_pct)}</b></span><span>Spread <b>${pct(s.alpha_spread_pct)}</b></span><span title="Base fair value / reference price - 1；不是 classical margin of safety">Base upside <b>${pct(v.base_upside_pct)}</b></span></div><p><b>Failed gates:</b> ${esc(failed(s))}</p><p><b>Market implied EPS:</b> ${e.status==='COMPLETE'?fmt.format(e.market_implied_eps):'—'} · Base gap ${pct(e.base_vs_implied_eps_gap_pct)}</p><p><b>Next evidence:</b> ${esc(s.next_check||'—')}</p><details><summary>Deterministic score inputs</summary><pre>${esc(JSON.stringify({factors:s.factor_scores,penalties:s.penalties,features:s.feature_inputs,freshness:s.freshness},null,2))}</pre></details></article>`;
  }).join('');
}
function renderScreen(screen){
  const q=screen.deep_research_queue||[];
  $('#screenMeta').textContent=`${screen.meta.status} · ${screen.meta.as_of} · Top50 ${screen.candidates?.length||0}`;
  $('#queue').innerHTML=q.map(x=>`<div class="queue-row"><div><b>#${x.rank} ${esc(x.ticker)} ${esc(x.name)}</b><small>${esc(x.industry||'—')}</small></div>${badge(x.discovery_lane,'lane')}<span>${fmt.format(x.screen_priority)}</span><span class="${x.verification_priority==='HIGH'?'warn':''}">${esc(x.verification_priority||'NORMAL')}</span></div>`).join('')||'<p>No queue.</p>';
}
function renderPerformance(p){
  $('#performance').innerHTML=(p.horizons||[]).map(x=>`<div class="metricbox"><small>${x.weeks}W realized alpha</small><b>${pct(x.mean_excess_return_pct)}</b><span>n=${x.sample_size}</span></div>`).join('');
  $('#calStatus').textContent=p.meta.status;
}
async function init(){
  try{
    const [data,screen,performance]=await Promise.all(['data/alpha.json','data/screen.json','data/performance.json'].map(x=>fetch(`${x}?v=${Date.now()}`,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`${x} ${r.status}`);return r.json()})));
    renderHero(data);renderStocks(data);renderScreen(screen);renderPerformance(performance);
  }catch(e){$('#fatal').textContent=`Decision Console unavailable: ${e.message}`;$('#fatal').hidden=false}
}
init();
