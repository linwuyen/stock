#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import build_alpha as v5

ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "security-v6.0.0"
DEFAULT_WEIGHTS = v5.DEFAULT_WEIGHTS
CONFIDENCE_WEIGHTS = v5.CONFIDENCE_WEIGHTS

KEY_RENAMES = {
    "margin_of_safety_pct": "base_upside_pct",
    "min_margin_of_safety_pct": "min_base_upside_pct",
    "margin_of_safety": "base_upside",
}
VALUE_RENAMES = {
    "margin_of_safety": "base_upside",
}


def save(path: str, obj: dict) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate(obj):
    """Versioned semantic rename only; no valuation formula or gate threshold changes."""
    if isinstance(obj, dict):
        return {KEY_RENAMES.get(k, k): migrate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [migrate(v) for v in obj]
    if isinstance(obj, str):
        return VALUE_RENAMES.get(obj, obj)
    return obj


def fingerprint(data: dict) -> str:
    payload = copy.deepcopy(data)
    payload.get("meta", {}).pop("decision_fingerprint", None)
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def assert_no_legacy_names(obj, path="root") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in KEY_RENAMES:
                raise AssertionError(f"legacy schema key at {path}.{k}")
            assert_no_legacy_names(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_no_legacy_names(v, f"{path}[{i}]")


def generate(write: bool = False) -> dict:
    # V5 remains the frozen economic engine for this migration. V6 changes naming,
    # not economics: base upside is still base_fair_value/reference_price - 1.
    out = migrate(v5.generate(write=False))
    meta = out.setdefault("meta", {})
    meta["schema_version"] = 6
    meta["decision_engine_version"] = ENGINE_VERSION
    meta["schema_migration"] = {
        "from": 5,
        "to": 6,
        "semantic_change": False,
        "renamed": {
            "margin_of_safety_pct": "base_upside_pct",
            "min_margin_of_safety_pct": "min_base_upside_pct",
            "buy_gate.margin_of_safety": "buy_gate.base_upside",
        },
        "definition": "base_upside_pct = base_fair_value / reference_price - 1",
        "classical_margin_of_safety": "not implemented by this migration",
    }
    for asset in [out.get("benchmark_asset"), *(out.get("stocks") or [])]:
        if isinstance(asset, dict) and asset.get("score_provenance"):
            asset["score_provenance"] = ENGINE_VERSION
    assert_no_legacy_names(out)
    meta["decision_fingerprint"] = fingerprint(out)
    if write:
        save("data/alpha.json", out)
    return out


def main() -> None:
    out = generate(True)
    print(json.dumps({
        "engine": out["meta"]["decision_engine_version"],
        "schema_version": out["meta"]["schema_version"],
        "fingerprint": out["meta"]["decision_fingerprint"],
        "actions": {x["ticker"]: x["action"] for x in out.get("stocks", [])},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
