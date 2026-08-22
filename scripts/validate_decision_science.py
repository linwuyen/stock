#!/usr/bin/env python3
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


performance = load("data/performance.json")
assert performance["meta"]["schema_version"] == 3
assert performance["meta"]["return_type"] == "TOTAL_RETURN_CASH_DISTRIBUTIONS_NO_REINVESTMENT"
assert performance["minimum_samples_for_calibration"] >= 30
for row in performance["horizons"]:
    assert "mean_excess_total_return_pct" in row
    assert "mean_excess_price_return_pct" in row
    assert row["sample_size"] >= 0
    assert row["price_return_diagnostic_sample_size"] >= row["sample_size"]

actions = load("data/corporate-actions.json")
assert actions["schema_version"] == 1
assert actions["source"]["authority"] == "TWSE OpenAPI"
assert actions["source"]["first_party"] is True
assert actions["ledger"]["historical_backfill_complete"] is False
seen = set()
previous = None
for action in actions.get("actions", []):
    key = (action["date"], action["ticker"])
    assert key not in seen
    seen.add(key)
    assert previous is None or previous <= key
    previous = key
    for field in ("cash_dividend_per_share", "stock_dividend_ratio_raw"):
        value = action.get(field)
        assert value is None or (math.isfinite(float(value)) and float(value) >= 0)

voi = load("data/research-voi.json")
assert voi["schema_version"] == 1
assert voi["authority"] is False
assert voi["score_influence"] is False
assert voi["buy_gate_influence"] is False
priorities = [row["research_priority"] for row in voi["rows"]]
assert priorities == sorted(priorities, reverse=True)
assert [row["rank"] for row in voi["rows"]] == list(range(1, len(voi["rows"]) + 1))
for row in voi["rows"]:
    assert 0 <= row["research_priority"] <= 100
    assert "upstream_action" in row
    assert "guardrail" in row

contract = load("data/model-promotion-contract.json")
assert contract["contract"] == "pre_registered_security_model_promotion_v1"
assert contract["automatic_promotion"] is False
assert contract["immutable_without_version_bump"] is True
rr = contract["rules"]["realized_return_calibration"]
assert rr["eligible_return_metric"] == "EXCESS_TOTAL_RETURN_VS_2330"
assert rr["price_return_diagnostic_not_eligible"] is True
assert rr["minimum_samples_per_primary_horizon"] >= 30
assert rr["requires_point_in_time_entry_state"] is True
assert rr["requires_corporate_action_complete"] is True
sc = contract["rules"]["scenario_probability_challenger"]
assert sc["minimum_resolved_forecasts"] >= 30
assert sc["promotion_requires_versioned_review"] is True
assert contract["rules"]["buy_gate_change"]["cannot_be_triggered_by_voi"] is True

print("decision science PASS")
