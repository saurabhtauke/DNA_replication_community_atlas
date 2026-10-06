#!/usr/bin/env python3
"""Credential-free public-literature retrieval, identity matching, and state merge."""
from __future__ import annotations

import argparse
import csv
import copy
import hashlib
import html
import json
import re
import time
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/literature_alerts.json"
OUTPUT = ROOT / "outputs/literature_tracker.json"
CACHE = ROOT / "work/literature_cache"
AGENT = "DNAReplicationCommunityAtlas/1.0 (+https://github.com/saurabhtauke/DNA_replication_community_atlas)"
PAPER_TYPES = {"article", "preprint", "review", "conference-paper", "editorial", "letter"}


def text(value):
    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or ""))).strip()


def normalized(value):
    value = unicodedata.normalize("NFKD", text(value).casefold())
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c))))


def doi_key(value):
    value = urllib.parse.unquote(str(value or "").strip()).lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else ""


def orcid_key(value):
    return str(value or "").rstrip("/").rsplit("/", 1)[-1].upper()


def valid_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return ""


def safe_url(value):
    value = str(value or "")
    return value if urllib.parse.urlsplit(value).scheme in {"https", "http"} else ""


def validate_config(config):
    if config.get("schema_version") != 1 or not isinstance(config.get("alerts"), list):
        raise ValueError("Expected schema_version=1 and an alerts array")
    if not 1 <= config.get("lookback_days", 190) <= 730:
        raise ValueError("lookback_days must be between 1 and 730")
    ids = set()
    for alert in config["alerts"]:
        aid = alert.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", aid) or aid in ids:
            raise ValueError(f"Invalid or duplicate alert ID: {aid}")
        ids.add(aid)
        if not alert.get("name") or not isinstance(alert.get("enabled"), bool):
            raise ValueError(f"Missing name/enabled: {aid}")
        if alert.get("type") not in {"author", "keyword"}:
            raise ValueError(f"Unsupported alert type: {aid}")
        if alert["enabled"] and alert["type"] == "author":
            author = alert.get("author", {})
            if author.get("identity_status") != "verified" or not author.get("verification_notes"):
                raise ValueError(f"Unverified author cannot be enabled: {aid}")
            if not author.get("openalex_ids") and not author.get("orcid"):
                raise ValueError(f"Author needs a persistent identifier: {aid}")
            if any(not re.fullmatch(r"A\d+", x) for x in author.get("openalex_ids", [])):
                raise ValueError(f"Invalid OpenAlex author ID: {aid}")
        if alert["enabled"] and alert["type"] == "keyword" and not alert.get("query", {}).get("all"):
            raise ValueError(f"Keyword alert needs query.all: {aid}")
        if not alert["enabled"] and not alert.get("disabled_reason"):
            raise ValueError(f"Disabled alert needs a reason: {aid}")
        sources = alert.get("sources", ["openalex", "europe_pmc", "biorxiv", "medrxiv"])
        if not sources or set(sources) - {"openalex", "europe_pmc", "biorxiv", "medrxiv"}:
            raise ValueError(f"Invalid alert sources: {aid}")
    return config


