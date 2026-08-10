#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(path): return json.loads((ROOT/path).read_text())
def sumv(d): return sum(float(v or 0) for v in (d or {}).values())
def grade(score,t):
    if score>=t['A']: return 'A'
    if score>=t['B']: return 'B'
    if score>=t['C']: return 'C'
    return 'D'

def valuation(asset):
    m=asset.get('valuation_model',{})
    p=asset.get('reference_price')
    base=m.get('scenarios',{}).get('base',{})
    base_fv=base.get('fair_value')
    exp=m.get('expected_fair_value')
    if exp is None:
        scenarios=[m.get('scenarios',{}).get(k,{}) for k in ('bear','base','bull')]
        if all(s.get('fair_value') is not None and s.get('probability') is not None for s in scenarios):
            prob=sum(float(s['probability']) for s in scenarios)
            div=100 if prob>1.01 else 1
            exp=sum(float(s['fair_value'])*float(s['probability'])/div for s in scenarios)
    er=m.get('expected_return_pct')
    if er is None and p and exp is not None: er=(exp/p-1)*100
    mos=m.get('margin_of_safety_pct')
    if mos is None and p and base_fv is not None: mos=(base_fv/p-1)*100
    return er,mos

def evidence_ok(stock,required):
    ev=stock.get('evidence',[])
    return all(any(x.get('metric')==metric and x.get('quality')=='FIRST_PARTY' and x.get('status')=='VERIFIED' for x in ev) for metric in required)

def implied_action(stock,data):
    if stock.get('thesis_status')=='INVALIDATED': return 'AVOID'
    er,mos=valuation(stock); ber,_=valuation(data['benchmark_asset']); spread=None if er is None or ber is None else er-ber
    complete=stock.get('valuation_model',{}).get('status')=='COMPLETE'
    benchmark_complete=data['benchmark_asset'].get('valuation_model',{}).get('status')=='COMPLETE' and ber is not None
    buy=(stock['score']>=data['methodology']['buy_gate'] and stock['confidence_score']>=data['decision_policy']['min_confidence_score'] and benchmark_complete and complete and mos is not None and mos>=data['decision_policy']['min_margin_of_safety_pct'] and spread is not None and spread>=data['decision_policy']['min_alpha_spread_pct'] and evidence_ok(stock,data['decision_policy']['required_evidence_metrics']))
    if buy:return 'BUY CANDIDATE'
    if stock['score']>=data['methodology']['buy_gate']:return 'VERIFY'
    if stock['score']>=data['methodology']['grade_thresholds']['B']:return 'WATCH'
    return 'AVOID'

def main():
    data=load(Path('data/alpha.json')); screen=load(Path('data/screen.json')); perf=load(Path('data/performance.json')); hist=load(Path('data/history/index.json'))
    assert data['meta']['schema_version']>=3
    assert sum(data['methodology']['weights'].values())==100
    assert sum(data['confidence_methodology']['weights'].values())==100
    tickers=[]; ranks=[]
    prev_score=None
    for s in sorted(data['stocks'], key=lambda x:x['rank']):
        tickers.append(s['ticker']); ranks.append(s['rank'])
        score=sumv(s['factor_scores'])+sumv(s.get('penalties'))
        conf=sumv(s['confidence_factors'])
        assert abs(score-s['score'])<1e-9, f"{s['ticker']} score mismatch {score} != {s['score']}"
        assert abs(conf-s['confidence_score'])<1e-9, f"{s['ticker']} confidence mismatch"
        assert s['grade']==grade(s['score'],data['methodology']['grade_thresholds']), f"{s['ticker']} grade mismatch"
        assert s['action']==implied_action(s,data), f"{s['ticker']} action must be derived: {implied_action(s,data)}"
        if prev_score is not None: assert s['score']<=prev_score, 'ranks must be descending by score'
        prev_score=s['score']
        for k,v in s['factor_scores'].items(): assert 0<=v<=data['methodology']['weights'][k]
        for k,v in s['confidence_factors'].items(): assert 0<=v<=data['confidence_methodology']['weights'][k]
        assert sumv(s.get('penalties'))>=data['methodology']['penalty_floor']
        if s.get('reference_price_date'): assert s['reference_price_date']<=data['meta']['as_of']
        m=s.get('valuation_model',{})
        if m.get('status')=='COMPLETE':
            scenarios=m['scenarios']; prob=sum(float(scenarios[k]['probability']) for k in ('bear','base','bull'))
            assert abs(prob-1)<1e-6 or abs(prob-100)<1e-6, f"{s['ticker']} scenario probabilities"
            for k in ('bear','base','bull'):
                x=scenarios[k]; assert all(x.get(z) is not None for z in ('eps','multiple','fair_value','probability'))
                assert abs(x['eps']*x['multiple']-x['fair_value'])<=max(1,abs(x['fair_value'])*0.02), f"{s['ticker']} {k} FV mismatch"
    assert len(tickers)==len(set(tickers)); assert ranks==list(range(1,len(ranks)+1))
    assert data['rotation_event']['meaning'].lower().find('automatic')>=0, '3000 must remain event-only'
    fallback=data['rotation_model']['fallback_allocations']; assert abs(sum(float(x['weight']) for x in fallback)-100)<1e-9
    cash=next(x for x in fallback if x['ticker']=='CASH'); assert cash['weight']>=data['rotation_model']['guardrails']['cash_floor_pct']
    for x in fallback:
        if x['ticker']!='CASH': assert x['weight']<=data['rotation_model']['guardrails']['max_single_stock_pct']
    market=date.fromisoformat(data['meta']['market_data_as_of']); review=date.fromisoformat(data['meta']['as_of']); assert 0<=(review-market).days<=data['freshness_policy']['market_max_calendar_days']
    assert screen['meta']['schema_version']>=1 and 'research_funnel' in screen['rules']
    assert perf['meta']['schema_version']>=1 and [h['weeks'] for h in perf['horizons']]==[1,4,13,26,52]
    snaps=hist.get('snapshots',[]); dates=[x['date'] for x in snaps]; assert dates==sorted(set(dates)); assert hist['latest']==dates[-1]
    for entry in snaps:
        p=ROOT/entry['path']; assert p.exists(), f'missing {p}'
        snap=json.loads(p.read_text()); assert snap['meta']['as_of']==entry['date']
        assert all(0<=x['score']<=100 for x in snap.get('stocks',[]))
    print(f"PASS: v3 engine, {len(tickers)} stocks, {len(snaps)} snapshots")
if __name__=='__main__': main()
