# Job Crawler – Dockerized Template (8h DB-scheduled)

## Start
```sh
docker network create backend_net   # once
python scripts/download_models.py
docker compose build
docker compose up -d
docker compose logs -f app
docker compose logs -f worker
docker compose logs -f beat
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
- `POST /api/crawl/trigger/`
- `GET /api/crawl/status/`

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
