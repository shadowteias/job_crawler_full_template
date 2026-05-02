# 2026-04-27 Project Status and Remaining Work

## Purpose

This document summarizes:

1. what was included in the recent pushed branches,
2. which functions, commands, and files implement each capability,
3. what phase the project is currently in,
4. and what work remains.

It is intended as a practical status handoff for continuing development without losing context.

---

## Current Project Phase

The project is no longer in the early “can we crawl anything?” stage.

It is currently in a **late stabilization / pre-wrap-up phase**:

- core collection pipeline exists,
- major operational issues have been reduced,
- recruit-page discovery has gone through multiple measured experiments,
- job posting validity rules are implemented,
- admin performance was improved,
- manual crawl control API was added,
- CSV export path exists and has been validated.

The remaining work is mostly about:

- cleanup,
- recommendation trust,
- surface simplification,
- and final operational/documentation quality.

---

## Branches and What They Represent

### 1. `listing-date-fallback-validation`

This branch was used to validate and preserve:

- listing-date fallback behavior,
- discovery experiments,
- CSV snapshot outputs,
- and several documentation artifacts.

### 2. `main-selected-integration`

This branch was created from the latest GitHub `main` and then selectively integrated with only the validated feature set.

This is the branch that currently contains the cleaner, main-based integration work, including:

- selected discovery improvements,
- posting validity and stale expiration behavior,
- listing-date fallback,
- and the new manual crawl API.

---

## Included Capabilities and Where They Are Implemented

## A. Company source ingestion / seed collection

### What it does
- collects company seeds from OSM,
- enriches or imports from SWDB / DART,
- maintains `Company` rows.

### Main implementation files
- `api/tasks.py`
  - `collect_osm_companies()`
- `api/company_sources.py`
  - `collect_swdb_companies()`
  - `collect_dart_companies()`
  - `check_company_homepages()`

### Related commands
- `api/management/commands/import_companies_from_csv.py`
- `api/management/commands/seed_companies_from_csv.py`

---

## B. Homepage liveness checking

### What it does
- verifies whether company homepages are alive,
- updates homepage status fields,
- supports manual recheck and range-based execution.

### Main implementation files
- `api/company_sources.py`
  - `check_company_homepages()`
- `scripts/homepage_check_range.py`
  - parallel range homepage checker used for operational validation

### Important fields
- `Company.homepage_url_status`
- `Company.homepage_checked_at`
- `Company.homepage_last_status_code`
- `Company.homepage_fail_count`

---

## C. Recruit-page discovery

### What it does
- finds likely recruit pages from company homepages,
- classifies them as `listing`, `one_page`, `main`, or `external`,
- stores `recruits_url`, `page_type`, and `post_type`.

### Main implementation file
- `crawler/crawler/spiders/discover_careers.py`

### Important current behaviors
- same-response parsing cache
- direct recruit-link ranking instead of naive first-match selection
- hard stop after the first confident save

### Related task entrypoints
- `api/tasks.py`
  - `run_discover_careers_spiders()`
  - `run_discover_careers_spiders_concurrent()`

### Important implementation areas in code
- `find_direct_recruit_link()`
- `looks_like_listing()`
- `looks_like_onepage()`
- `detect_post_type()`
- `save_result()`

---

## D. Job posting collection

### What it does
- crawls actual recruit pages,
- extracts posting text and structured fields,
- stores/updates `JobPosting` rows.

### Main implementation file
- `crawler/crawler/spiders/job_collector.py`

### Related task entrypoints
- `api/tasks.py`
  - `run_job_collector_spiders()`
  - `run_job_collector_spiders_concurrent()`

### Important collection behaviors
- supports `listing`, `one_page`, and `main` post styles
- uses parser-assisted extraction where possible
- can update existing postings by `post_url`

---

## E. Posting validity and stale cleanup

### What it does
- prevents clearly outdated postings from remaining active,
- applies a currentness rule before accepting a posting,
- expires postings that are no longer rediscovered for a company.

### Main implementation files
- `crawler/crawler/spiders/job_collector.py`
- `api/llm_parser.py`

### Current validity rule
A posting is considered valid when:

- `deadline_at >= today`, or
- `deadline_at` is missing and `posted_at` is within the last 30 days.

Otherwise it should not remain active.

### Important functions
- `evaluate_posting_validity()` in `job_collector.py`
- `deactivate_existing_posting()` in `job_collector.py`
- `extract_posting_dates()` in `api/llm_parser.py`

---

## F. Listing-date fallback

### What it does
- when a detail page lacks visible dates,
- it can use date hints from the listing page.

### Main implementation files
- `crawler/crawler/spiders/job_collector.py`
- `api/llm_parser.py`

### Important functions
- `extract_listing_dates_for_anchor()`
- `extract_posting_dates_for_text()`
- `parse_job_detail(... listing_deadline_at, listing_posted_at ...)`

### Validation document
- `docs/2026-04-09_listing_date_fallback_validation.md`

---

## G. Stale posting expiration

### What it does
- after a company crawl completes successfully,
- previously stored postings that are not rediscovered can be marked expired/inactive.

### Main implementation file
- `crawler/crawler/spiders/job_collector.py`

### Important method
- `closed(self, reason)`

---

## H. Manual range rerun and operational testing tools

### What it does
- allows chunked reruns over company ID ranges,
- supports safe validation on small groups instead of full-scale reruns.

### Main implementation files
- `api/management/commands/rerun_company_crawl_range.py`
- `scripts/homepage_check_range.py`

### Typical use
- rerun discovery and collection for a narrow company range,
- compare before/after behavior,
- validate changes conservatively.

