#!/usr/bin/env python3
"""Bundle the survey CSVs into a browser-friendly JavaScript data file."""

import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

from literature_tracker import validate_store, website_payload

root = Path(__file__).resolve().parents[1]
out = root / "outputs"
site = out / "website"
site.mkdir(parents=True, exist_ok=True)

with (out / "dna_replication_researchers.csv").open(encoding="utf-8") as f:
    researchers = list(csv.DictReader(f))
with (out / "replication_network_edges.csv").open(encoding="utf-8") as f:
    edges = list(csv.DictReader(f))

updates_path = out / "replication_publication_updates.json"
publication_updates = json.loads(updates_path.read_text(encoding="utf-8")) if updates_path.exists() else {"meta": {}, "updates": []}
tracker_path = out / "literature_tracker.json"
tracker = website_payload(validate_store(json.loads(tracker_path.read_text(encoding="utf-8")))) if tracker_path.exists() else {"meta": {}, "alerts": [], "publications": [], "latest_ids": [], "discovered_ids": [], "new_ids": [], "by_alert": {}}

numeric_fields = {
    "rank": int,
    "combined_impact_score_0_100": float,
    "lifetime_impact_score_0_100": float,
    "impact_2021_2026_score_0_100": float,
    "lifetime_relevant_works": int,
    "lifetime_relevant_citations": int,
    "recent_relevant_works": int,
    "recent_relevant_citations": int,
    "recent_distinct_collaborators": int,
}
for row in researchers:
    for key, convert in numeric_fields.items():
        row[key] = convert(row[key]) if row.get(key) else None
    row["techniques"] = [x.strip() for x in row["technique_expertise"].split(";") if x.strip()]
    row["subfields"] = [x.strip() for x in row["replication_expertise_subfield"].split(";") if x.strip()]
    for key in ("top_5_collaborators_2021_2026", "top_5_papers_all_time", "top_5_papers_2021_2026", "five_most_recent_lab_papers", "top_5_trainees_or_future_leaders"):
        row[key + "_list"] = [x.strip() for x in row[key].split(" || ") if x.strip()]
    row["technique_details_list"] = [x.strip() for x in row["technique_details"].split(";") if x.strip()]
    row["replication_expertise_details_list"] = [x.strip() for x in row["replication_expertise_details"].split(";") if x.strip()]

for edge in edges:
    edge["weight_recent_shared_papers"] = int(edge["weight_recent_shared_papers"])
    edge["shared_citation_sum"] = int(edge["shared_citation_sum"])
    edge["supporting_papers_list"] = [x.strip() for x in edge["supporting_papers"].split(" || ") if x.strip()]

ranking_path = out / "ranking_refresh.json"
ranking = json.loads(ranking_path.read_text()) if ranking_path.exists() else {}
def display_date(value):
    return date.fromisoformat(value).strftime("%d %B %Y").lstrip("0")

cutoff = display_date(ranking.get("publication_cutoff", "2026-09-08"))
recent_window = "2021–" + ranking.get("recent_end", "2026-09-08")[:4]
snapshot_note = ranking.get("snapshot_note", "Publication cutoff 8 September 2026. Gheorghe Chistol added with metadata/citations retrieved 21 October; other researchers retain September evidence. Percentile ranks recomputed across 101 eligible PIs.")
if ranking:
    checked = datetime.fromisoformat(ranking["last_successful_check_at"]).astimezone(timezone.utc)
    snapshot_note += " Last successful ranking check: " + checked.strftime("%d %B %Y at %H:%M UTC").lstrip("0") + ". " + ranking["sampling"]

payload = {
    "meta": {
        "title": "DNA Replication Research Atlas",
        "asOf": cutoff,
        "rosterUpdatedAt": display_date(ranking.get("roster_updated_at", "2026-10-21")),
        "rankingSnapshotNote": snapshot_note,
        "rankingLastSuccessfulCheckAt": ranking.get("last_successful_check_at"),
        "recentWindow": recent_window,
        "researcherCount": len(researchers),
        "rankedCount": sum(x["ranking_status"] == "ranked" for x in researchers),
        "edgeCount": len(edges),
    },
    "researchers": researchers,
    "edges": edges,
    "publicationUpdates": publication_updates["updates"],
    "publicationUpdateMeta": publication_updates["meta"],
    "literatureTracker": tracker,
}

(site / "data.js").write_text(
    "window.REPLICATION_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
# New HTML must request the matching bundle rather than a cached older feed.
# Content hashes are stable when data is unchanged and rotate on every refresh.
index_path = site / "index.html"
if index_path.exists():
    html = index_path.read_text(encoding="utf-8")
    for element_id, value in {
        "rankingDates": f"Global field map · publication cutoff {cutoff} · roster updated {payload['meta']['rosterUpdatedAt']}",
        "rankingSnapshotNote": snapshot_note,
        "directoryCounts": f"{payload['meta']['rankedCount']} ranked · {len(researchers) - payload['meta']['rankedCount']} requested additions",
        "networkWindow": f"Evidence-backed coauthorship · {recent_window}",
    }.items():
        html, count = re.subn(rf'(<p\b[^>]*\bid="{element_id}"[^>]*>).*?(</p>)',
                              lambda m: m[1] + escape(value) + m[2], html)
        if count != 1:
            raise RuntimeError(f"Expected one metadata element: {element_id}")
    for asset in ("data.js", "app.js", "literature.js", "styles.css"):
        attribute = "href" if asset.endswith(".css") else "src"
        digest = hashlib.sha256((site / asset).read_bytes()).hexdigest()[:12]
        html, replacements = re.subn(
            rf'{attribute}="{re.escape(asset)}(?:\?[^"\s]*)?"',
            f'{attribute}="{asset}?v={digest}"',
            html,
        )
        if replacements != 1:
            raise RuntimeError(f"Expected exactly one asset reference for {asset}")
    index_path.write_text(html, encoding="utf-8")
if ranking:
    readme_path = out / "README.md"
    readme = readme_path.read_text()
    readme = re.sub(r"^(?:Original data snapshot:|Ranking evidence refreshed:).*?$",
                    f"Ranking evidence refreshed: **{cutoff}**; roster extended **21 October 2026**", readme, flags=re.M)
    readme = re.sub(r"^Recent window:.*?$", f"Recent window: **1 January 2021–{cutoff}**", readme, flags=re.M)
    readme_path.write_text(readme)
print(site / "data.js")
