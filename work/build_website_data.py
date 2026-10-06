#!/usr/bin/env python3
"""Bundle the survey CSVs into a browser-friendly JavaScript data file."""

import csv
import hashlib
import json
import re
from pathlib import Path

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

payload = {
    "meta": {
        "title": "DNA Replication Research Atlas",
        "asOf": "8 September 2026",
        "recentWindow": "2021–2026",
        "researcherCount": len(researchers),
        "rankedCount": sum(x["ranking_status"] == "ranked" for x in researchers),
        "edgeCount": len(edges),
    },
    "researchers": researchers,
    "edges": edges,
    "publicationUpdates": publication_updates["updates"],
    "publicationUpdateMeta": publication_updates["meta"],
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
    for asset in ("data.js", "app.js"):
        digest = hashlib.sha256((site / asset).read_bytes()).hexdigest()[:12]
        html, replacements = re.subn(
            rf'src="{re.escape(asset)}(?:\?[^"\s]*)?"',
            f'src="{asset}?v={digest}"',
            html,
        )
        if replacements != 1:
            raise RuntimeError(f"Expected exactly one script reference for {asset}")
    index_path.write_text(html, encoding="utf-8")
print(site / "data.js")
