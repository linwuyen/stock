#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True, help="ticker or MARKET")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--payload", default="{}", help="JSON object string")
    parser.add_argument("--observed-at", default=None, help="ISO timestamp; defaults Asia/Taipei now")
    args = parser.parse_args()

    observed = datetime.fromisoformat(args.observed_at) if args.observed_at else datetime.now(TZ)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=TZ)
    payload = json.loads(args.payload)
    if not isinstance(payload, dict):
        raise SystemExit("--payload must be a JSON object")

    subject = SAFE.sub("_", args.subject).strip("_") or "MARKET"
    event_id = f"{observed.strftime('%Y-%m-%dT%H%M%S')}-{subject}-{SAFE.sub('_', args.kind)}"
    rel_path = f"data/events/{event_id}.json"
    path = ROOT / rel_path
    if path.exists():
        raise SystemExit(f"event already exists; refusing overwrite: {rel_path}")

    event = {
        "schema_version": 1,
        "id": event_id,
        "observed_at": observed.isoformat(timespec="seconds"),
        "subject": args.subject,
        "kind": args.kind,
        "summary": args.summary,
        "payload": payload,
    }
    write(rel_path, event)

    index = load("data/events/index.json")
    if any(x.get("id") == event_id or x.get("path") == rel_path for x in index.get("events", [])):
        raise SystemExit("duplicate event index entry")
    index.setdefault("events", []).append({
        "id": event_id,
        "observed_at": event["observed_at"],
        "subject": args.subject,
        "kind": args.kind,
        "path": rel_path,
    })
    index["events"].sort(key=lambda x: (x["observed_at"], x["id"]))
    write("data/events/index.json", index)
    print(rel_path)


if __name__ == "__main__":
    main()
