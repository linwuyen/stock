#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
screen = json.loads((ROOT / "data/screen.json").read_text(encoding="utf-8"))
LANES = {"GROWTH", "INFLECTION", "MISPRICING_QUALITY"}
FINANCIAL_WORDS = ("金融", "銀行", "保險", "證券", "票券", "金控", "投信", "期貨")

meta = screen.get("meta") or {}
rules = screen.get("rules") or {}
if meta.get("status") == "BOOTSTRAP_PENDING_FIRST_FULL_SCAN":
    print("screen priority validation skipped during bootstrap")
    raise SystemExit(0)

assert int(meta.get("schema_version") or 0) >= 5
assert set((rules.get("discovery_lanes") or {}).keys()) == LANES
assert rules.get("ranking", {}).get("primary") == "screen_priority"
assert rules.get("screen_is_not_buy_gate") is True
assert rules.get("market_cap", {}).get("mode") == "HARD_DERIVED"

cap = float(rules["ranking"]["growth_ranking_cap_pct"])
minimum_cap = float(rules["market_cap"]["min_twd"])
candidates = screen.get("candidates") or []
priorities = []

for item in candidates:
    assert "action" not in item
    lane = item.get("discovery_lane")
    assert lane in LANES, (item.get("ticker"), lane)
    priority = float(item.get("screen_priority"))
    priorities.append(priority)
    industry = str(item.get("industry") or "")
    haystack = f"{industry} {item.get('name','')}"
    assert industry != "17"
    assert not any(word in haystack for word in FINANCIAL_WORDS)
    assert float(item.get("market_cap_twd") or 0) >= minimum_cap
    assert item.get("market_cap_source") in {"DERIVED_ISSUED_SHARES_X_CLOSE", "DIRECT_OFFICIAL_FIELD"}
    yoy = item.get("revenue_yoy_pct")
    cum = item.get("cumulative_revenue_yoy_pct")
    if lane == "GROWTH":
        assert yoy is not None and float(yoy) >= 25
    elif lane == "INFLECTION":
        assert yoy is not None and float(yoy) >= 15
        assert cum is None or float(yoy) >= float(cum) + 5
    else:
        assert yoy is not None and float(yoy) >= 8
        assert item.get("latest_reported_eps") is not None and float(item["latest_reported_eps"]) > 0
        assert item.get("pe_ttm") is not None and 0 < float(item["pe_ttm"]) <= 20
    outlier = (yoy is not None and float(yoy) > cap) or (cum is not None and float(cum) > cap)
    if outlier:
        assert "GROWTH_BASE_EFFECT_OUTLIER" in (item.get("flags") or [])
        assert item.get("verification_priority") == "HIGH"
        assert float(item.get("priority_revenue_yoy_pct") or 0) <= cap
        assert float(item.get("priority_cumulative_revenue_yoy_pct") or 0) <= cap

assert priorities == sorted(priorities, reverse=True), "Top50 must be sorted by lane-aware robust priority"
deep = screen.get("deep_research_queue") or []
assert len(deep) <= 10
if len(deep) >= 3 and len({x.get("discovery_lane") for x in candidates}) >= 2:
    assert len({x.get("discovery_lane") for x in deep}) >= 2, "Deep Research collapsed into one discovery lane"

print("SCREEN V5 PRIORITY PASS", len(candidates), "candidates", {x.get("discovery_lane") for x in deep})
