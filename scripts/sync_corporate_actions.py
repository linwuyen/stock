#!/usr/bin/env python3
import argparse
import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "corporate-actions.json"
URL = "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"


def load_existing():
    if not OUT.exists():
        return {
            "schema_version": 1,
            "source": {
                "authority": "TWSE OpenAPI",
                "url": URL,
                "first_party": True,
            },
            "actions": [],
        }
    return json.loads(OUT.read_text(encoding="utf-8"))


def roc_date_to_iso(raw):
    s = str(raw or "").strip()
    if not s:
        return None
    if len(s) == 7 and s.isdigit():
        year = int(s[:3]) + 1911
        month = int(s[3:5])
        day = int(s[5:7])
        return f"{year:04d}-{month:02d}-{day:02d}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    raise ValueError(f"unsupported TWSE action date: {raw!r}")


def number(raw):
    s = str(raw or "").replace(",", "").strip()
    if not s:
        return None
    x = float(s)
    if not math.isfinite(x) or x < 0:
        raise ValueError(f"invalid non-negative action value: {raw!r}")
    return x


def fetch_rows():
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "stock-security-engine/decision-science-v1"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("TWSE corporate-action payload is empty/non-list")
    return payload


def normalize(row):
    ticker = str(row.get("Code") or "").strip()
    action_date = roc_date_to_iso(row.get("Date"))
    if not ticker or not action_date:
        raise ValueError("TWSE corporate action missing ticker/date")
    cash = number(row.get("CashDividend"))
    stock_ratio = number(row.get("StockDividendRatio"))
    return {
        "date": action_date,
        "ticker": ticker,
        "name": str(row.get("Name") or "").strip(),
        "ex_right_or_dividend": str(row.get("Exdividend") or "").strip(),
        "cash_dividend_per_share": cash,
        "stock_dividend_ratio_raw": stock_ratio,
        "source": "TWSE_TWT48U_ALL",
    }


def build(rows=None):
    rows = fetch_rows() if rows is None else rows
    existing = load_existing()
    merged = {
        (str(x.get("date")), str(x.get("ticker"))): x
        for x in existing.get("actions", [])
        if x.get("date") and x.get("ticker")
    }
    normalized = [normalize(row) for row in rows]
    for action in normalized:
        merged[(action["date"], action["ticker"])] = action
    actions = sorted(merged.values(), key=lambda x: (x["date"], x["ticker"]))
    current_dates = [x["date"] for x in normalized]
    return {
        "schema_version": 1,
        "source": {
            "authority": "TWSE OpenAPI",
            "url": URL,
            "first_party": True,
            "contract": "prospective append-only ex-right/ex-dividend ledger",
        },
        "source_window": {
            "row_count": len(normalized),
            "min_date": min(current_dates),
            "max_date": max(current_dates),
        },
        "ledger": {
            "action_count": len(actions),
            "coverage_start": actions[0]["date"] if actions else None,
            "coverage_end": actions[-1]["date"] if actions else None,
            "historical_backfill_complete": False,
            "note": "Ledger is prospective from first capture. Missing pre-capture actions are never inferred.",
        },
        "actions": actions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    if args.check:
        current = load_existing()
        if current != built:
            raise SystemExit("corporate-actions.json is stale; run sync_corporate_actions.py")
        print("corporate actions PASS")
    else:
        OUT.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(OUT)


if __name__ == "__main__":
    main()
