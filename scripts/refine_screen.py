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
UA = "linwuyen-alpha-engine/5.0 (+https://github.com/linwuyen/stock)"
TPEX_PROFILE_JSON = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_PROFILE_CSV = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv"
LANES = ("GROWTH", "INFLECTION", "MISPRICING_QUALITY")
INDUSTRY_ALIASES = ["產業別", "產業類別", "產業代碼", "產業別代碼", "Industry", "IndustryCode", "IndustryName", "SecuritiesIndustryCode", "SecuritiesIndustry", "SecuritiesIndustryName"]
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
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "identity", "Connection": "close"})
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except (http.client.IncompleteRead, OSError) as exc:
            last = exc
            if attempt < attempts: time.sleep(attempt * 1.5)
    raise last


def rows_json():
    payload = json.loads(fetch_bytes(TPEX_PROFILE_JSON, "application/json").decode("utf-8-sig"))
    return payload if isinstance(payload, list) else payload.get("data", [])


def rows_csv():
    text = fetch_bytes(TPEX_PROFILE_CSV, "text/csv,*/*").decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    header = next((i for i, line in enumerate(lines[:5]) if "公司代號" in line and "產業別" in line), 0)
    return list(csv.DictReader(io.StringIO("\n".join(lines[header:]))))


def mapping_from(rows):
    out = {}
    keys = sorted({k for row in rows[:25] if isinstance(row, dict) for k in row.keys() if k})
    for row in rows:
        code = str(pick(row, CODE_ALIASES) or "").strip()
        industry = str(pick(row, INDUSTRY_ALIASES) or "").strip()
        if code and industry: out[code] = industry
    return out, keys


def tpex_industries():
    errors = []
    for source, loader in (("TPEX_JSON", rows_json), ("MOPS_CSV_FALLBACK", rows_csv)):
        try:
            rows = loader()
            mapping, keys = mapping_from(rows)
            if mapping: return mapping, keys, len(rows), source
            errors.append(f"{source}:NO_INDUSTRY_VALUES")
        except Exception as exc:
            errors.append(f"{source}:{type(exc).__name__}:{exc}")
    raise RuntimeError(" | ".join(errors))


def cluster_key(item):
    industry = str(item.get("industry") or "").strip()
    return f"IND:{industry}" if industry else f"UNKNOWN:{item.get('market','?')}"


def diversified_queue(candidates, limit=10):
    selected, used, industry_counts, lane_counts = [], set(), {}, {}
    for lane in LANES:
        for item in candidates:
            if item.get("discovery_lane") != lane or item["ticker"] in used: continue
            cluster = cluster_key(item)
            if industry_counts.get(cluster, 0) >= 2: continue
            selected.append(dict(item)); used.add(item["ticker"])
            industry_counts[cluster] = industry_counts.get(cluster, 0) + 1
            lane_counts[lane] = lane_counts.get(lane, 0) + 1
            break
        if len(selected) >= limit: return selected
    for item in candidates:
        if item["ticker"] in used: continue
        lane, cluster = item.get("discovery_lane"), cluster_key(item)
        if industry_counts.get(cluster, 0) >= 2 or lane_counts.get(lane, 0) >= 4: continue
        selected.append(dict(item)); used.add(item["ticker"])
        industry_counts[cluster] = industry_counts.get(cluster, 0) + 1
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        if len(selected) >= limit: return selected
    for item in candidates:
        if item["ticker"] in used: continue
        selected.append(dict(item)); used.add(item["ticker"])
        if len(selected) >= limit: break
    return selected


def main():
    screen = load("data/screen.json")
    candidates = screen.get("candidates", [])
    mapping, profile_keys, row_count, source_used = {}, [], 0, None
    try:
        mapping, profile_keys, row_count, source_used = tpex_industries(); industry_status = "OK"
    except Exception as exc:
        industry_status = f"ERROR:{type(exc).__name__}:{exc}"
    mapped = 0
    for item in candidates:
        if item.get("market") == "TPEX" and not str(item.get("industry") or "").strip():
            industry = mapping.get(item["ticker"])
            if industry: item["industry"] = industry; mapped += 1
        item["research_industry_key"] = cluster_key(item)
        item["flags"] = list(dict.fromkeys(item.get("flags", [])))
    queue = diversified_queue(candidates, limit=10)
    queue_tickers = {x["ticker"] for x in queue}
    for item in candidates: item["deep_research_selected"] = item["ticker"] in queue_tickers
    screen["candidates"] = candidates
    screen["deep_research_queue"] = queue
    screen.setdefault("rules", {})["deep_research_diversity"] = {"lane_round_robin_first": list(LANES), "max_per_industry_cluster_first_pass": 2, "max_per_lane_before_final_fill": 4, "fill_remaining_by_screen_rank": True, "reason": "Research capacity is diversified across business regimes before ranking fill."}
    screen.setdefault("meta", {})["industry_enrichment"] = {"tpex_status": industry_status, "tpex_profile_rows": row_count, "tpex_mapped_candidates": mapped, "tpex_profile_keys_sample": profile_keys, "source_used": source_used, "source_priority": [TPEX_PROFILE_JSON, TPEX_PROFILE_CSV]}
    note = "Deep Research is lane- and industry-aware. Extreme growth raises verification priority; it never creates Buy authority."
    notes = screen.setdefault("notes", [])
    if note not in notes: notes.append(note)
    write("data/screen.json", screen)
    print("screen v5 refined:", [(x["ticker"], x.get("discovery_lane")) for x in queue])


if __name__ == "__main__":
    main()
