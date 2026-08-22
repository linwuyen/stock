#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data/scenario-calibration.json"
ALPHA_PATH = ROOT / "data/alpha.json"
CLASSES = ("bear", "base", "bull")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finite(v):
    try:
        x = float(v)
        return x == x and x not in (float("inf"), float("-inf"))
    except (TypeError, ValueError):
        return False


def normalize_probabilities(scenarios):
    values = [float((scenarios.get(k) or {}).get("probability")) for k in CLASSES]
    total = sum(values)
    if abs(total - 100) <= .1:
        values = [x / 100 for x in values]
        total = sum(values)
    if abs(total - 1) > .001 or any(x < 0 or x > 1 for x in values):
        return None
    return {k: round(v, 8) for k, v in zip(CLASSES, values)}


def scenario_contract(asset):
    model = asset.get("valuation_model") or {}
    if model.get("status") != "COMPLETE":
        return None
    scenarios = model.get("scenarios") or {}
    if any(not finite((scenarios.get(k) or {}).get("fair_value")) or not finite((scenarios.get(k) or {}).get("probability")) for k in CLASSES):
        return None
    fair_values = {k: float(scenarios[k]["fair_value"]) for k in CLASSES}
    if not (fair_values["bear"] < fair_values["base"] < fair_values["bull"]):
        return None
    probabilities = normalize_probabilities(scenarios)
    if probabilities is None:
        return None
    return {
        "fair_values": fair_values,
        "probabilities": probabilities,
        "bin_boundaries": {
            "bear_base_midpoint": round((fair_values["bear"] + fair_values["base"]) / 2, 4),
            "base_bull_midpoint": round((fair_values["base"] + fair_values["bull"]) / 2, 4),
        },
    }


