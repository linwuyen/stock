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
REVERSE_KEY_RENAMES = {v: k for k, v in KEY_RENAMES.items()}
REVERSE_VALUE_RENAMES = {v: k for k, v in VALUE_RENAMES.items()}


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


def reverse_migrate(obj):
    """Present a V6 artifact to the frozen V5 core using its original vocabulary."""
    if isinstance(obj, dict):
        return {REVERSE_KEY_RENAMES.get(k, k): reverse_migrate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [reverse_migrate(v) for v in obj]
    if isinstance(obj, str):
        return REVERSE_VALUE_RENAMES.get(obj, obj)
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


def v5_compatible_source() -> dict:
    """Return the checked-in Alpha artifact in the vocabulary expected by V5.

    CI and writer jobs may call the V6 builder repeatedly. After the first call,
    data/alpha.json is already V6. The frozen V5 economic core must therefore see
    a reverse-migrated in-memory view rather than reading V6 field names directly.
    No on-disk downgrade is performed.
    """
    source = json.loads((ROOT / "data/alpha.json").read_text(encoding="utf-8"))
    meta = source.get("meta") or {}
    is_v6 = int(meta.get("schema_version") or 0) >= 6 or "min_base_upside_pct" in (source.get("decision_policy") or {})
    if not is_v6:
        return source

    source = reverse_migrate(source)
    meta = source.setdefault("meta", {})
    meta["schema_version"] = 5
    meta["decision_engine_version"] = v5.ENGINE_VERSION
    meta.pop("schema_migration", None)
    for asset in [source.get("benchmark_asset"), *(source.get("stocks") or [])]:
        if isinstance(asset, dict) and asset.get("score_provenance"):
            asset["score_provenance"] = v5.ENGINE_VERSION
    return source


def run_v5_core() -> dict:
    """Run V5 economics with a compatibility read shim, then restore its loader."""
    source = v5_compatible_source()
    original_load = v5.load

    def compatible_load(path, default=None):
        if str(path) == "data/alpha.json":
            return copy.deepcopy(source)
        return original_load(path, default)

    v5.load = compatible_load
    try:
        return v5.generate(write=False)
    finally:
        v5.load = original_load


def generate(write: bool = False) -> dict:
    # V5 remains the frozen economic engine for this migration. V6 changes naming,
    # not economics: base upside is still base_fair_value/reference_price - 1.
    out = migrate(run_v5_core())
    meta = out.setdefault("meta", {})
    meta["schema_version"] = 6
    meta["decision_engine_version"] = ENGINE_VERSION
    meta["schema_migration"] = {
        "from": 5,
        "to": 6,
        "semantic_change": False,
        "renamed": [
            "legacy MOS-named valuation field -> base_upside_pct",
            "legacy MOS-named policy threshold -> min_base_upside_pct",
            "legacy MOS-named Buy Gate check -> buy_gate.base_upside",
        ],
        "definition": "base_upside_pct = base_fair_value / reference_price - 1",
        "classical_margin_of_safety": "not implemented by this migration",
        "compatibility": "V6 builder may consume either checked-in V5 or V6 Alpha state; the V5 economic core receives an in-memory compatibility view only.",
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
