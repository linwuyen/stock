#!/usr/bin/env python3
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "linwuyen-alpha-engine/4.1 (+https://github.com/linwuyen/stock)"
TPEX_PROFILE = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

INDUSTRY_ALIASES = [
    "產業別", "產業類別", "產業代碼", "產業別代碼",
    "Industry", "IndustryCode", "IndustryName",
    "SecuritiesIndustryCode", "SecuritiesIndustry", "SecuritiesIndustryName",
]
CODE_ALIASES = ["公司代號", "公司代碼", "Code", "SecuritiesCompanyCode", "股票代號", "證券代號"]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write(path, obj):
    (ROOT / path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(value):
    return re.sub(r"[\s()（）\-_/:%％,.]", "", str(value)).lower()


def pick(row, aliases):
    if not isinstance(row, dict): return None
    for alias in aliases:
        if row.get(alias) not in (None, ""): return row[alias]
    normalized = {norm(k): v for k, v in row.items()}
    for alias in aliases:
        value = normalized.get(norm(alias))
        if value not in (None, ""): return value
    return None


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, list) else payload.get("data", [])


def tpex_industries():
    rows = fetch_json(TPEX_PROFILE)
    mapping = {}
    keys = sorted({k for row in rows[:25] if isinstance(row, dict) for k in row.keys()})
    for row in rows:
        code = str(pick(row, CODE_ALIASES) or "").strip()
        industry = str(pick(row, INDUSTRY_ALIASES) or "").strip()
        if code and industry: mapping[code] = industry
    return mapping, keys, len(rows)


def cycle_flag(item):
    yoy = item.get("revenue_yoy_pct")
    pe = item.get("pe_ttm")
    eps = item.get("latest_reported_eps")
    return yoy is not None and yoy >= 100 and pe is not None and 0 < pe <= 12 and eps is not None and eps > 0


def cluster_key(item):
    industry = str(item.get("industry") or "").strip()
    if industry: return f"IND:{industry}"
    return f"UNKNOWN:{item.get('market','?')}"


def diversified_queue(candidates, limit=10, max_per_cluster=2):
    selected, counts = [], {}
    # First pass: enforce diversity.
    for item in candidates:
        key = cluster_key(item)
        if counts.get(key, 0) >= max_per_cluster: continue
        selected.append(dict(item))
        counts[key] = counts.get(key, 0) + 1
        if len(selected) == limit: return selected
    # Second pass: fill remaining slots without dropping strong discovery signals.
    chosen = {x["ticker"] for x in selected}
    for item in candidates:
        if item["ticker"] in chosen: continue
        selected.append(dict(item))
        if len(selected) == limit: break
    return selected


def main():
    screen = load("data/screen.json")
    candidates = screen.get("candidates", [])
    mapping, profile_keys, row_count = {}, [], 0
    try:
        mapping, profile_keys, row_count = tpex_industries()
        industry_status = "OK" if mapping else "NO_INDUSTRY_VALUES"
    except Exception as exc:
        industry_status = f"ERROR:{type(exc).__name__}:{exc}"

    mapped = 0
    for item in candidates:
        if item.get("market") == "TPEX" and not str(item.get("industry") or "").strip():
            industry = mapping.get(item["ticker"])
            if industry:
                item["industry"] = industry
                mapped += 1
        item["research_industry_key"] = cluster_key(item)
        item["flags"] = list(dict.fromkeys(item.get("flags", [])))
        if cycle_flag(item) and "CYCLE_EXTREME_GROWTH_LOW_PE" not in item["flags"]:
            item["flags"].append("CYCLE_EXTREME_GROWTH_LOW_PE")

    queue = diversified_queue(candidates, limit=10, max_per_cluster=2)
    queue_tickers = {x["ticker"] for x in queue}
    for item in candidates:
        item["deep_research_selected"] = item["ticker"] in queue_tickers

    screen["candidates"] = candidates
    screen["deep_research_queue"] = queue
    screen.setdefault("rules", {})["deep_research_diversity"] = {
        "max_per_industry_cluster_first_pass": 2,
        "fill_remaining_by_screen_rank": True,
        "reason": "Prevent one cyclical/industry regime from consuming the whole Deep Research queue while preserving Top 50 raw discovery signals."
    }
    screen.setdefault("meta", {})["industry_enrichment"] = {
        "tpex_status": industry_status,
        "tpex_profile_rows": row_count,
        "tpex_mapped_candidates": mapped,
        "tpex_profile_keys_sample": profile_keys,
    }
    screen.setdefault("notes", []).append(
        "Deep Research Top 10 is diversity-aware; Top 50 remains raw ranking. Extreme revenue growth + low PE is flagged for normalized-cycle review rather than automatically rewarded as buyable alpha."
    )
    write("data/screen.json", screen)
    print(f"screen refined; tpex mapped={mapped}; deep={[x['ticker'] for x in queue]}")


if __name__ == "__main__":
    main()
