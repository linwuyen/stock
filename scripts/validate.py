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

def age_days(value, as_of):
    if not value: return float('inf')
    return (date.fromisoformat(as_of)-date.fromisoformat(value)).days

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

def evidence_ok(asset,required):
    ev=asset.get('evidence',[])
    return all(any(x.get('metric')==metric and x.get('quality')=='FIRST_PARTY' and x.get('status')=='VERIFIED' for x in ev) for metric in required)

def freshness(asset, policy, meta):
    dates={
        'market': asset.get('reference_price_date') or meta.get('market_data_as_of'),
        'fundamentals': asset.get('fundamental_data_as_of'),
        'revenue': asset.get('revenue_data_as_of'),
        'events': asset.get('event_data_as_of') or meta.get('as_of'),
    }
    limits={
        'market': policy['market_max_calendar_days'],
        'fundamentals': policy['fundamental_max_days'],
        'revenue': policy['revenue_max_days'],
        'events': policy['event_max_days'],
    }
    required=set(policy.get('required_for_buy',['market','fundamentals','revenue','events']))
    checks={}; ages={}
    for key,value in dates.items():
        ages[key]=age_days(value,meta['as_of'])
        checks[key]=(key not in required) if value is None else 0<=ages[key]<=limits[key]
    return {'checks':checks,'ages':ages,'ok':all(checks.values())}

def implied_action(stock,data):
    if stock.get('thesis_status')=='INVALIDATED': return 'AVOID'
    er,mos=valuation(stock); ber,_=valuation(data['benchmark_asset'])
    spread=None if er is None or ber is None else er-ber
    complete=stock.get('valuation_model',{}).get('status')=='COMPLETE'
    benchmark_complete=data['benchmark_asset'].get('valuation_model',{}).get('status')=='COMPLETE' and ber is not None
    stock_fresh=freshness(stock,data['freshness_policy'],data['meta'])['ok']
    benchmark_fresh=freshness(data['benchmark_asset'],data['freshness_policy'],data['meta'])['ok']
    required=data['decision_policy']['required_evidence_metrics']
    buy=(
        stock['score']>=data['methodology']['buy_gate'] and
        stock['confidence_score']>=data['decision_policy']['min_confidence_score'] and
        benchmark_complete and benchmark_fresh and evidence_ok(data['benchmark_asset'],required) and
        complete and mos is not None and mos>=data['decision_policy']['min_margin_of_safety_pct'] and
        spread is not None and spread>=data['decision_policy']['min_alpha_spread_pct'] and
        stock_fresh and evidence_ok(stock,required)
    )
    if buy:return 'BUY CANDIDATE'
    if stock['score']>=data['methodology']['buy_gate']:return 'VERIFY'
    if stock['score']>=data['methodology']['grade_thresholds']['B']:return 'WATCH'
    return 'AVOID'

def validate_complete_valuation(asset,label):
    m=asset.get('valuation_model',{})
    if m.get('status')!='COMPLETE': return
    scenarios=m['scenarios']; prob=sum(float(scenarios[k]['probability']) for k in ('bear','base','bull'))
    assert abs(prob-1)<1e-6 or abs(prob-100)<1e-6, f"{label} scenario probabilities"
    divisor=100 if prob>1.01 else 1; expected=0.0
    for k in ('bear','base','bull'):
        x=scenarios[k]
        assert all(x.get(z) is not None for z in ('eps','multiple','fair_value','probability'))
        assert abs(x['eps']*x['multiple']-x['fair_value'])<=max(1,abs(x['fair_value'])*0.02), f"{label} {k} FV mismatch"
        expected+=float(x['fair_value'])*float(x['probability'])/divisor
    if m.get('expected_fair_value') is not None:
        assert abs(expected-float(m['expected_fair_value']))<=max(0.5,abs(expected)*0.002), f"{label} expected FV mismatch"
    p=asset.get('reference_price')
    if p and m.get('expected_return_pct') is not None:
        assert abs((expected/p-1)*100-float(m['expected_return_pct']))<0.1, f"{label} expected return mismatch"
    base_fv=float(scenarios['base']['fair_value'])
    if p and m.get('margin_of_safety_pct') is not None:
        assert abs((base_fv/p-1)*100-float(m['margin_of_safety_pct']))<0.1, f"{label} MOS mismatch"

