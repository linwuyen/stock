#!/usr/bin/env python3
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = [1, 4, 13, 26, 52]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def price(snapshot, ticker):
    if ticker == "2330":
        b = snapshot.get("benchmark_asset") or snapshot.get("benchmark") or snapshot.get("tsmc") or {}
        return b.get("reference_price")
    stock = next((x for x in snapshot.get("stocks", []) if x.get("ticker") == ticker), None)
    return None if not stock else stock.get("reference_price")


def stock_map(snapshot):
    return {x.get("ticker"): x for x in snapshot.get("stocks", []) if x.get("ticker")}


def nearest(snaps, target, max_days=5):
    pairs = [(abs((date.fromisoformat(s["meta"]["as_of"]) - target).days), s) for s in snaps]
    if not pairs:
        return None
    distance, snapshot = min(pairs, key=lambda x: x[0])
    return snapshot if distance <= max_days else None


def is_buy(stock):
    return stock is not None and stock.get("action") == "BUY CANDIDATE"


def is_a_grade(stock):
    return stock is not None and stock.get("grade") == "A"


def transition_entries(snaps, predicate):
    entries = []
    previous = {}
    for snapshot in snaps:
        current = stock_map(snapshot)
        for ticker, stock in current.items():
            if predicate(stock) and not predicate(previous.get(ticker)):
                entries.append((snapshot, stock))
        previous = current
    return entries


