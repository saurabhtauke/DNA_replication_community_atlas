# DNA Replication Researchers Survey

Data snapshot: **8 September 2026**  
Recent window: **1 January 2021–8 September 2026**

This release contains a curated, globally distributed survey of **100 ranking-eligible active researchers/PIs** in DNA replication and closely coupled fork-stress/repair biology, plus **3 explicitly unranked requested researchers** (Jacob S. Lewis, Lisanne Spenkelink, and Thomas C. R. Miller). Joseph Yeeles, Tom Deegan, and Christoph Kurat are included in the ranked roster; all previously requested names remain present.

The list is intended for field mapping and hypothesis generation—not as a definitive or purely objective league table. Coverage spans initiation/licensing, replisome mechanism, replication timing, chromatin inheritance, replication stress and repair, bacterial replication, structural biology, single-molecule biophysics, cell biology, genomics, and proteomics.

## Files

- `dna_replication_researchers.csv` — main researcher database; one row per person.
- `replication_network_nodes.csv` — researcher-node table for network software.
- `replication_network_edges.csv` — evidence-backed recent coauthorship edges among people in the roster.
- `replication_community_network.graphml` — ready-to-import undirected GraphML network.
- `replication_community_network.json` — the same network in portable node/edge JSON.
- `author_resolution_audit.csv` — author-name matching audit, expected affiliations, selected OpenAlex IDs, and match confidence.
- `replication_publication_updates.csv` and `replication_publication_updates.json` — one-time 8 September 2026 recent-publication snapshot used by the website's Updates tab.
- `website/index.html` — static interactive research atlas; open directly in a browser. Its bundled `data.js` is regenerated from the CSVs by `work/build_website_data.py`.

## Selection and ranking

The roster was expert-curated for relevance, influence, recent activity, methodological breadth, geographic breadth, and coverage of the major mechanistic subfields. It is not the top 100 returned by a generic keyword search. That choice avoids allowing cancer-wide or DNA-repair-wide citation volume to overwhelm core replication researchers, but it introduces curator judgement.

Only rows with `ranking_status=ranked` receive a rank. Scores are percentile-based within this curated roster:

- **Lifetime impact score:** 75% percentile of citations to field-relevant works + 25% percentile of field-relevant work count.
- **2021–2026 impact score:** 65% percentile of citations to recent field-relevant works + 25% percentile of recent work count + 10% percentile of recent distinct collaborator count.
- **Combined score:** 55% lifetime impact + 45% 2021–2026 impact.

Percentiles reduce domination by a few extreme citation outliers. Citation counts are OpenAlex counts at retrieval time and will drift. Ranking should be interpreted in bands rather than as meaningful one-place differences.

`career_impact_category` is an expert-curated contextual label:

- `established giant` — major long-run field-shaping influence.
- `current leader` — established and strongly active in the current era.
- `rising/recent leader` — especially strong recent trajectory or newer independent leadership.
- `additional requested researcher` — included at the user's request without forcing the person into the PI ranking.

## Publication, collaborator, and trainee logic

OpenAlex author/work metadata supplies publication titles, dates, DOI/OpenAlex links, citation counts, authorships, and recent coauthorship. A field-relevance filter uses titles and OpenAlex topics for replication, replisome, origins, helicases, polymerases, fork stress/repair, checkpoints, chromatin inheritance, replication timing, and closely coupled genome-stability mechanisms.

Repeated rich-text entries within a CSV cell are separated by ` || `; semicolons inside each entry separate its metadata fields. Technique and subfield values use simple semicolon-separated tags.

- `top_5_papers_all_time` and `top_5_papers_2021_2026` are the five most-cited field-relevant indexed works available for the selected author profile. Fewer than five may be present for a split or sparse profile. Reviews can appear because the field-impact question is not restricted to primary research.
- `five_most_recent_lab_papers` contains five works ordered by publication date. It prioritizes papers where the focal researcher is last and/or corresponding author, then backfills from other authored works when fewer than five such records are indexed. Backfilled papers require manual laboratory-provenance checking.
- The five-recent-paper lists do **not exclude preprints**: any OpenAlex-indexed work was eligible, including a record typed as a preprint. They are therefore not a complete preprint inventory and do not reliably distinguish accepted manuscripts from version-of-record articles without a source-specific check.
- `top_5_collaborators_2021_2026` ranks coauthors by number of shared recent field-relevant papers, with up to two supporting examples. It measures coauthorship, not necessarily an external collaboration; lab members and consortium coauthors can appear.
- `top_5_trainees_or_future_leaders` is deliberately labelled as an **inference**. Candidates are first authors on recent field-relevant papers where the focal researcher is last and/or corresponding author. This is not proof of a PhD/postdoc relationship, laboratory membership, independence, or future success. Verify CVs, ORCID records, lab alumni pages, and current positions before using this field for recruitment or evaluation.

