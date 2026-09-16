# MSNewsFetch

Automated, evidence-gated research watch for multiple-sclerosis remyelination / myelin-repair research.

## What the homepage prioritises
The page starts with **“Για ασθενείς στην Ελλάδα”**. This is deliberately different from a generic news feed: it prioritises whether a trial actually has a Greek recruiting site, relevant EU/CTIS status, important human readouts, and Greek research participation. A global `Recruiting` label is never treated as equivalent to access in Greece.

## Research structure
The site separates:
1. Active / upcoming human trials
2. Translational pipeline (selected late-preclinical / development programmes)
3. Completed / failed / key readouts
4. Latest substantive updates

Animal, cell, imaging or biomarker findings are labelled as such and are not presented as proven clinical benefit.

## Two-layer live data architecture
The deployed site shell is static, but research updates are not limited to the last Netlify production deploy.

- `news.json` is the curated/baseline dataset bundled with a production release.
- `live-data` is a dedicated Git branch containing `live-feed.json`.
- `app.js` fetches `live-feed.json` directly from GitHub and merges it with the deployed baseline in the browser.
- Daily/weekly monitors write structured updates to `live-data` without changing `main`.

This means a new trial status, Greek-site change, result posting or high-signal research discovery can appear on the **same public Netlify URL without a new Netlify production deploy**.

The live feed can provide:
- latest-update cards
- Greece-priority cards
- status overrides for already tracked programmes
- newly discovered human/translational programme cards

If the remote live feed is temporarily unavailable, the site fails safely to the last deployed `news.json` baseline.

## Zero-touch publication policy
Manual approval is **not required** for normal updates.

Auto-publication is deterministic and source-aware:
- primary trial-registry changes can publish automatically
- explicit EU CTIS operational changes/conflicts can publish automatically
- high-signal human trials/programmes can publish automatically
- qualifying peer-reviewed, preprint, grant, university/company and translational signals can publish with evidence/source labels

The wording is template-based rather than free-form medical interpretation. Every automated entry carries source quality, evidence level and clinical context. Preclinical, animal, cell, imaging, biomarker and preprint findings are never transformed into a claim of proven clinical benefit.

Parser/source failures, ambiguous records without enough structured evidence, and lower-signal discoveries are quarantined/suppressed without blocking the rest of the feed. They are retried later; the user does not have to approve them before other updates go live.

## Monitoring architecture

### Daily known-program monitor
`.github/workflows/research-monitor.yml` runs daily at `05:23 UTC`.

It watches established programmes already on the radar and compares current source snapshots with the previous run. Sources include ClinicalTrials.gov, EU/CTIS cross-checks, literature discovery and selected official company/lab/programme pages.

Substantive signals include trial status changes, temporary halts/restarts, newly posted results, meaningful schedule changes, primary-outcome changes and the appearance/disappearance of Greek trial sites. If nothing substantive changed, it stays silent. When something changes, the deterministic update is written to `live-data`; a GitHub issue may also be created as an audit trail, but it is not a publication gate.

### Weekly deep discovery
`.github/workflows/deep-discovery.yml` runs Sundays at `05:37 UTC`.

Its job is different: find **new programmes not already represented in the watchlist**, including work that may not use `remyelination` in its title. It searches or cross-checks:

- ClinicalTrials.gov
- EU/CTIS discovery pages with official CTIS verification links
- ANZCTR, including browser-compatible and headless-Chrome fallbacks
- ISRCTN official XML API
- Europe PMC
- bioRxiv and medRxiv
- NIH RePORTER
- UKRI Gateway to Research
- CORDIS public EU project records
- ECTRIMS / ACTRIMS official discovery pages
- selected official company, university, tech-transfer and investigator pages
- secondary news/RSS only as a lead source under a stricter development-signal gate

Search vocabulary includes remyelination, myelin repair/regeneration, promyelination, oligodendrocyte/OPC differentiation or maturation, myelin water fraction, magnetization transfer, VEP, myelin PET, neurorepair, neural/glial progenitors and related translational terms.

Each source has its own baseline. Adding a new source does **not** generate a flood of historical “new” alerts. Subsequent runs publish only newly seen high-signal candidates.

## Canonical programme identity and genealogy
`monitor/program_registry.json` is the curated identity layer used by weekly discovery.

It distinguishes three things that must not be conflated:
- **same programme / alias** — alternate programme names, trial names and known identifiers
- **new registry record under a known programme** — still publishable/reviewable because it may represent a new phase, arm or registration
- **programme family / related programme** — related, but not automatically the same programme or a successor

For example, `PIPE-307` and the `VISTA` trial name are treated as one canonical programme identity, while distinct metformin trials share a family but are not collapsed into one record. NeuOrphan-related programmes can be family-linked without inventing an unverified successor relationship.

The matching system is deterministic and auditable: exact identifiers first, then curated aliases. It does **not** use opaque embedding similarity for identity decisions.

### Cross-source deduplication
`scripts/enrich_discovery_report.py` runs after all weekly discovery sources. It:
- canonicalises known programmes
- preserves genuinely new registry records under known programmes
- clusters duplicate unmatched leads using an explainable title-token similarity rule
- records alternate source sightings instead of publishing duplicate items

## Review confidence
Every weekly candidate receives a `review_confidence` score from 0–100. This is a **triage / review-priority score, not a probability of scientific truth or clinical benefit**.

The score is source-aware. Primary trial registries start highest; official grant/project sources and peer-reviewed indexes are next; conference records, preprints and secondary-news discovery are progressively more cautious. Human-study context, Greek access and explicit development/remyelination signals can raise priority; preclinical-only model context and secondary sourcing reduce it.

The publication gate combines:
- canonical identity status
- source class
- review confidence
- human versus non-human evidence
- explicit development signals
- Greece priority

Ordinary mentions of already-known programmes are routed away from weekly discovery and left to the daily monitor.

## Local validation
```bash
python scripts/restore_data.py
python scripts/build_rss.py
python scripts/validate_site.py
python scripts/test_program_identity.py
python scripts/test_discovery_policy.py
python scripts/test_live_feed.py
python scripts/build_rss.py --check
node --check app.js
node scripts/test_netlify_ignore.js
```

## Credit-safe GitHub → Netlify workflow
The repository is connected to the Netlify project **msnewsfetch**.

### Branch policy
- `main` = production app shell
- `development` = ongoing engineering / review work
- `live-data` = zero-touch research updates
- PRs target `main`
- engineering work is batched and merged only when ready, rather than committing repeatedly to production

### Credit-safe production deploys
Netlify credit-based plans charge successful **production** deploys, while branch/deploy-preview deployments are non-metered. To avoid spending a production deploy on monitoring-only changes, `netlify.toml` uses:

```toml
ignore = "node ./scripts/netlify_ignore.js"
```

A production build proceeds only when a change can affect the public app shell/output, such as:
- `index.html`, `app.js`, `styles.css`, favicon or robots
- compressed public baseline payloads under `data/`
- RSS/data build scripts
- Netlify configuration itself

Changes only to `.github/`, monitoring scripts, identity/watch configuration or documentation are skipped before the Netlify build. Live research updates go to `live-data`, so they do not need a Netlify production deploy at all.

`.github/workflows/validate.yml` runs on both `development` and `main`, and on PRs to `main`. It validates site data, programme identity, discovery policy, zero-touch live-feed transformation, RSS synchronisation, JavaScript and the Netlify credit guard before merge.
