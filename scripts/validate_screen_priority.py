#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
screen = json.loads((ROOT / "data/screen.json").read_text(encoding="utf-8"))
FINANCIAL_WORDS = ("金融", "銀行", "保險", "證券", "票券", "金控", "投信", "期貨")
FINANCIAL_INDUSTRY_CODES = {"17"}

rules = screen.get("rules", {})
status = screen.get("meta", {}).get("status")
if status == "BOOTSTRAP_PENDING_FIRST_FULL_SCAN":
    print("screen priority validation skipped during bootstrap")
    raise SystemExit(0)
if rules.get("ranking", {}).get("primary") != "screen_priority":
    print("screen priority validation deferred until first scanner refresh after migration")
    raise SystemExit(0)

assert "Alpha Engine" in rules.get("profitability_proxy_boundary", "")
winsor = float(rules.get("ranking", {}).get("growth_winsorization_pct", 500))

candidates = screen.get("candidates", [])
priorities = []
for item in candidates:
    assert "action" not in item, "discovery rows may not carry portfolio actions"
    priority = item.get("screen_priority")
    assert priority is not None, f"{item.get('ticker')} missing screen_priority"
    priorities.append(float(priority))

    industry = str(item.get("industry", "")).strip()
    haystack = f"{industry} {item.get('name','')}"
    assert industry not in FINANCIAL_INDUSTRY_CODES, f"financial industry code leaked into screen: {item.get('ticker')} {item.get('name')}"
    assert not any(word in haystack for word in FINANCIAL_WORDS), f"financial issuer leaked into screen: {item.get('ticker')} {item.get('name')}"

    basis = item.get("profitability_basis")
    if basis == "POSITIVE_TTM_PE_PROXY":
        assert item.get("latest_reported_eps") is None
        assert item.get("pe_ttm") is not None and float(item["pe_ttm"]) > 0
        assert "PROFITABILITY_PROXY_TTM_PE" in item.get("flags", [])
        assert "EARNINGS_FILING_NOT_IN_CURRENT_DATASET" in item.get("flags", [])

    raw_rev = item.get("revenue_yoy_pct")
    raw_cum = item.get("cumulative_revenue_yoy_pct")
    is_outlier = (raw_rev is not None and float(raw_rev) > winsor) or (raw_cum is not None and float(raw_cum) > winsor)
    if is_outlier:
        assert "GROWTH_BASE_EFFECT_OUTLIER" in item.get("flags", []), f"{item.get('ticker')} unflagged growth outlier"
        assert float(item.get("priority_revenue_yoy_pct", winsor)) <= winsor
        assert float(item.get("priority_cumulative_revenue_yoy_pct", winsor)) <= winsor

assert priorities == sorted(priorities, reverse=True), "Top 50 must be ordered by robust screen_priority"
assert len({round(x, 4) for x in priorities[:10]}) > 1 or len(priorities) <= 1, "screen_priority unexpectedly saturated across top names"
print(f"screen priority PASS: {len(candidates)} candidates")