def forecast_signature(ticker, contract):
    payload = {
        "ticker": str(ticker),
        "fair_values": contract["fair_values"],
        "probabilities": contract["probabilities"],
        "horizon_weeks": 52,
        "binning": "midpoint_fair_value_bins",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def price_observations(alpha):
    assets = [alpha.get("benchmark_asset") or {}, *(alpha.get("stocks") or [])]
    out = {}
    for asset in assets:
        ticker = asset.get("ticker")
        price = asset.get("reference_price")
        observed = asset.get("reference_price_date")
        if ticker and finite(price) and observed:
            out[str(ticker)] = {
                "price": float(price),
                "observed_at": str(observed),
            }
    return out


def classify(realized_price, boundaries):
    p = float(realized_price)
    if p < float(boundaries["bear_base_midpoint"]):
        return "bear"
    if p < float(boundaries["base_bull_midpoint"]):
        return "base"
    return "bull"


def brier(probabilities, outcome):
    return sum((float(probabilities[k]) - (1.0 if k == outcome else 0.0)) ** 2 for k in CLASSES)


def forecast_date(alpha):
    meta = alpha.get("meta") or {}
    return meta.get("research_inputs_as_of") or meta.get("as_of") or meta.get("decision_as_of")


def eligible_assets(alpha):
    return [alpha.get("benchmark_asset") or {}, *(alpha.get("stocks") or [])]


def append_new_forecasts(ledger, alpha):
    origin = forecast_date(alpha)
    if not origin:
        return
    d0 = date.fromisoformat(str(origin))
    spacing = int(ledger["minimum_spacing_days"])
    existing = ledger.setdefault("forecasts", [])

    for asset in eligible_assets(alpha):
        ticker = str(asset.get("ticker") or "")
        contract = scenario_contract(asset)
        if not ticker or contract is None:
            continue
        signature = forecast_signature(ticker, contract)
        prior = [x for x in existing if str(x.get("ticker")) == ticker]
        if any(x.get("scenario_signature") == signature for x in prior):
            continue
        if prior:
            last = max(date.fromisoformat(x["forecast_at"]) for x in prior)
            if (d0 - last).days < spacing:
                continue
        due = d0 + timedelta(weeks=int(ledger["horizon_weeks"]))
        existing.append({
            "forecast_id": f"{origin}-{ticker}-{signature[:8]}",
            "ticker": ticker,
            "name": asset.get("name"),
            "forecast_at": str(origin),
            "resolution_due": due.isoformat(),
            "scenario_signature": signature,
            "source_decision_fingerprint": (alpha.get("meta") or {}).get("decision_fingerprint"),
            "reference_price_at_forecast": asset.get("reference_price"),
            "reference_price_date": asset.get("reference_price_date"),
            **contract,
            "status": "PENDING",
            "resolution": None,
        })


def resolve_due_forecasts(ledger, alpha):
    observations = price_observations(alpha)
    tolerance = int(ledger["resolution_tolerance_days"])
    for row in ledger.get("forecasts", []):
        if row.get("status") != "PENDING":
            continue
        obs = observations.get(str(row.get("ticker")))
        if not obs:
            continue
        due = date.fromisoformat(row["resolution_due"])
        observed = date.fromisoformat(obs["observed_at"])
        delta = (observed - due).days
        if delta < 0 or delta > tolerance:
            continue
        outcome = classify(obs["price"], row["bin_boundaries"])
        score = brier(row["probabilities"], outcome)
        row["status"] = "RESOLVED"
        row["resolution"] = {
            "price": obs["price"],
            "observed_at": obs["observed_at"],
            "days_from_due": delta,
            "outcome_class": outcome,
            "multiclass_brier": round(score, 8),
        }


def summarize(ledger):
    resolved = [x for x in ledger.get("forecasts", []) if x.get("status") == "RESOLVED"]
    pending = [x for x in ledger.get("forecasts", []) if x.get("status") == "PENDING"]
    ledger["resolved_samples"] = len(resolved)
    ledger["pending_samples"] = len(pending)
    minimum = int(ledger["minimum_resolved_samples"])
    ledger["status"] = "CALIBRATED" if len(resolved) >= minimum else "INSUFFICIENT_HISTORY"
    if not resolved:
        ledger["multiclass_brier_score"] = None
        ledger["mean_forecast_probabilities"] = None
        ledger["empirical_outcome_frequencies"] = None
        return ledger

    ledger["multiclass_brier_score"] = round(sum(x["resolution"]["multiclass_brier"] for x in resolved) / len(resolved), 8)
    ledger["mean_forecast_probabilities"] = {
        k: round(sum(float(x["probabilities"][k]) for x in resolved) / len(resolved), 8) for k in CLASSES
    }
    ledger["empirical_outcome_frequencies"] = {
        k: round(sum(1 for x in resolved if x["resolution"]["outcome_class"] == k) / len(resolved), 8) for k in CLASSES
    }
    return ledger


def build():
    ledger = load(LEDGER_PATH)
    alpha = load(ALPHA_PATH)
    out = copy.deepcopy(ledger)
    append_new_forecasts(out, alpha)
    resolve_due_forecasts(out, alpha)
    out["forecasts"].sort(key=lambda x: (x["forecast_at"], x["ticker"], x["forecast_id"]))
    return summarize(out)


def validate(obj):
    assert obj.get("schema_version") == 1
    assert obj.get("horizon_weeks") == 52
    assert obj.get("minimum_resolved_samples", 0) >= 30
    assert obj.get("minimum_spacing_days", 0) >= 28
    assert obj.get("resolution_tolerance_days", 99) <= 14
    assert obj.get("status") in {"INSUFFICIENT_HISTORY", "CALIBRATED"}
    forecasts = obj.get("forecasts") or []
    ids = [x.get("forecast_id") for x in forecasts]
    assert len(ids) == len(set(ids))
    for row in forecasts:
        assert row.get("status") in {"PENDING", "RESOLVED"}
        probs = row.get("probabilities") or {}
        assert set(probs) == set(CLASSES)
        assert abs(sum(float(probs[k]) for k in CLASSES) - 1) <= .001
        fvs = row.get("fair_values") or {}
        assert float(fvs["bear"]) < float(fvs["base"]) < float(fvs["bull"])
        if row["status"] == "RESOLVED":
            assert row.get("resolution", {}).get("outcome_class") in CLASSES
            assert 0 <= float(row["resolution"]["multiclass_brier"]) <= 2
    if obj["status"] == "CALIBRATED":
        assert obj["resolved_samples"] >= obj["minimum_resolved_samples"]
        assert obj["multiclass_brier_score"] is not None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    built = build()
    validate(built)
    if args.check:
        current = load(LEDGER_PATH)
        assert current == built, "scenario-calibration.json is stale; run sync_scenario_calibration.py"
        print("scenario calibration PASS")
        return
    write(LEDGER_PATH, built)
    print(json.dumps({
        "status": built["status"],
        "resolved_samples": built["resolved_samples"],
        "pending_samples": built["pending_samples"],
        "multiclass_brier_score": built["multiclass_brier_score"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
