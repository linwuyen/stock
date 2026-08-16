#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import build_alpha

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ACTIONS = {"BUY CANDIDATE", "VERIFY", "WATCH", "AVOID"}
ALLOWED_LANES = {"GROWTH", "INFLECTION", "MISPRICING_QUALITY"}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validate_screen(screen):
    meta = screen.get("meta") or {}
    rules = screen.get("rules") or {}
    assert int(meta.get("schema_version") or 0) >= 5
    assert meta.get("status") in {"COMPLETE", "DEGRADED", "BOOTSTRAP_PENDING_FIRST_FULL_SCAN"}
    assert meta.get("fail_closed") is True
    assert rules.get("screen_is_not_buy_gate") is True
    assert rules.get("market_cap", {}).get("mode") == "HARD_DERIVED"
    lanes = rules.get("discovery_lanes") or {}
    assert set(lanes) == ALLOWED_LANES
    candidates = screen.get("candidates") or []
    deep = screen.get("deep_research_queue") or []
    assert len(candidates) <= 50
    assert len(deep) <= 10
    assert len({x.get("ticker") for x in candidates}) == len(candidates)
    assert [x.get("rank") for x in candidates] == list(range(1, len(candidates) + 1))
    assert {x.get("ticker") for x in deep} <= {x.get("ticker") for x in candidates}
    priorities = [float(x.get("screen_priority")) for x in candidates]
    assert priorities == sorted(priorities, reverse=True)
    cap = float(rules["ranking"]["growth_ranking_cap_pct"])
    for row in candidates:
        assert row.get("discovery_lane") in ALLOWED_LANES
        assert "action" not in row
        assert row.get("promotion_eligible") is True
        assert float(row.get("market_cap_twd") or 0) >= float(rules["market_cap"]["min_twd"])
        assert row.get("market_cap_source") in {"DERIVED_ISSUED_SHARES_X_CLOSE", "DIRECT_OFFICIAL_FIELD"}
        yoy = row.get("revenue_yoy_pct")
        cum = row.get("cumulative_revenue_yoy_pct")
        outlier = (yoy is not None and float(yoy) > cap) or (cum is not None and float(cum) > cap)
        if outlier:
            assert "GROWTH_BASE_EFFECT_OUTLIER" in (row.get("flags") or [])
            assert row.get("verification_priority") == "HIGH"
            assert float(row.get("priority_revenue_yoy_pct") or 0) <= cap
            assert float(row.get("priority_cumulative_revenue_yoy_pct") or 0) <= cap


def validate_alpha(alpha):
    assert int(alpha["meta"].get("schema_version") or 0) >= 5
    assert alpha["meta"].get("authority") == "PYTHON_CANONICAL_SECURITY_ENGINE"
    assert alpha["meta"].get("decision_engine_version") == build_alpha.ENGINE_VERSION
    assert alpha["meta"].get("decision_fingerprint")
    assert "market_max_calendar_days" not in alpha["freshness_policy"]
    expected = build_alpha.generate(write=False)
    assert expected == alpha, "alpha.json is not canonical; run scripts/build_alpha.py"
    benchmark = alpha["benchmark_asset"]
    assert benchmark.get("valuation_metrics") is not None
    assert benchmark.get("freshness") is not None
    assert benchmark.get("evidence_gate") is not None
    ranks = []
    last_score = None
    for stock in alpha.get("stocks", []):
        ranks.append(stock["rank"])
        assert stock.get("action") in ALLOWED_ACTIONS
        assert stock.get("score_provenance") == build_alpha.ENGINE_VERSION
        assert set(stock.get("factor_scores") or {}) == set(build_alpha.DEFAULT_WEIGHTS)
        assert set(stock.get("confidence_factors") or {}) == set(build_alpha.CONFIDENCE_WEIGHTS)
        assert stock.get("buy_gate", {}).get("authority") == "PYTHON_SECURITY_BUY_GATE"
        assert stock.get("market_expectation", {}).get("authority") == "ANALYTIC_ONLY"
        if stock["action"] == "BUY CANDIDATE":
            assert stock["buy_gate"]["ok"] is True
        if last_score is not None:
            assert float(stock["score"]) <= last_score
        last_score = float(stock["score"])
    assert ranks == list(range(1, len(ranks) + 1))
    rotation = alpha.get("rotation_review") or {}
    assert rotation.get("event_is_gate") is False
    assert rotation.get("portfolio_authority") == "ELEPHANT_CAPITAL_ALLOCATION_OS"
    assert rotation.get("allocations") == []
    assert "EVENT ALERT ONLY" in alpha["rotation_event"]["meaning"]


def validate_alerts(alerts, alpha):
    assert alerts["policy"].get("notify_only_on_transition_into_buy_candidate") is True
    assert alerts["policy"].get("never_notify_for_screen_only") is True
    assert alerts["policy"].get("never_execute_trade") is True
    expected = sorted(x["ticker"] for x in alpha.get("stocks", []) if x.get("action") == "BUY CANDIDATE")
    actual = sorted(x["ticker"] if isinstance(x, dict) else x for x in alerts.get("active_buy_candidates", []))
    assert actual == expected, f"alert state stale: {actual} != {expected}"


def validate_performance(performance):
    assert performance["meta"]["primary_cohort"] == "BUY_CANDIDATE"
    assert performance["meta"]["return_type"] == "PRICE_RETURN_EX_DIVIDENDS"
    assert [x["weeks"] for x in performance["horizons"]] == [1, 4, 13, 26, 52]
    assert performance["meta"]["status"] in {"CALIBRATED", "INSUFFICIENT_HISTORY"}


def main():
    alpha = load("data/alpha.json")
    screen = load("data/screen.json")
    alerts = load("data/alerts.json")
    performance = load("data/performance.json")
    liquidity = load("data/liquidity-history.json")
    validate_screen(screen)
    validate_alpha(alpha)
    validate_alerts(alerts, alpha)
    validate_performance(performance)
    assert liquidity.get("schema_version", 0) >= 1
    assert liquidity.get("window") == 20
    print("SECURITY ENGINE V5 VALIDATION PASS")
    print("decision fingerprint:", alpha["meta"]["decision_fingerprint"])
    print("actions:", {x["ticker"]: x["action"] for x in alpha["stocks"]})


if __name__ == "__main__":
    main()
