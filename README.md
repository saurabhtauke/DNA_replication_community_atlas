# DNA Replication Research Atlas

https://saurabhtauke.github.io/DNA_replication_community_atlas/

An interactive, data-driven survey of active DNA-replication researchers, their fields, methods, recent collaborations, and recent publications.

The public site is deployed from `outputs/website/`. Its researcher database, network exports, publication-update feed, methods, evidence caveats, and data dictionary are documented in [outputs/README.md](outputs/README.md).

## Publication updates

The daily GitHub Actions workflow refreshes the OpenAlex-backed publication feed at **06:00 Europe/London**, validates the generated CSV and JSON files, rebuilds the browser data bundle, and commits any changed publication data **or last-successful-check date**. The Updates tab therefore distinguishes the publication coverage date from the most recent verified source check, even when no newly indexed records are found. It uses two UTC triggers to accommodate UK daylight-saving transitions, then performs a local-time guard before collecting data.

The feed includes all OpenAlex-indexed works coauthored by the 103 roster author profiles during the rolling 190-day window, including related chromatin, DNA topology, and biophysics work. It retrieves every cursor page and applies no title/topic keyword gate. Live source failures block validation and publishing rather than silently substituting stale cached records. Preprint and accepted-manuscript status remain source-inferred and are labelled accordingly in the site; see the caveats in `outputs/README.md`.

Rebuilding the website also fingerprints its data and application script links in `index.html`, so refreshed pages request matching assets instead of an older cached feed. The refresh workflow commits these updated links along with the data. This does not change the refresh schedule or GitHub Pages deployment triggers.

## Local preview

Run a static HTTP server from `outputs/website/`, then open `index.html` through that server. The site is entirely static and requires no client-side API credentials.
