# Taiwan Security Alpha Engine V5

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
Python Security Engine (`scripts/build_alpha.py`)
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

The market screen is a research-discovery system, never a Buy Gate.

Three lanes prevent one market regime from consuming the entire queue:

- **GROWTH** — revenue YoY ≥ 25%.
- **INFLECTION** — revenue YoY ≥ 15% and accelerating versus cumulative growth.
- **MISPRICING_QUALITY** — revenue YoY ≥ 8%, positive reported EPS and official TTM P/E ≤ 20.

Market cap and liquidity remain hard gates.

### Extreme-growth handling

Revenue growth used for ranking is capped at **100%**. Growth above 100% creates a base-effect verification penalty and `HIGH` verification priority; growth above 200% receives an additional `EXTREME_GROWTH_VERIFY_FIRST` flag.

This preserves the raw number for research while preventing a near-zero comparison base from dominating the ranking.

## Deterministic Security Engine

`scripts/build_alpha.py` ignores stored legacy `factor_scores` as authority and derives the current decision from structured fields:

- current screen features
- forward / normalized scenario valuation
- margin of safety and relative return versus TSMC
- verified first-party evidence
- explicit catalyst and cash-flow evidence
- freshness
- risk/cyclicality fields

The canonical artifact carries:

- `decision_engine_version`
- `decision_fingerprint`
- deterministic `factor_scores`
- deterministic `confidence_factors`
- `valuation_metrics`
- `market_expectation`
- `freshness`
- `evidence_gate`
- `buy_gate`
- canonical `action`

`validate.py` rebuilds the artifact in memory and requires exact equality. This prevents hand-edited derived scores/actions from silently becoming authority.

## Market-implied expectation

For scenario-P/E models:

```text
market_implied_eps = reference_price / base_case_multiple
```

The gap between Base EPS and market-implied EPS is `ANALYTIC_ONLY`; it explains the mispricing thesis but cannot create BUY authority.

## Freshness V2

Market freshness uses trading weekdays rather than calendar days. Fundamental and revenue ages remain calendar-based.

The artifact separates:

```text
last_event_at
last_event_checked_at
```

so “no new event was found today” is not confused with “an event occurred today.”

## TSMC 3000

TSMC 3000 is an **event alert only**.

It never gates:

- BUY CANDIDATE
- rotation review
- position sizing
- portfolio allocation

A security must pass the complete Security Buy Gate and beat the benchmark hurdle regardless of whether TSMC has touched 3000.

## Calibration

Existing point-in-time historical snapshots and `performance.json` remain the learning record. Primary calibration continues to use BUY-entry transitions and realized excess price return versus TSMC at 1/4/13/26/52 weeks.

The engine should not add new scoring complexity until prospective history demonstrates predictive value.

## Safety invariants

- Screen never writes BUY.
- Missing required evidence fails closed.
- Incomplete/stale valuation cannot pass BUY.
- Browser JavaScript cannot create action authority.
- TSMC 3000 is not a gate.
- Portfolio allocation is not owned here.
- No automatic trading.

See `docs/SECURITY_ENGINE_V5.md` for implementation contracts.
