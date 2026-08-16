#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "security-v5.0.0"
DEFAULT_WEIGHTS = {
    "earnings_acceleration": 30,
    "revenue_quality": 20,
    "valuation": 25,
    "structural_catalyst": 15,
    "balance_sheet_cash_flow": 10,
}
CONFIDENCE_WEIGHTS = {
    "evidence_quality": 35,
    "forecast_visibility": 25,
    "model_completeness": 20,
    "thesis_falsifiability": 10,
    "data_freshness": 10,
}


def load(path: str, default=None):
    p = ROOT / path
    if not p.exists():
        return copy.deepcopy(default)
    return json.loads(p.read_text(encoding="utf-8"))


def save(path: str, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finite(v):
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def clamp(v, lo, hi):
    return max(lo, min(hi, float(v)))


def pct_change(new, old):
    if not finite(new) or not finite(old) or float(old) == 0:
        return None
    return (float(new) / float(old) - 1.0) * 100.0


def trading_weekday_age(value: str | None, as_of: str | None):
    if not value or not as_of:
        return None
    start, end = date.fromisoformat(value), date.fromisoformat(as_of)
    if end < start:
        return -1
    count, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            count += 1
    return count


def calendar_age(value: str | None, as_of: str | None):
    if not value or not as_of:
        return None
    return (date.fromisoformat(as_of) - date.fromisoformat(value)).days


def expected_fair_value(model):
    scenarios = model.get("scenarios") or {}
    rows = [scenarios.get(k) or {} for k in ("bear", "base", "bull")]
    if not rows or any(not finite(x.get("fair_value")) or not finite(x.get("probability")) for x in rows):
        return None
    total = sum(float(x["probability"]) for x in rows)
    if not (abs(total - 1.0) <= 0.001 or abs(total - 100.0) <= 0.1):
        return None
    divisor = 100.0 if total > 1.01 else 1.0
    return sum(float(x["fair_value"]) * float(x["probability"]) / divisor for x in rows)


def valuation_metrics(asset):
    model = asset.get("valuation_model") or {}
    price = asset.get("reference_price")
    expected = model.get("expected_fair_value")
    if not finite(expected):
        expected = expected_fair_value(model)
    expected_return = pct_change(expected, price)
    base = (model.get("scenarios") or {}).get("base") or {}
    mos = pct_change(base.get("fair_value"), price)
    forward_pe = float(price) / float(model["forward_eps"]) if finite(price) and finite(model.get("forward_eps")) and float(model["forward_eps"]) > 0 else None
    normalized_pe = float(price) / float(model["normalized_eps"]) if finite(price) and finite(model.get("normalized_eps")) and float(model["normalized_eps"]) > 0 else None
    return {
        "expected_fair_value": round(expected, 4) if finite(expected) else None,
        "expected_return_pct": round(expected_return, 4) if finite(expected_return) else None,
        "margin_of_safety_pct": round(mos, 4) if finite(mos) else None,
        "forward_pe": round(forward_pe, 4) if finite(forward_pe) else None,
        "normalized_pe": round(normalized_pe, 4) if finite(normalized_pe) else None,
    }


def evidence_summary(asset, required):
    evidence = asset.get("evidence") or []
    first_party = [x for x in evidence if x.get("quality") == "FIRST_PARTY" and x.get("status") == "VERIFIED"]
    verified_metrics = {x.get("metric") for x in first_party}
    missing = [m for m in required if m not in verified_metrics]
    latest_event = max((x.get("observed_at") for x in first_party if x.get("observed_at")), default=None)
    return {
        "verified_first_party_count": len(first_party),
        "verified_metric_count": len(verified_metrics),
        "required_metrics": list(required),
        "missing_required_metrics": missing,
        "ok": not missing,
        "latest_verified_observed_at": latest_event,
    }


def freshness(asset, policy, meta, evidence):
    as_of = meta.get("decision_as_of") or meta.get("as_of")
    market_date = asset.get("reference_price_date") or meta.get("market_data_as_of")
    market_age = trading_weekday_age(market_date, as_of)
    fundamental_age = calendar_age(asset.get("fundamental_data_as_of"), as_of)
    revenue_age = calendar_age(asset.get("revenue_data_as_of"), as_of)
    event_checked = asset.get("event_data_as_of")
    event_age = calendar_age(event_checked, as_of)

    max_market = int(policy.get("market_max_trading_sessions", 1))
    checks = {
        "market": market_age is not None and 0 <= market_age <= max_market,
        "fundamentals": fundamental_age is not None and 0 <= fundamental_age <= int(policy.get("fundamental_max_days", 130)),
        "revenue": revenue_age is not None and 0 <= revenue_age <= int(policy.get("revenue_max_days", 45)),
        "events": event_age is not None and 0 <= event_age <= int(policy.get("event_check_max_days", policy.get("event_max_days", 14))),
    }
    required = set(policy.get("required_for_buy", checks))
    return {
        "ok": all(checks[k] for k in required),
        "checks": checks,
        "ages": {
            "market_trading_sessions": market_age,
            "fundamentals_calendar_days": fundamental_age,
            "revenue_calendar_days": revenue_age,
            "event_check_calendar_days": event_age,
        },
        "dates": {
            "market_observed_at": market_date,
            "fundamental_period_end": asset.get("fundamental_data_as_of"),
            "revenue_period_end": asset.get("revenue_data_as_of"),
            "last_event_at": evidence.get("latest_verified_observed_at"),
            "last_event_checked_at": event_checked,
        },
        "policy": {
            "market_max_trading_sessions": max_market,
            "fundamental_max_days": int(policy.get("fundamental_max_days", 130)),
            "revenue_max_days": int(policy.get("revenue_max_days", 45)),
            "event_check_max_days": int(policy.get("event_check_max_days", policy.get("event_max_days", 14))),
        },
    }


def screen_row_map(screen):
    return {str(x.get("ticker")): x for x in screen.get("candidates", []) if x.get("ticker")}


def evidence_catalyst_score(asset):
    evidence = asset.get("evidence") or []
    verified = {x.get("metric") for x in evidence if x.get("quality") == "FIRST_PARTY" and x.get("status") == "VERIFIED"}
    if "structural_catalyst" in verified:
        return 15.0, "VERIFIED_STRUCTURAL_CATALYST"
    supporting = len(verified & {"guidance", "revenue_trend", "capacity", "product_ramp", "backlog"})
    if supporting >= 2:
        return 12.0, "MULTI_SOURCE_CATALYST_SUPPORT"
    if supporting == 1:
        return 8.0, "SINGLE_SUPPORTING_CATALYST_SIGNAL"
    return 0.0, "NO_STRUCTURED_CATALYST_EVIDENCE"


def cash_flow_score(asset):
    evidence = asset.get("evidence") or []
    verified = {x.get("metric") for x in evidence if x.get("quality") == "FIRST_PARTY" and x.get("status") == "VERIFIED"}
    if "free_cash_flow" in verified:
        return 10.0, "VERIFIED_FCF"
    if "operating_cash_flow" in verified or "cash_flow" in verified:
        return 8.0, "VERIFIED_OPERATING_CASH_FLOW"
    if "balance_sheet_cash_flow" in verified or "balance_sheet" in verified:
        return 5.0, "VERIFIED_BALANCE_SHEET_ONLY"
    return 0.0, "MISSING_DEDICATED_CASH_FLOW_EVIDENCE"


def growth_score(pct, max_score):
    if not finite(pct):
        return 0.0
    x = float(pct)
    if x <= 0:
        return 0.0
    return round(max_score * clamp(x, 0, 40) / 40.0, 4)


def revenue_quality_score(row):
    if not row:
        return 0.0, {"status": "MISSING_SCREEN_FEATURES"}
    yoy = row.get("revenue_yoy_pct")
    cum = row.get("cumulative_revenue_yoy_pct")
    if not finite(yoy):
        return 0.0, {"status": "MISSING_REVENUE_GROWTH"}
    raw_yoy = float(yoy)
    clipped_yoy = clamp(raw_yoy, 0, 100)
    values = [clipped_yoy]
    if finite(cum):
        values.append(clamp(float(cum), 0, 100))
    signal = sum(values) / len(values)
    score = 20.0 * signal / 100.0
    if raw_yoy > 100 or (finite(cum) and float(cum) > 100):
        score = min(score, 14.0)
    return round(score, 4), {
        "status": "COMPLETE",
        "raw_yoy_pct": raw_yoy,
        "raw_cumulative_yoy_pct": float(cum) if finite(cum) else None,
        "ranking_cap_pct": 100,
        "base_effect_outlier": raw_yoy > 100 or (finite(cum) and float(cum) > 100),
    }


def valuation_score(metrics, benchmark_metrics):
    mos = metrics.get("margin_of_safety_pct")
    er = metrics.get("expected_return_pct")
    benchmark_er = benchmark_metrics.get("expected_return_pct")
    spread = float(er) - float(benchmark_er) if finite(er) and finite(benchmark_er) else None
    mos_component = 12.5 * clamp(float(mos) if finite(mos) else 0, 0, 40) / 40.0
    spread_component = 12.5 * clamp((float(spread) if finite(spread) else -10) + 10, 0, 30) / 30.0
    return round(mos_component + spread_component, 4), spread


def deterministic_factors(asset, screen_row, benchmark_metrics):
    model = asset.get("valuation_model") or {}
    forward_vs_normalized = pct_change(model.get("forward_eps"), model.get("normalized_eps"))
    profitability_bonus = 6.0 if screen_row and finite(screen_row.get("latest_reported_eps")) and float(screen_row["latest_reported_eps"]) > 0 else 0.0
    earnings = min(30.0, growth_score(forward_vs_normalized, 24.0) + profitability_bonus)
    revenue, revenue_meta = revenue_quality_score(screen_row)
    metrics = valuation_metrics(asset)
    value, spread = valuation_score(metrics, benchmark_metrics)
    catalyst, catalyst_basis = evidence_catalyst_score(asset)
    cashflow, cashflow_basis = cash_flow_score(asset)
    factors = {
        "earnings_acceleration": round(earnings, 4),
        "revenue_quality": revenue,
        "valuation": value,
        "structural_catalyst": catalyst,
        "balance_sheet_cash_flow": cashflow,
    }
    inputs = {
        "screen_lane": screen_row.get("discovery_lane") if screen_row else None,
        "reported_eps": screen_row.get("latest_reported_eps") if screen_row else None,
        "forward_vs_normalized_eps_pct": round(forward_vs_normalized, 4) if finite(forward_vs_normalized) else None,
        "revenue": revenue_meta,
        "valuation_metrics": metrics,
        "alpha_spread_pct": round(spread, 4) if finite(spread) else None,
        "catalyst_basis": catalyst_basis,
        "cash_flow_basis": cashflow_basis,
    }
    return factors, inputs, metrics, spread


def deterministic_penalties(asset, row, fresh, inputs):
    penalties = {}
    if (asset.get("valuation_model") or {}).get("status") != "COMPLETE":
        penalties["valuation_incomplete"] = -5
    if not fresh["checks"].get("fundamentals"):
        penalties["fundamental_staleness"] = -4
    revenue = inputs.get("revenue") or {}
    if revenue.get("base_effect_outlier"):
        penalties["growth_base_effect"] = -6
    if str((asset.get("risk_model") or {}).get("cyclicality", "")).upper() == "HIGH":
        penalties["high_cyclicality"] = -5
    if inputs.get("cash_flow_basis") == "MISSING_DEDICATED_CASH_FLOW_EVIDENCE":
        penalties["cash_flow_evidence_gap"] = -3
    if not row:
        penalties["screen_feature_gap"] = -3
    return penalties


def confidence_factors(asset, row, fresh, evidence, factors):
    required_count = max(1, len(evidence["required_metrics"]))
    evidence_quality = 35.0 * (required_count - len(evidence["missing_required_metrics"])) / required_count
    model = asset.get("valuation_model") or {}
    scenario_complete = model.get("status") == "COMPLETE" and all(
        finite(((model.get("scenarios") or {}).get(k) or {}).get("fair_value")) and finite(((model.get("scenarios") or {}).get(k) or {}).get("probability"))
        for k in ("bear", "base", "bull")
    )
    forecast_visibility = 0.0
    if scenario_complete: forecast_visibility += 12.0
    if row and finite(row.get("revenue_yoy_pct")): forecast_visibility += 6.0
    if asset.get("next_check"): forecast_visibility += 4.0
    if evidence.get("latest_verified_observed_at"): forecast_visibility += 3.0
    available = 0
    available += 1 if finite((asset.get("valuation_model") or {}).get("forward_eps")) else 0
    available += 1 if row and finite(row.get("revenue_yoy_pct")) else 0
    available += 1 if finite(valuation_metrics(asset).get("expected_return_pct")) else 0
    available += 1 if factors.get("structural_catalyst", 0) > 0 else 0
    available += 1 if factors.get("balance_sheet_cash_flow", 0) > 0 else 0
    completeness = 20.0 * available / 5.0
    falsifiability = (5.0 if asset.get("invalidation_condition") else 0.0) + (5.0 if asset.get("next_check") else 0.0)
    freshness_score = 10.0 * sum(1 for v in fresh["checks"].values() if v) / max(1, len(fresh["checks"]))
    return {
        "evidence_quality": round(evidence_quality, 4),
        "forecast_visibility": round(min(25.0, forecast_visibility), 4),
        "model_completeness": round(completeness, 4),
        "thesis_falsifiability": round(falsifiability, 4),
        "data_freshness": round(freshness_score, 4),
    }


def market_expectation(asset):
    model = asset.get("valuation_model") or {}
    base = (model.get("scenarios") or {}).get("base") or {}
    price = asset.get("reference_price")
    multiple = base.get("multiple")
    base_eps = base.get("eps")
    if not finite(price) or not finite(multiple) or float(multiple) <= 0:
        return {"status": "INCOMPLETE", "authority": "ANALYTIC_ONLY"}
    implied_eps = float(price) / float(multiple)
    gap = pct_change(base_eps, implied_eps)
    return {
        "status": "COMPLETE",
        "authority": "ANALYTIC_ONLY",
        "base_multiple": float(multiple),
        "market_implied_eps": round(implied_eps, 4),
        "base_case_eps": float(base_eps) if finite(base_eps) else None,
        "base_vs_implied_eps_gap_pct": round(gap, 4) if finite(gap) else None,
        "guardrail": "Expectation gap cannot create or upgrade BUY authority.",
    }


def buy_gate(asset, benchmark, data):
    p = data["decision_policy"]
    checks = {
        "score": float(asset.get("score") or 0) >= float(data["methodology"]["buy_gate"]),
        "confidence": float(asset.get("confidence_score") or 0) >= float(p["min_confidence_score"]),
        "valuation_complete": (asset.get("valuation_model") or {}).get("status") == "COMPLETE",
        "margin_of_safety": finite(asset["valuation_metrics"].get("margin_of_safety_pct")) and float(asset["valuation_metrics"]["margin_of_safety_pct"]) >= float(p["min_margin_of_safety_pct"]),
        "alpha_spread": finite(asset.get("alpha_spread_pct")) and float(asset["alpha_spread_pct"]) >= float(p["min_alpha_spread_pct"]),
        "freshness": (asset.get("freshness") or {}).get("ok") is True,
        "evidence": (asset.get("evidence_gate") or {}).get("ok") is True,
        "benchmark_complete": (benchmark.get("valuation_model") or {}).get("status") == "COMPLETE",
        "benchmark_freshness": (benchmark.get("freshness") or {}).get("ok") is True,
        "benchmark_evidence": (benchmark.get("evidence_gate") or {}).get("ok") is True,
        "thesis": asset.get("thesis_status") != "INVALIDATED",
    }
    failed = [k for k, ok in checks.items() if not ok]
    return {"ok": not failed, "checks": checks, "failed": failed, "authority": "PYTHON_SECURITY_BUY_GATE"}


def derive_asset(asset, row, data, benchmark_metrics):
    required = data["decision_policy"]["required_evidence_metrics"]
    evidence = evidence_summary(asset, required)
    fresh = freshness(asset, data["freshness_policy"], data["meta"], evidence)
    factors, inputs, metrics, spread = deterministic_factors(asset, row, benchmark_metrics)
    penalties = deterministic_penalties(asset, row, fresh, inputs)
    score = clamp(sum(factors.values()) + sum(penalties.values()), 0, 100)
    confidence_parts = confidence_factors(asset, row, fresh, evidence, factors)
    confidence = clamp(sum(confidence_parts.values()), 0, 100)
    asset["factor_scores"] = factors
    asset["penalties"] = penalties
    asset["score"] = round(score, 2)
    asset["confidence_factors"] = confidence_parts
    asset["confidence_score"] = round(confidence, 2)
    asset["score_provenance"] = ENGINE_VERSION
    asset["feature_inputs"] = inputs
    asset["valuation_metrics"] = metrics
    asset["alpha_spread_pct"] = round(spread, 4) if finite(spread) else None
    asset["freshness"] = fresh
    asset["evidence_gate"] = evidence
    asset["market_expectation"] = market_expectation(asset)
    return asset


def canonical_fingerprint(data):
    payload = copy.deepcopy(data)
    payload.get("meta", {}).pop("decision_fingerprint", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate(write=False):
    data = load("data/alpha.json", {})
    screen = load("data/screen.json", {})
    out = copy.deepcopy(data)
    screen_as_of = (screen.get("meta") or {}).get("as_of")
    research_as_of = (out.get("meta") or {}).get("as_of")
    decision_as_of = max(x for x in (screen_as_of, research_as_of) if x)
    out.setdefault("meta", {})["schema_version"] = max(5, int(out["meta"].get("schema_version") or 0))
    out["meta"]["decision_engine_version"] = ENGINE_VERSION
    out["meta"]["decision_as_of"] = decision_as_of
    out["meta"]["authority"] = "PYTHON_CANONICAL_SECURITY_ENGINE"
    out["meta"]["research_inputs_as_of"] = research_as_of
    out["meta"]["screen_inputs_as_of"] = screen_as_of
    out.setdefault("methodology", {})["weights"] = DEFAULT_WEIGHTS
    out["methodology"]["score_max"] = 100
    out["methodology"]["score_contract"] = "factor scores and penalties are derived from structured market-screen fields, valuation scenarios, first-party evidence, freshness and explicit risk fields; stored legacy factor scores are ignored."
    out["confidence_methodology"] = {"score_max": 100, "weights": CONFIDENCE_WEIGHTS, "note": "Confidence is deterministic evidence/model/freshness completeness, not attractiveness."}
    out["freshness_policy"].pop("market_max_calendar_days", None)
    out["freshness_policy"]["market_max_trading_sessions"] = int(out["freshness_policy"].get("market_max_trading_sessions", 1))
    out["freshness_policy"]["event_check_max_days"] = int(out["freshness_policy"].get("event_check_max_days", out["freshness_policy"].get("event_max_days", 14)))
    out["freshness_policy"]["market_target"] = "<= 1 observed trading weekday"
    out["freshness_policy"]["note"] = "Market freshness uses trading weekdays; event occurrence and event-check timestamps are separate."
    rows = screen_row_map(screen)
    benchmark = out["benchmark_asset"]
    required = out["decision_policy"]["required_evidence_metrics"]
    benchmark_evidence = evidence_summary(benchmark, required)
    benchmark["valuation_metrics"] = valuation_metrics(benchmark)
    benchmark["freshness"] = freshness(benchmark, out["freshness_policy"], out["meta"], benchmark_evidence)
    benchmark["evidence_gate"] = benchmark_evidence
    benchmark["market_expectation"] = market_expectation(benchmark)
    derived = [derive_asset(stock, rows.get(str(stock.get("ticker"))), out, benchmark["valuation_metrics"]) for stock in out.get("stocks", [])]
    derived.sort(key=lambda x: (-float(x.get("score") or 0), -float(x.get("confidence_score") or 0), str(x.get("ticker"))))
    thresholds = out["methodology"]["grade_thresholds"]
    for i, stock in enumerate(derived, 1):
        stock["rank"] = i
        score = float(stock["score"])
        stock["grade"] = "A" if score >= thresholds["A"] else "B" if score >= thresholds["B"] else "C" if score >= thresholds["C"] else "D"
    for stock in derived:
        gate = buy_gate(stock, benchmark, out)
        stock["buy_gate"] = gate
        if stock.get("thesis_status") == "INVALIDATED": action = "AVOID"
        elif gate["ok"]: action = "BUY CANDIDATE"
        elif float(stock["score"]) >= float(out["methodology"]["buy_gate"]): action = "VERIFY"
        elif float(stock["score"]) >= float(thresholds["B"]): action = "WATCH"
        else: action = "AVOID"
        stock["action"] = action
    out["stocks"] = derived
    trigger = out.get("rotation_event") or {}
    trigger_hit = finite(benchmark.get("reference_price")) and finite(trigger.get("trigger_price")) and float(benchmark["reference_price"]) >= float(trigger["trigger_price"])
    buyable = [x for x in derived if x.get("action") == "BUY CANDIDATE"]
    buyable.sort(key=lambda x: float(x.get("alpha_spread_pct") or -999), reverse=True)
    out["rotation_event"]["meaning"] = "EVENT ALERT ONLY. It never gates BUY, rotation review, or allocation."
    out["rotation_review"] = {
        "status": "READY_FOR_REVIEW" if buyable else "BLOCKED",
        "security_authority": "PYTHON_SECURITY_BUY_GATE",
        "portfolio_authority": "ELEPHANT_CAPITAL_ALLOCATION_OS",
        "tsmc_3000_event_triggered": bool(trigger_hit),
        "event_is_gate": False,
        "buy_candidate_tickers": [x["ticker"] for x in buyable],
        "best_relative_alpha_ticker": buyable[0]["ticker"] if buyable else None,
        "rule": "Review only securities that pass the full Buy Gate and beat the benchmark hurdle; TSMC 3000 is informational.",
        "allocations": [],
    }
    out["rotation_model"]["allocation_mode"] = "MOVED_TO_ELEPHANT"
    out["rotation_model"]["note"] = "Portfolio sizing/cash/debt/leverage ownership moved to linwuyen/Elephant. This repo publishes security authority only."
    out["meta"]["decision_fingerprint"] = canonical_fingerprint(out)
    if write:
        save("data/alpha.json", out)
    return out


def main():
    out = generate(write=True)
    print(json.dumps({"engine": out["meta"]["decision_engine_version"], "decision_as_of": out["meta"]["decision_as_of"], "fingerprint": out["meta"]["decision_fingerprint"], "stocks": [{"ticker": x["ticker"], "score": x["score"], "action": x["action"]} for x in out["stocks"]], "rotation": out["rotation_review"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
