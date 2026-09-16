# PR #2 release review — BLOCKED

Reviewed application revision: `13fd7433040d90fad96265af3d4587a209e229e8`.
Main at review: `be8063aa4b9ba4215089079d8f1819b5f29e3927`.
Review date: 2026-09-17 Europe/Athens (2026-09-16 UTC).

This is a separate assistant-led source and executable test review, not a new Codex GitHub Code Review and not human certification. No production code fixes for these new findings have been applied during this audit. No main/development/live-data ref was advanced by the audit. The PR was returned to Draft instead of merged.

## Reproduction and limits

[Independent audit run](https://github.com/fokas-hoa/msnewsfetch/actions/runs/35159736873), job `105007481672`, CPython 3.12.14 on Ubuntu.

[Test source](https://github.com/fokas-hoa/msnewsfetch/blob/f2b1dba93a316466a4b76eb5475aee6afda8b067/scripts/test_release_review.py).

The existing validation scripts all pass in the same job. The new targeted suite reports **19 tests; 2 control passes; 17 assertion failures**, reproduced locally as well. This is adversarial contract testing, not a sampled system failure rate or 17 independent P1 bugs. Several cases share a root cause; some are defense-in-depth or presentation findings.

**Every trial transition and test research abstract is a synthetic fixture, not actual clinical news.** Fetch functions are mocked; temporary state is isolated; the workflow has only `contents: read`. No synthetic events were written to the public feed. Browser data functions are executed from the real app.js through Node vm against the bundled baseline, not reimplemented mocks.

## Confirmed release blockers

### P1 — CTIS outages become factual public transitions
`monitor_research.py:118-150,217-244`; `publish_live_feed.py:232-269`.

Both failed CTIS reads return status=null, Greece=false and halt=false. Comparison against last-known halted/Greek context produces three substantive events, which apply_daily publishes. Internal snapshot errors do not reliably reach report warnings. Quarantine merely records warnings; it does not withhold these observations. Preserve last-good facts, distinguish unknown/source health from false, and reject transitions based on failed observations.

### P1 — mirror halt silently overrides the official status
`monitor_research.py:118-150`; `app.js:92-105`.

With official recruiting and mirror halted fixtures, status initially prefers the official source, but halt is computed from both texts. The browser then forces the card to halted. Conflict reporting elsewhere does not resolve this contradictory projection. Use source-specific observations, explicit current-status extraction and an auditable conflict rule; never derive current halt from an arbitrary combined text match.

### P1 — novel trial suppression and identity-schema mismatch
`deep_discovery.py:136-145,202-247`; `program_identity.py:67-117`; `publish_live_feed.py:145-219`.

A simple novel Lucid-MS ID passes the control. A different new metformin record still falls through to generic legacy alias suppression. A novel record citing a previous known NCT in metadata becomes a known mention and is dropped. Publisher fields canonical_id/canonical_name do not match canonical_program_id/canonical_program_name emitted by identity matching, so the public record loses its identity. Keep programme, family and trial-record identities separate; do not fix this by collapsing distinct phases into one programme card.

### P1 — public projections do not consistently update
`app.js:90-147`; `publish_live_feed.py:247-277`.

Real baseline MODIF-MS does not match watcher MODIF-MS / ifenprodil. New live programmes are appended after overrides and keep their initial status despite a subsequent override. Terminated trials remain in Active/Upcoming. Use stable record identifiers and compute sections from the fully merged current state. Greek baseline claims also need supersession rather than append-only contradictory cards.

### P1 — source failure erases comparison baseline
`monitor_research.py:217-244`.

A transient CTG failure drops the last-good record from the newly saved state. Recovery then has no old snapshot to compare. Preserve successful observations across failures and track staleness separately.

### P1 — rejected discovery records cannot be reconsidered
`deep_discovery.py:567-638`; `discovery_source_utils.py:29-70`.

IDs become seen before the gate/publication. A rejected paper later receiving stronger evidence under the same ID is never emitted again. Store record/content/policy versions and separate seen, assessed, quarantined and published state. Implement a durable retry/outbox; the existing warning list is not that mechanism.

### P1 — Greek site recruitment changes are invisible when count stays equal
`monitor_research.py:50-105`.

Only Greek site count is stored. The fixture changes the Greek centre from recruiting to completed while global recruitment and count=1 remain unchanged; no Greece alert results. Track individual centre identity/status/contact, and do not equate country mention with recruiting access.

### P1 — cell work can acquire a human-study label
`deep_discovery.py:300-334`; `publish_live_feed.py:106-170`; `app.js:8-12`.

Patient-derived oligodendrocytes plus mice match the patient substring and set human_data=true. Conversely every preprint is treated as preclinical in the browser. Separate actual human-study context, model, endpoint and peer-review dimensions; ambiguous evidence must remain unknown rather than be upgraded by keywords.

### P1 — malformed optional live feed breaks the baseline fallback
`app.js:124-170`.

Valid JSON containing events={} throws during merge, outside the fetch catch. The existing static baseline is not safely retained. Validate shape/version before mutation, use non-destructive merge, and bound remote fetch time.

## Additional static release gap

**New discoveries are not automatically adopted for follow-up.** The daily watcher loops the static watchlist; it does not consume new verified IDs from live-data/programmes. Weekly seen-ID suppression is not ongoing monitoring. Auto-watch copy therefore overstates the implementation. This is a source-inspection finding rather than a live registration test.

## P2 / defense in depth / limitations

- `apply_weekly` accepts a low-signal record that issue_worthy rejects. The normal workflow DOES filter first: this is missing final-boundary validation, not proof that ordinary runs skip filtering.
- Operational status overrides replace the Greek readout description stored in status. The separate English evidence text survives; this is not total loss of scientific readout information. Separate operational_status from readout_summary.
- Equal CACHED_COMMIT_REF/COMMIT_REF makes netlify_ignore return 0. Netlify documents equal refs on uncached builds, so a deliberate uncached rebuild can be skipped. Test the main command as well as file lists. [Environment variables](https://docs.netlify.com/build/configure-builds/environment-variables/) / [Ignore builds](https://docs.netlify.com/build/configure-builds/ignore-builds/).
- Daily and weekly use separate concurrency groups but update the same Contents-API object without a conflict reload/remerge retry. No real concurrent write was attempted; this is a static reliability gap, not a proven production-loss incident.
- RSS is generated only from news.json, not live-feed.json. Live data updates do not refresh the advertised RSS.
- Netlify's build command runs restoration/RSS generation, not the entire regression suite. Parallel GitHub CI is not by itself a demonstrated deployment gate.

## Decision

**Do not merge/deploy this revision, even if hosting credits are available.** Some defects are inherited from report-only collectors, but automatic public publication raises their consequences. Green unit checks and the earlier five Codex fixes do not establish end-to-end readiness.

Zero-touch publication remains the requirement. These are engineering corrections, not a proposal to make the user approve every research item. Required work is a shared observation/identity schema, safe source handling, durable retry/adoption, gated publisher and consistent public projection, followed by regression and real-preview checks. Production capacity must then be independently verified; this audit did not test billing by issuing a production deploy.

Reproduce on the audit branch with:

```bash
python scripts/restore_data.py
python scripts/build_rss.py
python scripts/test_release_review.py
```

The final command is expected to fail at the reviewed application revision. No API credentials are needed. The first audit export run failed because its checkout was shallow; that harness setup was corrected in the second run. The third run cited above successfully exports source, passes the original checks and fails specifically on the new assertions.

This audit does not validate every historical medical entry, guarantee exhaustive registry/research coverage, certify production authorization, or show that any synthetic failure was actually published. It supports the blocked release decision on reproducible defects in the named code revision.
