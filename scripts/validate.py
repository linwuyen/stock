#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sumv(values):
    return sum(float(v or 0) for v in (values or {}).values())


def grade(score, thresholds):
    if score >= thresholds["A"]: return "A"
    if score >= thresholds["B"]: return "B"
    if score >= thresholds["C"]: return "C"
    return "D"


def age_days(value, as_of):
    if not value: return float("inf")
    return (date.fromisoformat(as_of) - date.fromisoformat(value)).days


def valuation(asset):
    model = asset.get("valuation_model", {})
    price = asset.get("reference_price")
    base = model.get("scenarios", {}).get("base", {})
    base_fv = base.get("fair_value")
    expected = model.get("expected_fair_value")
    if expected is None:
        scenarios = [model.get("scenarios", {}).get(k, {}) for k in ("bear", "base", "bull")]
        if all(s.get("fair_value") is not None and s.get("probability") is not None for s in scenarios):
            probability = sum(float(s["probability"]) for s in scenarios)
            divisor = 100 if probability > 1.01 else 1
            expected = sum(float(s["fair_value"]) * float(s["probability"]) / divisor for s in scenarios)
    expected_return = model.get("expected_return_pct")
    if expected_return is None and price and expected is not None:
        expected_return = (expected / price - 1) * 100
    mos = model.get("margin_of_safety_pct")
    if mos is None and price and base_fv is not None:
        mos = (base_fv / price - 1) * 100
    return expected_return, mos


def evidence_ok(asset, required):
    evidence = asset.get("evidence", [])
    return all(any(
        item.get("metric") == metric and
        item.get("quality") == "FIRST_PARTY" and
        item.get("status") == "VERIFIED"
        for item in evidence
    ) for metric in required)


def freshness(asset, policy, meta):
    dates = {
        "market": asset.get("reference_price_date") or meta.get("market_data_as_of"),
        "fundamentals": asset.get("fundamental_data_as_of"),
        "revenue": asset.get("revenue_data_as_of"),
        "events": asset.get("event_data_as_of") or meta.get("as_of"),
    }
    limits = {
        "market": policy["market_max_calendar_days"],
        "fundamentals": policy["fundamental_max_days"],
        "revenue": policy["revenue_max_days"],
        "events": policy["event_max_days"],
    }
    required = set(policy.get("required_for_buy", ["market", "fundamentals", "revenue", "events"]))
    checks, ages = {}, {}
    for key, value in dates.items():
        ages[key] = age_days(value, meta["as_of"])
        checks[key] = (key not in required) if value is None else 0 <= ages[key] <= limits[key]
    return {"checks": checks, "ages": ages, "ok": all(checks.values())}


def implied_action(stock, data):
    if stock.get("thesis_status") == "INVALIDATED": return "AVOID"
    er, mos = valuation(stock)
    benchmark_er, _ = valuation(data["benchmark_asset"])
    spread = None if er is None or benchmark_er is None else er - benchmark_er
    complete = stock.get("valuation_model", {}).get("status") == "COMPLETE"
    benchmark_complete = data["benchmark_asset"].get("valuation_model", {}).get("status") == "COMPLETE" and benchmark_er is not None
    stock_fresh = freshness(stock, data["freshness_policy"], data["meta"])["ok"]
    benchmark_fresh = freshness(data["benchmark_asset"], data["freshness_policy"], data["meta"])["ok"]
    required = data["decision_policy"]["required_evidence_metrics"]
    buy = (
        stock["score"] >= data["methodology"]["buy_gate"] and
        stock["confidence_score"] >= data["decision_policy"]["min_confidence_score"] and
        benchmark_complete and benchmark_fresh and evidence_ok(data["benchmark_asset"], required) and
        complete and mos is not None and mos >= data["decision_policy"]["min_margin_of_safety_pct"] and
        spread is not None and spread >= data["decision_policy"]["min_alpha_spread_pct"] and
        stock_fresh and evidence_ok(stock, required)
    )
    if buy: return "BUY CANDIDATE"
    if stock["score"] >= data["methodology"]["buy_gate"]: return "VERIFY"
    if stock["score"] >= data["methodology"]["grade_thresholds"]["B"]: return "WATCH"
    return "AVOID"


