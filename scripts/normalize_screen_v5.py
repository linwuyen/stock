#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import scan_market

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(path, obj):
    (ROOT / path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_row(item):
    row = dict(item)
    lane = scan_market.discovery_lane(
        row.get("revenue_yoy_pct"),
        row.get("cumulative_revenue_yoy_pct"),
        row.get("pe_ttm"),
        row.get("latest_reported_eps"),
    )
    if lane is None:
        return None
    observations = int(row.get("liquidity_observations") or 0)
    profitability = row.get("profitability_basis") or "NO_PROFITABILITY_SIGNAL"
    row["discovery_lane"] = lane
    row["priority_revenue_yoy_pct"] = min(max(0.0, float(row.get("revenue_yoy_pct") or 0)), scan_market.GROWTH_RANKING_CAP_PCT)
    row["priority_cumulative_revenue_yoy_pct"] = min(max(0.0, float(row.get("cumulative_revenue_yoy_pct") or 0)), scan_market.GROWTH_RANKING_CAP_PCT)
    row["screen_priority"] = scan_market.lane_priority(
        lane,
        row.get("revenue_yoy_pct"),
        row.get("cumulative_revenue_yoy_pct"),
        row.get("pe_ttm"),
        row.get("latest_reported_eps"),
        profitability,
        row.get("median_turnover_twd"),
        row.get("latest_daily_turnover_twd"),
        observations,
        float(row.get("data_quality_score") or 0),
    )
    flags = list(dict.fromkeys(row.get("flags") or []))
    yoy = row.get("revenue_yoy_pct")
    cum = row.get("cumulative_revenue_yoy_pct")
    outlier = (yoy is not None and float(yoy) > scan_market.GROWTH_RANKING_CAP_PCT) or (cum is not None and float(cum) > scan_market.GROWTH_RANKING_CAP_PCT)
    if outlier and "GROWTH_BASE_EFFECT_OUTLIER" not in flags:
        flags.append("GROWTH_BASE_EFFECT_OUTLIER")
    if yoy is not None and float(yoy) > scan_market.EXTREME_GROWTH_PCT and "EXTREME_GROWTH_VERIFY_FIRST" not in flags:
        flags.append("EXTREME_GROWTH_VERIFY_FIRST")
    row["flags"] = flags
    row["verification_priority"] = "HIGH" if outlier or row.get("latest_reported_eps") is None else "NORMAL"
    row["promotion_eligible"] = bool(row.get("promotion_eligible", True))
    row.pop("action", None)
    return row


def diverse_top10(candidates):
    selected, used = [], set()
    for lane in scan_market.LANES:
        hit = next((x for x in candidates if x.get("discovery_lane") == lane and x["ticker"] not in used), None)
        if hit:
            selected.append(dict(hit)); used.add(hit["ticker"])
    for row in candidates:
        if row["ticker"] in used:
            continue
        selected.append(dict(row)); used.add(row["ticker"])
        if len(selected) == 10:
            break
    return selected[:10]


def generate(write=True):
    screen = load("data/screen.json")
    rows = []
    for item in screen.get("candidates") or []:
        normalized = normalize_row(item)
        if normalized and normalized.get("promotion_eligible"):
            rows.append(normalized)
    rows.sort(key=lambda x: (-float(x.get("screen_priority") or 0), -float(x.get("screen_score") or 0), str(x.get("ticker"))))
    rows = rows[:50]
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    deep = diverse_top10(rows)
    chosen = {x["ticker"] for x in deep}
    for row in rows:
        row["deep_research_selected"] = row["ticker"] in chosen
    meta = screen.setdefault("meta", {})
    meta["schema_version"] = 5
    meta["migration"] = "DETERMINISTIC_SCREEN_V5_NORMALIZATION"
    meta["fail_closed"] = True
    rules = screen.setdefault("rules", {})
    rules["market_cap"] = {
        "mode": "HARD_DERIVED",
        "min_twd": scan_market.MIN_MARKET_CAP_TWD,
        "primary_formula": "official close × official issued common shares",
        "fallback": "direct official market-cap field",
    }
    rules["discovery_lanes"] = {
        "GROWTH": "revenue YoY >=25%; outliers are capped and verification-prioritized",
        "INFLECTION": "revenue YoY >=15% and accelerating versus cumulative trend",
        "MISPRICING_QUALITY": "revenue YoY >=8%, positive reported EPS and official TTM PE <=20",
    }
    rules["ranking"] = {
        "primary": "screen_priority",
        "secondary": "screen_score",
        "growth_ranking_cap_pct": scan_market.GROWTH_RANKING_CAP_PCT,
        "extreme_growth_verify_pct": scan_market.EXTREME_GROWTH_PCT,
        "screen_priority": "lane-specific robust priority; growth above cap adds no ranking benefit and creates verification penalty",
        "screen_score": "legacy explainability only",
    }
    rules["screen_is_not_buy_gate"] = True
    rules["research_funnel"] = "Official market data -> multi-lane Screen Top50 -> Deep Research -> Python Security Engine -> Buy Gate"
    rules["universe_policy"] = "Screen discovers research candidates only; it never writes security action or portfolio allocation."
    screen["candidates"] = rows
    screen["deep_research_queue"] = deep
    note = "Existing snapshot normalized to Screen V5 without network access; next live scanner refresh remains source of truth."
    notes = screen.setdefault("notes", [])
    if note not in notes:
        notes.append(note)
    if write:
        save("data/screen.json", screen)
    return screen


if __name__ == "__main__":
    out = generate(True)
    print("SCREEN V5 NORMALIZED", len(out.get("candidates") or []), "candidates")
