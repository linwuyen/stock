#!/usr/bin/env python3
import hashlib
import json
import math
import re
import statistics
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
NOW = datetime.now(TZ)
TODAY = NOW.date().isoformat()
UA = "linwuyen-alpha-engine/4.0 (+https://github.com/linwuyen/stock)"

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"

SOURCES = {
    "TWSE": {
        "profiles": f"{TWSE}/opendata/t187ap03_L",
        "quotes": f"{TWSE}/exchangeReport/STOCK_DAY_ALL",
        "valuation": f"{TWSE}/exchangeReport/BWIBBU_ALL",
        "revenue": f"{TWSE}/opendata/t187ap05_L",
        "income": f"{TWSE}/opendata/t187ap06_L_ci",
    },
    "TPEX": {
        "profiles": f"{TPEX}/mopsfin_t187ap03_O",
        "quotes": f"{TPEX}/tpex_mainboard_quotes",
        "valuation": f"{TPEX}/tpex_mainboard_peratio_analysis",
        "revenue": f"{TPEX}/mopsfin_t187ap05_O",
        "income": f"{TPEX}/mopsfin_t187ap06_O_ci",
    },
}

FINANCIAL_WORDS = ("金融", "銀行", "保險", "證券", "票券", "金控")
CODE_RE = re.compile(r"^\d{4}$")


def load(path, default):
    p = ROOT / path
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "aaData", "result", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
        for value in payload.values():
            if isinstance(value, list):
                return value
    raise ValueError(f"unexpected payload shape from {url}")


def norm_key(value):
    return re.sub(r"[\s()（）\-_/:%％,.]", "", str(value)).lower()


def pick(row, aliases):
    if not isinstance(row, dict):
        return None
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    normalized = {norm_key(k): v for k, v in row.items()}
    for alias in aliases:
        value = normalized.get(norm_key(alias))
        if value not in (None, ""):
            return value
    return None


def num(value):
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "").replace("％", "")
    if s in {"", "-", "--", "---", "N/A", "nan", "None"}:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def text(value):
    return "" if value is None else str(value).strip()


def code_of(row):
    value = pick(row, ["公司代號", "公司代碼", "Code", "SecuritiesCompanyCode", "股票代號", "證券代號"])
    value = text(value)
    return value if CODE_RE.match(value) else None


def name_of(row):
    return text(pick(row, ["公司名稱", "公司簡稱", "Name", "CompanyName", "證券名稱", "股票名稱"]))


def industry_of(row):
    return text(pick(row, ["產業別", "產業類別", "Industry", "IndustryName", "產業別名稱"]))


def is_financial(industry):
    return any(word in industry for word in FINANCIAL_WORDS)


def period_key(row):
    year = num(pick(row, ["年度", "Year", "year"]))
    quarter = num(pick(row, ["季別", "Quarter", "季", "quarter"]))
    month = text(pick(row, ["資料年月", "年月", "YearMonth"]))
    if year is not None and quarter is not None:
        return (int(year), int(quarter), month)
    return (0, 0, month)


def latest_rows(rows):
    out = {}
    for row in rows:
        code = code_of(row)
        if not code:
            continue
        if code not in out or period_key(row) >= period_key(out[code]):
            out[code] = row
    return out


