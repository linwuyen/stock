# Taiwan Alpha Stock Selection Engine

**Live Dashboard:** https://linwuyen.github.io/stock/

這個 repository 維護台股 Alpha 選股、估值、證據、歷史快照、配置模擬與模型校準。目標不是預測短期漲跌，而是找出「市場預期低於基本面改善速度」且相對於持有台積電仍有足夠 **Net Alpha Spread** 的標的。

> Decision chain: **Evidence → Reproducible Score → Confidence → Fair Value → Expected Return → Alpha Spread vs TSMC → Risk Sizing → Realized Alpha → Calibration**

## 1. 第一性原理

Alpha 來源至少符合一項：

1. 盈餘成長速度高於市場目前隱含預期。
2. Forward / normalized valuation 低於可持續盈餘支持的合理區間。
3. 產品或產業結構改變尚未完全反映在獲利與估值。
4. 市場錯把暫時問題當永久問題，或把週期高峰誤認成永久成長。

不因「跌很多」、「題材熱門」、「法人買超」單獨買進。

## 2. Alpha Score 與 Confidence Score 分離

### Alpha Score（100）

| 因子 | 權重 |
|---|---:|
| Earnings acceleration | 30 |
| Revenue quality | 20 |
| Valuation | 25 |
| Structural catalyst | 15 |
| Balance sheet / cash flow | 10 |

每檔股票在 `factor_scores` 保存子分數；風險扣分放在 `penalties`。CI 強制：

`score = sum(factor_scores) + sum(penalties)`

### Confidence Score（100）

| 因子 | 權重 |
|---|---:|
| Evidence quality | 30 |
| Forecast visibility | 25 |
| Circle of competence | 20 |
| Thesis clarity | 15 |
| Data freshness | 10 |

Circle of competence 不再提高 Alpha Score；它只提高我們對判斷的可信度。

## 3. Buy Gate

只有全部成立才可顯示 `BUY CANDIDATE`：

- Alpha Score ≥ 75
- Confidence Score ≥ 65
- valuation model = `COMPLETE`
- Base-case margin of safety ≥ 20%
- Expected return 相對 TSMC 的 Alpha Spread ≥ 8%
- 必要 evidence 為第一手且 VERIFIED
- freshness 通過
- thesis 未 invalidated

否則高分股只能是 `VERIFY`，不是買進訊號。

## 4. 台積電 3000 元的正確角色

`TSMC = 3000` 只是 **event trigger**：要求當週重新跑完整估值與比較，不代表自動賣出。

真正比較：

`Net Alpha Spread = Candidate Expected Return - TSMC Expected Return`

如果候選股沒有明顯勝過繼續持有台積電，最優行動可以是 **不換股**。

## 5. Valuation Engine

每檔候選與 TSMC 使用相同 schema：

- TTM EPS（可由 price / TTM PE 衍生，僅作參考）
- Forward EPS
- Normalized EPS
- Forward PE / Normalized PE
- Bear / Base / Bull EPS、multiple、fair value、probability
- Expected Fair Value
- Expected Return
- Margin of Safety

Forward / normalized inputs未由第一手資料完成時，`valuation_model.status = VERIFY`，Rotation Gate 必須 BLOCKED。

## 6. Evidence / Audit Trail

`stocks[].evidence[]` 保存：

- metric / value / period
- observed_at
- source_type / source_url
- quality: `FIRST_PARTY` / `SECONDARY` / `INFERRED`
- status: `VERIFIED` / `VERIFY`

資料優先順序：MOPS → TWSE → 公司 IR / 法說 → 可靠次級資料。歷史 snapshot 是當時判斷，不因後續結果而回寫。

## 7. Freshness 分層

- Market price：目標 ≤ 1 trading day；週末容忍最多 3 calendar days
- Monthly revenue：≤ 45 days
- Financial statements：≤ 130 days
- Event / IR check：≤ 14 days

不能再用一個「10 天」同時代表價格與基本面 freshness。

## 8. Universe Screen

`data/screen.json` 定義全市場候選漏斗：

**TWSE/TPEx non-financial → liquidity/size/growth/valuation screen → Top 50 → Deep Research Top 10 → Alpha Ranking**

目前 seed universe 只是起點；每週 automation 必須掃描新標的，避免 selection bias。

## 9. Risk-adjusted Position Sizing

完整模型可用時，sandbox 依下列方向產生相對權重：

`raw weight ∝ positive Alpha Spread × Confidence / downside risk`

再套：

- 單股上限 25%
- 現金底線 20%
- 不通過 Buy Gate 的股票權重 = 0

資料不足時可顯示 fallback research allocation，但 Rotation Gate 保持 BLOCKED。

## 10. Performance / Model Calibration

`data/performance.json` 追蹤進入 A / BUY 狀態後的：

- 1W
- 4W
- 13W
- 26W
- 52W

excess return（股票報酬 - TSMC 報酬）。`scripts/rebuild_performance.py` 從歷史 snapshot 重建資料；樣本不足前禁止為了漂亮結果調參。

閉環：

**Decision → Actual Return → Score bucket predictive power → Calibration**

## 11. Repository Data Contract

### `data/alpha.json` — schema v3
主決策資料：score decomposition、confidence、valuation、risk、evidence、TSMC benchmark、freshness、decision policy。

### `data/screen.json`
全市場 screen 規則與本週候選漏斗。

### `data/performance.json`
Realized Alpha / calibration 結果。

### `data/history/YYYY-MM-DD.json`
每週保存當時 snapshot。未來 snapshot 至少保存 benchmark price，以及每檔 rank / score / confidence / action / reference_price，供績效重建。

### `data/history/index.json`
歷史 snapshot 索引；日期必須唯一且排序。

## 12. CI Decision Integrity

`.github/workflows/pages.yml` 不只檢查 JSON 格式，還驗證：

- Alpha Score 可由 factor scores + penalties 重算
- Confidence 可由 confidence factors 重算
- Grade 與 threshold 一致
- Rank 按 Score 遞減
- Action 必須符合 Buy Gate
- Bear/Base/Bull complete 時 FV ≈ EPS × multiple
- allocation = 100%、cash floor、single-stock cap
- market data 與 review date freshness
- history index / snapshot 一致
- performance.json 與歷史資料可重建結果一致

驗證成功才部署 GitHub Pages。

## 13. 更新節奏

- **Weekly full scan**：每週一重新抓第一手資料、重算 universe / valuation / score / ranking / history / performance。
- **Event watch**：工作日檢查財報、月營收、法說、重大訊息；有 material change 才重算受影響標的並更新網站。

本系統是研究與決策紀錄，不構成自動交易系統，也不會送出交易。
