"""Collect public author candidates for manual identity review; never enable alerts."""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from literature_tracker import CONFIG, ROOT, PublicClient


def main():
    client = PublicClient()
    alerts = [a for a in json.loads(CONFIG.read_text())["alerts"] if a["type"] == "author" and not a["enabled"] and not a.get("legacy_mode") and a["author"]["name"]]

    def candidates(alert):
        query = re.sub(r"^(?:Prof\.\s*)?(?:Dr\.\s*)?", "", alert["author"]["name"], flags=re.I)
        results = client.get("openalex", "authors", {"search": query, "per-page": 5}, ttl=7 * 86400)
        out = []
        for author in results.get("results", [])[:3]:
            aid = author["id"].rsplit("/", 1)[-1]
            works = client.get("openalex", "works", {"filter": "authorships.author.id:" + aid, "sort": "cited_by_count:desc", "per-page": 4})["results"]
            institutions = set()
            for work in works:
                for authorship in work.get("authorships", []):
                    if (authorship.get("author") or {}).get("id") == author["id"]:
                        institutions.update(i["display_name"] for i in authorship.get("institutions", []))
            out.append({"id": aid, "name": author["display_name"], "orcid": author.get("orcid"), "institutions": sorted(institutions), "works": [{"title": w["display_name"], "doi": w.get("doi"), "id": w["id"]} for w in works]})
        return {"alert_id": alert["id"], "query": query, "candidate_count": results["meta"]["count"], "candidates": out}

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(candidates, a) for a in alerts]):
            try:
                result = future.result()
                results.append(result)
                print(result["query"], result["candidate_count"], flush=True)
            except Exception as error:
                print("Candidate lookup failed:", str(error), flush=True)
    target = ROOT / "work/literature_cache/author_candidates.json"
    target.write_text(json.dumps(sorted(results, key=lambda r: r["alert_id"]), ensure_ascii=False, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
