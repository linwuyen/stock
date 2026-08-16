#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "security-v5.0.1"
DEFAULT_WEIGHTS = {"earnings_acceleration":30,"revenue_quality":20,"valuation":25,"structural_catalyst":15,"balance_sheet_cash_flow":10}
CONFIDENCE_WEIGHTS = {"evidence_quality":35,"forecast_visibility":25,"model_completeness":20,"thesis_falsifiability":10,"data_freshness":10}


def load(path, default=None):
    p=ROOT/path
    return copy.deepcopy(default) if not p.exists() else json.loads(p.read_text(encoding="utf-8"))

def save(path,obj):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def finite(v):
    try:return math.isfinite(float(v))
    except (TypeError,ValueError):return False
def clamp(v,lo,hi):return max(lo,min(hi,float(v)))
def pct_change(new,old):return None if not finite(new) or not finite(old) or float(old)==0 else (float(new)/float(old)-1)*100

def trading_weekday_age(value,as_of):
    if not value or not as_of:return None
    start,end=date.fromisoformat(value),date.fromisoformat(as_of)
    if end<start:return -1
    n=0;cur=start
    while cur<end:
        cur+=timedelta(days=1)
        if cur.weekday()<5:n+=1
    return n

def calendar_age(value,as_of):
    return None if not value or not as_of else (date.fromisoformat(as_of)-date.fromisoformat(value)).days

def expected_fair_value(model):
    rows=[(model.get("scenarios") or {}).get(k) or {} for k in ("bear","base","bull")]
    if any(not finite(x.get("fair_value")) or not finite(x.get("probability")) for x in rows):return None
    total=sum(float(x["probability"]) for x in rows)
    if not (abs(total-1)<=.001 or abs(total-100)<=.1):return None
    d=100 if total>1.01 else 1
    return sum(float(x["fair_value"])*float(x["probability"])/d for x in rows)
def valuation_metrics(asset):
    model=asset.get("valuation_model") or {};price=asset.get("reference_price");ev=model.get("expected_fair_value")
    if not finite(ev):ev=expected_fair_value(model)
    base=(model.get("scenarios") or {}).get("base") or {}
    er=pct_change(ev,price);mos=pct_change(base.get("fair_value"),price)
    fpe=float(price)/float(model["forward_eps"]) if finite(price) and finite(model.get("forward_eps")) and float(model["forward_eps"])>0 else None
    npe=float(price)/float(model["normalized_eps"]) if finite(price) and finite(model.get("normalized_eps")) and float(model["normalized_eps"])>0 else None
    return {"expected_fair_value":round(ev,4) if finite(ev) else None,"expected_return_pct":round(er,4) if finite(er) else None,"margin_of_safety_pct":round(mos,4) if finite(mos) else None,"forward_pe":round(fpe,4) if finite(fpe) else None,"normalized_pe":round(npe,4) if finite(npe) else None}
def evidence_summary(asset,required):
    ev=asset.get("evidence") or [];first=[x for x in ev if x.get("quality")=="FIRST_PARTY" and x.get("status")=="VERIFIED"]
    metrics={x.get("metric") for x in first};missing=[m for m in required if m not in metrics]
    latest=max((x.get("observed_at") for x in first if x.get("observed_at")),default=None)
    return {"verified_first_party_count":len(first),"verified_metric_count":len(metrics),"required_metrics":list(required),"missing_required_metrics":missing,"ok":not missing,"latest_verified_observed_at":latest}
