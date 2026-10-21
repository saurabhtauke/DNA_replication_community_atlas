"""Check survey additions, unchanged score rules, and synchronized exports."""
import csv
import json
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import build_replication_survey as survey


class SurveyTests(unittest.TestCase):
    def test_chistol_is_a_ranked_verified_pi_with_a_fixed_publication_cutoff(self):
        entries = [r for r in survey.ROSTER if r[0] == "Gheorghe Chistol"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][2], "rising/recent leader")
        self.assertEqual(entries[0][5], 1)
        self.assertEqual(survey.MANUAL_AUTHOR_IDS[entries[0][0]], "A5056925498")
        with patch.object(survey, "get_json", return_value={"results": []}) as fetch:
            survey.fetch_works("https://openalex.org/A5056925498")
            self.assertIn("to_publication_date:" + survey.AS_OF, fetch.call_args.args[0])
            survey.fetch_recent_works("https://openalex.org/A5056925498")
            self.assertIn("from_publication_date:2021-01-01", fetch.call_args.args[0])
            self.assertIn("to_publication_date:" + survey.AS_OF, fetch.call_args.args[0])

    def test_generated_scores_follow_original_formula_and_extras_stay_unranked(self):
        with (survey.OUT / "dna_replication_researchers.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        ranked = [r for r in rows if r["ranking_status"] == "ranked"]
        extras = [r for r in rows if r["ranking_status"] != "ranked"]
        self.assertEqual(len(rows), len(survey.ROSTER))
        self.assertEqual([int(r["rank"]) for r in ranked], list(range(1, len(ranked) + 1)))
        self.assertTrue(all(not r["rank"] and not r["combined_impact_score_0_100"] for r in extras))
        columns = ["lifetime_relevant_citations", "lifetime_relevant_works", "recent_relevant_citations", "recent_relevant_works", "recent_distinct_collaborators"]
        for row in ranked:
            p = [survey.percentile([int(r[k]) for r in ranked], int(row[k])) for k in columns]
            life, recent = .75*p[0] + .25*p[1], .65*p[2] + .25*p[3] + .10*p[4]
            self.assertEqual(float(row["combined_impact_score_0_100"]), round(.55*life + .45*recent, 1))
        chistol = next(r for r in rows if r["person"] == "Gheorghe Chistol")
        self.assertEqual(chistol["orcid"], "https://orcid.org/0000-0003-4868-3667")
        self.assertEqual(chistol["lab_website_url"], "https://chistol.stanford.edu/")
        self.assertIn("freshly retrieved" if (survey.OUT / "ranking_refresh.json").exists() else "mixed-retrieval-date", chistol["source_notes"])
        self.assertEqual(len(chistol["top_5_trainees_or_future_leaders"].split(" || ")), 5)

    def test_network_formats_agree_and_keep_the_added_pi(self):
        graph = json.loads((survey.OUT / "replication_community_network.json").read_text())
        with (survey.OUT / "replication_network_nodes.csv").open() as handle:
            names = {r["person"] for r in csv.DictReader(handle)}
        self.assertEqual(names, {n["id"] for n in graph["nodes"]})
        self.assertIn("Gheorghe Chistol", names)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        xml = ET.parse(survey.OUT / "replication_community_network.graphml")
        self.assertEqual(names, {n.attrib["id"] for n in xml.findall(".//g:node", ns)})
        self.assertEqual(len(graph["edges"]), len(xml.findall(".//g:edge", ns)))
        for edge in graph["edges"]:
            self.assertTrue({edge["source"], edge["target"]} <= names)
            self.assertTrue(edge["supporting_papers"])


if __name__ == "__main__":
    unittest.main()