def quote_fingerprint(rows):
    normalized = []
    for row in rows:
        code = code_of(row)
        if not code:
            continue
        price = num(pick(row, ["ClosingPrice", "Close", "收盤價", "最後成交價", "收盤"]))
        turnover = num(pick(row, ["TradeValue", "TransactionAmount", "成交金額", "成交值", "TradeAmount"]))
        normalized.append((code, price, turnover))
    payload = json.dumps(sorted(normalized), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() if normalized else None


def score_revenue(yoy):
    if yoy is None: return 0
    if yoy >= 50: return 40
    if yoy >= 35: return 35
    if yoy >= 25: return 30
    if yoy >= 15: return 24
    if yoy >= 8: return 14
    if yoy >= 0: return 6
    return 0


def score_pe(pe, revenue_yoy):
    if pe is None: return 4 if (revenue_yoy or 0) >= 35 else 0
    if pe <= 0: return 0
    if pe <= 12: return 25
    if pe <= 18: return 22
    if pe <= 25: return 18
    if pe <= 35: return 12
    return 7 if (revenue_yoy or 0) >= 35 else 0


def score_eps(eps):
    if eps is None: return 0
    if eps >= 10: return 15
    if eps >= 5: return 13
    if eps > 0: return 10
    return 0


def liquidity_score(median_turnover, latest_turnover, observations):
    basis = median_turnover if observations >= 10 and median_turnover is not None else latest_turnover
    if basis is None: return 0
    if basis >= 200_000_000: return 10
    if basis >= 100_000_000: return 9
    if basis >= 50_000_000: return 8
    if basis >= 20_000_000: return 6
    if basis >= 5_000_000: return 3
    return 0


def quality_score(fields):
    present = sum(value is not None and value != "" for value in fields)
    return round(10 * present / len(fields), 2)


def update_liquidity(history, market, code, turnover, append_snapshot):
    key = f"{market}:{code}"
    series = history.setdefault("series", {}).setdefault(key, [])
    if append_snapshot and turnover is not None:
        series = [x for x in series if x.get("date") != TODAY]
        series.append({"date": TODAY, "turnover_twd": round(turnover, 2)})
        series = sorted(series, key=lambda x: x["date"])[-20:]
        history["series"][key] = series
    values = [float(x["turnover_twd"]) for x in series if x.get("turnover_twd") is not None]
    return series, statistics.median(values) if values else None


def scan_market(market, datasets, history, append_liquidity):
    profiles = latest_rows(datasets.get("profiles", []))
    quotes = latest_rows(datasets.get("quotes", []))
    valuation = latest_rows(datasets.get("valuation", []))
    revenue = latest_rows(datasets.get("revenue", []))
    income = latest_rows(datasets.get("income", []))
    candidates = []
    coverage = {"profiles": len(profiles), "quotes": len(quotes), "revenue": len(revenue), "income": len(income), "valuation": len(valuation)}

    for code, profile in profiles.items():
        industry = industry_of(profile)
        if not CODE_RE.match(code) or is_financial(industry):
            continue
        quote, rev, inc, val = quotes.get(code, {}), revenue.get(code, {}), income.get(code, {}), valuation.get(code, {})
        name = name_of(profile) or name_of(quote) or name_of(rev) or code
        price = num(pick(quote, ["ClosingPrice", "Close", "收盤價", "最後成交價", "收盤"]))
        turnover = num(pick(quote, ["TradeValue", "TransactionAmount", "成交金額", "成交值", "TradeAmount"]))
        pe = num(pick(val, ["PEratio", "PriceEarningRatio", "本益比", "P/E", "PERatio"]))
        rev_yoy = num(pick(rev, ["營業收入-去年同月增減(%)", "營業收入去年同月增減(%)", "去年同月增減(%)", "RevenueYoY", "YoY(%)"]))
        cum_rev_yoy = num(pick(rev, ["累計營業收入-前期比較增減(%)", "累計營業收入前期比較增減(%)", "累計年增率(%)", "CumulativeRevenueYoY"]))
        eps = num(pick(inc, ["基本每股盈餘（元）", "基本每股盈餘(元)", "基本每股盈餘", "EPS", "BasicEarningsPerShare"]))
        market_cap = num(pick(quote, ["MarketValue", "MarketCap", "市值"])) or num(pick(profile, ["MarketValue", "MarketCap", "市值"]))
        series, median_turnover = update_liquidity(history, market, code, turnover, append_liquidity)
        observations = len(series)

        liquidity_pass = (median_turnover or 0) >= 20_000_000 if observations >= 10 else (turnover or 0) >= 5_000_000
        revenue_pass = rev_yoy is not None and rev_yoy >= 15
        earnings_pass = (eps is not None and eps > 0) or (rev_yoy is not None and rev_yoy >= 35)
        valuation_pass = pe is None or pe <= 35 or (rev_yoy is not None and rev_yoy >= 35)
        if not (liquidity_pass and revenue_pass and earnings_pass and valuation_pass):
            continue

        data_quality = quality_score([price, turnover, pe, rev_yoy, eps])
        screen_score = round(score_revenue(rev_yoy) + score_pe(pe, rev_yoy) + score_eps(eps) + liquidity_score(median_turnover, turnover, observations) + data_quality, 2)
        flags = []
        if observations < 10: flags.append("LIQUIDITY_BOOTSTRAP")
        if not append_liquidity: flags.append("NO_NEW_MARKET_SNAPSHOT")
        if pe is None: flags.append("VALUATION_VERIFY")
        if eps is None: flags.append("EARNINGS_VERIFY")
        if market_cap is None: flags.append("MARKET_CAP_UNAVAILABLE_NOT_HARD_FILTERED")
        candidates.append({
            "ticker": code,
            "name": name,
            "market": market,
            "industry": industry,
            "screen_score": screen_score,
            "reference_price": price,
            "revenue_yoy_pct": rev_yoy,
            "cumulative_revenue_yoy_pct": cum_rev_yoy,
            "pe_ttm": pe,
            "latest_reported_eps": eps,
            "latest_daily_turnover_twd": turnover,
            "median_turnover_twd": round(median_turnover, 2) if median_turnover is not None else None,
            "liquidity_observations": observations,
            "liquidity_mode": "MEDIAN_20D" if observations >= 10 else "BOOTSTRAP_LATEST_DAY",
            "market_cap_twd": market_cap,
            "data_quality_score": data_quality,
            "flags": flags,
            "status": "SCREEN_PASS",
            "promotion_eligible": True,
        })

    candidates.sort(key=lambda x: (-x["screen_score"], -(x.get("revenue_yoy_pct") or -999), x["ticker"]))
    for i, item in enumerate(candidates, 1): item["rank"] = i
    return candidates, coverage


def main():
    previous = load("data/screen.json", {"candidates": []})
    alpha = load("data/alpha.json", {"stocks": []})
    history = load("data/liquidity-history.json", {"schema_version": 1, "as_of": None, "window": 20, "series": {}, "market_state": {}})
    history.setdefault("market_state", {})
    source_health, fetched = {}, {}

    for market, endpoints in SOURCES.items():
        fetched[market], source_health[market] = {}, {}
        for label, url in endpoints.items():
            try:
                rows = fetch(url)
                fetched[market][label] = rows
                source_health[market][label] = {"ok": True, "rows": len(rows), "url": url}
            except Exception as exc:
                fetched[market][label] = []
                source_health[market][label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "url": url}

    all_candidates, coverage, promotion_by_market = [], {}, {}
    critical = {"profiles", "quotes", "valuation", "revenue", "income"}
    previous_by_market = {market: [x for x in previous.get("candidates", []) if x.get("market") == market] for market in SOURCES}

    for market in SOURCES:
        market_ok = all(source_health[market].get(label, {}).get("ok") for label in critical)
        promotion_by_market[market] = market_ok
        if market_ok:
            fingerprint = quote_fingerprint(fetched[market]["quotes"])
            prior_state = history["market_state"].get(market, {})
            new_snapshot = bool(fingerprint and fingerprint != prior_state.get("fingerprint"))
            source_health[market]["quotes"]["new_market_snapshot"] = new_snapshot
            if new_snapshot:
                history["market_state"][market] = {"fingerprint": fingerprint, "last_new_snapshot_date": TODAY}
            candidates, market_coverage = scan_market(market, fetched[market], history, append_liquidity=new_snapshot)
            market_coverage["new_market_snapshot"] = new_snapshot
            coverage[market] = market_coverage
            all_candidates.extend(candidates)
        else:
            coverage[market] = {"status": "SOURCE_DEGRADED"}
            for old in previous_by_market.get(market, []):
                stale = dict(old)
                stale["status"] = "STALE_CARRYOVER"
                stale["promotion_eligible"] = False
                stale["flags"] = list(dict.fromkeys(stale.get("flags", []) + ["SOURCE_DEGRADED"]))
                all_candidates.append(stale)

    all_candidates.sort(key=lambda x: (not x.get("promotion_eligible", False), -float(x.get("screen_score") or 0), x.get("ticker", "")))
    eligible = [x for x in all_candidates if x.get("promotion_eligible")]
    top50 = eligible[:50]
    for i, item in enumerate(top50, 1): item["rank"] = i
    deep = [dict(x) for x in top50[:10]]
    by_ticker = {x["ticker"]: x for x in all_candidates}
    incumbent = []
    for stock in alpha.get("stocks", []):
        row = by_ticker.get(stock["ticker"])
        incumbent.append({
            "ticker": stock["ticker"],
            "name": stock.get("name"),
            "alpha_rank": stock.get("rank"),
            "alpha_action": stock.get("action"),
            "screen_rank": row.get("rank") if row else None,
            "screen_status": row.get("status") if row else "NOT_IN_SCREEN",
        })

    status = "COMPLETE" if all(promotion_by_market.values()) else "DEGRADED"
    out = {
        "meta": {
            "schema_version": 2,
            "as_of": TODAY,
            "generated_at": NOW.isoformat(timespec="seconds"),
            "status": status,
            "coverage": "TWSE + TPEx current common-stock issuer universe; non-financial discovery screen.",
            "promotion_enabled_by_market": promotion_by_market,
            "fail_closed": True,
        },
        "rules": {
            "exclude_sectors": ["Financials"],
            "revenue_yoy_pct_min": 15,
            "ttm_pe_soft_cap": 35,
            "high_growth_pe_exception_revenue_yoy_pct": 35,
            "earnings_gate": "positive latest reported EPS OR revenue YoY >= 35% with EARNINGS_VERIFY flag",
            "liquidity": {
                "target_median_daily_turnover_twd_million": 20,
                "established_after_observations": 10,
                "bootstrap_latest_day_floor_twd_million": 5,
                "window_observations": 20,
                "dedupe": "full-market quote fingerprint; unchanged market snapshots do not add observations",
            },
            "market_cap": {
                "mode": "SOFT_ONLY",
                "reason": "No symmetric authoritative free market-cap field is assumed across TWSE and TPEx. Do not create cross-market selection bias by hard-filtering only one market.",
            },
            "screen_is_not_buy_gate": True,
            "research_funnel": "Full TWSE/TPEx issuer universe → quantitative screen → Top 50 → deep research Top 10 + incumbent VERIFY/BUY → Alpha Engine Buy Gate",
            "universe_policy": "Deep research queue is Top 10 screen candidates plus incumbent BUY/VERIFY names; screen ranking never directly creates BUY CANDIDATE.",
        },
        "source_health": source_health,
        "coverage_counts": coverage,
        "candidates": top50,
        "deep_research_queue": deep,
        "incumbent_research": incumbent,
        "notes": [
            "Market-cap hard filtering is intentionally disabled until a symmetric authoritative field is available for both markets.",
            "Liquidity uses rolling unique market snapshots; holidays and repeated runs do not duplicate observations.",
            "Any degraded market source disables promotion from that market and preserves prior rows only as stale carryover outside the promotion queue.",
        ],
    }
    history["schema_version"] = 1
    history["as_of"] = TODAY
    history["window"] = 20
    write("data/liquidity-history.json", history)
    write("data/screen.json", out)
    print(f"screen status={status}; eligible={len(eligible)}; top50={len(top50)}; deep={len(deep)}")
    if not any(promotion_by_market.values()):
        print("ERROR: both markets unavailable; fail closed", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