def freshness(asset,policy,meta,evidence):
    as_of=meta.get("decision_as_of") or meta.get("as_of");market=asset.get("reference_price_date") or meta.get("market_data_as_of")
    ages={"market_trading_sessions":trading_weekday_age(market,as_of),"fundamentals_calendar_days":calendar_age(asset.get("fundamental_data_as_of"),as_of),"revenue_calendar_days":calendar_age(asset.get("revenue_data_as_of"),as_of),"event_check_calendar_days":calendar_age(asset.get("event_data_as_of"),as_of)}
    checks={"market":ages["market_trading_sessions"] is not None and 0<=ages["market_trading_sessions"]<=int(policy.get("market_max_trading_sessions",1)),"fundamentals":ages["fundamentals_calendar_days"] is not None and 0<=ages["fundamentals_calendar_days"]<=int(policy.get("fundamental_max_days",130)),"revenue":ages["revenue_calendar_days"] is not None and 0<=ages["revenue_calendar_days"]<=int(policy.get("revenue_max_days",45)),"events":ages["event_check_calendar_days"] is not None and 0<=ages["event_check_calendar_days"]<=int(policy.get("event_check_max_days",policy.get("event_max_days",14)))}
    required=set(policy.get("required_for_buy",checks))
    return {"ok":all(checks[k] for k in required),"checks":checks,"ages":ages,"dates":{"market_observed_at":market,"fundamental_period_end":asset.get("fundamental_data_as_of"),"revenue_period_end":asset.get("revenue_data_as_of"),"last_event_at":evidence.get("latest_verified_observed_at"),"last_event_checked_at":asset.get("event_data_as_of")}}
def screen_map(screen):return {str(x.get("ticker")):x for x in screen.get("candidates",[]) if x.get("ticker")}
def evidence_metrics(asset):return {x.get("metric") for x in asset.get("evidence",[]) if x.get("quality")=="FIRST_PARTY" and x.get("status")=="VERIFIED"}
def catalyst_score(asset):
    m=evidence_metrics(asset)
    if "structural_catalyst" in m:return 15.0,"VERIFIED_STRUCTURAL_CATALYST"
    n=len(m & {"guidance","revenue_trend","capacity","product_ramp","backlog"})
    return (12.0,"MULTI_SOURCE_CATALYST_SUPPORT") if n>=2 else (8.0,"SINGLE_SUPPORTING_CATALYST_SIGNAL") if n==1 else (0.0,"NO_STRUCTURED_CATALYST_EVIDENCE")
def cash_score(asset):
    m=evidence_metrics(asset)
    if "free_cash_flow" in m:return 10.0,"VERIFIED_FCF",True
    if m & {"operating_cash_flow","cash_flow"}:return 8.0,"VERIFIED_OPERATING_CASH_FLOW",True
    if m & {"balance_sheet_cash_flow","balance_sheet"}:return 5.0,"VERIFIED_BALANCE_SHEET_ONLY",True
    return 0.0,"MISSING_DEDICATED_CASH_FLOW_EVIDENCE",False
def growth_score(p,max_score):return 0.0 if not finite(p) or float(p)<=0 else round(max_score*clamp(float(p),0,40)/40,4)
def revenue_score(row):
    if not row or not finite(row.get("revenue_yoy_pct")):return 0.0,{"status":"MISSING_REVENUE_GROWTH"},False
    yoy=float(row["revenue_yoy_pct"]);cum=float(row["cumulative_revenue_yoy_pct"]) if finite(row.get("cumulative_revenue_yoy_pct")) else None
    vals=[clamp(yoy,0,100)]+([clamp(cum,0,100)] if cum is not None else []);signal=sum(vals)/len(vals);score=20*signal/100
    outlier=yoy>100 or (cum is not None and cum>100)
    if outlier:score=min(score,14)
    return round(score,4),{"status":"COMPLETE","raw_yoy_pct":yoy,"raw_cumulative_yoy_pct":cum,"ranking_cap_pct":100,"base_effect_outlier":outlier},True
def valuation_score(metrics,benchmark):
    mos,er,ber=metrics.get("margin_of_safety_pct"),metrics.get("expected_return_pct"),benchmark.get("expected_return_pct");spread=float(er)-float(ber) if finite(er) and finite(ber) else None
    score=12.5*clamp(float(mos) if finite(mos) else 0,0,40)/40+12.5*clamp((float(spread) if finite(spread) else -10)+10,0,30)/30
    complete=finite(mos) and finite(er) and finite(ber)
    return round(score,4),spread,complete
