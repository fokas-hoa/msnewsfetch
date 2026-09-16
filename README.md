# MSNewsFetch

Static, Netlify-ready research watch for multiple-sclerosis remyelination / myelin-repair research.

## What the homepage prioritises
The page starts with **“Για ασθενείς στην Ελλάδα”**. This is deliberately different from a generic news feed: it prioritises whether a trial actually has a Greek recruiting site, relevant EU/CTIS status, important human readouts, and Greek research participation. A global `Recruiting` label is never treated as equivalent to access in Greece.

## Research structure
The site separates:
1. Active / upcoming human trials
2. Translational pipeline (selected late-preclinical / development programmes)
3. Completed / failed / key readouts
4. Latest substantive updates

Animal, cell, imaging or biomarker findings are labelled as such and are not presented as proven clinical benefit.

## Data model
`news.json` is the source of truth. It contains:
- `greece`: Greece-priority patient-relevance cards
- `pipeline`: human trials / announced human development
- `translational`: named preclinical-to-clinic programmes
- `readouts`: completed, negative, stopped and key results
- `items`: chronological research update feed

`app.js` renders the site. `rss.xml` is generated from `items`.

## Monitoring architecture

### Daily known-program monitor
`.github/workflows/research-monitor.yml` runs daily at `05:23 UTC`.

It watches established programmes already on the radar and compares current source snapshots with the previous run. Sources include ClinicalTrials.gov, EU/CTIS cross-checks, PubMed-style literature discovery and selected official company/lab/programme pages.

Substantive signals include trial status changes, temporary halts/restarts, newly posted results, meaningful schedule changes, primary-outcome changes and the appearance/disappearance of Greek trial sites. If nothing substantive changed, it stays silent.

### Weekly deep discovery
`.github/workflows/deep-discovery.yml` runs Sundays at `05:37 UTC`.

Its job is different: find **new programmes not already represented in the watchlist**, including work that may not use `remyelination` in its title. It searches or cross-checks:

- ClinicalTrials.gov
- EU/CTIS discovery pages with official CTIS verification links
- ANZCTR, including a headless-browser fallback for the browser-oriented registry
- ISRCTN official XML API
- Europe PMC
- bioRxiv and medRxiv
- NIH RePORTER
- UKRI Gateway to Research
- CORDIS public EU project records
- ECTRIMS / ACTRIMS official discovery pages
- selected official company, university, tech-transfer and investigator pages
- secondary news/RSS only as a lead source requiring primary-source verification

Search vocabulary includes remyelination, myelin repair/regeneration, promyelination, oligodendrocyte/OPC differentiation or maturation, myelin water fraction, magnetization transfer, VEP, myelin PET, neurorepair, neural/glial progenitors and related translational terms.

Each source has its own baseline. Adding a new source does **not** generate a flood of historical “new” alerts. Subsequent runs report only newly seen high-signal candidates.

## Evidence gate
Neither monitor edits `news.json` automatically. A candidate can open a GitHub review issue, but publication requires human review of the primary source.

The review layer explicitly separates:
- human trial / human results
- preclinical animal work
- cell / organoid work
- imaging or biomarker evidence
- preprints
- grants / announced development programmes

Animal, cell, imaging, biomarker or mechanistic findings must never be converted into a claim of proven clinical benefit. Secondary news cannot trigger a review issue merely because it says “remyelination therapy”; it also needs a strong development marker such as a clinical trial, Phase 1/2, first-in-human, IND, GMP or licensing signal.

## Local validation
```bash
python scripts/validate_site.py
python scripts/build_rss.py
python scripts/build_rss.py --check
node --check app.js
```

## GitHub → Netlify automation
`.github/workflows/validate.yml` validates structured research data, RSS synchronisation and JavaScript syntax on pushes and pull requests to `main`.

The repository is connected to the Netlify project **msnewsfetch**. Netlify continuous deployment publishes pushes to `main`; no separate deploy workflow is required.