def load_actions():
    path = ROOT / "data" / "corporate-actions.json"
    if not path.exists():
        return {"ledger": {"historical_backfill_complete": False}, "actions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def action_window(actions, ticker, start, end):
    return [
        x for x in actions
        if x.get("ticker") == ticker
        and x.get("date")
        and start < date.fromisoformat(x["date"]) <= end
    ]


def holding_period_return(p0, p1, actions):
    if not p0 or not p1:
        return None, "MISSING_PRICE"
    # Stock dividends/rights alter share count. Until an official adjustment-factor
    # contract is present, samples containing them are excluded instead of guessed.
    if any((x.get("stock_dividend_ratio_raw") or 0) > 0 for x in actions):
        return None, "UNSUPPORTED_STOCK_ACTION"
    cash = sum(float(x.get("cash_dividend_per_share") or 0) for x in actions)
    return (p1 + cash) / p0 - 1, "COMPLETE"


def samples_for_entries(snaps, entries, corporate_actions):
    total = {w: [] for w in HORIZONS}
    price_only = {w: [] for w in HORIZONS}
    unresolved = {w: [] for w in HORIZONS}
    actions = corporate_actions.get("actions", [])
    ledger_start = corporate_actions.get("ledger", {}).get("coverage_start")
    ledger_start_date = date.fromisoformat(ledger_start) if ledger_start else None

    for entry_snapshot, stock in entries:
        d0 = date.fromisoformat(entry_snapshot["meta"]["as_of"])
        p0 = stock.get("reference_price")
        b0 = price(entry_snapshot, "2330")
        if not p0 or not b0:
            continue
        for weeks in HORIZONS:
            target = d0 + timedelta(weeks=weeks)
            end_snapshot = nearest(snaps, target)
            if not end_snapshot:
                continue
            d1 = date.fromisoformat(end_snapshot["meta"]["as_of"])
            p1 = price(end_snapshot, stock["ticker"])
            b1 = price(end_snapshot, "2330")
            if not p1 or not b1:
                continue

            stock_price_return = p1 / p0 - 1
            benchmark_price_return = b1 / b0 - 1
            price_only[weeks].append((stock_price_return - benchmark_price_return) * 100)

            # The prospective action ledger cannot certify intervals that begin
            # before its own coverage. Those observations remain unresolved.
            if ledger_start_date is None or d0 < ledger_start_date:
                unresolved[weeks].append({
                    "ticker": stock["ticker"],
                    "entry_date": d0.isoformat(),
                    "end_date": d1.isoformat(),
                    "reason": "CORPORATE_ACTION_LEDGER_NOT_POINT_IN_TIME_COMPLETE",
                })
                continue

            stock_actions = action_window(actions, stock["ticker"], d0, d1)
            benchmark_actions = action_window(actions, "2330", d0, d1)
            stock_total, stock_status = holding_period_return(p0, p1, stock_actions)
            benchmark_total, benchmark_status = holding_period_return(b0, b1, benchmark_actions)
            if stock_status != "COMPLETE" or benchmark_status != "COMPLETE":
                unresolved[weeks].append({
                    "ticker": stock["ticker"],
                    "entry_date": d0.isoformat(),
                    "end_date": d1.isoformat(),
                    "reason": f"{stock_status}/{benchmark_status}",
                })
                continue
            total[weeks].append((stock_total - benchmark_total) * 100)
    return total, price_only, unresolved


def horizon_rows(total, price_only, unresolved):
    rows = []
    for weeks in HORIZONS:
        total_values = total[weeks]
        price_values = price_only[weeks]
        rows.append({
            "weeks": weeks,
            "sample_size": len(total_values),
            "mean_excess_total_return_pct": (
                round(sum(total_values) / len(total_values), 2) if total_values else None
            ),
            "price_return_diagnostic_sample_size": len(price_values),
            "mean_excess_price_return_pct": (
                round(sum(price_values) / len(price_values), 2) if price_values else None
            ),
            "unresolved_total_return_samples": len(unresolved[weeks]),
        })
    return rows


def build():
    index = load("data/history/index.json")
    snapshots = [load(entry["path"]) for entry in index["snapshots"]]
    snapshots.sort(key=lambda s: s["meta"]["as_of"])
    out = load("data/performance.json")
    actions = load_actions()

    buy_entries = transition_entries(snapshots, is_buy)
    a_entries = transition_entries(snapshots, is_a_grade)
    buy_total, buy_price, buy_unresolved = samples_for_entries(snapshots, buy_entries, actions)
    a_total, a_price, a_unresolved = samples_for_entries(snapshots, a_entries, actions)

    out["meta"]["schema_version"] = 3
    out["meta"]["return_type"] = "TOTAL_RETURN_CASH_DISTRIBUTIONS_NO_REINVESTMENT"
    out["meta"]["method"] = (
        "Primary calibration measures forward cash-distribution-inclusive holding-period "
        "return minus TSMC on actual BUY_CANDIDATE entry transitions at 1/4/13/26/52 weeks. "
        "TWSE ex-right/ex-dividend events are captured prospectively. Periods beginning "
        "before action-ledger coverage, or containing unsupported stock actions, remain "
        "unresolved rather than being approximated. Price-return excess is retained only "
        "as a diagnostic."
    )
    out["meta"]["corporate_action_source"] = "TWSE_TWT48U_ALL"
    out["meta"]["corporate_action_coverage_start"] = actions.get("ledger", {}).get("coverage_start")
    out["horizons"] = horizon_rows(buy_total, buy_price, buy_unresolved)
    out.setdefault("diagnostic_cohorts", {})["A_GRADE"] = horizon_rows(
        a_total, a_price, a_unresolved
    )
    total = max((x["sample_size"] for x in out["horizons"]), default=0)
    out["meta"]["status"] = (
        "CALIBRATED" if total >= out["minimum_samples_for_calibration"]
        else "INSUFFICIENT_HISTORY"
    )
    out["meta"]["as_of"] = index["latest"]
    out["meta"]["primary_entry_count"] = len(buy_entries)
    out["meta"]["a_grade_entry_count"] = len(a_entries)
    out["calibration_actions"] = out.get("calibration_actions", [])
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    path = ROOT / "data/performance.json"
    if args.check:
        current = json.loads(path.read_text(encoding="utf-8"))
        assert current == built, "performance.json is stale; run rebuild_performance.py"
        print("performance PASS")
    else:
        path.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
