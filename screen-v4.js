(function(){
  'use strict';
  const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
  const fmt=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:2});

  function sourceSummary(screen){
    const health=screen.source_health||{};
    return ['TWSE','TPEX'].map(market=>{
      const rows=health[market]||{};
      const failed=Object.entries(rows).filter(([,v])=>!v?.ok).map(([k])=>k);
      const promotion=screen.meta?.promotion_enabled_by_market?.[market];
      const coverage=screen.coverage_counts?.[market];
      const incomeRatio=coverage?.income_coverage_ratio;
      return `<div class="change-row ${failed.length?'down':'up'}"><strong>${market} · ${failed.length?'DEGRADED':'HEALTHY'}</strong><small>Promotion ${promotion?'ON':'OFF'}${incomeRatio==null?'':` · current income coverage ${fmt.format(incomeRatio*100)}%`}${failed.length?` · failed: ${esc(failed.join(', '))}`:''}</small></div>`;
    }).join('');
  }

  function render(screen){
    const status=document.querySelector('#screenStatus');
    const rules=document.querySelector('#screenRules');
    const candidates=document.querySelector('#screenCandidates');
    if(!status||!rules||!candidates)return;

    const state=screen.meta?.status||'UNKNOWN';
    status.textContent=state;
    status.className=`status-pill ${state==='COMPLETE'?'good':state==='DEGRADED'?'blocked':''}`;
    const top50=screen.candidates||[];
    const deep=screen.deep_research_queue||[];
    const promotion=screen.meta?.promotion_enabled_by_market||{};
    rules.innerHTML=[
      ['Coverage',screen.meta?.coverage||'—'],
      ['Promotion',`TWSE ${promotion.TWSE?'ON':'OFF'} · TPEx ${promotion.TPEX?'ON':'OFF'}`],
      ['Funnel',screen.rules?.research_funnel||'—'],
      ['Ranking',`${screen.rules?.ranking?.primary||'screen_priority'} primary · legacy Screen Score secondary`],
      ['Top 50',`${top50.length} names`],
      ['Deep research',`${deep.length} names`],
      ['Liquidity',`20-observation median target ${screen.rules?.liquidity?.target_median_daily_turnover_twd_million??'—'}M; bootstrap floor ${screen.rules?.liquidity?.bootstrap_latest_day_floor_twd_million??'—'}M`],
      ['Earnings coverage','Missing current EPS row may use positive official TTM PE only as discovery proxy; Deep Research must verify filings'],
      ['Market cap',`${screen.rules?.market_cap?.mode||'—'} · asymmetric hard filter disabled`],
      ['Decision boundary','Screen can nominate research only; it can never create BUY_CANDIDATE']
    ].map(([a,b])=>`<div class="method-row"><span>${esc(a)}</span><strong>${esc(b)}</strong></div>`).join('');

    const source=sourceSummary(screen);
    const queue=deep.length?deep.map((x,i)=>{
      const proxy=x.profitability_basis==='POSITIVE_TTM_PE_PROXY'?' · EPS proxy→VERIFY':'';
      const cycle=(x.flags||[]).includes('CYCLE_EXTREME_GROWTH_LOW_PE')?' · CYCLE FLAG':'';
      return `<div class="watch-row"><span>#${i+1} ${esc(x.ticker)} ${esc(x.name)} <small>${esc(x.market||'')} · ${esc(x.industry||'industry?')}</small></span><small>Priority ${x.screen_priority==null?'—':fmt.format(x.screen_priority)} · Screen ${fmt.format(x.screen_score)} · Rev YoY ${x.revenue_yoy_pct==null?'—':fmt.format(x.revenue_yoy_pct)+'%'} · PE ${x.pe_ttm==null?'VERIFY':fmt.format(x.pe_ttm)+'x'}${proxy}${cycle}</small></div>`;
    }).join(''):'<div class="empty-state">等待第一次成功的全市場掃描；Bootstrap 名單不視為市場 Top 10。</div>';
    candidates.innerHTML=`<div class="change-list">${source}</div><div class="panel-note">Deep Research Queue</div>${queue}`;
  }

  async function refresh(){
    try{
      const response=await fetch(`data/screen.json?v=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    }catch(error){
      const status=document.querySelector('#screenStatus');
      if(status){status.textContent='SCREEN LOAD FAILED';status.className='status-pill blocked';}
    }
  }
  document.addEventListener('DOMContentLoaded',()=>{refresh();setTimeout(refresh,700)});
})();
