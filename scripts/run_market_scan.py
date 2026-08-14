#!/usr/bin/env python3
import csv
import http.client
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import scan_market

ROOT = Path(__file__).resolve().parents[1]
UA = "linwuyen-alpha-engine/4.7 (+https://github.com/linwuyen/stock)"

# Official MOPS CSV mirrors for datasets that are published by both market OpenAPI and MOPS open data.
CSV_FALLBACKS = {
    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L": "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv",
    "https://openapi.twse.com.tw/v1/opendata/t187ap05_L": "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv",
    "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci": "https://mopsfin.twse.com.tw/opendata/t187ap06_L_ci.csv",
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O": "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv",
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O": "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv",
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci": "https://mopsfin.twse.com.tw/opendata/t187ap06_O_ci.csv",
}
OPTIONAL_DATASETS = {
    "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci",
}
MIN_ROWS_BY_LABEL = {
    "profiles": 500,
    "quotes": 500,
    "valuation": 500,
    "revenue": 500,
    "income": 50,
}

telemetry = {}


def request_bytes(url, accept, attempts=5):
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": accept,
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
            return raw, attempt, errors
        except (urllib.error.HTTPError, urllib.error.URLError, http.client.IncompleteRead, OSError) as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(" | ".join(errors))


def parse_json_rows(raw):
    payload = json.loads(raw.decode("utf-8-sig"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "aaData", "result", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
        for value in payload.values():
            if isinstance(value, list):
                return value
    raise ValueError("unexpected JSON payload shape")


def parse_csv_rows(raw):
    text = raw.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header_index = 0
    for i, line in enumerate(lines[:6]):
        if "公司代號" in line or "公司代碼" in line:
            header_index = i
            break
    return list(csv.DictReader(io.StringIO("\n".join(lines[header_index:]))))


def dataset_label(url):
    for endpoints in scan_market.SOURCES.values():
        for label, endpoint in endpoints.items():
            if endpoint == url:
                return label
    return "unknown"


def minimum_rows(url):
    return MIN_ROWS_BY_LABEL.get(dataset_label(url), 1)


def fetch_rows_with_retry(url, accept, parser, min_rows, attempts=5):
    """Retry transport *and semantic* failures.

    A HTTP 200 response is not healthy unless it parses into the expected
    dataset shape and has a plausible row count. This catches transient HTML,
    empty responses and truncated official datasets.
    """
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            raw, _, transport_errors = request_bytes(url, accept, attempts=1)
            errors.extend(transport_errors)
            rows = parser(raw)
            if len(rows) < min_rows:
                raise ValueError(f"dataset row count {len(rows)} below semantic floor {min_rows}")
            return rows, attempt, errors
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(" | ".join(errors))


def resilient_fetch(url):
    min_rows = minimum_rows(url)
    record = telemetry.setdefault(url, {
        "primary_attempts": 0,
        "fallback_used": None,
        "errors": [],
        "optional_degraded": False,
        "semantic_min_rows": min_rows,
    })
    try:
        rows, attempts, errors = fetch_rows_with_retry(url, "application/json", parse_json_rows, min_rows)
        record["primary_attempts"] = attempts
        record["errors"].extend(errors)
        record["rows"] = len(rows)
        return rows
    except Exception as exc:
        record["primary_attempts"] = 5
        record["errors"].append(f"primary final: {type(exc).__name__}: {exc}")

    fallback = CSV_FALLBACKS.get(url)
    if fallback:
        try:
            rows, attempts, errors = fetch_rows_with_retry(fallback, "text/csv,*/*", parse_csv_rows, min_rows)
            record["fallback_attempts"] = attempts
            record["errors"].extend(errors)
            record["fallback_used"] = fallback
            record["rows"] = len(rows)
            return rows
        except Exception as exc:
            record["fallback_attempts"] = 5
            record["errors"].append(f"fallback final: {type(exc).__name__}: {exc}")

    if url in OPTIONAL_DATASETS:
        # Discovery can continue because a positive official TTM P/E is only a profitability proxy.
        # Deep Research / Buy Gate must still verify the actual filing.
        record["optional_degraded"] = True
        record["rows"] = 0
        return []
    raise RuntimeError(" ; ".join(record["errors"]))


def annotate_screen():
    path = ROOT / "data/screen.json"
    screen = json.loads(path.read_text(encoding="utf-8"))
    source_health = screen.setdefault("source_health", {})
    for market, endpoints in scan_market.SOURCES.items():
        for label, url in endpoints.items():
            rec = telemetry.get(url)
            if not rec:
                continue
            health = source_health.setdefault(market, {}).setdefault(label, {})
            health["transport"] = rec
            if rec.get("optional_degraded"):
                health["ok"] = False
                health["optional"] = True
                health["promotion_blocking"] = False
                health["error"] = "Official income endpoint unavailable after transport/parse/row-count retries and fallback; discovery continued with explicit earnings verification requirement."
            else:
                health["optional"] = label == "income"
                health["promotion_blocking"] = label != "income"
                if rec.get("fallback_used"):
                    health["fallback_used"] = rec["fallback_used"]
    screen.setdefault("meta", {})["transport_resilience"] = {
        "attempts_per_source": 5,
        "identity_encoding": True,
        "official_csv_fallbacks": True,
        "semantic_validation": ["JSON/CSV parse", "minimum plausible row count"],
        "minimum_rows_by_dataset": MIN_ROWS_BY_LABEL,
        "income_endpoint_optional_for_discovery_only": True,
        "fail_closed_for": ["profiles", "quotes", "valuation", "revenue"],
    }
    screen.setdefault("rules", {})["source_failure_policy"] = (
        "profiles/quotes/valuation/revenue fail closed after transport, parse and row-count retries plus official fallback; "
        "income may degrade discovery to TTM-PE profitability proxy but cannot satisfy Alpha earnings evidence."
    )
    path.write_text(json.dumps(screen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    scan_market.fetch = resilient_fetch
    scan_market.main()
    annotate_screen()
    print("resilient transport + semantic telemetry persisted")


if __name__ == "__main__":
    main()
