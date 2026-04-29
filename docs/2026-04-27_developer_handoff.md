# 2026-04-27 Developer Handoff

## Can a new session continue from `docs/` alone?

Partially, but **not safely enough**.

The existing docs describe many important experiments and outcomes, but they are spread across multiple files and do not provide a single continuation guide that answers all of these at once:

- what is currently on `main`,
- what was tried and intentionally reverted,
- what the current operational direction is,
- what APIs exist now,
- what the next safest development priority is.

This handoff document is meant to solve that.

---

## Current Source-of-Truth Branch State

As of this handoff:

- the important selected changes were pushed to **GitHub `main`**,
- the large experimental branches were used to test ideas, but only some of those ideas were kept,
- `main` should be treated as the current source of truth for future work.

Do **not** assume that every experiment described in earlier docs was kept.

---

## Project Goal (Practical Interpretation)

The project is **not** trying to maximize posting volume.

The current product principle is:

> It is acceptable to miss some real job postings, but it is **not acceptable** to recommend expired postings, generic hiring-info pages, or low-trust results that disappoint users.

Practical consequence:

- precision and currentness are more important than recall,
- manual/controlled crawl operation is preferred over blind periodic automation,
- downstream recommendation trust matters more than raw crawl count.

---

## What Is Currently Implemented and Kept

## 1. Recruit-page discovery improvements kept

File:
- `crawler/crawler/spiders/discover_careers.py`

Kept behaviors:
- response-level parsing cache
- hard stop after first confident save
- direct recruit-link ranking instead of naive first-match selection

These were tested and kept because they either improved behavior or reduced risk without introducing obvious regression.

## 2. Posting validity logic kept

Files:
- `crawler/crawler/spiders/job_collector.py`
- `api/llm_parser.py`

Kept behaviors:
- valid posting rule:
  - `deadline_at >= today`, or
  - no deadline but `posted_at` within the last 30 days
- stale posting expiration for company reruns
- listing-date fallback when detail page lacks dates

## 3. Admin performance improvements kept

Files:
- `api/admin.py`
- `config/settings.py`
- `.env`

Kept behaviors:
- `JobPostingAdmin` no longer has the huge `company` list filter
- `list_select_related = ("company",)`
- `autocomplete_fields = ("company",)`
- `list_per_page = 50`
- default `DEBUG=False`
- environment currently set to `DJANGO_DEBUG=False`

## 4. Manual on-demand crawl API kept

Files:
- `api/tasks.py`
- `api/views.py`
- `api/urls.py`

Kept endpoint:
- `POST /api/crawl/run/`

Purpose:
- user-triggered non-periodic crawl execution
- stage-level control (`homepage_check`, `discover`, `collect`)
- range control (`company_id_start`, `company_id_end`)

This is the preferred operational direction going forward.

## 5. CSV export command kept

File:
- `api/management/commands/export_snapshot_to_csv.py`

Characteristics:
- UTF-8 BOM
- quote-all CSV
- newline normalization
- safer real-world export format than the older export path

---

## What Was Tried but Intentionally Reverted

These are important because a future developer may be tempted to retry them without knowing they already failed in sample comparison.

## 1. Broad one-page tightening in discovery

Reason reverted:
- did not prove improvement in before/after samples,
- sometimes introduced regressions,
- too easy to overfit and break valid pages.

## 2. Deeper follow-up from generic one-page pages

Reason reverted:
- sometimes improved cases,
- but also created regressions,
- not trustworthy enough to keep.

## 3. Lightweight post-discovery verifier

Reason reverted:
- sample-based testing did not show measurable improvement,
- too weak to justify the added complexity.

## 4. Aggressive high-confidence collector gate

Reason reverted:
- filtered some bad rows,
- but also killed real useful postings,
- false-negative cost was too high.

Bottom line:

> Discovery-stage and collector-stage aggressive precision tuning was repeatedly tested and mostly rejected unless evidence was clearly positive.

Future work should respect that history.

---

## What the Current API Surface Looks Like

Main exposed API endpoints:

