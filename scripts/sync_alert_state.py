#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write(path, obj):
    (ROOT / path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(alpha, alerts):
    out = json.loads(json.dumps(alerts))
    previous_active = {x["ticker"] if isinstance(x, dict) else x for x in out.get("active_buy_candidates", [])}
    current_stocks = {x["ticker"]: x for x in alpha.get("stocks", []) if x.get("action") == "BUY CANDIDATE"}
    current_active = set(current_stocks)
    entered = sorted(current_active - previous_active)
    exited = sorted(previous_active - current_active)

    max_sequence = {}
    for note in out.get("notifications", []):
        ticker = note.get("ticker")
        seq = int(note.get("buy_entry_sequence") or 0)
        max_sequence[ticker] = max(max_sequence.get(ticker, 0), seq)

    now = datetime.now(TZ).isoformat(timespec="seconds")
    for ticker in entered:
        stock = current_stocks[ticker]
        model = stock.get("valuation_model", {})
        seq = max_sequence.get(ticker, 0) + 1
        max_sequence[ticker] = seq
        out.setdefault("notifications", []).append({
            "ticker": ticker,
            "name": stock.get("name"),
            "buy_entry_sequence": seq,
            "detected_at": now,
            "alpha_as_of": alpha.get("meta", {}).get("as_of"),
            "status": "PENDING",
            "payload": {
                "alpha_score": stock.get("score"),
                "confidence_score": stock.get("confidence_score"),
                "expected_return_pct": model.get("expected_return_pct"),
                "alpha_spread_pct": stock.get("alpha_spread_pct"),
                "margin_of_safety_pct": model.get("margin_of_safety_pct"),
                "invalidation_condition": stock.get("invalidation_condition"),
            },
        })

    out["active_buy_candidates"] = [
        {"ticker": ticker, "name": current_stocks[ticker].get("name"), "entered_sequence": max_sequence.get(ticker, 1)}
        for ticker in sorted(current_active)
    ]
    out["last_evaluated_at"] = now
    out["last_evaluated_alpha_as_of"] = alpha.get("meta", {}).get("as_of")
    out["last_transition"] = {"entered": entered, "exited": exited}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    alpha = load("data/alpha.json")
    alerts = load("data/alerts.json")
    built = build(alpha, alerts)
    if args.check:
        assert alerts == built, "alerts.json is stale; run sync_alert_state.py"
        print("alerts PASS")
    else:
        write("data/alerts.json", built)
        entered = built.get("last_transition", {}).get("entered", [])
        exited = built.get("last_transition", {}).get("exited", [])
        print(f"alerts synced; entered={entered}; exited={exited}")


if __name__ == "__main__":
    main()
