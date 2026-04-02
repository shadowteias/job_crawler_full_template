# Docs vs Codebase Comparison

## Purpose

This document compares the current Markdown documentation in `docs/` with the actual implementation in the repository.

It answers two questions:

1. What does the documentation say the project does?
2. What is actually implemented in code right now?

---

## Overall Summary

The docs and code agree on the project's core identity:

- a Django/DRF backend
- Celery + Redis for background orchestration
- Scrapy spiders for crawling
- MariaDB-backed persistence
- a pipeline centered on `Company` and `JobPosting`

The main documented product purpose is also accurate: the project collects company seeds from multiple sources, checks homepage health, discovers recruiting pages, crawls job postings, and exposes the results through API endpoints.

The main drift is in the details:

- some functions are documented under `api/tasks.py` but are actually implemented in `api/company_sources.py`
- some documented Celery tasks do not exist in the current codebase
- the LLM documentation describes a local llama/Qwen-style setup, but the checked-in parser currently uses `transformers` zero-shot classification plus regex/section extraction
- some API route shapes in docs do not exactly match the current URL config

---

## Project Purpose: Docs vs Code

| Topic | Documentation claim | Codebase reality | Status |
|---|---|---|---|
| Core product goal | Collect Korean company data and crawl hiring pages/job postings | Implemented through company seed ingestion, homepage checks, career-page discovery, and job posting collection | Aligned |
| Primary sources | OSM, SWDB, DART | Implemented in `api/tasks.py` for OSM and `api/company_sources.py` for SWDB/DART | Aligned |
| Pipeline shape | Company seed → homepage → recruits page → postings | Implemented in `run_full_crawling_cycle()`, `run_discover_careers_spiders()`, and `run_job_collector_spiders()` | Aligned |
| API product surface | Read job postings and trigger/status crawl APIs | Implemented in `api/views.py`, `api/views_jobs.py`, `api/urls.py` | Aligned |
| Matching system | Student-job/company matching exists | Implemented in `api/matching.py` and `api/views_match.py` | Aligned |
| LLM-assisted extraction | Local LLM-based extraction support exists | Partial: code has an `llm_parser`, but implementation differs from docs description | Partially aligned |

---

## Feature-by-Feature Comparison

### 1. Company seed ingestion

| Area | Docs say | Code says | Status |
|---|---|---|---|
| OSM collection | OSM-based regional company collection exists | `collect_osm_companies()` exists in `api/tasks.py` and uses `iter_region_records` from `api/osm_overpass.py` | Aligned |
| SWDB collection | SWDB-based large seed collection exists | `collect_swdb_companies()` exists in `api/company_sources.py` with homepage cleaning and CSV ingestion | Aligned |
| DART collection | DART-based listed-company discovery/enrichment exists | `collect_dart_companies()` exists in `api/company_sources.py` and handles listed-company filtering | Aligned |
| Upsert/dedup policy | Merge by corp code, homepage host, normalized name, name fallback | Implemented by `upsert_company()` in `api/company_sources.py` and OSM dedup helpers in `api/tasks.py` | Mostly aligned |

### 2. Homepage liveness management

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Dead/alive checks | Homepage liveness is periodically checked | `check_company_homepages()` exists in `api/company_sources.py` and updates status/code/fail count fields | Aligned |
| Dead recheck skip | Dead entries can be skipped to save cost | Implemented via `skip_dead=True` and `skip_recent_days` parameters | Aligned |
| Implementation location | Some docs describe this as part of `api/tasks.py` | Actual implementation is in `api/company_sources.py` and imported into `api/tasks.py` | Drift |

### 3. Recruiting page discovery

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Discover careers spider | Finds `recruits_url`, `page_type`, `post_type` | Implemented in `crawler/crawler/spiders/discover_careers.py` | Aligned |
| Page type classification | listing / one_page / main / external | Implemented in spider and stored on `Company` | Aligned |
| External platform detection | wanted / saramin / jobkorea treated specially | Implemented via `EXTERNAL_JOB_DOMAINS` and `contains_external_job_link()` | Aligned |
| Negative keyword handling | Docs mention negative keyword filtering/alternative links in some places | Code still contains `has_negative_keywords()` and `find_alternative_job_links()`, but current main flow is driven by `find_direct_recruit_link`, listing/one-page heuristics, and external link checks | Partially aligned |

### 4. Job posting collection

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Job collector spider | Extracts postings and upserts `JobPosting` | Implemented in `crawler/crawler/spiders/job_collector.py` | Aligned |
| Structured field extraction | Description, qualifications, preferred qualifications, process, benefits, location, salary | Implemented through parser hooks plus fallback section extraction in `extract_job_from_detail()` | Aligned |
| Text/image/external handling | `post_type` governs behavior | Implemented: non-text post types are skipped in `start_requests()` | Aligned |
| Unique `post_url` behavior | Docs mention hash-based uniqueness improvements | Implemented in `_make_unique_post_url()` | Aligned |

### 5. Data model

| Area | Docs say | Code says | Status |
|---|---|---|---|
| `Company` model | Stores homepage, recruits URL, source/enrichment, DART/SWDB fields | Implemented in `api/models.py` | Aligned |
| `JobPosting` model | Stores main job content and metadata | Implemented in `api/models.py` | Aligned |
| `Trainee` model | Exists for matching | Implemented in `api/models.py` | Aligned |