class PublicClient:
    def __init__(self, cache=CACHE, retries=3, timeout=35):
        self.cache, self.retries, self.timeout = Path(cache), retries, timeout
        self.cache.mkdir(parents=True, exist_ok=True)
        self.locks = defaultdict(threading.Lock)
        self.source_blocks = {}

    def get(self, source, path, params=None, ttl=0):
        key = json.dumps([source, path, params], sort_keys=True)
        with self.locks[key]:
            return self._get(source, path, params, ttl)

    def _get(self, source, path, params=None, ttl=0):
        bases = {"openalex": "https://api.openalex.org", "europe_pmc": "https://www.ebi.ac.uk/europepmc/webservices/rest", "crossref": "https://api.crossref.org", "biorxiv": "https://api.biorxiv.org", "medrxiv": "https://api.biorxiv.org"}
        url = bases[source] + "/" + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        cached = self.cache / (key + ".json")
        if cached.exists() and time.time() - cached.stat().st_mtime < ttl:
            return json.loads(cached.read_text())
        if source in self.source_blocks:
            raise RuntimeError(self.source_blocks[source])
        # Retrieval uses live responses (ttl=0). Only optional DOI enrichment
        # opts into long-lived caching; cached data never becomes a fresh check.
        for attempt in range(self.retries):
            try:
                if source in {"biorxiv", "medrxiv"}:
                    from vendor.biorxiv.rest_request import execute
                    raw = self.cache / (key + ".raw.json")
                    response = execute({"base_url": bases[source], "path": path, "params": params or {}, "headers": {"User-Agent": AGENT}, "timeout_sec": self.timeout, "save_raw": True, "raw_output_path": str(raw), "max_items": 10})
                    if not response.get("ok"):
                        raise RuntimeError(str(response.get("error")))
                    payload = json.loads(raw.read_text())
                else:
                    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=self.timeout) as handle:
                        payload = json.load(handle)
                if not isinstance(payload, dict):
                    raise ValueError(f"Unexpected {source} response")
                temp = cached.with_suffix(".tmp")
                temp.write_text(json.dumps(payload), encoding="utf-8")
                temp.replace(cached)
                return payload
            except urllib.error.HTTPError as error:
                if error.code == 429:
                    try:
                        message = error.read().decode("utf-8", errors="replace")
                    except Exception:
                        message = ""
                    if "insufficient budget" in message.lower() or "daily budget" in message.lower():
                        self.source_blocks[source] = "Anonymous public API daily quota exhausted; previous results retained. Retry after the provider's daily reset. No account/API key is required by this tracker."
                        raise RuntimeError(self.source_blocks[source]) from error
                if error.code not in {408, 429, 500, 502, 503, 504} or attempt == self.retries - 1:
                    raise
                try:
                    delay = min(30, max(1, float(error.headers.get("Retry-After", 2 ** attempt))))
                except (TypeError, ValueError):
                    delay = 2 ** attempt
                time.sleep(delay)
            except Exception:
                if attempt == self.retries - 1:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Request exhausted retries")


def quote_term(term):
    return '"' + normalized(term) + '"'


def query_for(alert, source, since, until):
    override = alert.get("source_queries", {}).get(source)
    if alert["type"] == "keyword":
        terms = alert["query"]["all"]
        if source == "openalex":
            return {"search": override or " AND ".join(quote_term(t) for t in terms), "filter": f"from_publication_date:{since},to_publication_date:{until}"}
        field = "TITLE" if alert["query"].get("title_only") else "TITLE_ABS"
        return {"query": f"({override or ' AND '.join(field + ':' + quote_term(t) for t in terms)}) AND (SRC:MED OR SRC:PMC OR SRC:PPR) AND FIRST_PDATE:[{since} TO {until}] sort_date:y"}
    author = alert["author"]
    if source == "openalex":
        ids = "|".join(author.get("openalex_ids", []))
        identity = f"authorships.author.id:{ids}" if ids else f"authorships.author.orcid:https://orcid.org/{orcid_key(author['orcid'])}"
        return {"filter": f"{identity},from_publication_date:{since},to_publication_date:{until}"}
    if author.get("orcid"):
        return {"query": f"AUTHORID:{orcid_key(author['orcid'])} AND (SRC:MED OR SRC:PMC OR SRC:PPR) AND FIRST_PDATE:[{since} TO {until}] sort_date:y"}
    return None  # Name-only querying is deliberately prohibited.


def paginate_openalex(client, params):
    cursor, seen, records = "*", set(), {}
    while cursor:
        if cursor in seen:
            raise RuntimeError("OpenAlex repeated cursor")
        seen.add(cursor)
        payload = client.get("openalex", "works", {**params, "per-page": 200, "cursor": cursor})
        if "results" not in payload or "count" not in payload.get("meta", {}):
            raise RuntimeError("Malformed OpenAlex page")
        for row in payload["results"]:
            records[row["id"]] = row
        expected = int(payload["meta"]["count"])
        if len(records) >= expected:
            break
        cursor = payload["meta"].get("next_cursor")
        if not cursor or not payload["results"]:
            raise RuntimeError(f"Incomplete OpenAlex pagination: {len(records)}/{expected}")
    return list(records.values())


