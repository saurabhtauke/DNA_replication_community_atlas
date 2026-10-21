"""Protect monthly freshness, pinned identities, and fail-before-publication behavior."""
import csv
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import build_replication_survey as survey
import refresh_rankings as refresh


class RankingRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "outputs"
        self.out.mkdir()
        for name in refresh.EXPORTS:
            shutil.copyfile(survey.ROOT / "outputs" / name, self.out / name)
        self.previous = refresh.read_rows(self.out / refresh.EXPORTS[0])

    def mutate_rows(self, change):
        rows = refresh.read_rows(self.out / refresh.EXPORTS[0])
        change(rows)
        with (self.out / refresh.EXPORTS[0]).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)

    def test_valid_exports_and_formula(self):
        self.assertEqual(len(refresh.validate_exports(self.out, self.previous)), len(survey.ROSTER))

    def test_author_swap_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(openalex_author_id="A123"))
        with self.assertRaisesRegex(ValueError, "openalex_author_id"):
            refresh.validate_exports(self.out, self.previous)

    def test_roster_loss_is_rejected(self):
        self.mutate_rows(lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, "Roster changed"):
            refresh.validate_exports(self.out, self.previous)

    def test_changed_formula_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(combined_impact_score_0_100="0"))
        with self.assertRaisesRegex(ValueError, "formula"):
            refresh.validate_exports(self.out, self.previous)

    def test_orcid_change_is_rejected(self):
        row = next(r for r in self.previous if r.get("orcid"))
        self.mutate_rows(lambda rows: next(r for r in rows if r["person"] == row["person"]).update(orcid=""))
        with self.assertRaisesRegex(ValueError, "ORCID"):
            refresh.validate_exports(self.out, self.previous)

    def test_month_guard_handles_year_rollover(self):
        now = datetime(2027, 1, 2, tzinfo=timezone.utc)
        self.assertFalse(refresh.already_refreshed({}, now))
        self.assertFalse(refresh.already_refreshed({"last_successful_check_at": "2026-01-01T00:00:00+00:00"}, now))
        self.assertTrue(refresh.already_refreshed({"last_successful_check_at": "2027-01-01T00:00:00+00:00"}, now))

    def test_retrieval_failure_preserves_every_published_file(self):
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        with patch.object(survey, "ROOT", self.root), patch.object(survey, "OUT"), patch.object(survey, "RAW"), patch.object(survey, "AS_OF"), patch.object(survey, "FRESH_REFRESH"), patch.object(survey, "MANUAL_AUTHOR_IDS", dict(survey.MANUAL_AUTHOR_IDS)), patch.object(survey, "main", side_effect=RuntimeError("provider unavailable")):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                refresh.refresh(datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_all_refreshed_lifetime_queries_use_cutoff(self):
        with patch.object(survey, "FRESH_REFRESH", True), patch.object(survey, "AS_OF", "2027-01-01"), patch.object(survey, "get_json", return_value={"results": []}) as fetch:
            survey.fetch_works("https://openalex.org/A123")
            self.assertIn("to_publication_date:2027-01-01", fetch.call_args.args[0])

    def test_invalid_staged_snapshot_preserves_published_data_and_date(self):
        (self.out / "ranking_refresh.json").write_text('{"last_successful_check_at":"2026-09-01"}')
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        def invalid_build():
            self.assertTrue(survey.FRESH_REFRESH)
            self.assertEqual(list(survey.RAW.iterdir()), [])
            self.assertEqual(survey.AS_OF, "2027-01-01")
            for row in self.previous:
                self.assertEqual(survey.MANUAL_AUTHOR_IDS[row["person"]], row["openalex_author_id"])
            for name in refresh.EXPORTS:
                shutil.copyfile(self.out / name, survey.OUT / name)
            path = survey.OUT / refresh.EXPORTS[0]
            rows = refresh.read_rows(path)
            rows[0]["openalex_author_id"] = "A123"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
        with patch.object(survey, "ROOT", self.root), patch.object(survey, "OUT"), patch.object(survey, "RAW"), patch.object(survey, "AS_OF"), patch.object(survey, "FRESH_REFRESH"), patch.object(survey, "MANUAL_AUTHOR_IDS", dict(survey.MANUAL_AUTHOR_IDS)), patch.object(survey, "main", side_effect=invalid_build):
            with self.assertRaisesRegex(ValueError, "openalex_author_id"):
                refresh.refresh(datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_redirected_pinned_profile_is_rejected(self):
        with patch.object(survey, "get_json", return_value={"id": "https://openalex.org/A123"}):
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                survey.resolve_author("Gheorghe Chistol", "Stanford")


if __name__ == "__main__":
    unittest.main()
