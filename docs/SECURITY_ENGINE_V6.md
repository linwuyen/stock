# Security Engine V6 contract

## Scope

Security Engine V6 is a schema/semantics migration around the frozen V5 economic core. It does not change factor weights, valuation arithmetic, Buy Gate thresholds, security actions, or portfolio authority.

## Canonical artifact

`data/alpha.json` must publish:

```text
meta.schema_version = 6
meta.decision_engine_version = security-v6.0.0
meta.authority = PYTHON_CANONICAL_SECURITY_ENGINE
```

`decision_fingerprint` is recomputed after migration and excludes only the fingerprint field itself.

## Base-upside migration

The V5 field name implied classical margin of safety but the stored formula was price upside to the base fair value. V6 names the quantity by what it actually measures:

```text
base_upside_pct = base_fair_value / reference_price - 1
```

Renames:

```text
margin_of_safety_pct       -> base_upside_pct
min_margin_of_safety_pct   -> min_base_upside_pct
buy_gate.margin_of_safety  -> buy_gate.base_upside
```

No formula or threshold changes are permitted in this migration. Classical margin of safety is a different quantity and would require a later versioned model change plus Buy Gate recalibration.

## Frozen economics boundary

`scripts/build_alpha.py` remains the V5 economic core. `scripts/build_alpha_v6.py` is the canonical publisher.

The V6 wrapper must be idempotent. If the checked-in artifact is already V6, the wrapper reverse-migrates it **in memory** for the V5 core, monkey-patches only the V5 Alpha read during that call, restores the original loader, and then republishes V6. It must not downgrade the repository on disk.

This allows these sequences to be deterministic:

```text
build_v6 -> build_v6
build_v6 -> alert sync -> validate
market scan -> build_v6 -> alert sync -> validate
```

## Writer ownership

All production writers that rebuild canonical Alpha state must call `build_alpha_v6.py` or import `build_alpha_v6`:

- Pages validation/deploy
- full-market scanner
- alert-state synchronizer

A V5 writer running after a V6 writer is a contract violation because it can reintroduce legacy schema names.

## Validation

`scripts/validate.py` must:

- require Alpha schema version 6;
- require `security-v6.0.0` provenance;
- rebuild canonical Alpha in memory and require exact equality;
- reject legacy MOS-named keys anywhere in the Alpha artifact;
- require `base_upside_pct` in benchmark/security valuation metrics;
- require `base_upside` in Buy Gate checks;
- preserve all existing security authority, freshness, evidence, ranking and alert invariants.

## Expected Return and probability semantics

Expected Return is the probability-weighted fair-value upside from the declared Bear/Base/Bull scenario model. Scenario probabilities are model priors. They are not empirical probabilities until prospective outcome observations are sufficient for a predeclared calibration test.

Therefore:

- Expected Return is not a probability of gain;
- Confidence is not a probability of gain;
- Alpha Score is not a probability of gain;
- none of these can bypass the complete Security Buy Gate.

## Authority boundary

V6 changes no ownership:

```text
stock     -> security research + BUY/VERIFY/WATCH/AVOID authority
Elephant  -> portfolio sizing, debt, leverage, liquidity, concentration and capital allocation
execution -> none; review only
```

No automatic trading is introduced.