def paginate_epmc(client, params):
    cursor, seen, records = "*", set(), {}
    while cursor:
        if cursor in seen:
            raise RuntimeError("Europe PMC repeated cursor")
        seen.add(cursor)
        payload = client.get("europe_pmc", "search", {**params, "format": "json", "resultType": "core", "pageSize": 1000, "cursorMark": cursor})
        if "hitCount" not in payload or "resultList" not in payload:
            raise RuntimeError("Malformed Europe PMC response")
        rows = payload["resultList"].get("result", [])
        for row in rows:
            records[(row["source"], row["id"])] = row
        expected = int(payload["hitCount"])
        if len(records) >= expected:
            break
        cursor = payload.get("nextCursorMark")
        if not cursor or not rows:
            raise RuntimeError(f"Incomplete Europe PMC pagination: {len(records)}/{expected}")
    return list(records.values())


def paginate_preprints(client, server, since, until):
    cursor, records, seen = 0, [], set()
    while True:
        payload = client.get(server, f"details/{server}/{since}/{until}/{cursor}/json")
        messages = payload.get("messages") or []
        if not messages:
            raise RuntimeError(f"Malformed {server} response")
        message = messages[0]
        status = str(message.get("status", "")).lower()
        if status not in {"ok", "no posts found"}:
            raise RuntimeError(f"{server}: {message}")
        rows = payload.get("collection", [])
        if status == "no posts found":
            return records
        total = int(message.get("total", 0))
        for row in rows:
            key = (row.get("doi"), str(row.get("version")))
            if key not in seen:
                seen.add(key)
                records.append(row)
        count = int(message.get("count", len(rows)))
        cursor += count
        if cursor and cursor % 300 == 0:
            print(f"{server} harvest {min(cursor, total)}/{total}", flush=True)
        if cursor >= total:
            return records
        if not rows or not count:
            raise RuntimeError(f"Incomplete {server} pagination")


def base_record(title, authors, published, venue, doi, url, source, source_id, status="Article", abstract=""):
    doi = doi_key(doi)
    return {"title": text(title), "authors": [text(a) for a in authors if a], "publication_date": valid_date(published), "venue": text(venue), "doi": doi, "abstract": text(abstract), "url": safe_url(url) or ("https://doi.org/" + doi if doi else ""), "preprint_url": "", "status": status, "sources": [source], "enrichment_sources": [], "source_records": [{"source": source, "id": str(source_id)}], "alert_ids": [], "author_ids": [], "author_orcids": [], "related_publication_dois": []}


def normalize_openalex(work):
    authorships = work.get("authorships") or []
    source = ((work.get("primary_location") or {}).get("source") or {})
    inverted = work.get("abstract_inverted_index") or {}
    words = sorted((position, word) for word, positions in inverted.items() for position in positions)
    kind = work.get("type") or "article"
    status = {"preprint": "Preprint", "review": "Review", "article": "Journal article"}.get(kind, kind.replace("-", " ").title())
    row = base_record(work.get("title") or work.get("display_name"), [(a.get("author") or {}).get("display_name") for a in authorships], work.get("publication_date"), source.get("display_name"), work.get("doi"), (work.get("primary_location") or {}).get("landing_page_url") or work.get("id"), "openalex", work.get("id"), status, " ".join(word for _, word in words))
    row["author_ids"] = [(a.get("author") or {}).get("id", "").rsplit("/", 1)[-1] for a in authorships]
    row["author_orcids"] = [orcid_key((a.get("author") or {}).get("orcid")) for a in authorships if (a.get("author") or {}).get("orcid")]
    if status == "Preprint":
        row["preprint_url"] = row["url"]
    return row


def normalize_epmc(work):
    authors = (work.get("authorList") or {}).get("author") or []
    journal = ((work.get("journalInfo") or {}).get("journal") or {}).get("title", "")
    preprint = work.get("source") == "PPR"
    types = {str(x).lower() for x in (work.get("pubTypeList") or {}).get("pubType", [])}
    status = "Preprint" if preprint else "Review" if "review" in types else "Editorial" if "editorial" in types else "Journal article"
    row = base_record(work.get("title"), [a.get("fullName") for a in authors] or str(work.get("authorString", "")).split(", "), work.get("firstPublicationDate"), journal or ("Preprint" if preprint else "Europe PMC"), work.get("doi"), "https://europepmc.org/article/" + work.get("source", "") + "/" + work.get("id", ""), "europe_pmc", work.get("source", "") + ":" + work.get("id", ""), status, work.get("abstractText"))
    row["author_orcids"] = [orcid_key(a["authorId"].get("value")) for a in authors if (a.get("authorId") or {}).get("type") == "ORCID"]
    if preprint:
        row["preprint_url"] = "https://doi.org/" + row["doi"] if row["doi"] else row["url"]
    for item in (work.get("commentCorrectionList") or {}).get("commentCorrection", []):
        if "published" in str(item.get("type", "")).lower() and doi_key(item.get("id")):
            row["related_publication_dois"].append(doi_key(item["id"]))
    return row


