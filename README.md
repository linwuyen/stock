# Taiwan Alpha Stock Selection

**Live Dashboard:** https://linwuyen.github.io/stock/

這個 repository 用來維護台股 Alpha 選股框架、每週研究結果與 GitHub Pages 儀表板。

目標不是預測短期漲跌，而是在可承受風險下，尋找「市場預期低於基本面實際改善速度」的股票，並以固定規則持續驗證 thesis。

## 1. 第一性原理

Alpha 來源必須至少符合其中一種：

1. 盈餘成長速度高於市場目前隱含預期。
2. 估值低於可持續的 normalized earnings 所合理支持的區間。
3. 產品/產業結構改變尚未完全反映在獲利與估值。
4. 市場錯把暫時性問題當永久問題，或錯把週期高峰當永久成長。

不因「跌很多」、「題材熱門」、「法人買超」單獨買進。

## 2. 資料來源優先順序

每週更新時優先採用：

1. 公開資訊觀測站（MOPS）：季報、月營收、重大訊息。
2. 臺灣證券交易所（TWSE）：收盤價、本益比、股價淨值比、殖利率。
3. 公司官方 Investor Relations / 法說會簡報。
4. 必要時才用可靠媒體或研究資料補充。

任何數據若無法用第一手資料驗證，標記為「待驗證」。

## 3. Alpha Score（100 分）

| 因子 | 權重 | 核心問題 |
|---|---:|---|
| Earnings acceleration | 25 | EPS / 營業利益是否持續加速？ |
| Revenue quality | 15 | 營收成長是否能轉成毛利、營益與現金流？ |
| Valuation | 25 | Forward / normalized PE 是否仍有安全邊際？ |
| Structural catalyst | 15 | 是否存在 12–24 個月可驗證的產品/產業催化劑？ |
| Balance sheet / cash flow | 10 | 淨負債、FCF、營運資金是否健康？ |
| Circle of competence | 10 | 是否能從工程/產業知識形成額外判斷優勢？ |

### 風險扣分

- 週期高峰但以 peak EPS 估值：-5 ~ -20
- Forward PE 已反映極高成長：-5 ~ -20
- 毛利率下降、營收成長但 EPS 不成長：-5 ~ -15
- 客戶/產品集中度過高：-5 ~ -10
- FCF 明顯落後會計盈餘：-5 ~ -10
- Thesis 依賴單一未驗證事件：-5 ~ -15

## 4. 分級

- **A (>= 75)**：Alpha 候選，可進一步評估買點與部位。
- **B (65–74)**：Watch，基本面有吸引力但估值或證據不足。
- **C (50–64)**：觀察，不建立新部位。
- **D (< 50)**：排除。

A 級不等於立即買進。買進仍需估值與風險條件同時成立。

## 5. 初始 Universe（2026-08-10）

### A / 優先研究

- **2301 光寶科**：AI power / BBU / Power Shelf / HVDC，重點驗證 AI 電源成長能否持續轉成 margin expansion 與 EPS。
- **2376 技嘉**：AI server 成長與相對較低估值，重點驗證 server 營收能否持續轉成 EPS 與現金流。
- **2382 廣達**：AI server 營收成長強，但需確認營收成長與 EPS 成長之間的落差是否收斂。

### B / 週期型或等待確認

- **2451 創見**：記憶體週期高 Beta；禁止直接使用 peak trailing EPS，必須以 normalized EPS 估值。
- **3515 華擎**：等待 server / AI 相關營運對 EPS 的持續性證據。
- **3081 聯亞**：成長性高，但估值與最新財報需同步重估，避免追高。

### 高估值觀察池

- 2383 台光電
- 2360 致茂
- 3450 聯鈞
- 6442 光聖
- 2308 台達電
- 2368 金像電

高估值不代表公司差，只表示必須要求更高的 earnings growth 與更大的估值安全邊際才可升級。

## 6. 每週固定檢查

每週重新取得最新資料，而不是沿用前一週數字：

