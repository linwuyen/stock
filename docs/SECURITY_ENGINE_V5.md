# Security Engine V5 contracts

## 1. Single authority

`data/alpha.json` is the published security-decision artifact. Research assumptions may live in the same document for compatibility, but all derived fields are rebuilt by `scripts/build_alpha.py`.

Canonical fields include score, confidence, grade, rank, valuation metrics, relative Alpha, freshness, evidence gate, market-implied expectation, Buy Gate and action.

`engine.js` is a presentation adapter only. It may read canonical fields but may not independently calculate BUY authority.

## 2. Reproducibility

`data/alpha.json.meta.decision_fingerprint` is a SHA-256 fingerprint of the canonical artifact excluding the fingerprint field itself.

`validate.py` rebuilds the artifact and requires exact structural equality. A hand-edited score/action therefore fails CI.

## 3. Score derivation

Alpha Score is bounded to 0–100 and composed from:

- earnings acceleration — 30
- revenue quality — 20
- valuation / benchmark spread — 25
- structural catalyst evidence — 15
- balance-sheet / cash-flow evidence — 10

Every component is derived from structured input fields. When required structured evidence does not exist, the component receives no fabricated points.

Confidence Score measures evidence/model quality rather than attractiveness:

- first-party evidence completeness — 35
- forecast visibility — 25
- model completeness — 20
- thesis falsifiability — 10
- freshness — 10

## 4. Screen lanes

Screen V5 has three mutually assigned discovery lanes: `GROWTH`, `INFLECTION`, `MISPRICING_QUALITY`.

The screen has no BUY authority. Deep Research capacity is diversified across lanes and industries before ranking fill.

Growth ranking is capped at 100% YoY/cumulative YoY. Raw values remain available for audit. Outliers become verification tasks rather than additional ranking reward.

## 5. Freshness

Market price freshness is evaluated in trading weekdays. Fundamental, revenue and event-check freshness remain calendar-based.

The event contract separates the latest verified event observation from the most recent event check.

## 6. Buy Gate

A BUY CANDIDATE requires all of:

- deterministic Alpha Score threshold
- deterministic Confidence threshold
- complete valuation
- margin-of-safety hurdle
- expected-return spread versus TSMC
- security freshness
- required first-party evidence
- benchmark valuation/freshness/evidence
- non-invalidated thesis

Missing or stale required inputs fail closed.

## 7. TSMC event

The 3000 reference is stored only as an event alert. `rotation_review.event_is_gate` must always be false.

## 8. Portfolio boundary

No stock-side function may produce authoritative portfolio weights. The canonical artifact explicitly names `ELEPHANT_CAPITAL_ALLOCATION_OS` as portfolio authority.

## 9. Migration

`scripts/normalize_screen_v5.py` deterministically upgrades an existing Screen V4 snapshot without fetching network data. It exists only to make the V5 migration reproducible; the next successful live TWSE/TPEx scan becomes the fresh source of truth.

## 10. Calibration

Existing historical snapshots are not rewritten. Future snapshots use canonical Python-derived actions. `rebuild_performance.py` therefore keeps one continuous point-in-time learning history across the migration.