def normalize_preprint(work, server):
    authors = [name.strip() for name in str(work.get("authors", "")).split(";")]
    row = base_record(work.get("title"), authors, work.get("date"), server, work.get("doi"), "https://doi.org/" + doi_key(work.get("doi")), server, work.get("doi"), "Preprint", work.get("abstract"))
    row["preprint_url"] = row["url"]
    published = doi_key(work.get("published"))
    if published:
        row["related_publication_dois"] = [published]
    row["corresponding_author"] = text(work.get("author_corresponding"))
    row["corresponding_institution"] = text(work.get("author_corresponding_institution"))
    return row


def matches_keyword(alert, row):
    query = alert["query"]
    haystack = normalized(row["title"] + (" " + row.get("abstract", "") if not query.get("title_only") else ""))
    return all(" " + normalized(term) + " " in " " + haystack + " " for term in query["all"])


def verified_author_match(alert, row):
    author = alert["author"]
    if set(author.get("openalex_ids", [])) & set(row.get("author_ids", [])):
        return True
    if author.get("orcid") and orcid_key(author["orcid"]) in row.get("author_orcids", []):
        return True
    # bioRxiv names are not persistent identifiers. Only corroborated DOI hits
    # or corresponding-author + pinned institution evidence are accepted.
    aliases = {normalized(x) for x in author.get("aliases", []) + [author.get("name", "")]}
    institution = normalized(author.get("affiliation", ""))
    return bool(institution and normalized(row.get("corresponding_author")) in aliases and institution in normalized(row.get("corresponding_institution")))


def compatible_authors(a, b):
    if set(a.get("author_ids", [])) & set(b.get("author_ids", [])):
        return True
    if set(a.get("author_orcids", [])) & set(b.get("author_orcids", [])):
        return True
    def author_key(name):
        parts = normalized(name.replace(",", " ")).split()
        if not parts:
            return ""
        if "," in name:  # bioRxiv: family, given initials
            family, given = name.split(",", 1)
            return normalized(family) + ":" + normalized(given)[:1]
        if len(parts) > 1 and len(parts[-1]) <= 3:  # Europe PMC: Family AB
            return " ".join(parts[:-1]) + ":" + parts[-1][:1]
        return parts[-1] + ":" + parts[0][:1]
    return bool({author_key(x) for x in a.get("authors", []) if x} & {author_key(x) for x in b.get("authors", []) if x})


def record_identity(row):
    seed = row.get("doi") or normalized(row["title"]) + "|" + "|".join(sorted(normalized(a) for a in row.get("authors", []))) + "|" + json.dumps(row.get("source_records", []), sort_keys=True)
    return "paper-" + hashlib.sha256(seed.encode()).hexdigest()[:20]


