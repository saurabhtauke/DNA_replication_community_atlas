# bioRxiv public request helper

`rest_request.py` is the unmodified generic REST helper supplied by the OpenAI
life-science-research bioRxiv skill (version 1.0.3). Vendoring it makes the
scheduled pipeline independent of a local Codex installation. Direct bioRxiv
and medRxiv requests use its `execute` interface, preserving raw responses only
in the ignored cache. It requires `requests`; no credentials are supplied.
