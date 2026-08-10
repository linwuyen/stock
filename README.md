# Taiwan Alpha Stock Selection Engine

**Live Dashboard:** https://linwuyen.github.io/stock/

這個 repository 維護台股 Alpha discovery、估值、證據、歷史快照、配置模擬、通知與模型校準。目標不是預測短期漲跌，而是找出「市場預期低於基本面改善速度」且相對於持有台積電仍有足夠 **Net Alpha Spread** 的標的。

> Decision chain: **Official Data → Full-Market Screen → Deep Research → Evidence → Reproducible Score → Confidence → Fair Value → Expected Return → Alpha Spread vs TSMC → Buy Gate → Risk Sizing → Realized Alpha → Calibration**

## 1. 第一性原理

Alpha 至少來自一項：盈餘成長高於市場隱含預期、Forward/normalized valuation 有安全邊際、結構性產品/產業變化尚未反映、或市場把暫時問題錯當永久問題。單純「跌很多、題材熱門、法人買超」不構成買進理由。

## 2. Alpha Score 與 Confidence Score 分離

### Alpha Score（100）

| 因子 | 權重 |
|---|---:|
| Earnings acceleration | 30 |
| Revenue quality | 20 |
| Valuation | 25 |
| Structural catalyst | 15 |
| Balance sheet / cash flow | 10 |

CI 強制：`score = sum(factor_scores) + sum(penalties)`。

### Confidence Score（100）

Evidence quality 30、Forecast visibility 25、Circle of competence 20、Thesis clarity 15、Data freshness 10。Circle of competence 不增加內在價值，只增加我們對判斷的可信度。

## 3. Buy Gate

只有全部成立才可顯示 `BUY CANDIDATE`：

- Alpha Score ≥ 75
- Confidence Score ≥ 65
- Candidate 與 TSMC valuation model 都是 `COMPLETE`
- Base MOS ≥ 20%
- Candidate Expected Return - TSMC Expected Return ≥ 8%
- 必要 evidence 為 `FIRST_PARTY + VERIFIED`
- market / fundamentals / revenue / event freshness 全部通過
- thesis 未 invalidated

高分但少一個 Gate 也只能 `VERIFY`。

## 4. TSMC 3000 的角色

`TSMC = 3000` 只是 **event trigger**，不是賣出訊號。真正比較：

`Net Alpha Spread = Candidate Expected Return - TSMC Expected Return`

沒有足夠 spread 時，最優解可以是繼續持有台積電或現金。

## 5. Full-Market Discovery v4

`data/screen.json` 已由手動 Seed 改成 scanner-driven schema v2。`scripts/scan_market.py` 使用官方 OpenAPI：

- TWSE：公司基本資料、每日行情、PE/PB、月營收、一般業損益表
- TPEx：上櫃公司基本資料、收盤行情、PE/PB、月營收、一般業損益表

漏斗：

**TWSE + TPEx issuer universe → non-financial → growth / earnings / valuation / liquidity → Top 50 → Deep Research Top 10 + incumbent BUY/VERIFY → Alpha Engine**

重要邊界：

- **Screen 永遠不能直接產生 BUY_CANDIDATE**；只負責 discovery。
- 任一市場必要官方來源失敗時，該市場 `promotion = OFF`，舊資料只能 `STALE_CARRYOVER`。
- Market cap 暫不做跨市場 hard filter，因為在未有對稱官方欄位前硬套會製造 TWSE/TPEx selection bias；目前只作 soft metadata。
- 流動性最終使用 20 個「不同市場快照」的 turnover median；前 10 個 observation 前明確標記 bootstrap。
- 使用全市場 quote fingerprint 去重，國定假日或重複執行不會灌入假的新 liquidity observation。
- Top 50 保留 raw discovery；Deep Research Top 10 先做產業分散，同一 industry cluster 第一輪最多 2 檔，再按排名補滿。
- TPEx 產業 enrichment 採 TPEx JSON 優先、官方 MOPS CSV fallback，避免單一路徑截斷使產業分散失效。
- 最新損益表 endpoint 在任一時點可能只涵蓋當批新申報公司。若某公司本批沒有 EPS row，但官方 TTM PE > 0，Screen 可用 `POSITIVE_TTM_PE_PROXY` 作**純 discovery 盈利 proxy**；必須加 `EARNINGS_FILING_NOT_IN_CURRENT_DATASET`，Deep Research 仍要回到正式 filing 驗證盈餘，proxy 永遠不能滿足 Alpha Buy Gate。
- 排名改用非飽和 `screen_priority`：log-scaled revenue growth + 累計成長一致性 + valuation + profitability + liquidity + data quality - cycle / missing-EPS penalties。舊 `screen_score` 僅保留作可解釋 secondary metric，不再讓多檔極端成長股一起卡在 100 分並靠單月 YoY 排序。
- 極端 Revenue YoY + 低 PE + 正 EPS 會加 `CYCLE_EXTREME_GROWTH_LOW_PE`；它只要求 normalized-cycle review，不直接排除候選，也不代表可買。