def merge_records(previous, incoming, now):
    records = [copy.deepcopy(r) for r in previous]
    by_doi, by_title, by_source = {}, {}, {}
    def index(row):
        if row.get("doi"):
            by_doi[row["doi"]] = row
        group = by_title.setdefault(normalized(row["title"]), [])
        if not any(existing is row for existing in group):
            group.append(row)
        for source in row.get("source_records", []):
            by_source[(source["source"], source["id"])] = row
    def rebuild_index():
        by_doi.clear()
        by_title.clear()
        by_source.clear()
        for item in records:
            index(item)
    for row in records:
        index(row)
    new_ids, updated_ids, new_matches = set(), set(), []
    for candidate in incoming:
        row = copy.deepcopy(candidate)
        row["doi"] = doi_key(row.get("doi"))
        existing = by_doi.get(row["doi"]) if row["doi"] else None
        if existing is None:
            for source in row.get("source_records", []):
                match = by_source.get((source["source"], source["id"]))
                if match is not None and not (match.get("doi") and row["doi"] and match["doi"] != row["doi"]):
                    existing = match
                    break
        if existing is None:
            options = [p for p in by_title.get(normalized(row["title"]), []) if not (p.get("doi") and row["doi"] and p["doi"] != row["doi"]) and compatible_authors(p, row)]
            # Do not ambiguously attach a DOI-less title to either of two DOIs.
            if len(options) == 1:
                existing = options[0]
        if existing is None:
            row["id"] = record_identity(row)
            row["first_discovered_at"] = now
            row["last_seen_at"] = now
            records.append(row)
            index(row)
            new_ids.add(row["id"])
            continue
        before = json.dumps(existing, sort_keys=True)
        # A source ID can bridge an older DOI-less record and a later DOI
        # record. Consolidate only explicit source identities, never two DOIs.
        bridges = []
        for source in row.get("source_records", []):
            match = by_source.get((source["source"], source["id"]))
            if match is not None and match is not existing and not match.get("doi") and match not in bridges:
                bridges.append(match)
        for bridge in bridges:
            existing["first_discovered_at"] = min(existing["first_discovered_at"], bridge["first_discovered_at"])
            for field in ["alert_ids", "sources", "enrichment_sources", "author_ids", "author_orcids", "related_publication_dois"]:
                existing[field] = sorted(set(existing.get(field, [])) | set(bridge.get(field, [])))
            existing["source_records"] += bridge.get("source_records", [])
            records.remove(bridge)
            new_ids.discard(bridge["id"])
            updated_ids.discard(bridge["id"])
            new_matches = [m for m in new_matches if m["paper_id"] != bridge["id"]]
            rebuild_index()
        original_alerts = set(existing.get("alert_ids", []))
        for field in ["alert_ids", "sources", "enrichment_sources", "author_ids", "author_orcids", "related_publication_dois"]:
            existing[field] = sorted(set(existing.get(field, [])) | set(row.get(field, [])))
        for alert_id in set(existing["alert_ids"]) - original_alerts:
            new_matches.append({"paper_id": existing["id"], "alert_id": alert_id})
        sources = {(s["source"], s["id"]): s for s in existing.get("source_records", []) + row.get("source_records", [])}
        existing["source_records"] = [sources[key] for key in sorted(sources)]
        for field in ["doi", "abstract", "venue", "preprint_url", "authors"]:
            if row.get(field) and (not existing.get(field) or field == "abstract" and len(row[field]) > len(existing[field])):
                existing[field] = row[field]
        if existing.get("authors_complete") is False and row.get("authors") and row.get("authors_complete") is not False:
            existing["authors"] = row["authors"]
            existing["authors_complete"] = True
            existing.pop("source_note", None)
        if row.get("publication_date"):
            existing["publication_date"] = min(filter(None, [existing.get("publication_date"), row["publication_date"]]))
        if existing.get("doi"):
            existing["url"] = "https://doi.org/" + existing["doi"]
        if before != json.dumps(existing, sort_keys=True) and existing["id"] not in new_ids:
            updated_ids.add(existing["id"])
        existing["last_seen_at"] = now
        index(existing)
    return records, sorted(new_ids), sorted(updated_ids), new_matches


def publication_sort(row):
    return row.get("publication_date", ""), row.get("first_discovered_at", ""), row["id"]


def website_payload(store):
    rows = sorted(store.get("publications", []), key=publication_sort, reverse=True)
    by_alert = {alert["id"]: [r["id"] for r in rows if alert["id"] in r["alert_ids"]][:20] for alert in store.get("alerts", [])}
    latest = [r["id"] for r in rows[:100]]
    new_view = [r["id"] for r in sorted(rows, key=lambda r: (r["first_discovered_at"], r.get("publication_date", ""), r["id"]), reverse=True)[:100]]
    new_ids = set(store.get("meta", {}).get("new_publication_ids", []))
    new_latest = [r["id"] for r in sorted(rows, key=lambda r: (r["first_discovered_at"], r.get("publication_date", ""), r["id"]), reverse=True) if r["id"] in new_ids][:100]
    wanted = set(latest + new_view + new_latest + [rid for ids in by_alert.values() for rid in ids])
    alerts = [{**a, "publication_count": sum(a["id"] in r["alert_ids"] for r in rows)} for a in store.get("alerts", [])]
    return {"meta": store.get("meta", {}), "alerts": alerts, "publications": [r for r in rows if r["id"] in wanted], "latest_ids": latest, "discovered_ids": new_view, "new_ids": new_latest, "by_alert": by_alert}


