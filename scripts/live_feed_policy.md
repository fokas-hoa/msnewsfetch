# Zero-touch live publication policy

MSNewsFetch publishes structured research updates without requiring a manual approval step.

## What can auto-publish

- deterministic trial-registry changes (status, results-posted flag, meaningful date shifts, primary-outcome changes, Greek-site changes)
- EU CTIS operational changes and explicit source conflicts
- high-signal newly discovered human trials/programmes
- peer-reviewed, preprint, grant, university/company or translational leads that pass the weekly evidence gate

Every live entry carries its source class, evidence level and clinical-meaning disclaimer. Preclinical, cell, animal, imaging, biomarker and preprint findings are never converted into a claim of proven clinical benefit.

## What is quarantined

Parser/source failures, ambiguous source conflicts with insufficient structured evidence, and items below the high-signal threshold are not published. They do not block other updates and are retried on later runs.

## Hosting separation

The app shell remains on Netlify. Live research data is stored on the `live-data` branch as `live-feed.json` and fetched by the browser. Updating live data therefore does not require a Netlify production deploy.
