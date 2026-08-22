#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import build_alpha_v6 as build_alpha

ROOT=Path(__file__).resolve().parents[1]
ALLOWED_ACTIONS={"BUY CANDIDATE","VERIFY","WATCH","AVOID"}
ALLOWED_LANES={"GROWTH","INFLECTION","MISPRICING_QUALITY"}
LEGACY_KEYS={"margin_of_safety_pct","min_margin_of_safety_pct","margin_of_safety"}
def load(path):return json.loads((ROOT/path).read_text(encoding="utf-8"))

def assert_no_legacy_keys(obj,path="root"):
    if isinstance(obj,dict):
        for k,v in obj.items():
            assert k not in LEGACY_KEYS,f"legacy field {path}.{k}"
            assert_no_legacy_keys(v,f"{path}.{k}")
    elif isinstance(obj,list):
        for i,v in enumerate(obj):assert_no_legacy_keys(v,f"{path}[{i}]")

def validate_screen(screen):
    meta=screen.get("meta") or {};rules=screen.get("rules") or {}
    assert int(meta.get("schema_version") or 0)>=5
    assert meta.get("status") in {"COMPLETE","DEGRADED","BOOTSTRAP_PENDING_FIRST_FULL_SCAN"}
    assert meta.get("fail_closed") is True;assert rules.get("screen_is_not_buy_gate") is True
    assert rules.get("market_cap",{}).get("mode")=="HARD_DERIVED";assert set(rules.get("discovery_lanes") or {})==ALLOWED_LANES
    c=screen.get("candidates") or [];deep=screen.get("deep_research_queue") or []
    assert len(c)<=50 and len(deep)<=10;assert len({x.get("ticker") for x in c})==len(c);assert [x.get("rank") for x in c]==list(range(1,len(c)+1));assert {x.get("ticker") for x in deep}<={x.get("ticker") for x in c}
    priorities=[float(x.get("screen_priority")) for x in c];assert priorities==sorted(priorities,reverse=True)
    cap=float(rules["ranking"]["growth_ranking_cap_pct"])
    for row in c:
        assert row.get("discovery_lane") in ALLOWED_LANES;assert "action" not in row;assert row.get("promotion_eligible") is True
        assert float(row.get("market_cap_twd") or 0)>=float(rules["market_cap"]["min_twd"]);assert row.get("market_cap_source") in {"DERIVED_ISSUED_SHARES_X_CLOSE","DIRECT_OFFICIAL_FIELD"}
        yoy=row.get("revenue_yoy_pct");cum=row.get("cumulative_revenue_yoy_pct");out=(yoy is not None and float(yoy)>cap) or (cum is not None and float(cum)>cap)
        if out:
            assert "GROWTH_BASE_EFFECT_OUTLIER" in (row.get("flags") or []);assert row.get("verification_priority")=="HIGH";assert float(row.get("priority_revenue_yoy_pct") or 0)<=cap;assert float(row.get("priority_cumulative_revenue_yoy_pct") or 0)<=cap