def derive_factors(asset,row,benchmark):
    model=asset.get("valuation_model") or {};fvn=pct_change(model.get("forward_eps"),model.get("normalized_eps"));earn_complete=finite(fvn)
    earnings=growth_score(fvn,24)+(6 if row and finite(row.get("latest_reported_eps")) and float(row["latest_reported_eps"])>0 else 0);earnings=min(30,earnings)
    revenue,rmeta,rev_complete=revenue_score(row);metrics=valuation_metrics(asset);value,spread,val_complete=valuation_score(metrics,benchmark);cat,catbasis=catalyst_score(asset);cash,cashbasis,cash_complete=cash_score(asset)
    factors={"earnings_acceleration":round(earnings,4),"revenue_quality":revenue,"valuation":value,"structural_catalyst":cat,"balance_sheet_cash_flow":cash}
    coverage={"earnings_acceleration":earn_complete,"revenue_quality":rev_complete,"valuation":val_complete and model.get("status")=="COMPLETE","structural_catalyst":True,"balance_sheet_cash_flow":cash_complete};missing=[k for k,v in coverage.items() if not v]
    inputs={"screen_lane":row.get("discovery_lane") if row else None,"reported_eps":row.get("latest_reported_eps") if row else None,"forward_vs_normalized_eps_pct":round(fvn,4) if finite(fvn) else None,"revenue":rmeta,"valuation_metrics":metrics,"alpha_spread_pct":round(spread,4) if finite(spread) else None,"catalyst_basis":catbasis,"cash_flow_basis":cashbasis}
    return factors,inputs,metrics,spread,{"status":"COMPLETE" if not missing else "INCOMPLETE","coverage":coverage,"missing_factors":missing,"rule":"Missing structured factor evidence is VERIFY, never silently equivalent to negative evidence."}
def penalties(asset,row,fresh,inputs):
    p={}
    if (asset.get("valuation_model") or {}).get("status")!="COMPLETE":p["valuation_incomplete"]=-5
    if not fresh["checks"].get("fundamentals"):p["fundamental_staleness"]=-4
    if (inputs.get("revenue") or {}).get("base_effect_outlier"):p["growth_base_effect"]=-6
    if str((asset.get("risk_model") or {}).get("cyclicality","")).upper()=="HIGH":p["high_cyclicality"]=-5
    if inputs.get("cash_flow_basis")=="MISSING_DEDICATED_CASH_FLOW_EVIDENCE":p["cash_flow_evidence_gap"]=-3
    if not row:p["screen_feature_gap"]=-3
    return p
def confidence(asset,row,fresh,evidence,factors):
    required=max(1,len(evidence["required_metrics"]));eq=35*(required-len(evidence["missing_required_metrics"]))/required;model=asset.get("valuation_model") or {}
    scenario=model.get("status")=="COMPLETE" and all(finite(((model.get("scenarios") or {}).get(k) or {}).get("fair_value")) for k in ("bear","base","bull"));fv=(12 if scenario else 0)+(6 if row and finite(row.get("revenue_yoy_pct")) else 0)+(4 if asset.get("next_check") else 0)+(3 if evidence.get("latest_verified_observed_at") else 0)
    available=sum([finite(model.get("forward_eps")),bool(row and finite(row.get("revenue_yoy_pct"))),finite(valuation_metrics(asset).get("expected_return_pct")),factors.get("structural_catalyst",0)>0,factors.get("balance_sheet_cash_flow",0)>0]);mc=20*available/5
    tf=(5 if asset.get("invalidation_condition") else 0)+(5 if asset.get("next_check") else 0);df=10*sum(1 for v in fresh["checks"].values() if v)/max(1,len(fresh["checks"]))
    return {"evidence_quality":round(eq,4),"forecast_visibility":round(min(25,fv),4),"model_completeness":round(mc,4),"thesis_falsifiability":round(tf,4),"data_freshness":round(df,4)}
