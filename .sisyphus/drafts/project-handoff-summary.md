# Project Handoff Summary

## Project purpose

This project collects Korean company hiring information and stores it in structured form for downstream matching and recommendation.

Core goals:
- discover company homepages
- discover recruit/careers pages from those homepages
- collect job postings from recruit pages
- parse job postings into structured DB fields
- match trainees/job seekers to postings based on preferences and requirements

## Current architecture

- Backend: Django + DRF
- Crawling: Scrapy
- Background jobs: Celery + Redis
- Database: MariaDB
- Optional parsing support: transformers / local LLM path in `api/llm_parser.py`

Main production flow:

1. Seed and enrich `Company`
2. Check `homepage_url` health
3. Discover `recruits_url` with `discover_careers.py`
4. Collect postings with `job_collector.py`
5. Store/update `JobPosting`
6. Normalize trainee preferences
7. Match trainees to jobs

## Key directories and files

### Django app
- `api/models.py`
  - `Company`: homepage, recruit page, company metadata
  - `JobPosting`: parsed job fields
  - `Trainee`: preference/profile data for matching
- `api/tasks.py`
  - Celery entrypoints for company collection, homepage checks, recruit-page discovery, job collection, and full pipeline runs
- `api/company_sources.py`
  - SWDB / DART ingestion and homepage normalization helpers
- `api/osm_overpass.py`
  - OSM company discovery helpers
- `api/llm_parser.py`
  - structured job-post parsing helpers
- `api/matching.py`
  - ranking and hard-filter logic for trainee/job matching
- `api/views.py`, `api/views_jobs.py`, `api/views_match.py`, `api/views_extract.py`
  - crawl trigger/status, job listing, matching, and normalization endpoints

### Crawlers
- `crawler/crawler/spiders/discover_careers.py`
  - recruit-page discovery logic
- `crawler/crawler/spiders/job_collector.py`
  - job extraction and DB upsert logic

### Project config
- `config/settings.py`
- `config/celery.py`
- `docker-compose.yml`
- `entrypoint.sh`

## Core runtime functions

### Company discovery / enrichment
- `api/tasks.py::collect_osm_companies`
- `api/company_sources.py::collect_swdb_companies`
- `api/company_sources.py::collect_dart_companies`
- `api/tasks.py::find_missing_homepages`
- `api/company_sources.py::check_company_homepages`
- `api/company_sources.py::setup_company_seed_schedules`

### Recruit-page discovery
- `api/tasks.py::run_discover_careers_spiders`
- `api/tasks.py::run_discover_careers_spiders_concurrent`
- `crawler/crawler/spiders/discover_careers.py::parse_page`
- `crawler/crawler/spiders/discover_careers.py::find_direct_recruit_link`
- `crawler/crawler/spiders/discover_careers.py::select_candidate_links`
- `crawler/crawler/spiders/discover_careers.py::looks_like_listing`
- `crawler/crawler/spiders/discover_careers.py::looks_like_onepage`
- `crawler/crawler/spiders/discover_careers.py::detect_post_type`
- `crawler/crawler/spiders/discover_careers.py::save_result`

### Job collection / parsing / storage
- `api/tasks.py::run_job_collector_spiders`
- `api/tasks.py::run_job_collector_spiders_concurrent`
- `crawler/crawler/spiders/job_collector.py::parse_listing`
- `crawler/crawler/spiders/job_collector.py::parse_onepage`
- `crawler/crawler/spiders/job_collector.py::parse_job_detail`
- `crawler/crawler/spiders/job_collector.py::extract_job_from_detail`
- `crawler/crawler/spiders/job_collector.py::extract_all_sections`
- `crawler/crawler/spiders/job_collector.py::upsert_jobposting`
- `api/llm_parser.py::parse_job_details_with_llm`
- `api/llm_parser.py::_extract_dates`
- `api/llm_parser.py::_extract_salary`

### Matching
- `api/matching.py::top_jobs_for_student`
- `api/matching.py::top_students_for_company`
- `api/matching.py::batch_match`

### Counseling normalization
- `api/counseling_field_extractor.py::extract_from_text`
- `api/views_extract.py::CounselingNormalizeView`

## Important data flow

### Company -> recruit page
`Company.homepage_url` -> `discover_careers.py` -> `Company.recruits_url`, `page_type`, `post_type`

### Recruit page -> job postings
`Company.recruits_url` -> `job_collector.py` -> parsed fields -> `JobPosting`

### Trainee -> recommendations
`Trainee` preferences + `JobPosting` structured fields -> `api/matching.py`

## Completed work worth knowing

- company ingestion from OSM / SWDB / DART exists
- homepage liveness checks exist
- recruit-page discovery pipeline exists
- job collection pipeline exists
- parser/storage safeguards for job posting extraction were refined and preserved in current local work
- post URL uniqueness improvements exist
- date extraction exists
- CSV export/import workflow exists
- matching engine exists
- counseling text normalization API exists
- safe integration branch was prepared to bring in discovery/admin/ops changes while preserving current parser/storage logic