- `GET /api/job-postings/`
- `GET /api/job-postings/{id}/`
- `GET /api/jobs`
- `GET /api/crawl/status/`
- `POST /api/crawl/trigger/`  ← legacy-ish full-cycle trigger
- `POST /api/crawl/run/`      ← preferred manual crawl API
- `POST /api/match/student-top`
- `POST /api/match/company-top`
- `POST /api/match/batch`
- `POST /api/normalize/counseling`

Reference docs:
- `docs/2026-04-23_api_surface_and_wrapup_plan.md`

---

## Current Operational Reality

### 1. Manual run is now preferred over periodic scheduling

There are still periodic scheduling remnants in the codebase, but the intended direction is now:

- manual,
- targeted,
- range-limited,
- non-periodic crawl execution.

### 2. Docker Desktop / WSL remains a real operational risk

Repeatedly observed:
- WSL Ubuntu can stay alive while `docker-desktop` stops,
- long-running builds or heavy execution can destabilize Docker Desktop,
- work should be chunked conservatively.

### 3. Large-volume brute-force changes are risky

The safest pattern discovered so far is:
- small controlled change,
- sample-based rerun,
- manual page inspection,
- only keep the change if it clearly helps.

---

## Most Important Existing Docs to Read First

If continuing work in a new session, read these in this order:

1. `docs/2026-04-27_project_status_and_remaining_work.md`
2. `docs/2026-04-23_api_surface_and_wrapup_plan.md`
3. `docs/2026-04-23_main_selected_integration.md`
4. `docs/2026-04-10_discovery_iteration_status.md`
5. `docs/2026-04-09_listing_date_fallback_validation.md`

These collectively explain:
- what was integrated,
- what was rejected,
- what APIs exist,
- what the project phase is,
- and what still needs to be done.

---

## Current Phase

The project is in a **late stabilization / wrap-up preparation phase**.

It already has:
- company ingestion,
- homepage liveness handling,
- recruit-page discovery,
- job crawling,
- posting validity rules,
- exports,
- admin usability fixes,
- and a manual crawl API.

It does **not yet** have a final recommendation-grade trust layer.

That is likely the next major product-quality step.

---

## Highest-Priority Remaining Work

## 1. Recommendation trust layer

This is the most important remaining product task.

Reason:
- active postings are much better than before,
- but “active” is still not equal to “safe to recommend to users.”

Needed outcome:
- a narrower `recommendable` subset,
- based on currentness + page quality + parsing confidence.

## 2. Legacy / periodic cleanup

Still present and should be reviewed:
- `api/management/commands/setup_periodic_tasks.py`
- `api/management/commands/init_schedule.py`
- `api.company_sources.setup_company_seed_schedules()`
- old docs that assume beat-first crawling

## 3. API surface simplification

Need to decide what to do with:
- `POST /api/crawl/trigger/`

Because now both exist:
- legacy full-cycle trigger
- new manual stage-selective trigger

The project would be cleaner with one clearly preferred operational API.

## 4. Final documentation cleanup

Old task names still appear in some docs and should be normalized.

Examples already known to be stale in docs:
- `crawl_company_careers`
- `crawl_single_company_career`
- `extract_job_content`

---

## What a New Session Should Do First

If a future session continues development, the safest sequence is:

1. Read the docs listed above.
2. Confirm `main` is the base branch.
3. Verify runtime:
   - `docker compose ps`
   - `python manage.py check`
   - admin loads correctly
4. If working on crawling behavior:
   - use small company-ID ranges first
   - compare before/after with real page inspection
5. Prefer recommendation-layer improvements before touching discovery aggressively again.

---

## Final Handoff Summary

If you only remember a few things from this handoff, remember these:

1. `main` is now the source of truth.
2. Only a subset of earlier experiments was intentionally kept.
3. The current direction is **manual, non-periodic crawl control**.
4. Discovery has been improved, but aggressive discovery tweaks have a history of regression.
5. The most important remaining product problem is **recommendation trust**, not raw crawl volume.
