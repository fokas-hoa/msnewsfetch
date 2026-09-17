# PR #2 — Safety remediation, 17 September 2026

## Baseline and acceptance

The independent review targeted `13fd7433040d90fad96265af3d4587a209e229e8`, against main `be8063aa4b9ba4215089079d8f1819b5f29e3927`. It found release-blocking defects despite the earlier small green suite. The user authorised repairs, then merge/deployment only when safe. This document describes code acceptance, **not a statement that deployment has already succeeded**. Refer to the exact final commit's CI/deployment checks for release status.

## Corrections

| Audit concern | Implemented boundary | Verification |
|---|---|---|
| Failed CTIS fetch becoming halt=false/status=null/Greece=false | Official successful observation required; unknown remains null; mirrors distinct | Original release cases + malformed HTTP200, history ambiguity, mirror-only |
| Mirror conflict overriding official | Official status selected, separate mirror observation and age | Publisher and browser contract tests |
| New registry ID lost through generic alias/prior reference | Exact record identity before programme matching; families do not deduplicate trials | Original alias/prior-reference cases, distinct-ID tests |
| Name-keyed/stale/live-added card overrides | ID projection after merging baseline/live programmes; operational fields independent | Original integration cases + real Chromium terminal transition |
| Ended trial remains active/readout erased | Terminal projection, separate readout_summary | Release and browser tests |
| Failed fetch destroys last-good state | Copy prior state, update only successful snapshots; source-health separately | Success → failure → successful transition test |
| Seen means permanently dropped | Per-source durable journal with fingerprint, disposition, policy version | Rejected retry; changed content/policy; published unchanged silent |
| Greek site count misses local recruitment changes | Structured sites and local status/contacts; per-field last-observed dates | Local-status change and incomplete-list freshness tests |
| Patient-derived cells/human preprint misclassification | Population and publication status independent; explicit human-study signals | Original cases + numeric enrolled-human and randomized mouse cases |
| Malformed remote feed breaks baseline | Schema validation, bounded fetch, nonmutating merge, cached/baseline fallback | Node startup scenarios + Chromium desktop/mobile cases |
| New trials not actually monitored | Verified watch targets adopted with initial snapshot; explicit primary paths | Adoption/first-transition tests; only structured primary targets |
| Publisher trusts upstream pipeline blindly | Final current-policy/provenance/identity/source gate | Bad fields, status/proof mismatch, URL spoof, secondary source tests |
| Concurrent writers / acknowledged-but-unpublished state | Feed, RSS and collector journal in one non-force transaction; reload/retry | 409 competing writer; same-mode conflict; failed network acknowledgment |
| RSS remains static | RSS generated in same transaction; Netlify proxy | XML parse/escaping and merged-event test |
| Technical refresh masquerades as science update | latest_event_at separate; warnings not event refresh | Reconfirmation/no-redate and warning tests |
| Uncached build ignored / green CI unrelated to deploy | Equal/missing refs rebuild; Netlify build executes same offline gate | Original uncached test, build_site execution |

## Test integrity

All **19 original release assertions** are retained. Their fixture setup was adapted to the new, required publication contract: successful source provenance, current policy, stable IDs and registry URLs consistent with each named synthetic trial. Tests which constructed an unverified low-level `change()` can no longer implicitly impersonate a successful registry fetch. Assertions were not deleted or relaxed to make the suite green.

The older `test_live_feed.py` fixture similarly supplies a valid parsed observation rather than bypassing the boundary. The original independent failure report remains available on `audit/pr2-release-review`; its failures describe the earlier revision and are not rewritten.

At the time of preparing this patch, local execution passed the 19 release tests, all 29 added hardening tests, the existing identity/discovery/feed/RSS/JS/ignore checks, four Node startup/fallback scenarios and eight real Chromium desktop/mobile scenarios. The Chromium suite renders built HTML/CSS/JS in a blank browser document with a mocked fetch boundary; it is not an external-production-network test. All simulated research data remain offline.

A read-only live-source smoke and exact-commit GitHub/Netlify validation are required before claiming a successful release. They must be reported separately from local tests. Code merging does not restore exhausted Netlify production credits.

## Remaining deliberate limitations

No claim of perfect literature recall, exhaustive registry coverage or verified treatment efficacy is made. Bibliographic and programme-page events use neutral source-observation templates. A failed official source stays unknown, even if a mirror has text. Rejected candidates are reassessed when re-observed; inaccessible or out-of-window records cannot be magically refreshed. Historical baseline claims were not a full new medical review. Audit issues are best-effort notifications, not a durable guaranteed delivery service. Zero-touch operation does not mean zero possibility of an upstream or heuristic error.

## Release procedure

Keep main/live-data untouched while testing fixtures. Upload the final code as one batched development commit, verify the exact-head CI and preview, and check hosting capacity. Make at most one intentional production release under the user's authorisation; do not buy credits or trigger repeated deployments to work around billing. Verify the deployed app shell, live feed and RSS separately before reporting them live.