def fetch_alert(client, alert, source, since, until, corroborated=None):
    params = query_for(alert, source, since, until)
    if params is None:
        dois = sorted(corroborated or [])
        results = []
        for start in range(0, len(dois), 20):
            query = " OR ".join("DOI:" + doi for doi in dois[start:start + 20])
            results += paginate_epmc(client, {"query": "(" + query + ")"})
    elif source == "openalex":
        results = paginate_openalex(client, params)
    else:
        results = paginate_epmc(client, params)
    rows = []
    for work in results:
        if source == "openalex" and work.get("type") not in PAPER_TYPES:
            continue
        row = normalize_openalex(work) if source == "openalex" else normalize_epmc(work)
        if not row["title"] or not row["url"] or not since <= row["publication_date"] <= until:
            continue
        if alert["type"] == "keyword":
            accepted = matches_keyword(alert, row)
        else:
            accepted = verified_author_match(alert, row) or row["doi"] in (corroborated or set())
        if accepted:
            row["alert_ids"] = [alert["id"]]
            rows.append(row)
    return rows


def atlas_seed(config, since, until):
    """Import known public records without claiming a fresh OpenAlex query."""
    snapshot_path = ROOT / "outputs/replication_publication_updates.json"
    roster_path = ROOT / "outputs/dna_replication_researchers.csv"
    if not snapshot_path.exists() or not roster_path.exists():
        return []
    snapshot = json.loads(snapshot_path.read_text())
    with roster_path.open(encoding="utf-8", newline="") as handle:
        roster = {r["person"]: r["openalex_author_id"] for r in csv.DictReader(handle)}
    rows = []
    for work in snapshot["updates"]:
        if not since <= work["publication_date"] <= until or work["status"] not in {"Journal article", "Review", "Preprint", "Accepted manuscript", "Article"}:
            continue
        row = base_record(work["title"], work["network_researchers"], work["publication_date"], work["venue"], work["doi"], work["url"], "openalex", work["openalex_id"], work["status"])
        row["author_ids"] = [roster[name] for name in work["network_researchers"] if name in roster]
        row["authors_complete"] = False
        row["source_note"] = "Imported from the existing validated public atlas snapshot; not a fresh OpenAlex search. Author list initially contains roster coauthors only."
        row["source_records"][0]["snapshot_last_checked"] = snapshot["meta"].get("last_successful_check_date")
        if row["status"] == "Preprint":
            row["preprint_url"] = row["url"]
        row["alert_ids"] = [a["id"] for a in config["alerts"] if a["enabled"] and (matches_keyword(a, row) if a["type"] == "keyword" else verified_author_match(a, row))]
        if row["alert_ids"]:
            rows.append(row)
    return rows