def validate_alpha(alpha):
    assert int(alpha["meta"].get("schema_version") or 0)==6;assert alpha["meta"].get("authority")=="PYTHON_CANONICAL_SECURITY_ENGINE";assert alpha["meta"].get("decision_engine_version")==build_alpha.ENGINE_VERSION;assert alpha["meta"].get("decision_fingerprint");assert "market_max_calendar_days" not in alpha["freshness_policy"]
    assert "min_base_upside_pct" in alpha.get("decision_policy",{});assert "min_margin_of_safety_pct" not in alpha.get("decision_policy",{})
    expected=build_alpha.generate(write=False);assert expected==alpha,"alpha.json is not canonical; run scripts/build_alpha_v6.py"
    assert_no_legacy_keys(alpha)
    b=alpha["benchmark_asset"];assert b.get("valuation_metrics") is not None and b.get("freshness") is not None and b.get("evidence_gate") is not None;assert "base_upside_pct" in b.get("valuation_metrics",{})
    ranks=[];order=[]
    for s in alpha.get("stocks",[]):
        ranks.append(s["rank"]);status=s.get("score_coverage",{}).get("status");order.append((status!="COMPLETE",-float(s.get("score") or 0)))
        assert s.get("action") in ALLOWED_ACTIONS;assert s.get("score_provenance")==build_alpha.ENGINE_VERSION;assert set(s.get("factor_scores") or {})==set(build_alpha.DEFAULT_WEIGHTS);assert set(s.get("confidence_factors") or {})==set(build_alpha.CONFIDENCE_WEIGHTS);assert s.get("buy_gate",{}).get("authority")=="PYTHON_SECURITY_BUY_GATE";assert s.get("market_expectation",{}).get("authority")=="ANALYTIC_ONLY";assert "base_upside_pct" in s.get("valuation_metrics",{});assert "base_upside" in s.get("buy_gate",{}).get("checks",{})
        assert status in {"COMPLETE","INCOMPLETE"}
        if status=="INCOMPLETE":assert s.get("action")=="VERIFY" or s.get("thesis_status")=="INVALIDATED","missing data must verify, not masquerade as negative evidence"
        if s["action"]=="BUY CANDIDATE":assert status=="COMPLETE" and s["buy_gate"]["ok"] is True
    assert ranks==list(range(1,len(ranks)+1));assert order==sorted(order)
    rot=alpha.get("rotation_review") or {};assert rot.get("event_is_gate") is False;assert rot.get("portfolio_authority")=="ELEPHANT_CAPITAL_ALLOCATION_OS";assert rot.get("allocations")==[];assert "EVENT ALERT ONLY" in alpha["rotation_event"]["meaning"]

def validate_alerts(alerts,alpha):
    assert alerts["policy"].get("notify_only_on_transition_into_buy_candidate") is True;assert alerts["policy"].get("never_notify_for_screen_only") is True;assert alerts["policy"].get("never_execute_trade") is True
    expected=sorted(x["ticker"] for x in alpha.get("stocks",[]) if x.get("action")=="BUY CANDIDATE");actual=sorted(x["ticker"] if isinstance(x,dict) else x for x in alerts.get("active_buy_candidates",[]));assert actual==expected,f"alert state stale: {actual} != {expected}"
def validate_performance(p):
    assert int(p["meta"].get("schema_version") or 0)==3
    assert p["meta"]["primary_cohort"]=="BUY_CANDIDATE"
    assert p["meta"]["return_type"]=="TOTAL_RETURN_CASH_DISTRIBUTIONS_NO_REINVESTMENT"
    assert p["meta"].get("corporate_action_source")=="TWSE_TWT48U_ALL"
    assert [x["weeks"] for x in p["horizons"]]==[1,4,13,26,52]
    assert p["meta"]["status"] in {"CALIBRATED","INSUFFICIENT_HISTORY"}
    assert int(p.get("minimum_samples_for_calibration") or 0)>=30
    for row in p["horizons"]:
        assert "mean_excess_total_return_pct" in row
        assert "mean_excess_price_return_pct" in row
        assert int(row.get("price_return_diagnostic_sample_size") or 0)>=int(row.get("sample_size") or 0)
def main():
    a=load("data/alpha.json");s=load("data/screen.json");alerts=load("data/alerts.json");p=load("data/performance.json");liq=load("data/liquidity-history.json");validate_screen(s);validate_alpha(a);validate_alerts(alerts,a);validate_performance(p);assert liq.get("schema_version",0)>=1 and liq.get("window")==20
    print("SECURITY ENGINE V6 VALIDATION PASS");print("decision fingerprint:",a["meta"]["decision_fingerprint"]);print("actions:",{x["ticker"]:x["action"] for x in a["stocks"]})
if __name__=="__main__":main()
