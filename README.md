# Job Crawler – Dockerized Template (manual crawl execution)

## Start
```sh
docker network create backend_net   # once
python scripts/download_models.py
docker compose build
docker compose up -d
docker compose logs -f app
docker compose logs -f worker
```

## Local model assets (not tracked in git)

Large model weights are intentionally **not committed** to this repository.

- `models/qwen2.5-0.5b/` → transformers checkpoint directory
- `models/qwen2.5-0.5b-instruct-q4_k_m.gguf` → GGUF file for local llama.cpp-style inference

Fetch them after clone:

```sh
python scripts/download_models.py
```

Optional variants:

```sh
python scripts/download_models.py --skip-gguf
python scripts/download_models.py --skip-transformers
python scripts/download_models.py --models-dir /custom/models/path
```

## API (with X-Internal-Token)
- `GET /api/job-postings/?limit=50`
- `POST /api/crawl/run/`
- `GET /api/crawl/status/`
- `POST /api/parse/job/` (internal parser test, no DB save)
- Browser test page: `GET /api-test/`
  - The page auto-attaches the internal token for local browser testing.
  - Usage details: `docs/API_TEST_PAGE.md`

## Optional GPT parsing
Job-posting parsing works without GPT by using local/rule fallback logic. To test GPT extraction with a development OpenAI account first, inject these env vars into both `app` and `worker`, then restart/recreate the containers:

```sh
OPENAI_PARSER_ENABLED=1
OPENAI_API_KEY=<development-account-key>
OPENAI_PROJECT_ID=<optional-development-project-id>
OPENAI_PROJECT=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
```

For production, keep the same variable names but provide a separate production key/project from deployment secrets. Never commit real OpenAI keys to `.env`, docs, logs, or git.
ChatGPT Plus alone is not enough for server-side API calls; create/use an OpenAI API key from the OpenAI Platform. `OPENAI_PROJECT_ID` can be left blank for a simple first smoke test.

## Local dev without Docker (optional)
```ps1
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# A) SQLite quick test
setx DJANGO_USE_SQLITE 1
python manage.py migrate
python manage.py runserver

# B) Use Docker DB (ensure db is up)
setx DJANGO_USE_SQLITE 0
setx DB_HOST 127.0.0.1
setx DB_PORT 3308
setx DB_NAME job_data
setx DB_USER user
setx DB_PASSWORD <from .env>
python manage.py migrate
python manage.py runserver
```