def build_store(config, previous, client, now):
    validate_config(config)
    until = now[:10]
    since = (date.fromisoformat(until) - timedelta(days=config.get("lookback_days", 190))).isoformat()
    enabled = [a for a in config["alerts"] if a["enabled"]]
    incoming, health, checkpoints = atlas_seed(config, since, until), {}, copy.deepcopy(previous.get("checkpoints", {}))
    known = {a["id"]: {r["doi"] for r in previous.get("publications", []) if r.get("doi") and a["id"] in r["alert_ids"]} for a in enabled}
    for row in incoming:
        if row["doi"]:
            for alert_id in row["alert_ids"]:
                known[alert_id].add(row["doi"])
    for source in ["openalex", "europe_pmc"]:
        tasks = [a for a in enabled if source in a.get("sources", ["openalex", "europe_pmc", "biorxiv", "medrxiv"])]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_alert, client, a, source, since, until, known[a["id"]]): a for a in tasks}
            for future in as_completed(futures):
                alert = futures[future]
                key = source + ":" + alert["id"]
                try:
                    rows = future.result()
                    incoming += rows
                    known[alert["id"]].update(r["doi"] for r in rows if r["doi"])
                    checkpoints[key] = now
                    health[key] = {"source": source, "alert_id": alert["id"], "status": "ok", "record_count": len(rows), "checked_at": now}
                    if source == "europe_pmc" and alert["type"] == "author" and not alert["author"].get("orcid"):
                        health[key]["scope_note"] = "Only DOI hits corroborated by a verified author source; no name-only author search."
                except Exception as error:
                    health[key] = {"source": source, "alert_id": alert["id"], "status": "failed", "error": str(error)[:300], "checked_at": now, "last_successful_check_at": checkpoints.get(key)}
                print(key, health[key]["status"], health[key].get("record_count", health[key].get("error", "")), flush=True)
    for server in ["biorxiv", "medrxiv"]:
        checkpoint = checkpoints.get(server)
        start = (date.fromisoformat(checkpoint[:10]) - timedelta(days=7)).isoformat() if checkpoint else (date.fromisoformat(until) - timedelta(days=30)).isoformat()
        start = max(start, since)
        try:
            raw = paginate_preprints(client, server, start, until)
            rows = []
            for work in raw:
                row = normalize_preprint(work, server)
                if not since <= row["publication_date"] <= until:
                    continue
                row["alert_ids"] = [a["id"] for a in enabled if server in a.get("sources", ["openalex", "europe_pmc", "biorxiv", "medrxiv"]) and (matches_keyword(a, row) if a["type"] == "keyword" else verified_author_match(a, row) or row["doi"] in known[a["id"]])]
                if row["alert_ids"]:
                    rows.append(row)
            incoming += rows
            checkpoints[server] = now
            health[server] = {"source": server, "status": "ok", "record_count": len(rows), "harvested_count": len(raw), "window_start": start, "checked_at": now}
        except Exception as error:
            health[server] = {"source": server, "status": "failed", "error": str(error)[:300], "checked_at": now, "last_successful_check_at": checkpoint}
        print(server, health[server]["status"], health[server].get("record_count", health[server].get("error", "")), flush=True)
    rows, new_ids, updated_ids, new_matches = merge_records(previous.get("publications", []), incoming, now)
    # Retain a compact discovery ledger even when papers leave the display window.
    ledger = copy.deepcopy(previous.get("discovery_registry", {}))
    for row in rows:
        keys = ["id:" + row["id"]] + (["doi:" + row["doi"]] if row["doi"] else []) + ["source:" + s["source"] + ":" + s["id"] for s in row["source_records"]]
        found = [ledger[k] for k in keys if k in ledger]
        if found:
            row["first_discovered_at"] = min(found + [row["first_discovered_at"]])
            if row["id"] in new_ids:
                new_ids.remove(row["id"])
        for key in keys:
            ledger[key] = row["first_discovered_at"]
    # Crossref enrichment is optional and cannot block actual literature retrieval.
    enrich_errors, enriched = [], 0
    candidates = [r for r in rows if r.get("doi") and "crossref" not in r["enrichment_sources"]]
    for row in sorted(candidates, key=publication_sort, reverse=True)[:100]:
        try:
            metadata = client.get("crossref", "works/" + urllib.parse.quote(row["doi"], safe=""), ttl=90 * 86400)["message"]
            if not row["abstract"]:
                row["abstract"] = text(metadata.get("abstract"))
            if not row["venue"]:
                row["venue"] = text((metadata.get("container-title") or [""])[0])
            for relation in (metadata.get("relation") or {}).get("is-preprint-of", []):
                if doi_key(relation.get("id")):
                    row["related_publication_dois"] = sorted(set(row["related_publication_dois"] + [doi_key(relation["id"])]))
            row["enrichment_sources"] = sorted(set(row["enrichment_sources"] + ["crossref"]))
            enriched += 1
        except Exception as error:
            enrich_errors.append({"doi": row["doi"], "error": str(error)[:180]})
    health["crossref"] = {"source": "crossref", "status": "partial" if enrich_errors else "ok", "role": "optional enrichment", "record_count": enriched, "errors": enrich_errors, "checked_at": now}
    required = [h for k, h in health.items() if k != "crossref"]
    failures = [h for h in required if h["status"] != "ok"]
    complete = not failures
    status = "ok" if complete else "partial" if any(h["status"] == "ok" for h in required) else "failed"
    baseline = not bool(previous.get("meta", {}).get("last_attempt_at"))
    rows = [r for r in rows if since <= r.get("publication_date", "") <= until]
    active_ids = {a["id"] for a in config["alerts"] if a["enabled"]}
    for row in rows:
        row["alert_ids"] = sorted(set(row["alert_ids"]) & active_ids)
    rows = [r for r in rows if r["alert_ids"]]
    # Compare final metadata, including enrichment, rather than intermediate
    # source merges. Observation time alone is not a metadata update.
    prior_by_id = {r["id"]: r for r in previous.get("publications", [])}
    def comparable(row):
        return {k: v for k, v in row.items() if k != "last_seen_at"}
    updated_ids = sorted(r["id"] for r in rows if r["id"] in prior_by_id and comparable(r) != comparable(prior_by_id[r["id"]]))
    return {"schema_version": 1, "meta": {"last_attempt_at": now, "last_successful_check_at": now if complete else previous.get("meta", {}).get("last_successful_check_at"), "refresh_status": status, "window_start": since, "window_end": until, "publication_count": len(rows), "enabled_alert_count": len(enabled), "disabled_alert_count": len(config["alerts"]) - len(enabled), "initial_baseline": baseline, "new_publication_ids": [] if baseline else new_ids, "metadata_updated_ids": updated_ids, "new_alert_matches": [] if baseline else new_matches, "source_health": health, "schedule": "Daily at 06:00 UTC; GitHub Actions may start later", "coverage_note": "Public databases, not Google Scholar. 190-day default; direct preprint bootstrap 30 days, then seven-day overlap. Identity-unresolved alerts are disabled. Abstracts and author coverage vary by source."}, "alerts": config["alerts"], "checkpoints": checkpoints, "discovery_registry": ledger, "publications": sorted(rows, key=publication_sort, reverse=True)}


