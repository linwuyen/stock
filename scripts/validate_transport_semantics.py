#!/usr/bin/env python3
import json

import run_market_scan as transport


def run_case(payloads, min_rows, expected_attempt):
    queue = list(payloads)
    original_request = transport.request_bytes
    original_sleep = transport.time.sleep

    def fake_request(url, accept, attempts=1):
        if not queue:
            raise AssertionError("test payload queue exhausted")
        value = queue.pop(0)
        if isinstance(value, Exception):
            raise value
        return value, 1, []

    transport.request_bytes = fake_request
    transport.time.sleep = lambda *_: None
    try:
        rows, attempt, errors = transport.fetch_rows_with_retry(
            "https://example.invalid/data",
            "application/json",
            transport.parse_json_rows,
            min_rows,
            attempts=5,
        )
        assert attempt == expected_attempt, (attempt, expected_attempt)
        assert len(rows) >= min_rows
        assert len(errors) == expected_attempt - 1
    finally:
        transport.request_bytes = original_request
        transport.time.sleep = original_sleep


# HTTP success with HTML/non-JSON must retry instead of immediately failing over.
run_case([
    b"<html>temporary upstream page</html>",
    json.dumps([{"ok": True}] * 500).encode(),
], 500, 2)

# Parsed but implausibly truncated data must also retry.
run_case([
    json.dumps([{"ok": True}] * 19).encode(),
    json.dumps([{"ok": True}] * 500).encode(),
], 500, 2)

# A plausible payload should pass first try.
run_case([json.dumps([{"ok": True}] * 500).encode()], 500, 1)

print("transport semantic retry PASS")
