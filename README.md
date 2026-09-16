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

## Local validation
```bash
python scripts/validate_site.py
python scripts/build_rss.py
python scripts/build_rss.py --check
node --check app.js
```

## GitHub → Netlify automation
The repository includes `.github/workflows/validate.yml`. Every push or pull request to `main` validates the structured research data, checks that RSS matches `news.json`, and checks JavaScript syntax.

Once this repository is connected to the existing Netlify project **msnewsfetch**, Netlify continuous deployment should publish every successful push to `main`. No separate Netlify deploy workflow is required.

The broad scientific monitoring itself should remain evidence-gated: registry changes can be automated safely, but papers, conference abstracts, company claims and translational programmes still need source-quality and clinical-meaning review before they are published to `news.json`.
