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


def excess_samples(snaps, entries):
    samples = {w: [] for w in HORIZONS}
    for entry_snapshot, stock in entries:
        d0 = date.fromisoformat(entry_snapshot["meta"]["as_of"])
        p0 = stock.get("reference_price")
        b0 = price(entry_snapshot, "2330")
        if not p0 or not b0:
            continue
        for weeks in HORIZONS:
            end = nearest(snaps, d0 + timedelta(weeks=weeks))
            if not end:
                continue
            p1 = price(end, stock["ticker"])
            b1 = price(end, "2330")
            if p1 and b1:
                stock_return = p1 / p0 - 1
                benchmark_return = b1 / b0 - 1
                samples[weeks].append((stock_return - benchmark_return) * 100)
    return samples


def horizon_rows(samples):
    rows = []
    for weeks in HORIZONS:
        values = samples[weeks]
        rows.append({
            "weeks": weeks,
            "sample_size": len(values),
            "mean_excess_return_pct": round(sum(values) / len(values), 2) if values else None,
        })
    return rows


def build():
    index = load("data/history/index.json")
    snapshots = [load(entry["path"]) for entry in index["snapshots"]]
    snapshots.sort(key=lambda s: s["meta"]["as_of"])
    out = load("data/performance.json")

    buy_entries = transition_entries(snapshots, is_buy)
    a_entries = transition_entries(snapshots, is_a_grade)
    buy_samples = excess_samples(snapshots, buy_entries)
    a_samples = excess_samples(snapshots, a_entries)

    out["horizons"] = horizon_rows(buy_samples)
    out.setdefault("diagnostic_cohorts", {})["A_GRADE"] = horizon_rows(a_samples)
    total = max((x["sample_size"] for x in out["horizons"]), default=0)
    out["meta"]["status"] = "CALIBRATED" if total >= out["minimum_samples_for_calibration"] else "INSUFFICIENT_HISTORY"
    out["meta"]["as_of"] = index["latest"]
    out["meta"]["primary_entry_count"] = len(buy_entries)
    out["meta"]["a_grade_entry_count"] = len(a_entries)
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