def expectation(asset):
    model=asset.get("valuation_model") or {};base=(model.get("scenarios") or {}).get("base") or {};price=asset.get("reference_price");multiple=base.get("multiple");eps=base.get("eps")
    if not finite(price) or not finite(multiple) or float(multiple)<=0:return {"status":"INCOMPLETE","authority":"ANALYTIC_ONLY"}
    implied=float(price)/float(multiple);gap=pct_change(eps,implied)
    return {"status":"COMPLETE","authority":"ANALYTIC_ONLY","base_multiple":float(multiple),"market_implied_eps":round(implied,4),"base_case_eps":float(eps) if finite(eps) else None,"base_vs_implied_eps_gap_pct":round(gap,4) if finite(gap) else None,"guardrail":"Expectation gap cannot create or upgrade BUY authority."}
def gate(asset,benchmark,data):
    p=data["decision_policy"];checks={"score_complete":asset.get("score_coverage",{}).get("status")=="COMPLETE","score":float(asset.get("score") or 0)>=float(data["methodology"]["buy_gate"]),"confidence":float(asset.get("confidence_score") or 0)>=float(p["min_confidence_score"]),"valuation_complete":(asset.get("valuation_model") or {}).get("status")=="COMPLETE","margin_of_safety":finite(asset["valuation_metrics"].get("margin_of_safety_pct")) and float(asset["valuation_metrics"]["margin_of_safety_pct"])>=float(p["min_margin_of_safety_pct"]),"alpha_spread":finite(asset.get("alpha_spread_pct")) and float(asset["alpha_spread_pct"])>=float(p["min_alpha_spread_pct"]),"freshness":asset.get("freshness",{}).get("ok") is True,"evidence":asset.get("evidence_gate",{}).get("ok") is True,"benchmark_complete":(benchmark.get("valuation_model") or {}).get("status")=="COMPLETE","benchmark_freshness":benchmark.get("freshness",{}).get("ok") is True,"benchmark_evidence":benchmark.get("evidence_gate",{}).get("ok") is True,"thesis":asset.get("thesis_status")!="INVALIDATED"};failed=[k for k,v in checks.items() if not v]
    return {"ok":not failed,"checks":checks,"failed":failed,"authority":"PYTHON_SECURITY_BUY_GATE"}
def derive(asset,row,data,benchmark):
    required=data["decision_policy"]["required_evidence_metrics"];ev=evidence_summary(asset,required);fresh=freshness(asset,data["freshness_policy"],data["meta"],ev);factors,inputs,metrics,spread,coverage=derive_factors(asset,row,benchmark);pens=penalties(asset,row,fresh,inputs);score=clamp(sum(factors.values())+sum(pens.values()),0,100);conf=confidence(asset,row,fresh,ev,factors)
    asset.update({"factor_scores":factors,"penalties":pens,"score":round(score,2),"score_coverage":coverage,"confidence_factors":conf,"confidence_score":round(clamp(sum(conf.values()),0,100),2),"score_provenance":ENGINE_VERSION,"feature_inputs":inputs,"valuation_metrics":metrics,"alpha_spread_pct":round(spread,4) if finite(spread) else None,"freshness":fresh,"evidence_gate":ev,"market_expectation":expectation(asset)})
    return asset