## Affiliation and identity quality control

Author entities were resolved by name, expected institution, citation profile, and inspection of ambiguous search results. Known split/common-name profiles were pinned manually. `author_resolution_audit.csv` makes those choices inspectable.

OpenAlex's first “last known institution” can be a secondary affiliation, funder, consortium address, or metadata collision. Obvious cases were manually corrected and given an institutional verification URL. Other rows use the OpenAlex last-known institution. All current affiliations should be rechecked on an official lab/institutional page before outreach; the row-level `source_notes` field records which route was used.

## Publication updates feed

The website's **Updates** tab is a one-time, network-wide snapshot generated on **8 September 2026**. It covers works dated 2 March–8 September 2026 and uses OpenAlex author IDs for all 103 people, preventing name-only matching where a persistent author ID is available. The update builder filters titles/topics for replication-relevant work, deduplicates works coauthored by more than one roster member, and records linked people, venue, DOI/PMID/OpenAlex links, open-access status, and location-version metadata.

Status is inferred as follows: `Preprint` from the OpenAlex work type or a submitted version without a published version; `Accepted manuscript` from an accepted version without a published version; `Journal article` from an article whose primary source is a journal. Datasets, peer reviews, editorials, abstracts, and corrections are retained as separately filterable research outputs rather than being silently presented as papers. Exact-title duplicate/version records are collapsed in the feed, retaining the strongest current status. This current snapshot has 77 relevant unique outputs, including 25 OpenAlex-indexed preprints; it has no items which OpenAlex's location metadata identifies as accepted-manuscript-only.

The repository contains a GitHub Actions workflow prepared to refresh the feed daily at **06:00 Europe/London**, rerun `work/build_updates_feed.py`, validate the output with `work/validate_updates_feed.py`, rebuild `website/data.js` with `work/build_website_data.py`, and publish the changed static assets through GitHub Pages. Each verified run writes `last_successful_check_date`, so the site shows the latest successful source check even when no publication rows change. It uses live OpenAlex queries with cached-record fallback when transient source failures occur. The recommended source hierarchy is:

- **OpenAlex author IDs** as the daily identity and deduplication backbone, including DOI/PMID/OpenAlex links and broad preprint discovery.
- **Europe PMC and PubMed** to verify biomedical indexing, `Epub ahead of print` status, and publication dates for DOI/PMID-bearing works.
- **bioRxiv and medRxiv** feeds/API as a targeted direct supplement for preprints that may lag or be absent in OpenAlex.
- **Publisher Crossref metadata and journal RSS/early-view feeds** to confirm acceptance or version-of-record transitions where available.

Google Scholar is useful for manual discovery and author-profile checks, but it has no stable public monitoring API and automated scraping can be unreliable and inconsistent with its terms. It should not be the unattended daily source of record.

## Main-field data dictionary

| Field | Meaning |
|---|---|
| `rank` | Combined-score order for ranking-eligible rows; blank for additions. |
| `ranking_status` | `ranked` or `additional/unranked`. |
| `person`, `openalex_display_name` | Curated display name and matched source-profile name. |
| `career_impact_category` | Contextual career/impact band, not computed from age. |
| `combined_impact_score_0_100` | 55% lifetime + 45% recent score. |
| `lifetime_impact_score_0_100` | Within-roster lifetime citation/output percentile composite. |
| `impact_2021_2026_score_0_100` | Within-roster recent citation/output/network percentile composite. |
| `affiliation`, `city`, `country`, `continent` | Current/last-known institutional geography after identity audit. |
| `top_5_collaborators_2021_2026` | Recent coauthors ranked by shared relevant-paper count, with evidence examples. |
| `top_5_papers_all_time` | Citation-ranked field-relevant works, each with year, citation snapshot, and DOI/OpenAlex URL. |
| `top_5_papers_2021_2026` | Same, restricted to the recent window. |
| `five_most_recent_lab_papers` | Five newest indexed works, prioritizing last/corresponding authorship. |
| `recent_lab_paper_evidence` | Exact senior-author prioritization and backfill rule. |
| `technique_expertise` | Ten-category normalized method vocabulary used by filters and network attributes. |
| `replication_expertise_subfield` | Ten-category normalized replication-area vocabulary used by filters and network attributes. |
| `technique_details`, `replication_expertise_details` | More granular curator-supplied descriptions retained for nuance and search. |
| `top_5_trainees_or_future_leaders` | Algorithmically inferred first-author candidates; see caveat above. |
| `trainee_evidence_type` | Exact inference rule and warning. |
| `*_relevant_works`, `*_relevant_citations` | Counts used in ranking; “relevant” follows the title/topic filter. |
| `recent_distinct_collaborators` | Unique coauthors on recent relevant works, not only people in this roster. |
| `openalex_author_id`, `orcid` | Persistent identity fields when available. |
| `author_source_url`, `affiliation_source_url`, `works_source_url` | Audit/provenance links. |
| `lab_website_url`, `lab_website_link_type` | Specific lab/group page where verified; otherwise an official institution/research-centre page with the fallback identified. |
| `google_scholar_url`, `google_scholar_link_type` | Google Scholar author search link; exact public profile is not claimed unless independently verified. |
| `resolution_confidence_score` | Matching heuristic for audit triage, not scientific impact. Manually pinned profiles score 20. |

