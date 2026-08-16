(function(global){
  'use strict';
  const valuationMetrics=asset=>asset?.valuation_metrics||{};
  const alphaSpread=stock=>stock?.alpha_spread_pct??null;
  const buyGate=stock=>stock?.buy_gate||{ok:false,checks:{},failed:['missing_canonical_gate']};
  const impliedAction=stock=>stock?.action||'AVOID';
  const freshness=asset=>asset?.freshness||{ok:false,checks:{},ages:{},dates:{}};
  const alphaScore=stock=>Number(stock?.score??0);
  const confidenceScore=stock=>Number(stock?.confidence_score??0);
  const rotationGate=data=>data?.rotation_review||{status:'BLOCKED',event_is_gate:false,allocations:[]};
  const riskAdjustedAllocations=()=>({mode:'MOVED_TO_ELEPHANT',allocations:[]});
  global.AlphaEngine={authority:'PRESENTATION_ONLY',valuationMetrics,alphaSpread,buyGate,impliedAction,freshness,alphaScore,confidenceScore,rotationGate,riskAdjustedAllocations};
})(window);
