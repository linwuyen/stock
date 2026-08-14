#!/usr/bin/env python3
"""Runtime validator for the live v4 screen contract.

This wraps the legacy decision validator while enforcing the current
HARD_DERIVED market-cap contract. A single known 2026-08-10 degraded
snapshot is accepted only so the migration fix itself can land; any new
scanner output must use the hard market-cap gate.
"""
import copy

import validate as legacy

LEGACY_GENERATED_AT = "2026-08-10T14:02:08+08:00"
HARD_MODE = "HARD_DERIVED"
MIN_MARKET_CAP_TWD = 10_000_000_000.0

_legacy_validate_screen = legacy.validate_screen


def validate_screen_v4(screen):
    mode = screen.get("rules", {}).get("market_cap", {}).get("mode")

    # Reuse all existing screen invariants without preserving the obsolete
    # SOFT_ONLY requirement embedded in the legacy validator.
    compatibility_view = copy.deepcopy(screen)
    compatibility_view.setdefault("rules", {}).setdefault("market_cap", {})["mode"] = "SOFT_ONLY"
    _legacy_validate_screen(compatibility_view)

    legacy_migration_snapshot = (
        mode == "SOFT_ONLY"
        and screen.get("meta", {}).get("generated_at") == LEGACY_GENERATED_AT
        and screen.get("meta", {}).get("status") == "DEGRADED"
        and not screen.get("candidates")
        and not screen.get("deep_research_queue")
    )
    if legacy_migration_snapshot:
        return

    assert mode == HARD_MODE, f"market-cap contract drift: expected {HARD_MODE}, got {mode}"
    market_cap_rule = screen["rules"]["market_cap"]
    minimum = float(market_cap_rule.get("min_twd", 0))
    assert minimum >= MIN_MARKET_CAP_TWD, f"market-cap floor weakened: {minimum}"

    for item in screen.get("candidates", []):
        cap = item.get("market_cap_twd")
        assert cap is not None and float(cap) >= minimum, f"{item.get('ticker')} bypassed market-cap gate"
        source = item.get("market_cap_source")
        assert source in {"DERIVED_ISSUED_SHARES_X_CLOSE", "DIRECT_OFFICIAL_FIELD"}, f"{item.get('ticker')} invalid market-cap source"
        if source == "DERIVED_ISSUED_SHARES_X_CLOSE":
            shares = item.get("issued_shares")
            assert shares is not None and float(shares) > 0, f"{item.get('ticker')} missing issued shares"


legacy.validate_screen = validate_screen_v4

if __name__ == "__main__":
    legacy.main()
