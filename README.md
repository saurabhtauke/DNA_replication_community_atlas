# DNA Replication Research Atlas

An interactive, data-driven survey of active DNA-replication researchers, their fields, methods, recent collaborations, and recent publications.

The public site is deployed from `outputs/website/`. Its researcher database, network exports, publication-update feed, methods, evidence caveats, and data dictionary are documented in [outputs/README.md](outputs/README.md).

## Publication updates

The daily GitHub Actions workflow refreshes the OpenAlex-backed publication feed at **06:00 Europe/London**, validates the generated CSV and JSON files, rebuilds the browser data bundle, and commits changes only when the feed differs. It uses two UTC triggers to accommodate UK daylight-saving transitions, then performs a local-time guard before collecting data.

The current source is OpenAlex author-ID metadata with cached-record fallback for transient failures. Preprint and accepted-manuscript status remain source-inferred and are labelled accordingly in the site; see the caveats in `outputs/README.md`.

## Local preview

Run a static HTTP server from `outputs/website/`, then open `index.html` through that server. The site is entirely static and requires no client-side API credentials.
