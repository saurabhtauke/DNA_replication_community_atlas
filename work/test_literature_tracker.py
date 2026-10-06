import copy
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import literature_tracker as t

NOW = "2026-10-06T06:00:00Z"
ALERT = {"id": "dna", "name": "DNA replication", "type": "keyword", "enabled": True, "query": {"all": ["DNA replication"], "title_only": False}}
AUTHOR = {"id": "rueda", "name": "David Rueda", "type": "author", "enabled": True, "author": {"name": "David Rueda", "aliases": ["David S. Rueda"], "openalex_ids": ["A1"], "orcid": "0000-0003-4657-6323", "affiliation": "Imperial College London", "identity_status": "verified", "verification_notes": "Known paper and ORCID"}}


def row(doi="10.1234/a", title="DNA replication", authors=None, source="openalex", sid="W1", alert_ids=None):
    r = t.base_record(title, authors or ["David S. Rueda"], "2026-09-24", "Nature", doi, "https://example.org/paper", source, sid)
    r["alert_ids"] = alert_ids or ["dna"]
    return r


class Client:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, source, path, params=None, ttl=3600):
        self.calls.append((source, path, params))
        return next(self.pages)


class TrackerTests(unittest.TestCase):
    def test_configuration_and_identity_guard(self):
        t.validate_config({"schema_version": 1, "alerts": [ALERT, AUTHOR]})
        invalid = copy.deepcopy(AUTHOR)
        invalid["author"]["identity_status"] = "needs identity review"
        with self.assertRaises(ValueError):
            t.validate_config({"schema_version": 1, "alerts": [invalid]})
        with self.assertRaises(ValueError):
            t.validate_config({"schema_version": 1, "alerts": [ALERT, ALERT]})

    def test_query_translation_and_title_only(self):
        alert = {**ALERT, "query": {"all": ["magnetic_tweezers", "single-molecule"], "title_only": True}}
        self.assertEqual(t.query_for(alert, "openalex", "2026-01-01", "2026-10-06")["search"], '"magnetic tweezers" AND "single molecule"')
        self.assertIn('TITLE:"magnetic tweezers"', t.query_for(alert, "europe_pmc", "2026-01-01", "2026-10-06")["query"])
        donson = {**ALERT, "query": {"all": ["DONSON"], "title_only": True}}
        self.assertFalse(t.matches_keyword(donson, {"title": "Replication", "abstract": "DONSON"}))
        self.assertTrue(t.matches_keyword(donson, {"title": "DONSON initiates replication"}))

    def test_author_name_alone_does_not_match(self):
        r = row()
        self.assertFalse(t.verified_author_match(AUTHOR, r))
        r["author_ids"] = ["A1"]
        self.assertTrue(t.verified_author_match(AUTHOR, r))
        r["author_ids"] = []
        r["corresponding_author"] = "David S. Rueda"
        r["corresponding_institution"] = "Imperial College London, UK"
        self.assertTrue(t.verified_author_match(AUTHOR, r))
        r["corresponding_institution"] = "Other institution"
        self.assertFalse(t.verified_author_match(AUTHOR, r))

    def test_openalex_pagination_and_incomplete_page(self):
        c = Client([{"results": [{"id": "W1"}], "meta": {"count": 2, "next_cursor": "two"}}, {"results": [{"id": "W2"}], "meta": {"count": 2}}])
        self.assertEqual(len(t.paginate_openalex(c, {})), 2)
        self.assertEqual(c.calls[1][2]["cursor"], "two")
        with self.assertRaises(RuntimeError):
            t.paginate_openalex(Client([{"results": [], "meta": {"count": 2}}]), {})
        with self.assertRaises(RuntimeError):
            t.paginate_openalex(Client([{"results": [{"id": "W1"}], "meta": {"count": 2, "next_cursor": "*"}}]), {})

    def test_epmc_and_preprint_pagination(self):
        c = Client([{"hitCount": 2, "resultList": {"result": [{"source": "MED", "id": "1"}]}, "nextCursorMark": "two"}, {"hitCount": 2, "resultList": {"result": [{"source": "PPR", "id": "2"}]}}])
        self.assertEqual(len(t.paginate_epmc(c, {})), 2)
        pages = [{"messages": [{"status": "ok", "count": 1, "total": 2}], "collection": [{"doi": "10.1234/a", "version": "1"}]}, {"messages": [{"status": "ok", "count": 1, "total": 2}], "collection": [{"doi": "10.1234/a", "version": "2"}]}]
        c = Client(pages)
        self.assertEqual(len(t.paginate_preprints(c, "biorxiv", "2026-01-01", "2026-10-06")), 2)
        self.assertIn("/1/json", c.calls[1][1])
        with self.assertRaises(RuntimeError):
            t.paginate_preprints(Client([{"messages": [{"status": "ok", "count": 0, "total": 2}], "collection": []}]), "biorxiv", "2026-01-01", "2026-10-06")

    def test_retry_and_no_expired_cache_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            c = t.PublicClient(folder, retries=2)
            error = urllib.error.HTTPError("https://api.openalex.org/works", 429, "rate limited", {"Retry-After": "0"}, None)
            with patch.object(t.urllib.request, "urlopen", side_effect=[error, OSError("offline")]), patch.object(t.time, "sleep") as sleep:
                with self.assertRaises(OSError):
                    c.get("openalex", "works")
                sleep.assert_called_once_with(1)
            self.assertFalse(list(Path(folder).glob("*.json")))

    def test_doi_dedup_and_alert_provenance_union(self):
        a = row(doi="HTTPS://DOI.ORG/10.1234/A")
        b = row(doi="doi:10.1234/a", source="europe_pmc", sid="MED:1", alert_ids=["rueda"])
        records, new, _, _ = t.merge_records([], [a, b], NOW)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["doi"], "10.1234/a")
        self.assertEqual(records[0]["alert_ids"], ["dna", "rueda"])
        self.assertEqual(records[0]["sources"], ["europe_pmc", "openalex"])
        self.assertEqual(len(new), 1)

    def test_doi_gain_preserves_id_and_first_seen(self):
        records, _, _, _ = t.merge_records([], [row(doi="")], NOW)
        original = records[0]
        update = row(authors=["Rueda DS"], source="europe_pmc", sid="MED:1")
        after, new, _, _ = t.merge_records(records, [update], "2026-10-07T06:00:00Z")
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["id"], original["id"])
        self.assertEqual(after[0]["first_discovered_at"], NOW)
        self.assertEqual(new, [])

    def test_conflicting_dois_and_names_stay_separate(self):
        rows = [row(), row(doi="10.1234/b", sid="W2"), row(doi="", authors=["Other Person"], sid="W3")]
        records, _, _, _ = t.merge_records([], rows, NOW)
        self.assertEqual(len(records), 3)

    def test_metadata_and_new_matches_not_new_publication(self):
        records, _, _, _ = t.merge_records([], [row()], NOW)
        update = row(alert_ids=["rueda"])
        update["abstract"] = "New abstract"
        records, new, changed, matches = t.merge_records(records, [update], "2026-10-07T06:00:00Z")
        self.assertEqual(new, [])
        self.assertEqual(changed, [records[0]["id"]])
        self.assertEqual(matches, [{"paper_id": records[0]["id"], "alert_id": "rueda"}])
        again, new, changed, matches = t.merge_records(records, [update], "2026-10-08T06:00:00Z")
        self.assertEqual(new + changed + matches, [])

    def test_explicit_preprint_link_and_abstract_sanitization(self):
        paper = t.normalize_preprint({"title": "<b>INO80</b>", "authors": "Rueda, D. S.; Smith, A.", "date": "2026-09-22", "doi": "10.1234/preprint", "published": "10.1234/article", "abstract": "<jats:p>Useful &amp; public</jats:p>"}, "biorxiv")
        self.assertEqual(paper["related_publication_dois"], ["10.1234/article"])
        self.assertEqual(paper["abstract"], "Useful & public")
        self.assertTrue(paper["preprint_url"])
        self.assertEqual(t.safe_url("javascript:alert(1)"), "")

    def test_independent_alert_twenty_outside_global_hundred(self):
        rows = []
        for n in range(150):
            paper = row(doi=f"10.1234/{n}", alert_ids=["dna"] if n < 130 else ["rare"])
            paper.update(id=str(n), first_discovered_at=NOW, publication_date="2026-09-24" if n < 130 else "2026-04-01")
            rows.append(paper)
        bundle = t.website_payload({"publications": rows, "alerts": [ALERT, {**ALERT, "id": "rare"}]})
        self.assertEqual(len(bundle["latest_ids"]), 100)
        self.assertEqual(len(bundle["by_alert"]["rare"]), 20)
        self.assertFalse(set(bundle["latest_ids"]) & set(bundle["by_alert"]["rare"]))
        self.assertTrue(set(bundle["by_alert"]["rare"]) <= {r["id"] for r in bundle["publications"]})

    def test_partial_failure_preserves_records_and_checkpoint(self):
        prior_rows, _, _, _ = t.merge_records([], [row()], NOW)
        previous = {"meta": {"last_attempt_at": NOW, "last_successful_check_at": NOW}, "publications": prior_rows, "checkpoints": {"openalex:dna": NOW}}
        class FailedOpenAlex:
            def get(self, source, path, params=None, ttl=3600):
                if source == "openalex":
                    raise RuntimeError("offline")
                if source == "europe_pmc":
                    return {"hitCount": 0, "resultList": {"result": []}}
                if source in {"biorxiv", "medrxiv"}:
                    return {"messages": [{"status": "no posts found"}], "collection": []}
                return {"message": {}}
        with patch.object(t, "atlas_seed", return_value=[]):
            store = t.build_store({"schema_version": 1, "alerts": [ALERT]}, previous, FailedOpenAlex(), "2026-10-07T06:00:00Z")
        self.assertEqual(store["meta"]["refresh_status"], "partial")
        self.assertEqual(store["meta"]["last_successful_check_at"], NOW)
        self.assertEqual(store["checkpoints"]["openalex:dna"], NOW)
        self.assertEqual(store["publications"][0]["first_discovered_at"], NOW)
        t.validate_store(store)

    def test_snapshot_seed_is_not_a_live_check_and_authors_upgrade(self):
        seed = row()
        seed["authors_complete"] = False
        seed["source_note"] = "Imported snapshot; not a fresh search"
        records, _, _, _ = t.merge_records([], [seed], NOW)
        full = row(authors=["First Author", "David S. Rueda"])
        records, _, _, _ = t.merge_records(records, [full], NOW)
        self.assertEqual(records[0]["authors"], full["authors"])
        self.assertTrue(records[0]["authors_complete"])
        self.assertNotIn("source_note", records[0])

    def test_missing_metadata_is_safe(self):
        for normalize, work in [(t.normalize_openalex, {"id": "W1"}), (t.normalize_epmc, {"id": "1", "source": "MED"})]:
            paper = normalize(work)
            self.assertEqual(paper["authors"], [])
            self.assertEqual(paper["abstract"], "")

    def test_openalex_null_coauthor_ids_are_not_an_identity(self):
        paper = t.normalize_openalex({"id": "W1", "title": "Known paper", "authorships": [{"author": {"id": None, "display_name": "Other Person"}}, {"author": {"id": "https://openalex.org/A1", "display_name": "David Rueda"}}, {"author": None}]})
        self.assertEqual(paper["author_ids"], ["A1"])
        self.assertTrue(t.verified_author_match(AUTHOR, paper))
        no_ids = t.normalize_openalex({"id": "W2", "title": "Known paper", "authorships": [{"author": {"id": None, "display_name": "Unrelated Author"}}]})
        self.assertFalse(t.compatible_authors(no_ids, paper))
        self.assertEqual(t.text("&lt;i&gt;Plain&lt;/i&gt; abstract"), "Plain  abstract")

    def test_doi_bridge_preserves_oldest_discovery(self):
        a = row(doi="", sid="W1", authors=["Other Person"])
        b = row(doi="10.1234/a", sid="W2")
        records, _, _, _ = t.merge_records([], [a], NOW)
        records, _, _, _ = t.merge_records(records, [b], "2026-10-07T06:00:00Z")
        bridge = row(doi="10.1234/a", sid="W1")
        records, new, _, _ = t.merge_records(records, [bridge], "2026-10-08T06:00:00Z")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["first_discovered_at"], NOW)
        self.assertFalse(new)


if __name__ == "__main__":
    unittest.main()