---

## I. CSV export

### What it does
- exports both `Company` and `JobPosting` datasets to validated CSV snapshots,
- uses safer quoting and newline handling than the earlier export path.

### Main implementation file
- `api/management/commands/export_snapshot_to_csv.py`

### Important export characteristics
- UTF-8 BOM (`utf-8-sig`)
- `csv.QUOTE_ALL`
- normalized embedded line breaks
- date and JSON-safe serialization

### Current notable snapshot files
- `data/2026-04-10_companies_snapshot.csv`
- `data/2026-04-10_job_postings_snapshot.csv`

---

## J. Job / company matching APIs

### What it does
- produces top job matches for a student,
- top student matches for a company,
- and batch matching.

### Main implementation files
- `api/views_match.py`
- `api/matching.py`

### Exposed endpoints
- `POST /api/match/student-top`
- `POST /api/match/company-top`
- `POST /api/match/batch`

### Status
- implemented and exposed,
- but not yet as deeply validated as the crawl and posting pipeline.

---

## K. Job listing APIs

### Main implementation files
- `api/views.py`
- `api/views_jobs.py`
- `api/serializers.py`

### Exposed endpoints
- `GET /api/job-postings/`
- `GET /api/job-postings/{id}/`
- `GET /api/jobs`

### Status
- functional,
- currently adequate for reading stored results.

---

## L. Counseling normalization API

### Main implementation files
- `api/views_extract.py`
- `api/urls_normalize.py`
- `api/counseling_field_extractor.py`

### Exposed endpoint
- `POST /api/normalize/counseling`

### Status
- exposed and callable,
- separate from the crawl/recruit pipeline.

---

## M. Manual non-periodic crawl API

### What it does
- supports explicit user-triggered crawl execution by API,
- allows choosing a company ID range and stage subset,
- is intended to support the project’s new manual/non-periodic operational direction.

### Main implementation files
- `api/views.py`
- `api/tasks.py`
- `api/urls.py`

### Exposed endpoint
- `POST /api/crawl/run/`

### Request controls
- `company_id_start`
- `company_id_end`
- `homepage_limit`
- `discover_limit`
- `collect_limit`
- `workers`
- `run_homepage_check`
- `run_discover`
- `run_collect`
- `force_homepage_recheck`

### Validation performed
- `GET /api/crawl/status/` returned `200`
- `POST /api/crawl/run/` returned `202 started`

### Related task
- `api.tasks.run_manual_crawl`

---

## Current API Inventory

### Public API surface currently exposed
- `GET /api/job-postings/`
- `GET /api/job-postings/{id}/`
- `GET /api/jobs`
- `GET /api/crawl/status/`
- `POST /api/crawl/run/`
- `POST /api/match/student-top`
- `POST /api/match/company-top`
- `POST /api/match/batch`
- `POST /api/normalize/counseling`

---

## What Is Still Weak, Untested, or Incomplete

## 1. Recommendation-grade trust filtering is not yet a first-class layer

The system now filters outdated postings much better than before, but it still does not have a dedicated “recommendable postings only” trust layer.

That means:
- active postings are more current,
- but recommendation-specific confidence scoring is still unfinished.

## 2. Discovery is improved but still not perfect

Discovery now has:
- caching,
- hard stop,
- better direct-link ranking.

But it can still pick generic HR/careers pages in some companies.

This was investigated heavily, and several aggressive fixes were intentionally rejected because they caused regressions.

## 3. Matching quality has not been validated as deeply as crawl quality

Matching APIs exist, but the crawl-side trust work has received much more experimental validation than the matching layer.

## 4. Manual crawl API is validated at the response/trigger level, but not yet deeply load-tested

It has been wired and responded correctly, but it still deserves more real-world operational use.

## 5. Old docs names and assumptions
- older task names still survive in some docs
- older periodic assumptions should be cleaned up so the code/docs story is consistent

## Miscellaneous leftover utility
- `api.tasks.hello`
  - likely a cleanup candidate

---

## Current Project Phase

This project is in a **late integration and cleanup phase**.

What is already true:
- crawl pipeline exists,
- recruit discovery exists,
- currentness filtering exists,
- manual crawl API now exists,
- admin performance was improved,
- export path exists.

What remains is less about inventing core features and more about:
- narrowing trust for recommendation use,
- simplifying the operational surface,
- cleaning legacy assumptions,
- and documenting final behavior clearly.

---

## Suggested Wrap-up Plan

## Phase 1 — API surface stabilization
- Keep `crawl/run/` as the primary manual execution API
- Document all API payloads and auth expectations clearly

## Phase 2 — Cleanup of stale/legacy assumptions
- review docs and runtime guidance for manual execution only
- remove outdated operational assumptions that no longer match the intended model

## Phase 3 — Recommendation trust layer
- define a high-trust subset of active postings
- do not assume all active postings are recommendation-ready
- validate recommendation precision manually before exposing broadly

## Phase 4 — Operational hardening
- keep export workflow documented
- verify admin remains usable under larger row counts
- verify manual crawl API under repeated real use

## Phase 5 — Final release documentation
- one concise “how the system works now” doc
- one concise “what is intentionally excluded / still weak” doc

---

## Bottom Line

The project now has a real usable API surface for:

- job retrieval,
- matching,
- counseling normalization,
- crawl status,
- legacy full-cycle crawl triggering,
- and new manual on-demand crawl execution.

The next major work is not “find more pages at any cost.”

It is:

- clean up stale periodic assumptions,
- keep the operational model coherent,
- and build a recommendation trust layer strong enough that users are not shown expired or misleading postings.