1. 最新收盤價與 TTM PE/PB。
2. 最新月營收與 YoY / MoM。
3. 最新季 EPS、毛利率、營益率。
4. 營業現金流與 FCF（財報公布後更新）。
5. 公司法說/重大訊息是否改變 thesis。
6. 重新估當年度 / 次年度 normalized EPS。
7. 重算 Forward PE 與 Alpha Score。
8. 比較上週：升級、降級、新增、剔除。
9. 明確列出 thesis invalidation condition。

## 7. 買進 Gate

只有同時符合以下條件才進入「可買候選」：

- Alpha Score >= 75。
- Forward / normalized valuation 有至少約 20% 安全邊際。
- EPS / Operating Profit 趨勢未惡化。
- 現金流沒有明顯反證。
- 沒有出現 thesis invalidation condition。

不因達到 A 級而一次買滿；採分批方式，並以新財報/里程碑作為加碼條件。

## 8. 台積電 3000 元事件

「台積電到 3000 元賣出一張」與「立刻買入 Alpha 股」是兩個獨立決策。

台積電到達 3000 元當週，必須用當時最新資料重新跑完整 Alpha Score。若沒有股票通過 Buy Gate，資金保持現金，不為了換股而換股。

## 9. 每週輸出格式

每週報告固定輸出：

| Rank | 股票 | Alpha Score | Grade | 最新估值 | Earnings trend | Thesis | 變化 | Action |
|---|---|---:|---|---|---|---|---|---|

並附：

- Top 3 Alpha candidate
- 新增 / 剔除名單
- 最大風險
- 下週需要驗證的事件
- 若台積電本週到 3000 元，資金應如何分配（只給研究建議，不執行交易）

## 10. Dashboard v2

GitHub Pages 由 `index.html`、`styles.css`、`app.js` 與 JSON 資料驅動。功能包括：

- 每週 Alpha Ranking。
- 與前一份 snapshot 比較的排名 ↑↓、Score、Grade 與 Action 變化。
- 最近最多 26 份 snapshot 的 Alpha Score 歷史曲線。
- 台積電 3000 元事件 Gate。
- 300 萬元資金配置 sandbox，可修改資金與權重。
- Buy Gate、單一持股上限、現金底線與資料過期檢查。

模擬器只計算研究部位，不建立或送出交易。

## 11. 資料契約

### `data/alpha.json`

目前 schema version 為 2。每週至少更新：

- `meta.as_of`
- `meta.market_data_as_of`
- `meta.next_review`
- `tsmc.reference_price`
- `tsmc.reference_price_date`
- `stocks[].rank / score / grade / action`
- `stocks[].reference_price / reference_price_date`
- `stocks[].pe_ttm / earnings_trend / valuation`
- `stocks[].thesis / risk / next_check`
- `watchlist`

`rotation_model` 的 guardrails 是風險規則，不應因單週市場情緒任意放寬。

### `data/history/YYYY-MM-DD.json`

每週保存當週決策快照。歷史 snapshot 是「當時的判斷」，不得事後改寫成最新事實，除非修正資料錯誤並留下 commit 紀錄。

### `data/history/index.json`

網站不掃描目錄，因此每次新增 snapshot 都必須同步：

1. 新增 snapshot 路徑。
2. 依日期排序。
3. 更新 `latest`。

## 12. 每週更新原子流程

每週研究完成後：

1. 先以第一手資料重算 Alpha。
2. 更新 `data/alpha.json`。
3. 建立或更新 `data/history/YYYY-MM-DD.json`。
4. 更新 `data/history/index.json`。
5. 提交到 `main`。
6. GitHub Actions 驗證 JS、JSON、權重、ticker、history index 與 snapshot。
7. 驗證成功後部署 GitHub Pages。

如果其中任一步驟缺資料，寧可保留 `WATCH / VERIFY`，不要用舊資料補洞。

## 13. 預設 Rotation Sandbox Guardrails

- 預設資金：NT$3,000,000。
- 預設只配置通過 Buy Gate 的 A 級候選。
- 單一股票上限：25%。
- 現金底線：20%。
- 資料超過 10 天未更新：配置 Gate 直接 BLOCKED。
- 台積電未達 3000：狀態維持 PREVIEW。
- 台積電達 3000 且所有 guardrail 通過：僅顯示 READY FOR REVIEW，不自動交易。

---

本框架是研究與決策紀錄，不構成自動交易系統。