def validate_store(store):
    if store.get("schema_version") != 1 or store["meta"]["publication_count"] != len(store["publications"]):
        raise ValueError("Invalid tracker schema/count")
    validate_config({"schema_version": 1, "alerts": store["alerts"]})
    ids, dois = set(), set()
    alerts = {a["id"] for a in store["alerts"]}
    for row in store["publications"]:
        if row["id"] in ids or not row["title"] or not safe_url(row["url"]) or not valid_date(row["publication_date"]):
            raise ValueError("Invalid/duplicate publication")
        ids.add(row["id"])
        if row["doi"] and (row["doi"] in dois or row["doi"] != doi_key(row["doi"])):
            raise ValueError("Duplicate/noncanonical DOI")
        if row["doi"]:
            dois.add(row["doi"])
        if not row["alert_ids"] or set(row["alert_ids"]) - alerts:
            raise ValueError("Invalid alert membership")
        if not row["first_discovered_at"] or not row["sources"] or not row["source_records"]:
            raise ValueError("Missing discovery/provenance")
        if set(row["sources"]) - {"openalex", "europe_pmc", "biorxiv", "medrxiv"}:
            raise ValueError("Invalid retrieval source")
    return store


def smoke(client):
    doi = "10.64898/2026.09.20.752975"
    negative = "10.64898/2026.09.23.753725"
    failures = []
    for source in ["openalex", "europe_pmc", "biorxiv", "medrxiv", "crossref"]:
        try:
            if source == "openalex":
                assert doi_key(client.get(source, "works/https://doi.org/" + doi)["doi"]) == doi
            elif source == "europe_pmc":
                for target in [doi, negative]:
                    assert any(doi_key(r.get("doi")) == target for r in paginate_epmc(client, {"query": "DOI:" + target}))
            elif source == "biorxiv":
                for target in [doi, negative]:
                    direct = client.get(source, f"details/biorxiv/{target}/na/json")
                    assert any(doi_key(r.get("doi")) == target for r in direct.get("collection", []))
            elif source == "medrxiv":
                end = datetime.now(timezone.utc).date()
                start = end - timedelta(days=1)
                payload = client.get(source, f"details/medrxiv/{start}/{end}/0/json")
                assert payload.get("messages") and payload["messages"][0].get("status") in {"ok", "no posts found"}
            else:
                assert doi_key(client.get(source, "works/" + urllib.parse.quote(doi, safe=""))["message"]["DOI"]) == doi
            print(source + ": unauthenticated live smoke passed", flush=True)
        except Exception as error:
            failures.append(source)
            print(source + ": live smoke failed: " + str(error), flush=True)
    if failures:
        raise RuntimeError("Smoke tests incomplete: " + ", ".join(failures))
    print("All five sources passed; both Rueda preprints retrieved directly and through Europe PMC.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--as-of")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        store = validate_store(json.loads(args.output.read_text()))
        print(f"Validated {len(store['publications'])} literature publications")
        return
    client = PublicClient()
    if args.smoke:
        smoke(client)
        return
    config = validate_config(json.loads(args.config.read_text()))
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if args.as_of:
        now = date.fromisoformat(args.as_of).isoformat() + "T06:00:00Z"
    store = validate_store(build_store(config, previous, client, now))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    temp.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({k: v for k, v in store["meta"].items() if k != "source_health"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
