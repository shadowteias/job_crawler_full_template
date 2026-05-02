# Small Manual Crawl and API Test Page Check (2026-05-01)

## Scope

- Run a minimal manual crawl against a small number of already-known live targets.
- Confirm whether a browser API test page existed.
- Add a Django API test page when absent.
- Check whether GPT development-account parsing and later production-account switching were implemented/documented.

## Live API check

Base URL used from this environment: `http://127.0.0.1:8200`.

Authenticated status check succeeded:

```json
{"running": false, "status": {"state": "IDLE"}}
```

`GET /api/jobs?active=1` was reachable and returned stored postings.

## Manual crawl run

Payload used:

```json
{
  "run_homepage_check": false,
  "run_discover": true,
  "run_collect": true,
  "discover_limit": 2,
  "collect_limit": 2,
  "workers": 1
}
```

Final crawl status:

```json
{
  "state": "DONE",
  "mode": "manual",
  "workers": 1,
  "run_homepage_check": false,
  "run_discover": true,
  "run_collect": true,
  "results": {
    "discover": {"total": 2, "saved": 2, "failed": 0, "elapsed": 19.61008882522583},
    "collect": {"total": 2, "completed": 2, "failed": 0, "elapsed": 85.30898332595825}
  }
}
```

Interpretation: the manual route queued correctly, Redis status moved through `discover` and `collect`, both small-stage runs finished without reported subprocess failures, and the API remained reachable after completion.

## API test page

Before this work, repository search found no templates, static UI files, `render(...)`, `TemplateResponse`, `TemplateView`, or `template_name` usage.

Added:

- `api/views_ui.py`
- `templates/api_test.html`
- `config/urls.py` route: `GET /api-test/`

The currently running Gunicorn process still returned 404 for `/api-test/` immediately after the code change because the URLConf was loaded before the edit and Docker is unavailable in this WSL environment for restart. The page should be available after restarting/recreating `app`.

## GPT parser readiness

Before this work, `api/llm_parser.py` only used local Transformers/rule fallback and no OpenAI package/config was present.

Added optional GPT parsing:

- `OPENAI_PARSER_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_PROJECT`
- `OPENAI_ORGANIZATION`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`

Development account test and production account switch instructions were documented in `README.md`, `docs/SETUP_GUIDE.md`, `docs/TECHNICAL.md`, and `docs/GPT_PARSER_SETUP.md`.

## Verification

- `python3 -m py_compile api/llm_parser.py api/views_ui.py config/urls.py api/views.py api/urls.py api/tasks.py api/company_sources.py config/settings.py` passed.
- `python3 -m unittest tests.test_spiders -v` passed: 44 tests OK.
- LSP for modified Python files only reports missing third-party imports in this local WSL Python environment (`django`, `transformers`, `openai`), not syntax errors.
