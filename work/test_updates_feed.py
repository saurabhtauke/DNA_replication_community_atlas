"""Regression checks for complete author retrieval and safe version merging."""

import io
import json
import unittest
from unittest.mock import patch

import build_updates_feed as feed


class UpdatesFeedTests(unittest.TestCase):
    def test_cursor_pagination(self):
        pages = [
            {"meta": {"count": 201, "next_cursor": "next"}, "results": [{"id": f"W{i}"} for i in range(200)]},
            {"meta": {"count": 201, "next_cursor": None}, "results": [{"id": "W200"}]},
        ]
        with patch.object(feed, "CACHE_ONLY", False), patch.object(feed.urllib.request, "urlopen", side_effect=[io.StringIO(json.dumps(p)) for p in pages]) as request:
            name, works = feed.fetch_author_works({"person": "Test PI", "openalex_author_id": "A1"})
        self.assertEqual(name, "Test PI")
        self.assertEqual(len(works), 201)
        self.assertEqual(request.call_count, 2)
        self.assertIn("cursor=next", request.call_args.args[0].full_url)

    def test_incomplete_results_fail(self):
        page = {"meta": {"count": 2, "next_cursor": None}, "results": [{"id": "W1"}]}
        with patch.object(feed, "CACHE_ONLY", False), patch.object(feed.urllib.request, "urlopen", return_value=io.StringIO(json.dumps(page))):
            with self.assertRaisesRegex(RuntimeError, "Incomplete OpenAlex results"):
                feed.fetch_author_works({"person": "Test PI", "openalex_author_id": "A1"})

    def test_live_failure_does_not_fall_back_to_cache(self):
        with patch.object(feed, "CACHE_ONLY", False), patch.object(feed.urllib.request, "urlopen", side_effect=OSError("source unavailable")), patch.object(feed.time, "sleep"):
            with self.assertRaisesRegex(OSError, "source unavailable"):
                feed.fetch_author_works({"person": "Test PI", "openalex_author_id": "A1"})

    def test_dataset_is_not_an_accepted_manuscript(self):
        work = {"type": "dataset", "locations": [{"version": "acceptedVersion"}]}
        self.assertEqual(feed.status_label(work), "Dataset")

    @staticmethod
    def row(status, record_id, doi="", title="Source data for figures"):
        return {
            "status": status, "title": title, "openalex_id": record_id, "doi": doi,
            "publication_date": "2026-09-24", "openalex_citations": 0,
            "network_researchers": ["Test PI"], "senior_or_last_network_researchers": [],
            "corresponding_network_researchers": [], "source_note": "Test",
        }

    def test_distinct_datasets_with_same_title_are_preserved(self):
        rows = [self.row("Dataset", "W1", "https://doi.org/10.1/data1"), self.row("Dataset", "W2", "https://doi.org/10.1/data2")]
        self.assertEqual(len(feed.deduplicate_updates(rows)), 2)

    def test_non_paper_doi_duplicates_merge(self):
        rows = [self.row("Dataset", "W1", "https://doi.org/10.1/data"), self.row("Dataset", "W2", "https://doi.org/10.1/data")]
        merged = feed.deduplicate_updates(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["related_openalex_records"], ["W1", "W2"])

    def test_paper_versions_merge_but_associated_data_stays_separate(self):
        rows = [self.row(status, record_id, title="INO80 rapidly shuttles nucleosomes between chromatin barriers") for status, record_id in [("Preprint", "W1"), ("Journal article", "W2"), ("Dataset", "W3")]]
        merged = feed.deduplicate_updates(rows)
        self.assertEqual(len(merged), 2)
        article = next(r for r in merged if r["status"] == "Journal article")
        self.assertEqual(article["related_openalex_records"], ["W1", "W2"])


if __name__ == "__main__":
    unittest.main()