def validate_complete_valuation(asset, label):
    model = asset.get("valuation_model", {})
    if model.get("status") != "COMPLETE": return
    scenarios = model["scenarios"]
    probability = sum(float(scenarios[k]["probability"]) for k in ("bear", "base", "bull"))
    assert abs(probability - 1) < 1e-6 or abs(probability - 100) < 1e-6, f"{label} scenario probabilities"
    divisor = 100 if probability > 1.01 else 1
    expected = 0.0
    for key in ("bear", "base", "bull"):
        scenario = scenarios[key]
        assert all(scenario.get(z) is not None for z in ("eps", "multiple", "fair_value", "probability"))
        assert abs(scenario["eps"] * scenario["multiple"] - scenario["fair_value"]) <= max(1, abs(scenario["fair_value"]) * 0.02), f"{label} {key} FV mismatch"
        expected += float(scenario["fair_value"]) * float(scenario["probability"]) / divisor
    if model.get("expected_fair_value") is not None:
        assert abs(expected - float(model["expected_fair_value"])) <= max(0.5, abs(expected) * 0.002), f"{label} expected FV mismatch"
    price = asset.get("reference_price")
    if price and model.get("expected_return_pct") is not None:
        assert abs((expected / price - 1) * 100 - float(model["expected_return_pct"])) < 0.1, f"{label} expected return mismatch"
    base_fv = float(scenarios["base"]["fair_value"])
    if price and model.get("margin_of_safety_pct") is not None:
        assert abs((base_fv / price - 1) * 100 - float(model["margin_of_safety_pct"])) < 0.1, f"{label} MOS mismatch"


def validate_screen(screen):
    assert screen["meta"]["schema_version"] >= 2
    assert screen["meta"]["status"] in {"BOOTSTRAP_PENDING_FIRST_FULL_SCAN", "COMPLETE", "DEGRADED"}
    assert screen["meta"].get("fail_closed") is True
    assert screen["rules"].get("screen_is_not_buy_gate") is True
    assert "research_funnel" in screen["rules"]
    assert screen["rules"].get("market_cap", {}).get("mode") == "SOFT_ONLY"
    promotion = screen["meta"].get("promotion_enabled_by_market", {})
    assert set(promotion) == {"TWSE", "TPEX"}
    candidates = screen.get("candidates", [])
    deep = screen.get("deep_research_queue", [])
    assert len(candidates) <= 50
    assert len(deep) <= 10
    tickers = [x["ticker"] for x in candidates]
    assert len(tickers) == len(set(tickers)), "duplicate screen ticker"
    ranks = [x["rank"] for x in candidates if x.get("rank") is not None]
    assert ranks == list(range(1, len(ranks) + 1)), "screen ranks must be contiguous"
    deep_tickers = {x["ticker"] for x in deep}
    assert deep_tickers.issubset(set(tickers)), "deep queue must be a subset of Top 50"
    for item in candidates:
        assert "action" not in item, "screen may never write portfolio action"
        assert item.get("market") in {"TWSE", "TPEX"}
        if item.get("promotion_eligible"):
            assert promotion[item["market"]] is True, "promotion allowed from degraded market"
    if screen["meta"]["status"] == "BOOTSTRAP_PENDING_FIRST_FULL_SCAN":
        assert not candidates and not deep
        assert promotion == {"TWSE": False, "TPEX": False}
    if screen["meta"]["status"] == "COMPLETE":
        assert all(promotion.values())


def validate_alerts(alerts, data):
    assert alerts["schema_version"] >= 1
    assert alerts["policy"].get("notify_only_on_transition_into_buy_candidate") is True
    assert alerts["policy"].get("never_notify_for_screen_only") is True
    assert alerts["policy"].get("never_execute_trade") is True
    expected_active = sorted(s["ticker"] for s in data["stocks"] if s.get("action") == "BUY CANDIDATE")
    actual_active = sorted(x["ticker"] if isinstance(x, dict) else x for x in alerts.get("active_buy_candidates", []))
    assert actual_active == expected_active, f"alert active set stale: {actual_active} != {expected_active}"
    keys = []
    for note in alerts.get("notifications", []):
        key = (note.get("ticker"), note.get("buy_entry_sequence"))
        assert None not in key
        keys.append(key)
    assert len(keys) == len(set(keys)), "duplicate alert notification entry"


def validate_events(events):
    assert events["schema_version"] >= 1
    assert events["policy"].get("do_not_overwrite_prior_event_records") is True
    ids, paths = [], []
    for event in events.get("events", []):
        ids.append(event["id"]); paths.append(event["path"])
        assert ".." not in event["path"]
        p = ROOT / event["path"]
        assert p.exists(), f"missing event file {p}"
    assert len(ids) == len(set(ids)), "duplicate event id"
    assert len(paths) == len(set(paths)), "duplicate event path"


def validate_performance(performance):
    assert performance["meta"]["schema_version"] >= 2
    assert performance["meta"]["primary_cohort"] == "BUY_CANDIDATE"
    assert performance["meta"]["return_type"] == "PRICE_RETURN_EX_DIVIDENDS"
    assert [h["weeks"] for h in performance["horizons"]] == [1, 4, 13, 26, 52]
    a_grade = performance.get("diagnostic_cohorts", {}).get("A_GRADE", [])
    assert [h["weeks"] for h in a_grade] == [1, 4, 13, 26, 52]


