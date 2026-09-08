#!/usr/bin/env python3
"""Build a recent-publication feed for the replication-researcher network.

OpenAlex author identifiers are used as the identity backbone. The resulting
feed deliberately preserves source/version metadata so preprints and accepted
manuscripts can be distinguished from version-of-record journal articles.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
CACHE = ROOT / "work" / "openalex_cache"
AS_OF = date.fromisoformat(os.environ["UPDATES_AS_OF"]) if os.environ.get("UPDATES_AS_OF") else date.today()
LOOKBACK_DAYS = int(os.environ.get("UPDATES_LOOKBACK_DAYS", "190"))
SINCE = AS_OF - timedelta(days=LOOKBACK_DAYS)
USER_AGENT = "DNAReplicationResearchAtlas/1.0 (academic field-mapping project)"
CACHE_ONLY = "--cache-only" in sys.argv

RELEVANCE = re.compile(
    r"replicat|replisom|replication fork|origin licensing|origin firing|"
    r"mcm\b|cmg\b|orc\b|dna polymerase|polymerase [αa-z0-9-]|pcna|rpa\b|"
    r"helicase|okazaki|fork protection|fork restart|fork reversal|"
    r"replication stress|replication timing|translesion|template switching|"
    r"dna damage tolerance|telomere replication|r-loop|transcription.replication|"
    r"topoisomerase|chromatin inheritance|histone recycling|sister chromatid|"
    r"fanconi|brca|homologous recombination|mismatch repair|genome instability",
    re.I,
)


def fetch_author_works(row: dict[str, str]) -> tuple[str, list[dict]]:
    aid = row["openalex_author_id"]
    cached = sorted(CACHE.glob(f"recent_works_{aid}*.json"))
    if CACHE_ONLY and cached:
        return row["person"], json.loads(cached[-1].read_text(encoding="utf-8")).get("results", [])
    fields = (
        "id,doi,ids,display_name,publication_year,publication_date,type,authorships,"
        "topics,primary_location,locations,open_access,cited_by_count,created_date,updated_date"
    )
    query = {
        "filter": (
            f"author.id:{aid},from_publication_date:{SINCE.isoformat()},"
            f"to_publication_date:{AS_OF.isoformat()}"
        ),
        "sort": "publication_date:desc",
        "per-page": "100",
        "select": fields,
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(query, safe=",:")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return row["person"], json.load(response).get("results", [])
        except Exception:
            if attempt == 3:
                if cached:
                    return row["person"], json.loads(cached[-1].read_text(encoding="utf-8")).get("results", [])
                raise
            time.sleep(1.5 * (attempt + 1))
    return row["person"], []


def topic_text(work: dict) -> str:
    return " ".join(topic.get("display_name", "") for topic in work.get("topics") or [])


def location_versions(work: dict) -> set[str]:
    return {loc.get("version") for loc in work.get("locations") or [] if loc.get("version")}


def status_label(work: dict) -> str:
    versions = location_versions(work)
    work_type = work.get("type") or ""
    primary = work.get("primary_location") or {}
    source_type = ((primary.get("source") or {}).get("type") or "").lower()
    if work_type == "preprint" or (
        "submittedVersion" in versions and "publishedVersion" not in versions
    ):
        return "Preprint"
    if "acceptedVersion" in versions and "publishedVersion" not in versions:
        return "Accepted manuscript"
    if work_type == "review":
        return "Review"
    if work_type == "article" and source_type == "journal":
        return "Journal article"
    return work_type.replace("-", " ").title() or "Publication"


def normalized_work(work: dict, roster_names: list[str]) -> dict[str, str | int | list[str]]:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    ids = work.get("ids") or {}
    versions = sorted(location_versions(work))
    authorships = work.get("authorships") or []
    senior = []
    corresponding = []
    for authorship in authorships:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if name in roster_names and authorship.get("author_position") == "last":
            senior.append(name)
        if name in roster_names and authorship.get("is_corresponding") is True:
            corresponding.append(name)
    doi = work.get("doi") or ids.get("doi") or ""
    pmid = ids.get("pmid") or ""
    url = doi or primary.get("landing_page_url") or work.get("id") or ""
    return {
        "publication_date": work.get("publication_date") or "",
        "title": work.get("display_name") or "Untitled",
        "status": status_label(work),
        "venue": source.get("display_name") or "Repository / venue not resolved",
        "venue_type": source.get("type") or "",
        "network_researchers": roster_names,
        "senior_or_last_network_researchers": sorted(set(senior)),
        "corresponding_network_researchers": sorted(set(corresponding)),
        "doi": doi,
        "pmid": pmid,
        "url": url,
        "openalex_id": work.get("id") or "",
        "open_access_status": ((work.get("open_access") or {}).get("oa_status") or ""),
        "indexed_versions": versions,
        "openalex_citations": work.get("cited_by_count") or 0,
        "created_date": work.get("created_date") or "",
        "updated_date": work.get("updated_date") or "",
        "source_note": "OpenAlex author-ID match; version/status inferred from OpenAlex work type and location versions",
    }


def title_key(title: str) -> str:
    """Conservative key for separate OpenAlex records of the same output."""
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def deduplicate_updates(updates: list[dict]) -> list[dict]:
    """Collapse exact-title duplicate records, retaining the strongest version."""
    strength = {
        "Journal article": 6,
        "Review": 5,
        "Accepted manuscript": 4,
        "Preprint": 3,
        "Dataset": 2,
        "Peer Review": 1,
    }
    groups: dict[str, list[dict]] = {}
    for row in updates:
        groups.setdefault(title_key(str(row["title"])), []).append(row)

    merged = []
    for rows in groups.values():
        rows.sort(key=lambda row: (
            strength.get(str(row["status"]), 0),
            str(row["publication_date"]),
            int(row["openalex_citations"]),
        ), reverse=True)
        chosen = rows[0]
        if len(rows) > 1:
            chosen = dict(chosen)
            for field in ("network_researchers", "senior_or_last_network_researchers", "corresponding_network_researchers"):
                chosen[field] = sorted({name for row in rows for name in row[field]})
            chosen["related_statuses"] = sorted({str(row["status"]) for row in rows})
            chosen["related_openalex_records"] = sorted({str(row["openalex_id"]) for row in rows})
            chosen["source_note"] += "; exact-title OpenAlex duplicates/version records collapsed, strongest current status retained"
        else:
            chosen["related_statuses"] = [str(chosen["status"])]
            chosen["related_openalex_records"] = [str(chosen["openalex_id"])]
        merged.append(chosen)
    return merged


def main() -> None:
    with (OUT / "dna_replication_researchers.csv").open(encoding="utf-8") as handle:
        researchers = list(csv.DictReader(handle))

    work_to_names: dict[str, set[str]] = {}
    works: dict[str, dict] = {}
    failures: list[str] = []
    # A modest worker count is friendlier to OpenAlex during unattended runs.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_author_works, row): row["person"] for row in researchers}
        for future in as_completed(futures):
            person = futures[future]
            try:
                _, items = future.result()
            except Exception:
                failures.append(person)
                continue
            for work in items:
                published = work.get("publication_date") or ""
                if not (SINCE.isoformat() <= published <= AS_OF.isoformat()):
                    continue
                key = work.get("id") or work.get("doi")
                if not key or not RELEVANCE.search((work.get("display_name") or "") + " " + topic_text(work)):
                    continue
                works[key] = work
                work_to_names.setdefault(key, set()).add(person)

    updates = [normalized_work(works[key], sorted(work_to_names[key])) for key in works]
    updates = deduplicate_updates(updates)
    updates.sort(key=lambda row: (row["publication_date"], row["updated_date"], row["title"]), reverse=True)

    payload = {
        "meta": {
            "generated_at": AS_OF.isoformat(),
            "window_start": SINCE.isoformat(),
            "window_end": AS_OF.isoformat(),
            "source": "OpenAlex API",
            "retrieval_mode": "cache-only" if CACHE_ONLY else "live API with cached-record fallback",
            "researcher_count": len(researchers),
            "publication_count": len(updates),
            "failed_researchers": failures,
            "status_method": "OpenAlex work type plus submittedVersion, acceptedVersion, and publishedVersion location metadata",
        },
        "updates": updates,
    }
    (OUT / "replication_publication_updates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fields = [
        "publication_date", "title", "status", "venue", "venue_type",
        "network_researchers", "senior_or_last_network_researchers",
        "corresponding_network_researchers", "doi", "pmid", "url", "openalex_id",
        "open_access_status", "indexed_versions", "related_statuses", "related_openalex_records", "openalex_citations", "created_date",
        "updated_date", "source_note",
    ]
    with (OUT / "replication_publication_updates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in updates:
            writer.writerow({
                key: "; ".join(str(item) for item in value) if isinstance(value, list) else value
                for key, value in row.items()
            })
    print(json.dumps(payload["meta"], indent=2))


if __name__ == "__main__":
    main()
