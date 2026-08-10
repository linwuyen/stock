(function(global){
  'use strict';
  const sumValues=obj=>Object.values(obj||{}).reduce((sum,value)=>sum+Number(value||0),0);
  const pct=(num,den)=>den?(num/den-1)*100:null;
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  const localDate=value=>value?new Date(`${value}T00:00:00+08:00`):null;
  const dateAgeDays=(value,asOf=null)=>{
    if(!value)return Infinity;
    const then=localDate(value);
    const ref=asOf?localDate(asOf):new Date();
    return Math.floor((ref.getTime()-then.getTime())/86400000);
  };
  function alphaScore(stock){return sumValues(stock.factor_scores)+sumValues(stock.penalties)}
  function confidenceScore(stock){return sumValues(stock.confidence_factors)}
  function gradeFor(score,methodology){
    const t=methodology.grade_thresholds||{A:75,B:65,C:50};
    if(score>=t.A)return'A';if(score>=t.B)return'B';if(score>=t.C)return'C';return'D'
  }
  function expectedFairValue(model){
    const scenarios=model?.scenarios;if(!scenarios)return null;
    const entries=['bear','base','bull'].map(key=>scenarios[key]).filter(Boolean);
    if(!entries.length||entries.some(s=>s.fair_value==null||s.probability==null))return null;
    const probability=entries.reduce((sum,s)=>sum+Number(s.probability),0);
    if(Math.abs(probability-1)>0.001&&Math.abs(probability-100)>0.1)return null;
    const divisor=probability>1.01?100:1;
    return entries.reduce((sum,s)=>sum+Number(s.fair_value)*Number(s.probability)/divisor,0)
  }
  function valuationMetrics(asset){
    const model=asset.valuation_model||{},price=asset.reference_price;
    const expectedFV=model.expected_fair_value??expectedFairValue(model);
    const expectedReturn=model.expected_return_pct??(price&&expectedFV?pct(expectedFV,price):null);
    const baseFV=model.scenarios?.base?.fair_value??null;
    const mos=model.margin_of_safety_pct??(price&&baseFV?pct(baseFV,price):null);
    const forwardPE=model.forward_pe??(price&&model.forward_eps?price/model.forward_eps:null);
    const normalizedPE=model.normalized_pe??(price&&model.normalized_eps?price/model.normalized_eps:null);
    return{expectedFV,expectedReturn,mos,forwardPE,normalizedPE}
  }
  function alphaSpread(stock,benchmark){
    const s=valuationMetrics(stock).expectedReturn,b=valuationMetrics(benchmark).expectedReturn;
    return s==null||b==null?null:s-b
  }
  function freshness(asset,policy,meta,{live=true}={}){
    const dates={
      market:asset.reference_price_date||meta.market_data_as_of||null,
      fundamentals:asset.fundamental_data_as_of||null,
      revenue:asset.revenue_data_as_of||null,
      events:asset.event_data_as_of||meta.as_of||null
    };
    const limits={market:policy.market_max_calendar_days,fundamentals:policy.fundamental_max_days,revenue:policy.revenue_max_days,events:policy.event_max_days};
    const required=new Set(policy.required_for_buy||['market','fundamentals','revenue','events']);
    const asOf=live?null:meta.as_of;
    const ages=Object.fromEntries(Object.entries(dates).map(([key,value])=>[key,dateAgeDays(value,asOf)]));
    const checks=Object.fromEntries(Object.keys(dates).map(key=>[key,dates[key]==null?!required.has(key):ages[key]>=0&&ages[key]<=limits[key]]));
    return{checks,ok:Object.values(checks).every(Boolean),ages,dates}
  }
  function evidenceGate(asset,policy){
    const required=policy.required_evidence_metrics||[],evidence=asset.evidence||[];
    const missing=required.filter(metric=>!evidence.some(item=>item.metric===metric&&item.quality==='FIRST_PARTY'&&item.status==='VERIFIED'));
    return{ok:missing.length===0,missing}
  }
  function buyGate(stock,data){
    const m=data.methodology,score=alphaScore(stock),confidence=confidenceScore(stock);
    const v=valuationMetrics(stock),benchmarkV=valuationMetrics(data.benchmark_asset),spread=alphaSpread(stock,data.benchmark_asset);
    const fresh=freshness(stock,data.freshness_policy,data.meta),benchmarkFresh=freshness(data.benchmark_asset,data.freshness_policy,data.meta);
    const evidence=evidenceGate(stock,data.decision_policy),benchmarkEvidence=evidenceGate(data.benchmark_asset,data.decision_policy);
    const checks={
      score:score>=m.buy_gate,
      confidence:confidence>=data.decision_policy.min_confidence_score,
      benchmark_complete:data.benchmark_asset.valuation_model?.status==='COMPLETE'&&benchmarkV.expectedReturn!=null,
      benchmark_freshness:benchmarkFresh.ok,
      benchmark_evidence:benchmarkEvidence.ok,
      valuation_complete:stock.valuation_model?.status==='COMPLETE'&&v.expectedReturn!=null&&v.mos!=null,
      margin_of_safety:v.mos!=null&&v.mos>=data.decision_policy.min_margin_of_safety_pct,
      alpha_spread:spread!=null&&spread>=data.decision_policy.min_alpha_spread_pct,
      freshness:fresh.ok,
      evidence:evidence.ok,
      thesis:stock.thesis_status!=='INVALIDATED'
    };
    return{ok:Object.values(checks).every(Boolean),checks,score,confidence,valuation:v,benchmarkValuation:benchmarkV,spread,fresh,benchmarkFresh,evidence,benchmarkEvidence}
  }
  function impliedAction(stock,data){
    const gate=buyGate(stock,data);
    if(stock.thesis_status==='INVALIDATED')return'AVOID';
    if(gate.ok)return'BUY CANDIDATE';
    if(gate.score>=data.methodology.buy_gate)return'VERIFY';
    if(gate.score>=data.methodology.grade_thresholds.B)return'WATCH';
    return'AVOID'
  }
  function riskAdjustedAllocations(data){
    const model=data.rotation_model,maxSingle=model.guardrails.max_single_stock_pct,cashFloor=model.guardrails.cash_floor_pct,investBudget=100-cashFloor;
    const eligible=data.stocks.map(stock=>{const gate=buyGate(stock,data),downside=Math.abs(stock.risk_model?.downside_pct??30),raw=gate.ok?Math.max(0,gate.spread)*(gate.confidence/100)/Math.max(10,downside):0;return{stock,gate,raw}}).filter(x=>x.raw>0);
    if(!eligible.length)return{mode:'FALLBACK',allocations:model.fallback_allocations||[{ticker:'CASH',name:'現金',weight:100}]};
    const result=new Map(eligible.map(x=>[x.stock.ticker,0]));let remaining=investBudget,active=[...eligible];
    while(remaining>0.0001&&active.length){
      const rawSum=active.reduce((s,x)=>s+x.raw,0);if(!rawSum)break;let distributed=0;const next=[];
      for(const item of active){const current=result.get(item.stock.ticker)||0,proposed=current+remaining*item.raw/rawSum,capped=Math.min(maxSingle,proposed);result.set(item.stock.ticker,capped);distributed+=capped-current;if(capped<maxSingle-1e-9)next.push(item)}
      if(distributed<0.0001)break;remaining-=distributed;active=next
    }
    const stockWeight=[...result.values()].reduce((s,v)=>s+v,0),allocations=[...result.entries()].filter(([,w])=>w>0.001).map(([ticker,weight])=>({ticker,weight:Number(weight.toFixed(2))}));
    allocations.push({ticker:'CASH',name:'現金',weight:Number((100-stockWeight).toFixed(2))});return{mode:'RISK_ADJUSTED',allocations}
  }
  function rotationGate(data){
    const triggerHit=data.benchmark_asset.reference_price>=data.rotation_event.trigger_price,benchmarkV=valuationMetrics(data.benchmark_asset),benchmarkComplete=data.benchmark_asset.valuation_model?.status==='COMPLETE';
    const benchmarkFresh=freshness(data.benchmark_asset,data.freshness_policy,data.meta),benchmarkEvidence=evidenceGate(data.benchmark_asset,data.decision_policy);
    const allocations=riskAdjustedAllocations(data),buyable=data.stocks.filter(stock=>buyGate(stock,data).ok),reasons=[];
    if(!triggerHit)reasons.push('TSMC 3000 event 尚未觸發；僅供 Preview');
    if(!benchmarkComplete||benchmarkV.expectedReturn==null)reasons.push('TSMC valuation 尚未 COMPLETE，禁止做 Rotation 決策');
    if(!benchmarkFresh.ok)reasons.push('TSMC benchmark 資料已過 freshness gate');
    if(!benchmarkEvidence.ok)reasons.push(`TSMC benchmark 缺第一手證據：${benchmarkEvidence.missing.join(', ')}`);
    if(!buyable.length)reasons.push('目前沒有候選股通過完整 Buy Gate');
    return{status:triggerHit&&benchmarkComplete&&benchmarkV.expectedReturn!=null&&benchmarkFresh.ok&&benchmarkEvidence.ok&&buyable.length?'READY FOR REVIEW':'BLOCKED / PREVIEW',triggerHit,allocations,buyable,reasons,benchmarkFresh,benchmarkEvidence}
  }
  global.AlphaEngine={alphaScore,confidenceScore,gradeFor,valuationMetrics,alphaSpread,freshness,evidenceGate,buyGate,impliedAction,riskAdjustedAllocations,rotationGate,dateAgeDays,clamp};
})(window);
