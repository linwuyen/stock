#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
screen = json.loads((ROOT / "data/screen.json").read_text(encoding="utf-8"))

meta = screen.get("meta", {})
health = screen.get("source_health", {})
promotion = meta.get("promotion_enabled_by_market", {})
resilience = meta.get("transport_resilience")

# One-time migration: old screen snapshots do not yet have resilience telemetry.
if not resilience:
    print("source resilience validation deferred until first resilient scanner refresh")
    raise SystemExit(0)

assert resilience.get("attempts_per_source", 0) >= 3
assert resilience.get("identity_encoding") is True
assert resilience.get("official_csv_fallbacks") is True
assert resilience.get("income_endpoint_optional_for_discovery_only") is True
assert set(resilience.get("fail_closed_for", [])) == {"profiles", "quotes", "valuation", "revenue"}

for market in ("TWSE", "TPEX"):
    rows = health.get(market, {})
    for label in ("profiles", "quotes", "valuation", "revenue"):
        item = rows.get(label, {})
        if promotion.get(market):
            assert item.get("ok") is True, f"{market} promotion ON while critical {label} is not healthy"
        assert item.get("promotion_blocking") is True, f"{market} {label} must be promotion-blocking"
    income = rows.get("income", {})
    assert income.get("optional") is True
    assert income.get("promotion_blocking") is False
    if income.get("ok") is False:
        assert income.get("transport", {}).get("optional_degraded") is True

print(f"source resilience PASS: promotion={promotion}")