`.github/workflows/market-scan.yml` 每個工作日台灣時間約 14:20 執行；scanner 或 workflow 合併 `main` 時也會立即跑一次。

## 6. Valuation / Evidence / Freshness

每檔與 TSMC 共用 Bear/Base/Bull schema：Forward EPS、Normalized EPS、Forward/Normalized PE、Expected FV、Expected Return、MOS。模型假設與 reported facts 分開保存。

`evidence[]` 保存 metric/value/period/observed_at/source_type/source_url/quality/status。資料優先：MOPS / TWSE / TPEx / 公司 IR。

Freshness 分層：市場價格、月營收、財報、事件各自獨立；必要日期缺漏即 FAIL，不會把 null 當 PASS。

## 7. Intraday Event Audit

每週 `data/history/YYYY-MM-DD.json` 仍是一日一份決策 snapshot；盤中/盤後重大事件不再覆寫同日 history。

Material event 使用 `data/events/YYYY-MM-DDTHHMMSS-*.json`，並由 `data/events/index.json` 索引。`scripts/record_event.py` 對既有 event 檔採拒絕覆寫，確保 audit trail immutable。

## 8. Alpha 通知去重

`data/alerts.json` 保存 BUY 狀態機：

- 只有 `非 BUY → BUY_CANDIDATE` 才建立 notification。
- 同一段 BUY 狀態不重複通知。
- 退出後再進入會增加 `buy_entry_sequence`，可再次通知。
- Screen Top 10 / A 級 / VERIFY 都不會單獨觸發 Alpha 通知。
- 永不自動交易。

`scripts/sync_alert_state.py` 由 `.github/workflows/alert-state.yml` 在 `alpha.json` 變更後同步 transition state。

## 9. Risk-adjusted Position Sizing

完整模型可用時：`raw weight ∝ positive Alpha Spread × Confidence / downside risk`，再套單股 ≤25%、現金 ≥20%、未過 Buy Gate 權重=0。資料不足時 fallback 只供研究展示，Rotation Gate 保持 blocked/preview。

## 10. Performance / Calibration v2

主校準 cohort 只使用真正 **切入 BUY_CANDIDATE 的 entry transition**；同一檔連續 BUY 多週不會重複算樣本。A 級股票另外放在 diagnostic cohort，不跟實際買進決策混在一起。

追蹤 1/4/13/26/52W excess return vs TSMC。現階段是 **price return，未含現金股息**，因此禁止稱為 total return。樣本不足 30 前不因短期漂亮/難看結果調模型權重。

## 11. Repository Data Contract

- `data/alpha.json`：主決策資料，schema v3。
- `data/screen.json`：全市場 discovery，schema v2。
- `data/liquidity-history.json`：跨日 unique market snapshot turnover history。
- `data/alerts.json`：BUY transition / notification dedupe state。
- `data/events/index.json` + timestamped event files：盤中重大事件 audit。
- `data/history/`：每週決策 snapshot。
- `data/performance.json`：realized alpha，schema v2。

## 12. CI Decision Integrity

Pages PR / push 必須先通過：

- 所有 JS / Python syntax
- Alpha / Confidence 可重算
- Grade / Rank / Action 與 Gate 一致
- TSMC benchmark 跟候選股同樣 evidence / freshness 標準
- Bear/Base/Bull FV 一致性
- Full-market screen schema、Top50/Top10、promotion fail-closed
- Screen 不得寫 portfolio action
- Live screen 必須按非飽和 `screen_priority` 排序；TTM PE profitability proxy 必須帶明確 flag 且不能冒充 reported EPS
- Alerts active BUY set 與 Alpha Engine 一致，notification sequence 不重複
- Event index 唯一且所有 event file 存在
- History index/snapshot 一致
- Performance dataset 可由 history deterministic rebuild

驗證失敗則 Pages 不部署。

## 13. 更新節奏

- **Market scanner**：工作日約 14:20，自動刷新 TWSE + TPEx Top 50 / Top 10。
- **Weekly full research**：每週一重新做 Deep Research、valuation、score、history、performance。
- **Event watch / Alpha alert**：財報、月營收、法說、重大訊息或 Gate crossing 發生時重算；只有新進 `BUY_CANDIDATE` 才通知。

本系統是研究與決策紀錄，不構成自動交易系統，也不會送出交易。
