# Taiwan Security Alpha Engine V6

`linwuyen/stock` is the **security research and BUY-authority layer** for Taiwan equities.

It does not own personal portfolio allocation, leverage, cash/debt decisions or automatic trading. Those responsibilities belong to `linwuyen/Elephant`.

## First-principles objective

The engine answers:

```text
Does this security have a sufficiently evidence-backed, valuation-supported,
relative-return advantage to deserve BUY CANDIDATE status?
```

It deliberately does **not** answer how much of a personal portfolio to allocate.

## Canonical flow

```text
Official TWSE / TPEx data
        ↓
Screen V5 — discovery only
  ├─ GROWTH
  ├─ INFLECTION
  └─ MISPRICING_QUALITY
        ↓
Deep Research / first-party evidence
        ↓
Frozen V5 economic core
        ↓
V6 canonical schema (`scripts/build_alpha_v6.py`)
        ↓
Deterministic Alpha + Confidence
Valuation / Expectation Gap / Freshness
        ↓
Security Buy Gate
        ↓
`data/alpha.json` canonical decisions
        ↓
Alerts / UI / historical calibration
        ↓
Elephant Capital Allocation OS
```

## Authority boundary

### `stock` owns

- market discovery and research queue
- security-specific evidence and valuation
- deterministic Alpha / Confidence derivation
- security BUY / VERIFY / WATCH / AVOID authority
- security calibration history

### Elephant owns

- macro regime
- cash / debt / leverage alternatives
- personal portfolio state
- position sizing and concentration
- survival / forced-sale constraints
- capital allocation and portfolio regret

`stock` publishes no portfolio weights. `engine.js` is presentation-only and `riskAdjustedAllocations()` returns `MOVED_TO_ELEPHANT`.

## Screen V5

The market screen remains schema V5 and is a research-discovery system, never a Buy Gate.

Three lanes prevent one market regime from consuming the entire queue:

- **GROWTH** — revenue YoY ≥ 25%.
- **INFLECTION** — revenue YoY ≥ 15% and accelerating versus cumulative growth.
- **MISPRICING_QUALITY** — revenue YoY ≥ 8%, positive reported EPS and official TTM P/E ≤ 20.

Market cap and liquidity remain hard gates.

Revenue growth used for ranking is capped at **100%**. Growth above 100% creates a base-effect verification penalty and `HIGH` verification priority; growth above 200% receives an additional `EXTREME_GROWTH_VERIFY_FIRST` flag. Raw growth is preserved for research while extreme base effects cannot dominate ranking.

## Security Engine V6

V6 is a **versioned semantic schema migration**, not a silent model change. The economic calculations remain frozen in the V5 core for this migration and the V6 builder provides the canonical names and artifact contract.

The legacy field called `margin_of_safety_pct` actually meant:

```text
base_upside_pct = base_fair_value / reference_price - 1
```

V6 therefore renames:

```text
margin_of_safety_pct       → base_upside_pct
min_margin_of_safety_pct   → min_base_upside_pct
buy_gate.margin_of_safety  → buy_gate.base_upside
```

The formula and Buy Gate threshold are unchanged. Classical margin of safety, `(fair_value - price) / fair_value`, is **not** introduced by this migration.

The V6 builder is idempotent: repeated build/alert/validation calls in one workflow may consume either a checked-in V5 or V6 artifact, while the frozen V5 core receives only an in-memory compatibility view. The repository is never temporarily downgraded on disk.

The canonical artifact carries:

- `schema_version = 6`
- `decision_engine_version = security-v6.0.0`
- `decision_fingerprint`
- deterministic `factor_scores`
- deterministic `confidence_factors`
- `valuation_metrics.base_upside_pct`
- `market_expectation`
- `freshness`
- `evidence_gate`
- `buy_gate`
- canonical `action`

`validate.py` rebuilds the artifact in memory and requires exact equality, and rejects legacy MOS-named schema keys. This prevents hand-edited derived scores/actions from silently becoming authority.

## Expected Return semantics

Expected Return is scenario-probability-weighted fair-value upside. Scenario probabilities are **model priors**, not empirically calibrated probabilities unless prospective outcome data later passes the declared calibration requirements.

Expected Return cannot create BUY authority by itself. It must pass the complete Security Buy Gate together with evidence, freshness, Base upside, and benchmark-relative alpha spread.

## Market-implied expectation

For scenario-P/E models:

```text
market_implied_eps = reference_price / base_case_multiple
```

The gap between Base EPS and market-implied EPS is `ANALYTIC_ONLY`; it explains the mispricing thesis but cannot create BUY authority.

## Freshness

Market freshness uses trading weekdays rather than calendar days. Fundamental and revenue ages remain calendar-based.

The artifact separates:

```text
last_event_at
last_event_checked_at
```

so “no new event was found today” is not confused with “an event occurred today.”

## TSMC 3000

TSMC 3000 is an **event alert only**. It never gates BUY CANDIDATE, rotation review, position sizing, or portfolio allocation.

## Prospective calibration

Existing point-in-time historical snapshots and `performance.json` are the realized-alpha learning record. Primary calibration uses actual BUY-entry transitions and realized excess **price** return versus TSMC at 1/4/13/26/52 weeks.

The minimum sample requirement remains fail-closed. `INSUFFICIENT_HISTORY` is a valid production state and must never be relabeled as predictive validation just to make a dashboard green.

## Safety invariants

- Screen never writes BUY.
- Missing required evidence fails closed.
- Incomplete/stale valuation cannot pass BUY.
- Alpha, Confidence and scenario probabilities are not interchangeable quantities.
- Browser JavaScript cannot create action authority.
- TSMC 3000 is not a gate.
- Portfolio allocation is not owned here.
- No automatic trading.

See `docs/SECURITY_ENGINE_V6.md` for the V6 implementation contract. `docs/SECURITY_ENGINE_V5.md` remains historical documentation for the frozen economic core.