def main():
    data = load("data/alpha.json")
    screen = load("data/screen.json")
    performance = load("data/performance.json")
    history = load("data/history/index.json")
    alerts = load("data/alerts.json")
    events = load("data/events/index.json")
    liquidity = load("data/liquidity-history.json")

    assert data["meta"]["schema_version"] >= 3
    assert sum(data["methodology"]["weights"].values()) == 100
    assert sum(data["confidence_methodology"]["weights"].values()) == 100
    assert set(data["freshness_policy"].get("required_for_buy", [])) == {"market", "fundamentals", "revenue", "events"}
    validate_complete_valuation(data["benchmark_asset"], "2330 benchmark")
    required = data["decision_policy"]["required_evidence_metrics"]
    if data["benchmark_asset"].get("valuation_model", {}).get("status") == "COMPLETE":
        assert evidence_ok(data["benchmark_asset"], required), "benchmark evidence incomplete"
        assert freshness(data["benchmark_asset"], data["freshness_policy"], data["meta"])["ok"], "benchmark freshness failed"

    tickers, ranks = [], []
    previous_score = None
    benchmark_er, _ = valuation(data["benchmark_asset"])
    for stock in sorted(data["stocks"], key=lambda x: x["rank"]):
        tickers.append(stock["ticker"]); ranks.append(stock["rank"])
        score = sumv(stock["factor_scores"]) + sumv(stock.get("penalties"))
        confidence = sumv(stock["confidence_factors"])
        assert abs(score - stock["score"]) < 1e-9, f"{stock['ticker']} score mismatch {score} != {stock['score']}"
        assert abs(confidence - stock["confidence_score"]) < 1e-9, f"{stock['ticker']} confidence mismatch"
        assert stock["grade"] == grade(stock["score"], data["methodology"]["grade_thresholds"]), f"{stock['ticker']} grade mismatch"
        expected_action = implied_action(stock, data)
        assert stock["action"] == expected_action, f"{stock['ticker']} action must be derived: {expected_action}"
        if previous_score is not None:
            assert stock["score"] <= previous_score, "ranks must be descending by score"
        previous_score = stock["score"]
        for key, value in stock["factor_scores"].items(): assert 0 <= value <= data["methodology"]["weights"][key]
        for key, value in stock["confidence_factors"].items(): assert 0 <= value <= data["confidence_methodology"]["weights"][key]
        assert sumv(stock.get("penalties")) >= data["methodology"]["penalty_floor"]
        if stock.get("reference_price_date"):
            assert stock["reference_price_date"] <= data["meta"]["as_of"]
        validate_complete_valuation(stock, stock["ticker"])
        er, _ = valuation(stock)
        stored_spread = stock.get("alpha_spread_pct")
        if er is None or benchmark_er is None:
            assert stored_spread is None
        else:
            assert stored_spread is not None and abs((er - benchmark_er) - float(stored_spread)) < 0.1, f"{stock['ticker']} alpha spread mismatch"

    assert len(tickers) == len(set(tickers))
    assert ranks == list(range(1, len(ranks) + 1))
    assert "automatic" in data["rotation_event"]["meaning"].lower(), "3000 must remain event-only"
    fallback = data["rotation_model"]["fallback_allocations"]
    assert abs(sum(float(x["weight"]) for x in fallback) - 100) < 1e-9
    cash = next(x for x in fallback if x["ticker"] == "CASH")
    assert cash["weight"] >= data["rotation_model"]["guardrails"]["cash_floor_pct"]
    for item in fallback:
        if item["ticker"] != "CASH":
            assert item["weight"] <= data["rotation_model"]["guardrails"]["max_single_stock_pct"]
    market = date.fromisoformat(data["meta"]["market_data_as_of"])
    review = date.fromisoformat(data["meta"]["as_of"])
    assert 0 <= (review - market).days <= data["freshness_policy"]["market_max_calendar_days"]

    validate_screen(screen)
    validate_alerts(alerts, data)
    validate_events(events)
    validate_performance(performance)
    assert liquidity["schema_version"] >= 1 and liquidity.get("window") == 20

    snapshots = history.get("snapshots", [])
    dates = [entry["date"] for entry in snapshots]
    assert dates == sorted(set(dates))
    assert history["latest"] == dates[-1]
    for entry in snapshots:
        p = ROOT / entry["path"]
        assert p.exists(), f"missing {p}"
        snapshot = json.loads(p.read_text(encoding="utf-8"))
        assert snapshot["meta"]["as_of"] == entry["date"]
        assert all(0 <= x["score"] <= 100 for x in snapshot.get("stocks", []))

    print(f"PASS: v4 invariants; {len(tickers)} researched stocks; screen={screen['meta']['status']}; benchmark ER={benchmark_er:.2f}%")


if __name__ == "__main__":
    main()
