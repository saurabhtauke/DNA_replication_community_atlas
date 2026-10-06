#!/usr/bin/env python3
"""Validate the generated recent-publication feed before it is published."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from build_updates_feed import update_key


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
JSON_PATH = OUT / "replication_publication_updates.json"
CSV_PATH = OUT / "replication_publication_updates.csv"
REQUIRED = ("publication_date", "title", "status", "url", "openalex_id")


def main() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    meta = payload.get("meta")
    updates = payload.get("updates")
    if not isinstance(meta, dict) or not isinstance(updates, list):
        raise SystemExit("Publication JSON must contain object fields 'meta' and 'updates'.")

    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    problems: list[str] = []
    if meta.get("publication_count") != len(updates):
        problems.append("metadata publication_count does not match JSON rows")
    if len(csv_rows) != len(updates):
        problems.append("CSV record count does not match JSON rows")
    if meta.get("failed_researchers"):
        problems.append("one or more roster researchers failed to refresh")
    for index, row in enumerate(updates, start=1):
        missing = [field for field in REQUIRED if not row.get(field)]
        if missing:
            problems.append(f"row {index} is missing {', '.join(missing)}")
    keys = [update_key(row) for row in updates if all(row.get(field) for field in REQUIRED)]
    if len(keys) != len(set(keys)):
        problems.append("duplicate paper titles or non-paper identifiers remain after deduplication")
    record_ids = [record_id for row in updates for record_id in row.get("related_openalex_records", [row.get("openalex_id")])]
    if len(record_ids) != len(set(record_ids)):
        problems.append("an OpenAlex record appears in multiple updates")

    if problems:
        print("Publication-update validation failed:", file=sys.stderr)
        print("\n".join(f"- {problem}" for problem in problems), file=sys.stderr)
        raise SystemExit(1)
    print(
        f"Validated {len(updates)} publication updates "
        f"({sum(row.get('status') == 'Preprint' for row in updates)} preprints)."
    )


if __name__ == "__main__":
    main()
