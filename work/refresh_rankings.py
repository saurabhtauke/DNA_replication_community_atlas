#!/usr/bin/env python3
"""Refresh the existing roster with fresh evidence, staging all outputs first."""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import build_replication_survey as survey

EXPORTS = (
    "dna_replication_researchers.csv", "author_resolution_audit.csv",
    "replication_network_nodes.csv", "replication_network_edges.csv",
    "replication_community_network.json", "replication_community_network.graphml",
)


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def already_refreshed(meta, now):
    return meta.get("last_successful_check_at", "").startswith(now.strftime("%Y-%m"))


def validate_exports(directory, previous):
    rows = read_rows(directory / EXPORTS[0])
    before = {r["person"]: r for r in previous}
    if len(rows) != len(before) or {r["person"] for r in rows} != set(before):
        raise ValueError("Roster changed or contains duplicate/missing people")
    expected = {r[0] for r in survey.ROSTER}
    if set(before) != expected:
        raise ValueError("Published roster and curated roster disagree; review required")
    for row in rows:
        old = before[row["person"]]
        for field in ("openalex_author_id", "ranking_status"):
            if row[field] != old[field]:
                raise ValueError(f"{field} changed for {row['person']}")
        if old.get("orcid") and row.get("orcid") != old["orcid"]:
            raise ValueError(f"ORCID changed for {row['person']}; review required")
        if int(old["lifetime_relevant_works"]) and not int(row["lifetime_relevant_works"]):
            raise ValueError(f"Lost all ranking evidence for {row['person']}")
    ranked = [r for r in rows if r["ranking_status"] == "ranked"]
    if [int(r["rank"]) for r in ranked] != list(range(1, len(ranked) + 1)):
        raise ValueError("Ranks are not contiguous")
    columns = ("lifetime_relevant_citations", "lifetime_relevant_works",
               "recent_relevant_citations", "recent_relevant_works", "recent_distinct_collaborators")
    scores = []
    for row in ranked:
        p = [survey.percentile([int(r[k]) for r in ranked], int(row[k])) for k in columns]
        life, recent = .75*p[0] + .25*p[1], .65*p[2] + .25*p[3] + .10*p[4]
        score = float(row["combined_impact_score_0_100"])
        if not math.isfinite(score) or score != round(.55*life + .45*recent, 1):
            raise ValueError("Score does not follow the published formula")
        scores.append(score)
    if scores != sorted(scores, reverse=True):
        raise ValueError("Ranks do not follow scores")
    for row in rows:
        if row["ranking_status"] != "ranked" and any(row[k] for k in (
            "rank", "combined_impact_score_0_100", "lifetime_impact_score_0_100", "impact_2021_2026_score_0_100"
        )):
            raise ValueError("Additional researchers must remain unranked")
    names = set(before)
    graph = json.loads((directory / EXPORTS[4]).read_text())
    node_rows = read_rows(directory / EXPORTS[2])
    edges = read_rows(directory / EXPORTS[3])
    xml = ET.parse(directory / EXPORTS[5])
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    for node_names in (
        [n["id"] for n in graph["nodes"]], [r["person"] for r in node_rows],
        [n.attrib["id"] for n in xml.findall(".//g:node", ns)],
        [r["person"] for r in read_rows(directory / EXPORTS[1])],
    ):
        if len(node_names) != len(names) or set(node_names) != names:
            raise ValueError("Network/audit roster mismatch")
    if len(edges) != len(graph["edges"]) or len(edges) != len(xml.findall(".//g:edge", ns)):
        raise ValueError("Network edge counts disagree")
    for edge in graph["edges"]:
        if not {edge["source"], edge["target"]} <= names or not edge["supporting_papers"]:
            raise ValueError("Invalid network evidence")
    return rows


def refresh(now=None):
    now = now or datetime.now(timezone.utc)
    as_of = now.date().isoformat()
    out = survey.ROOT / "outputs"
    previous = read_rows(out / EXPORTS[0])
    previous_meta = out / "ranking_refresh.json"
    old_meta = json.loads(previous_meta.read_text()) if previous_meta.exists() else {}
    # Pin every current identity; unattended name searches must never swap profiles.
    pins = {r["person"]: r["openalex_author_id"] for r in previous}
    if set(pins) != {r[0] for r in survey.ROSTER} or any(not v for v in pins.values()):
        raise ValueError("Current roster must have a reviewed OpenAlex ID for every person")
    with tempfile.TemporaryDirectory(prefix="ranking-refresh-") as tmp:
        stage = Path(tmp) / "outputs"
        cache = Path(tmp) / "fresh-api-cache"
        stage.mkdir()
        cache.mkdir()
        survey.OUT, survey.RAW = stage, cache
        survey.AS_OF, survey.FRESH_REFRESH = as_of, True
        survey.MANUAL_AUTHOR_IDS.update(pins)
        survey.main()
        rows = validate_exports(stage, previous)
        meta = {
            "last_successful_check_at": now.isoformat(), "publication_cutoff": as_of,
            "recent_start": survey.RECENT_START, "recent_end": as_of,
            "roster_updated_at": old_meta.get("roster_updated_at", "2026-10-21"),
            "researcher_count": len(rows),
            "ranked_count": sum(r["ranking_status"] == "ranked" for r in rows),
            "formula": "55% lifetime / 45% recent; unchanged within-roster percentiles",
            "sampling": "Up to 200 most-cited works per author per window before topic filtering; not exhaustive lifetime output or a field-wide ranking.",
            "snapshot_note": f"All {len(rows)} roster profiles refreshed from OpenAlex {as_of}; publication cutoff {as_of}. Recent window starts 1 January 2021. Curated affiliations, methods and verified trainee evidence retain their original review dates.",
        }
        graph = json.loads((stage / EXPORTS[4]).read_text())
        graph["metadata"].update({"citation_snapshot_note": meta["snapshot_note"],
                                  "last_successful_check_at": meta["last_successful_check_at"],
                                  "sampling": meta["sampling"]})
        (stage / EXPORTS[4]).write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")
        # Nothing reaches the tracked outputs until retrieval and validation finish.
        history = out / "ranking_history"
        history.mkdir(exist_ok=True)
        if not previous_meta.exists():
            (history / "baseline-before-monthly-refresh.csv").write_text((out / EXPORTS[0]).read_text(), encoding="utf-8")
        for name in EXPORTS:
            shutil.copyfile(stage / name, out / name)
        previous_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        shutil.copyfile(out / EXPORTS[0], history / f"{as_of}.csv")
        (history / f"{as_of}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(meta, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--due", action="store_true", help="Print true unless this UTC month already succeeded")
    args = parser.parse_args()
    if args.due:
        path = survey.ROOT / "outputs" / "ranking_refresh.json"
        meta = json.loads(path.read_text()) if path.exists() else {}
        print("false" if already_refreshed(meta, datetime.now(timezone.utc)) else "true")
    else:
        refresh()


if __name__ == "__main__":
    main()