### 6. API surface

| Area | Docs say | Code says | Status |
|---|---|---|---|
| `/api/job-postings/` | Read-only listing/detail | Implemented via DRF router and `JobPostingViewSet` | Aligned |
| `/api/crawl/trigger/` | Trigger full crawl | Implemented in `CrawlTriggerView` | Aligned |
| `/api/crawl/status/` | Read current crawl status | Implemented in `CrawlStatusView` | Aligned |
| `/api/jobs/` | Filterable jobs list | Route currently registered as `path("jobs", ...)` without trailing slash | Minor drift |
| Matching endpoints | Student/company/batch match APIs exist | Implemented in `api/views_match.py`; routes also omit trailing slash in current config | Minor drift |

### 7. Scheduling and operations

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Celery worker/beat orchestration | Background jobs and scheduled tasks exist | Implemented through Celery tasks plus `django-celery-beat` usage | Aligned |
| DB-backed periodic schedule setup | Schedules can be created/updated from code | `setup_company_seed_schedules()` exists in `api/company_sources.py` | Aligned |
| Full crawling cycle scheduling | Docs describe full crawling cadence | `run_full_crawling_cycle()` exists; code dispatches OSM → optional homepage fill → discover → collect | Mostly aligned |

### 8. Matching system

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Weighted matching | Skills/role/location/etc. weighted scoring | Implemented in `api/matching.py` using documented weight structure | Aligned |
| API exposure | Matching APIs available | Implemented in `api/views_match.py` and `api/urls.py` | Aligned |

### 9. LLM-assisted extraction

| Area | Docs say | Code says | Status |
|---|---|---|---|
| Local LLM integration | Docs describe local llama-cpp/Qwen-based extraction support | Current `api/llm_parser.py` imports `transformers` models and pipeline, not `llama_cpp` | Drift |
| Parser purpose | Extract structured fields from job content | Implemented: `_extract_dates()`, `_extract_salary()`, `parse_job_details_with_llm()` | Partially aligned |
| Dedicated Celery tasks | Docs mention `crawl_company_careers`, `crawl_single_company_career`, `extract_job_content` | These task names were not found in current `api/tasks.py` | Mismatch |

---

## Concrete Mismatches Worth Fixing in Docs

### 1. Task ownership drift

The docs repeatedly treat SWDB, DART, homepage checks, and schedule setup as if they are centered in `api/tasks.py`.

In the current codebase, these are actually implemented in:

- `api/company_sources.py`
  - `collect_swdb_companies()`
  - `collect_dart_companies()`
  - `check_company_homepages()`
  - `setup_company_seed_schedules()`

`api/tasks.py` imports them and contains the OSM and crawl orchestration layer.

### 2. LLM stack description is outdated

The documentation describes a more explicitly local-LLM pipeline with llama-cpp/Qwen.

The checked-in parser currently does this instead:

- imports `transformers`
- uses a zero-shot classifier in `is_job_posting()`
- uses regex/section extraction in `parse_job_details_with_llm()`

That means the docs currently overstate or mischaracterize the actual LLM implementation.

### 3. Documented task names missing from code

The docs mention these tasks as current:

- `crawl_company_careers`
- `crawl_single_company_career`
- `extract_job_content`

Those names do not appear in the current `api/tasks.py` that is checked into this repository.

### 4. API path shape drift

The docs often present trailing-slash forms for some endpoints.

Current `api/urls.py` uses:

- `path("jobs", ...)`
- `path("match/student-top", ...)`
- `path("match/company-top", ...)`
- `path("match/batch", ...)`

So the docs should either be updated to match the current route shape or the router should be normalized if trailing slashes are intended.

### 5. One explored path does not exist in this checkout

An earlier codebase exploration hinted at a `src/dashboard/` area, but that path is not present in the current repository checkout. It should not be described as part of the current system unless it is restored or exists in another branch.

---

## Recommended Documentation Updates

If the goal is to make the docs match the current codebase, the highest-value updates are:

1. Update all source-ingestion and homepage-check references to point to `api/company_sources.py`.
2. Rewrite the LLM section so it reflects the current `transformers` + regex/section-extraction implementation.
3. Remove or mark as historical any references to missing task names.
4. Normalize endpoint examples to the current `api/urls.py` definitions.
5. Keep `docs/TECHNICAL.md` as the authoritative operations overview, but reduce duplicated or stale implementation details in the other docs.

---

## Evidence Index

Primary implementation files checked for this comparison:

- `api/tasks.py`
- `api/company_sources.py`
- `api/models.py`
- `api/views.py`
- `api/views_jobs.py`
- `api/views_match.py`
- `api/urls.py`
- `api/matching.py`
- `api/llm_parser.py`
- `crawler/crawler/spiders/discover_careers.py`
- `crawler/crawler/spiders/job_collector.py`

Primary documentation files compared:

- `docs/TECHNICAL.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/DEVELOPMENT_CONTEXT.md`
- `docs/RUNBOOK.md`
- `docs/SETUP_GUIDE.md`
- `docs/DATA_SOURCES.md`