def main():
    data=load(Path('data/alpha.json')); screen=load(Path('data/screen.json')); perf=load(Path('data/performance.json')); hist=load(Path('data/history/index.json'))
    assert data['meta']['schema_version']>=3
    assert sum(data['methodology']['weights'].values())==100
    assert sum(data['confidence_methodology']['weights'].values())==100
    assert set(data['freshness_policy'].get('required_for_buy',[]))=={'market','fundamentals','revenue','events'}
    validate_complete_valuation(data['benchmark_asset'],'2330 benchmark')
    required=data['decision_policy']['required_evidence_metrics']
    if data['benchmark_asset'].get('valuation_model',{}).get('status')=='COMPLETE':
        assert evidence_ok(data['benchmark_asset'],required),'benchmark evidence incomplete'
        assert freshness(data['benchmark_asset'],data['freshness_policy'],data['meta'])['ok'],'benchmark freshness failed'

    tickers=[]; ranks=[]; prev_score=None; ber,_=valuation(data['benchmark_asset'])
    for s in sorted(data['stocks'], key=lambda x:x['rank']):
        tickers.append(s['ticker']); ranks.append(s['rank'])
        score=sumv(s['factor_scores'])+sumv(s.get('penalties')); conf=sumv(s['confidence_factors'])
        assert abs(score-s['score'])<1e-9, f"{s['ticker']} score mismatch {score} != {s['score']}"
        assert abs(conf-s['confidence_score'])<1e-9, f"{s['ticker']} confidence mismatch"
        assert s['grade']==grade(s['score'],data['methodology']['grade_thresholds']), f"{s['ticker']} grade mismatch"
        expected_action=implied_action(s,data)
        assert s['action']==expected_action, f"{s['ticker']} action must be derived: {expected_action}"
        if prev_score is not None: assert s['score']<=prev_score, 'ranks must be descending by score'
        prev_score=s['score']
        for k,v in s['factor_scores'].items(): assert 0<=v<=data['methodology']['weights'][k]
        for k,v in s['confidence_factors'].items(): assert 0<=v<=data['confidence_methodology']['weights'][k]
        assert sumv(s.get('penalties'))>=data['methodology']['penalty_floor']
        if s.get('reference_price_date'): assert s['reference_price_date']<=data['meta']['as_of']
        validate_complete_valuation(s,s['ticker'])
        er,_=valuation(s); stored=s.get('alpha_spread_pct')
        if er is None or ber is None: assert stored is None
        else: assert stored is not None and abs((er-ber)-float(stored))<0.1, f"{s['ticker']} alpha spread mismatch"

    assert len(tickers)==len(set(tickers)); assert ranks==list(range(1,len(ranks)+1))
    assert 'automatic' in data['rotation_event']['meaning'].lower(), '3000 must remain event-only'
    fallback=data['rotation_model']['fallback_allocations']; assert abs(sum(float(x['weight']) for x in fallback)-100)<1e-9
    cash=next(x for x in fallback if x['ticker']=='CASH'); assert cash['weight']>=data['rotation_model']['guardrails']['cash_floor_pct']
    for x in fallback:
        if x['ticker']!='CASH': assert x['weight']<=data['rotation_model']['guardrails']['max_single_stock_pct']
    market=date.fromisoformat(data['meta']['market_data_as_of']); review=date.fromisoformat(data['meta']['as_of'])
    assert 0<=(review-market).days<=data['freshness_policy']['market_max_calendar_days']
    assert screen['meta']['schema_version']>=1 and 'research_funnel' in screen['rules']
    assert perf['meta']['schema_version']>=1 and [h['weeks'] for h in perf['horizons']]==[1,4,13,26,52]
    snaps=hist.get('snapshots',[]); dates=[x['date'] for x in snaps]
    assert dates==sorted(set(dates)); assert hist['latest']==dates[-1]
    for entry in snaps:
        p=ROOT/entry['path']; assert p.exists(), f'missing {p}'
        snap=json.loads(p.read_text()); assert snap['meta']['as_of']==entry['date']
        assert all(0<=x['score']<=100 for x in snap.get('stocks',[]))
    print(f"PASS: v3 engine, {len(tickers)} stocks, {len(snaps)} snapshots; benchmark ER={ber:.2f}%")
if __name__=='__main__': main()
