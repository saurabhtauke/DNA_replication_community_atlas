# DNA Replication Research Atlas

https://saurabhtauke.github.io/DNA_replication_community_atlas/

An interactive, data-driven survey of active DNA-replication researchers, their fields, methods, recent collaborations, and recent publications.

The public site is deployed from `outputs/website/`. Its researcher database, network exports, publication-update feed, methods, evidence caveats, and data dictionary are documented in [outputs/README.md](outputs/README.md).

## Publication updates

The daily GitHub Actions workflow refreshes the network feed and credential-free literature tracker at **06:00 UTC** (07:00 London during BST, 06:00 during GMT). Delayed starts are not skipped. It validates the feeds, rebuilds the browser bundle, commits changed data/check timestamps, and explicitly invokes the reusable Pages deployment. Manual dispatch is also available under **Actions → Refresh publication updates → Run workflow**.

The network feed includes all OpenAlex-indexed works coauthored by the 103 roster profiles during the rolling 190-day window, including related chromatin, topology, and biophysics work. It retrieves every cursor page and applies no topic gate. If that refresh fails, the previous valid snapshot and check date are retained while the independent tracker can still update. Preprint and accepted-manuscript labels remain source-inferred; see `outputs/README.md`.

Rebuilding fingerprints data, application, tracker script, and stylesheet links, so refreshed pages request matching assets. A partial refresh is deployed with visible warnings, then the workflow reports failure so incomplete sources are not mistaken for a complete check.

## Credential-free literature tracker

Open **Updates → Literature tracker** for the latest 100 papers across the watchlist. Each clickable author/topic alert has its own latest 20 results, independently of the global 100. Search filters the currently selected list; it does not initiate browser API requests. Publication dates control the latest view. The discovery view sorts by when this system first found a paper, and the new view includes only papers first discovered in the latest run. The initial import is a baseline, not a flood of new alerts.

The public watchlist is [config/literature_alerts.json](config/literature_alerts.json), seeded from all 113 supplied alert definitions: 100 enabled author/topic searches and 13 inactive/review entries. Ambiguous John King, Amit Kumar, Jie Xiao, Dhananjay Singh, Neha Rana, Morgan Jones and sumit kumar author identities are disabled pending review. Citation/recommendation alerts and unidentified inactive profiles are preserved with explanatory reasons, not implemented as publication searches.

Edit readable names freely, but keep stable `id` values. For a topic, set `type: keyword` and `query.all` to terms/phrases that must all match; `title_only` restricts matching to titles. Underscores and hyphens normalize to spaces. For an author, pin `author.openalex_ids` and/or `author.orcid`, review affiliation and known publications, and retain `verification_notes`/`verification_urls`. A matching name alone is not enough to enable an author. Optional `sources` restrict retrieval databases; `source_queries` overrides OpenAlex/Europe PMC query translation (local matching still applies).

Sources are public OpenAlex and Europe PMC (PubMed/PMC articles and indexed preprints), plus direct bioRxiv/medRxiv harvesting. Crossref enriches DOI metadata only; it is not a broad search engine here. The implementation neither accesses Google accounts/email nor scrapes Scholar, and no scholarly credentials or API secrets are used. GitHub's built-in token handles repository commits and deployment only.

### Coverage and recovery

The configurable default is 190 publication days. Direct preprint harvesting bootstraps the last 30 days, then resumes from the last successful checkpoint with a seven-day overlap. Older indexed preprints may still arrive through OpenAlex/Europe PMC. Direct name-only preprint attribution is rejected; author hits need persistent-ID/DOI corroboration or exact corresponding-author plus pinned institution evidence. Europe PMC authors without ORCID are queried only through independently corroborated DOIs. This conservative rule can miss papers; source indexes, author profiles and metadata also have gaps.

Retrieval uses live responses with timeouts, bounded retries and pagination. Optional Crossref enrichment is cached for 90 days. Anonymous OpenAlex quotas can limit complete refreshes: failures preserve old records and checkpoints and are visible as partial/failed, without advancing the last complete-success time. The existing validated network snapshot may bootstrap known papers, explicitly labelled as a snapshot, not a fresh source check. Its initial author list can be roster-only until complete metadata arrives.

The next daily/manual run retries failed sources. A valid partial run merges successful sources and deploys truthful health metadata. A validation/programming failure stops publication entirely. No database outage should erase the previous valid file. GitHub schedules are best-effort, not guaranteed to start exactly at 06:00.

### Tracker data dictionary

`outputs/literature_tracker.json` is the full normalized store and state. Its website projection lives in `outputs/website/data.js`; browsers never run source searches.

| Field | Meaning |
| --- | --- |
| `alerts` | Public definitions, persistent identities, queries, review/inactive reasons |
| `publications[].id` | Stable internal ID; retained when a DOI-less paper gains a DOI |
| `title`, `authors`, `publication_date`, `venue`, `status` | Source-inferred bibliographic metadata; dates may be approximate and authors incomplete |
| `doi`, `url`, `preprint_url`, `abstract` | Canonical lowercase DOI, public links, optional plain-text abstract |
| `alert_ids` | All enabled alerts matching the paper |
| `sources`, `source_records` | Databases that returned it and their original record IDs |
| `enrichment_sources` | Metadata-only providers, separate from retrieval provenance |
| `related_publication_dois` | Explicit source-supplied version linkage; distinct DOIs remain separate records |
| `first_discovered_at`, `last_seen_at` | UTC discovery/observation timestamps, not publication dates |
| `meta.new_publication_ids`, `metadata_updated_ids`, `new_alert_matches` | New papers versus changes to existing papers/memberships |
| `meta.last_attempt_at`, `last_successful_check_at`, `refresh_status` | Latest attempt, last complete success, and ok/partial/failed health |
| `meta.source_health`, `checkpoints` | Per-source/alert status and successful resume points |
| `discovery_registry` | Compact identity ledger preserving discovery dates after display-window expiry |

Deduplication uses canonical DOI first; DOI-less titles require compatible author evidence. Different DOIs are never merged merely because titles match. Provenance and alert memberships are unioned. Source-inferred author profiles can still be incorrect and should be audited.

### Run and test locally

Use Python 3.12+ and install `work/literature_requirements.txt` in a virtual environment. Run `python work/literature_tracker.py`, then `python work/literature_tracker.py --validate` and `python work/build_website_data.py`. Tests: `python -m unittest discover -s work -p 'test_*.py'` and `node work/test_literature_ui.js`. `--smoke` checks all five unauthenticated APIs and both September 2026 Rueda preprints; live tests depend on provider availability/quotas. Raw public API caches are ignored by Git. The bioRxiv adapter uses the vendored skill helper, documented in `work/vendor/biorxiv/README.md`.

## Local preview

Run a static HTTP server from `outputs/website/`, then open `index.html` through that server. The site is entirely static and requires no client-side API credentials.