def fingerprint(data):
    p=copy.deepcopy(data);p.get("meta",{}).pop("decision_fingerprint",None);return hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def generate(write=False):
    data=load("data/alpha.json",{});screen=load("data/screen.json",{});out=copy.deepcopy(data);screen_as_of=screen.get("meta",{}).get("as_of");research_as_of=out.get("meta",{}).get("as_of");decision_as_of=max(x for x in (screen_as_of,research_as_of) if x)
    out.setdefault("meta",{}).update({"schema_version":max(5,int(out["meta"].get("schema_version") or 0)),"decision_engine_version":ENGINE_VERSION,"decision_as_of":decision_as_of,"authority":"PYTHON_CANONICAL_SECURITY_ENGINE","research_inputs_as_of":research_as_of,"screen_inputs_as_of":screen_as_of})
    out.setdefault("methodology",{})["weights"]=DEFAULT_WEIGHTS;out["methodology"]["score_max"]=100;out["methodology"]["score_contract"]="Derived from structured features; missing evidence yields INCOMPLETE coverage and VERIFY, never a fabricated zero-quality conclusion."
    out["confidence_methodology"]={"score_max":100,"weights":CONFIDENCE_WEIGHTS,"note":"Deterministic evidence/model/freshness completeness, not attractiveness."};out["freshness_policy"].pop("market_max_calendar_days",None);out["freshness_policy"]["market_max_trading_sessions"]=int(out["freshness_policy"].get("market_max_trading_sessions",1));out["freshness_policy"]["event_check_max_days"]=int(out["freshness_policy"].get("event_check_max_days",out["freshness_policy"].get("event_max_days",14)));out["freshness_policy"]["market_target"]="<= 1 observed trading weekday";out["freshness_policy"]["note"]="Market freshness uses trading weekdays; event occurrence and event-check timestamps are separate."
    rows=screen_map(screen);b=out["benchmark_asset"];req=out["decision_policy"]["required_evidence_metrics"];bev=evidence_summary(b,req);b["valuation_metrics"]=valuation_metrics(b);b["freshness"]=freshness(b,out["freshness_policy"],out["meta"],bev);b["evidence_gate"]=bev;b["market_expectation"]=expectation(b)
    derived=[derive(s,rows.get(str(s.get("ticker"))),out,b["valuation_metrics"]) for s in out.get("stocks",[])];derived.sort(key=lambda x:(x.get("score_coverage",{}).get("status")!="COMPLETE",-float(x.get("score") or 0),-float(x.get("confidence_score") or 0),str(x.get("ticker"))))
    t=out["methodology"]["grade_thresholds"]
    for i,s in enumerate(derived,1):
        s["rank"]=i;score=float(s["score"]);complete=s.get("score_coverage",{}).get("status")=="COMPLETE";s["grade"]=("A" if score>=t["A"] else "B" if score>=t["B"] else "C" if score>=t["C"] else "D") if complete else "VERIFY"
    for s in derived:
        g=gate(s,b,out);s["buy_gate"]=g
        if s.get("thesis_status")=="INVALIDATED":action="AVOID"
        elif s.get("score_coverage",{}).get("status")!="COMPLETE":action="VERIFY"
        elif g["ok"]:action="BUY CANDIDATE"
        elif float(s["score"])>=float(out["methodology"]["buy_gate"]):action="VERIFY"
        elif float(s["score"])>=float(t["B"]):action="WATCH"
        else:action="AVOID"
        s["action"]=action
    out["stocks"]=derived;trigger=out.get("rotation_event") or {};hit=finite(b.get("reference_price")) and finite(trigger.get("trigger_price")) and float(b["reference_price"])>=float(trigger["trigger_price"]);buy=[s for s in derived if s.get("action")=="BUY CANDIDATE"];buy.sort(key=lambda x:float(x.get("alpha_spread_pct") or -999),reverse=True);out["rotation_event"]["meaning"]="EVENT ALERT ONLY. It never gates BUY, rotation review, or allocation.";out["rotation_review"]={"status":"READY_FOR_REVIEW" if buy else "BLOCKED","security_authority":"PYTHON_SECURITY_BUY_GATE","portfolio_authority":"ELEPHANT_CAPITAL_ALLOCATION_OS","tsmc_3000_event_triggered":bool(hit),"event_is_gate":False,"buy_candidate_tickers":[x["ticker"] for x in buy],"best_relative_alpha_ticker":buy[0]["ticker"] if buy else None,"rule":"Only complete securities that pass the full Buy Gate can become BUY CANDIDATE; TSMC 3000 is informational.","allocations":[]};out["rotation_model"]["allocation_mode"]="MOVED_TO_ELEPHANT";out["rotation_model"]["note"]="Portfolio sizing/cash/debt/leverage ownership moved to linwuyen/Elephant.";out["meta"]["decision_fingerprint"]=fingerprint(out)
    if write:save("data/alpha.json",out)
    return out

def main():
    o=generate(True);print(json.dumps({"engine":o["meta"]["decision_engine_version"],"decision_as_of":o["meta"]["decision_as_of"],"fingerprint":o["meta"]["decision_fingerprint"],"stocks":[{"ticker":x["ticker"],"score":x["score"],"coverage":x["score_coverage"]["status"],"action":x["action"]} for x in o["stocks"]],"rotation":o["rotation_review"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