## Current branches / merge state worth knowing

- current parser/storage backup branch:
  - `backup/current-parser-storage-20260420`
- safe integration branch:
  - `integration/listing-date-fallback-with-current-parser`

Meaning:
- discovery/admin/ops changes from `listing-date-fallback-validation` were selectively integrated
- parser/storage logic was kept from the current local work

## Current practical limitations

- parser quality is still uneven on noisy recruit pages
- non-job or shell-like pages can still be discovered or stored in some cases
- `qualifications`, `preferred_qualifications`, `hiring_process` boundary contamination still exists
- salary extraction is weak
- some JS-heavy pages are hard for Scrapy-only collection

## Remaining TODOs

### High priority
- improve precision of recruit-page discovery validation
- improve `qualifications` / `preferred_qualifications` / `hiring_process` boundary separation
- improve salary extraction and normalization
- improve page-level rejection of culture / FAQ / landing / shell pages
- validate integration branch on larger, higher-probability undiscovered company sets
- wire `api/postprocess.py::JobPostingNormalizer` into an actual runtime or batch path if it is still needed
- audit and simplify duplicated schedule setup paths (`init_schedule`, `setup_periodic_tasks`, `setup_company_seed_schedules`)

### Medium priority
- strengthen normalized storage for recommendation quality:
  - welfare
  - location
  - employment type
  - salary
  - skills
- improve handling for JS-heavy recruit pages

## Operational commands to know

### Docker
```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f app
docker compose logs -f worker
```

### Django shell
```bash
docker compose exec app python manage.py shell
```

### Full crawl
```bash
docker compose exec app python manage.py shell -c "from api.tasks import run_full_crawling_cycle; run_full_crawling_cycle.delay()"
```

### Company seeding / homepage checks
```bash
docker compose exec app python manage.py shell -c "from api.tasks import collect_osm_companies; collect_osm_companies.delay()"
docker compose exec app python manage.py shell -c "from api.tasks import collect_swdb_companies; collect_swdb_companies.delay()"
docker compose exec app python manage.py shell -c "from api.tasks import collect_dart_companies; collect_dart_companies.delay()"
docker compose exec app python manage.py shell -c "from api.tasks import check_company_homepages; check_company_homepages.delay()"
```

### Discovery only
```bash
docker compose exec app python manage.py shell -c "from api.tasks import run_discover_careers_spiders; run_discover_careers_spiders.delay(limit=10)"
```

### Job collection only
```bash
docker compose exec app python manage.py shell -c "from api.tasks import run_job_collector_spiders; run_job_collector_spiders.delay(limit=10)"
```

### Data export/import
```bash
docker compose exec app python manage.py export_companies_to_csv --output /app/data/companies_latest.csv
docker compose exec app python manage.py import_companies_from_csv /app/data/companies_latest.csv --update
docker compose exec app python manage.py export_snapshot_to_csv --date 2026-04-10
```

### Management commands worth knowing
```bash
docker compose exec app python manage.py import_trainees /app/data/trainees.csv
docker compose exec app python manage.py seed_companies_from_csv --path /app/data/companies.csv
docker compose exec app python manage.py rerun_company_crawl_range --start-id 1 --end-id 100 --chunk-size 25 --workers 2 --sleep-seconds 1.0
docker compose exec app python manage.py init_schedule --hours 8
docker compose exec app python manage.py setup_periodic_tasks
```

### Tests
```bash
docker compose exec app python -m unittest tests.test_spiders -v
```

## API surface worth knowing

- `GET /api/job-postings/`
- `GET /api/job-postings/{id}/`
- `POST /api/crawl/trigger/` (`X-Internal-Token`)
- `GET /api/crawl/status/` (`X-Internal-Token`)
- `GET /api/jobs` (public list endpoint; current query params in code: `active`, `q`, `company`, `region`, `page_size`)
- `POST /api/normalize/counseling` (`X-Internal-Token`, legacy `X-API-KEY`, or `Authorization: Bearer`)
- `POST /api/match/student-top/`
- `POST /api/match/company-top/`
- `POST /api/match/batch/`

## Useful docs

- `README.md`
- `docs/DATA_SOURCES.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/DEVELOPMENT_CONTEXT.md`
- `docs/SETUP_GUIDE.md`
- `docs/RUNBOOK.md`
- `docs/TECHNICAL.md`
- `docs/DB_VS_GPT_COMPARISON_20260414.md`

Docs to read carefully because parts may be stale:
- `docs/SETUP_GUIDE.md`
- `docs/DEVELOPMENT_CONTEXT.md`
- older API usage guides if present

## Notes for the next session

- Treat parser/storage precision as more important than recall.
- Preserve the current local parser/storage behavior unless explicitly changing it with measured validation.
- If working on discovery, validate with changed `recruits_url` cases and manual page review rather than raw count alone.
- Treat current code under `api/`, `crawler/`, and `config/` as source of truth over older docs.