## Harmonized category vocabularies

Technique filters now use exactly ten categories: Biochemistry & reconstitution; Structural biology & cryo-EM; Single-molecule & biophysics; Cell biology & imaging; Genomics & sequencing; Genetics & genome engineering; Proteomics & mass spectrometry; Computational & systems biology; DNA fiber & electron microscopy; Extracts & cell-free systems.

Replication-area filters now use exactly ten categories: Initiation & origin licensing; Replisome architecture & dynamics; Replication stress & fork protection; DNA repair & damage tolerance; Timing & genome organization; Chromatin inheritance & cohesion; Transcription conflicts & R-loops; Termination, restart & topology; Polymerases, fidelity & mutagenesis; Telomeres & difficult templates.

## Network data dictionary

The network is undirected. Every researcher is retained as a node, including isolates.

- Node ID: `person`.
- Node attributes: rank/status, career category, score, affiliation/geography, techniques, subfields, OpenAlex identity, and source URL.
- Edge: two roster members coauthored at least one field-relevant work in the recent window.
- `weight_recent_shared_papers`: number of distinct supporting shared papers.
- `shared_citation_sum`: sum of current OpenAlex citation counts for those shared papers; use cautiously because older papers have more time to accrue citations.
- `supporting_papers`, `years`: row-level evidence for the edge.

No inferred “same topic” or “same technique” edges were added. This keeps collaboration claims auditable but makes the roster-only network sparse; collaborators outside the selected roster are present in the main CSV's collaborator field but not as graph nodes.

## Visualizing

### Gephi

1. Import `replication_community_network.graphml` as an undirected graph.
2. Size nodes by `combined_impact_score_0_100` or degree.
3. Size edges by `weight_recent_shared_papers`.
4. Color by `career_impact_category`, `country`, or `continent`.
5. Use filters/search on `technique_expertise` (for example, `single-molecule` or `cryo-EM`) and `replication_expertise_subfield`.
6. ForceAtlas2 is useful for exploratory layout; keep isolates visible in a separate component or use a geographic layout.

### Cytoscape

Import the GraphML directly, or import the nodes and edges CSVs with `person` as node key and `source`/`target` as edge endpoints. Map edge width to `weight_recent_shared_papers` and node fill to a categorical attribute.

### Python

```python
import networkx as nx

G = nx.read_graphml("replication_community_network.graphml")
print(G.number_of_nodes(), G.number_of_edges())
top_edges = sorted(G.edges(data=True), key=lambda x: int(x[2]["weight_recent_shared_papers"]), reverse=True)[:10]
```

For detailed filtering and plotting, read the two CSVs with pandas, split semicolon-delimited technique/subfield strings, and join them to NetworkX nodes.

## Limitations and responsible use

- The roster is broad but cannot eliminate regional, language, database-coverage, seniority, and citation biases. Continental Europe, the UK, North America, Japan/China/Saudi Arabia, and Australia are represented; Africa and Latin America remain underrepresented in this mechanistically focused cut.
- “Impact” is multidimensional. Citations favor older work, large fields, reviews, and consortium papers; recent papers have unequal exposure time.
- OpenAlex can merge or split identities and normalize titles imperfectly. Consult `author_resolution_audit.csv` and the linked records.
- Normalized technique/area categories are many-to-many curated summaries, not exhaustive inventories. Granular descriptions are retained in the detail columns.
- Do not use this dataset alone for hiring, awards, or other high-stakes individual evaluation.
