#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
screen = json.loads((ROOT / "data/screen.json").read_text(encoding="utf-8"))

rules = screen.get("rules", {})
if screen.get("meta", {}).get("status") == "BOOTSTRAP_PENDING_FIRST_FULL_SCAN":
    print("screen priority validation skipped during bootstrap")
    raise SystemExit(0)

assert rules.get("ranking", {}).get("primary") == "screen_priority"
assert "Alpha Engine" in rules.get("profitability_proxy_boundary", "")

candidates = screen.get("candidates", [])
priorities = []
for item in candidates:
    assert "action" not in item, "discovery rows may not carry portfolio actions"
    priority = item.get("screen_priority")
    assert priority is not None, f"{item.get('ticker')} missing screen_priority"
    priorities.append(float(priority))
    basis = item.get("profitability_basis")
    if basis == "POSITIVE_TTM_PE_PROXY":
        assert item.get("latest_reported_eps") is None
        assert item.get("pe_ttm") is not None and float(item["pe_ttm"]) > 0
        assert "PROFITABILITY_PROXY_TTM_PE" in item.get("flags", [])
        assert "EARNINGS_FILING_NOT_IN_CURRENT_DATASET" in item.get("flags", [])

assert priorities == sorted(priorities, reverse=True), "Top 50 must be ordered by non-saturating screen_priority"
assert len({round(x, 4) for x in priorities[:10]}) > 1 or len(priorities) <= 1, "screen_priority unexpectedly saturated across top names"
print(f"screen priority PASS: {len(candidates)} candidates")
