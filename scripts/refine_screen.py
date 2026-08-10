#!/usr/bin/env python3
import csv
import http.client
import io
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "linwuyen-alpha-engine/4.2 (+https://github.com/linwuyen/stock)"
TPEX_PROFILE_JSON = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_PROFILE_CSV = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv"

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


def fetch_bytes(url, accept, attempts=4):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": accept,
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except (http.client.IncompleteRead, OSError) as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 1.5)
    raise last


def fetch_json_rows():
    raw = fetch_bytes(TPEX_PROFILE_JSON, "application/json")
    payload = json.loads(raw.decode("utf-8-sig"))
    return payload if isinstance(payload, list) else payload.get("data", [])


def fetch_csv_rows():
    raw = fetch_bytes(TPEX_PROFILE_CSV, "text/csv,*/*")
    text = raw.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    # Some historical MOPS CSV variants prepend a title row. Detect the real header.
    header_index = next((i for i, line in enumerate(lines[:5]) if "公司代號" in line and "產業別" in line), 0)
    return list(csv.DictReader(io.StringIO("\n".join(lines[header_index:]))))


def build_mapping(rows):
    mapping = {}
    keys = sorted({k for row in rows[:25] if isinstance(row, dict) for k in row.keys() if k})
    for row in rows:
        code = str(pick(row, CODE_ALIASES) or "").strip()
        industry = str(pick(row, INDUSTRY_ALIASES) or "").strip()
        if code and industry:
            mapping[code] = industry
    return mapping, keys


def tpex_industries():
    errors = []
    try:
        rows = fetch_json_rows()
        mapping, keys = build_mapping(rows)
        if mapping:
            return mapping, keys, len(rows), "TPEX_JSON"
        errors.append("JSON:NO_INDUSTRY_VALUES")
    except Exception as exc:
        errors.append(f"JSON:{type(exc).__name__}:{exc}")

    try:
        rows = fetch_csv_rows()
        mapping, keys = build_mapping(rows)
        if mapping:
            return mapping, keys, len(rows), "MOPS_CSV_FALLBACK"
        errors.append("CSV:NO_INDUSTRY_VALUES")
    except Exception as exc:
        errors.append(f"CSV:{type(exc).__name__}:{exc}")

    raise RuntimeError(" | ".join(errors))


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
    for item in candidates:
        key = cluster_key(item)
        if counts.get(key, 0) >= max_per_cluster: continue
        selected.append(dict(item))
        counts[key] = counts.get(key, 0) + 1
        if len(selected) == limit: return selected
    chosen = {x["ticker"] for x in selected}
    for item in candidates:
        if item["ticker"] in chosen: continue
        selected.append(dict(item))
        if len(selected) == limit: break
    return selected


def main():
    screen = load("data/screen.json")
    candidates = screen.get("candidates", [])
    mapping, profile_keys, row_count, source_used = {}, [], 0, None
    try:
        mapping, profile_keys, row_count, source_used = tpex_industries()
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
        "source_used": source_used,
        "source_priority": [TPEX_PROFILE_JSON, TPEX_PROFILE_CSV],
        "retry_policy": "4 attempts per source, identity encoding, connection close"
    }
    notes = screen.setdefault("notes", [])
    note = "Deep Research Top 10 is diversity-aware; Top 50 remains raw ranking. Extreme revenue growth + low PE is flagged for normalized-cycle review rather than automatically rewarded as buyable alpha."
    if note not in notes: notes.append(note)
    write("data/screen.json", screen)
    print(f"screen refined; source={source_used}; tpex mapped={mapped}; deep={[x['ticker'] for x in queue]}")


if __name__ == "__main__":
    main()
