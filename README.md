# MSNewsFetch

Greece-first, zero-touch watch of selected MS remyelination / myelin-repair research sources.

## Public meaning

The homepage prioritises patient relevance in Greece. Global recruitment, an EU authorisation and a reference to Greece are **not** evidence that a Greek site is recruiting. Local access requires a recent successful primary-registry observation, structured Greek-site information and both global and local `RECRUITING`. Missing/unavailable information is labelled unknown, never “no trial exists”.

Registration, clinical-study context, clinical results, patient-derived cell work and publication/peer-review status are different fields. A preprint may concern humans. A patient-derived cell experiment is not a clinical trial. Automated templates report source observations, not treatment efficacy or clinical recommendations. Triage confidence is explainable prioritisation, not a probability that a treatment works.

## Branches and publication

`main` is the released app shell and scheduled workflows. `development` / PR #2 is engineering and preview. `live-data` stores:

- `live-feed.json` schema v2: events, trial-ID-keyed observations, discovered programmes, verified monitoring targets, source-health metadata;
- `rss.xml`: baseline and live events;
- `monitor-state.json` and `discovery-state.json`: durable collector journals.

The browser fetches the public GitHub JSON without a token. Updates to `live-data` do not need a Netlify production deploy. The RSS endpoint proxies the same data branch. A single app-shell release is needed to activate this architecture on an older deployment.

Successful observations, RSS and the corresponding journal are committed **in one Git tree/commit with a non-force ref update**. On a competing writer, the publisher reloads and retries. A same-mode journal advance is rejected for recollection rather than overwriting newer state. A failed write does not acknowledge new observations. The workflows share one non-cancelling publication concurrency group.

## Automatic collection and gates

Daily: `05:23 UTC`. Weekly: Sunday `05:37 UTC`. Schedules run from the default branch; checking in code on development does not activate those schedules. Publishers explicitly reject non-main refs.

Daily polling preserves last-good data on timeout, parse error or a malformed HTTP-200 response. CTIS status is selected only from an unambiguous official observation. Mirrors remain separately labelled and never replace an unavailable official observation. Greek site status/contacts are compared, not just site counts. Newly verified trial IDs are adopted from `live-data`, with the first observation carried forward as a polling baseline.

Weekly discovery covers configured registries, Europe PMC, preprints, grant portfolios, conference/discovery pages and selected programme pages. Every source has a silent initial baseline. The journal separates seen, pending, rejected/quarantined and published records, tracks content fingerprints and policy versions, and reassesses candidates after material/policy changes or an earlier rejection. Exact trial identifiers are distinct from programme families; similar titles do not collapse distinct trial IDs.

The final publisher recomputes identity and source-aware triage and validates source provenance and structured observations. Secondary-news/mirror leads alone cannot publish as primary facts. They remain retryable leads; this does not require the user's approval. Other healthy candidates continue automatically. No AI medical-summary API or Codex review is used by these scheduled scripts.

Issues are **optional post-publication audit notifications**, not approval gates. They are issued only for newly committed events, use a deterministic duplicate marker and are best-effort if GitHub Issues is unavailable. The durable public data transaction is independent of that notification.

## Failure and uncertainty handling

The frontend validates remote JSON before merging it into a cloned baseline. It has an eight-second request deadline, cached last-validated-feed fallback and an explicit health message. Trial cards join by stable record IDs, after adding new live cards. Ended/terminated/withdrawn records leave the active section. Scientific readout summaries are retained separately from operational status; other registries remain visible with their own scope.

Scientific news freshness is independent of a technical poll timestamp. Technical warnings do not become research news. Quarantine is not an automatic “false” judgement. A source that stays inaccessible remains unknown; no completeness or uptime guarantee is made.

## Release validation

```sh
python scripts/build_site.py
# Optional real-browser suite (also required in GitHub CI):
python -m pip install playwright==1.57.0
python -m playwright install --with-deps chromium
python scripts/test_browser_smoke.py
```

`build_site.py` restores the dated curated baseline, assigns explicit trial identities, builds baseline RSS, then runs **the mandatory offline gate**. It includes the original tests, the 19 independent release-contract tests, 29 additional multi-run/boundary/transaction tests, and a Node frontend startup/fallback suite. A failure stops the build. The same build command is used in Netlify, CI and before either scheduled publisher.

GitHub CI additionally runs eight actual Chromium desktop/mobile DOM scenarios, using the built HTML/CSS/JS and mocked research responses. Synthetic data never leave the isolated test environment. `source_smoke.py` is a separate **read-only real-source check**, not a publisher and not a prerequisite on every deploy (upstream availability is not code correctness).

Only seven allowlisted public files are copied to `dist/`. Journals, code, artifacts and synthetic tests cannot enter Netlify's public directory. CSS/JS use content-hash query strings. Monitoring/CI/docs-only changes skip the Netlify build; uncached/manual rebuilds deliberately do not skip. Production release is batched, never a series of micro-deploys.

## Scope and limitations

This is a research watch, **not an exhaustive systematic review or an independently verified clinical-benefit service**. Searches and parsing are bounded and conservative. JS-only registries, inaccessible conference databases, unusual abstract wording and sources outside the configured inventory can be missed. Source-health warnings and stored observation dates make those gaps visible. Official CTIS may not expose parseable current status via HTTP; the system then retains the last good official observation or remains unknown, rather than substituting a mirror. ANZCTR/ISRCTN adoption is limited to their explicitly parseable current status fields.

The historical baseline is dated editorial content, not a claim that every prior item was freshly scientifically re-reviewed during engineering remediation. See `docs/PR2-safety-remediation.md` for the audit acceptance matrix and fixture adjustments.

No paid hosting upgrade, paid review or API-key purchase is required by this code. Hosting suspension or GitHub scheduling restrictions can still prevent service and must be distinguished from a successful code merge.
