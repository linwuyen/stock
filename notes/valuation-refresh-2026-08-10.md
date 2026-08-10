# 2026-08-10 Alpha Engine v3 Valuation Refresh

## Decision summary

- Benchmark: 2330 TSMC, reference price NT$2,370 (2026-08-07).
- TSMC FY2027E scenario expected return: **36.13%**. This is a model estimate, not company guidance.
- 2376 Gigabyte is the only current A-grade candidate whose modeled expected return clears the configured **TSMC +8% Alpha Spread** hurdle: expected return 49.06%, spread +12.93%.
- Gigabyte remains **VERIFY**, not BUY CANDIDATE, because its latest verified quarterly fundamental period is 2026Q1 (2026-03-31), which is older than the 130-day fundamental freshness gate as of 2026-08-10. Q2 is the next minimum validation event.
- 2301 Lite-On remains A / VERIFY: base MOS clears 20%, but expected return 21.30% is below TSMC's modeled 36.13%, so Alpha Spread fails.
- 2382 Quanta is downgraded to B / WATCH: strong revenue growth is not yet sufficient evidence of EPS/FCF conversion, and modeled MOS/Alpha Spread fail.
- 2451 Transcend remains B / WATCH: trailing PE is distorted by peak-cycle earnings; normalized valuation gives only 3.96% modeled expected return.
- 3515 ASRock remains B / WATCH; evidence/freshness are insufficient.
- 3081 Landmark remains B / WATCH pending the next official Q2/forward-valuation refresh.

## Model assumptions

All Bear/Base/Bull EPS and PE multiples are explicit analyst-model assumptions for a common FY2027E / ~12-18 month comparison horizon. They are **not company guidance**. Reported facts and model assumptions are stored separately in `data/alpha.json`.

## Freshness fix

The v3 engine now treats missing required market/fundamental/revenue/event dates as a Buy Gate failure. The benchmark itself must also pass freshness and first-party evidence gates. CI uses `meta.as_of` for deterministic validation; the browser can additionally block decisions when the deployed data becomes stale.

## Timing note

TSMC's official financial calendar schedules July 2026 monthly sales for **2026-08-10 13:30 Asia/Taipei**. This refresh was performed before that release, so it intentionally does not claim July revenue. The weekday event monitor will reassess after a material official release.
