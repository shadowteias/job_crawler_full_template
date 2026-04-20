# Validation Environment Baseline

- Timestamp (KST): 2026-04-20
- Stack startup mode: `docker compose up -d db redis app worker` (beat intentionally excluded)

## Compose Status

```
NAME                 IMAGE                                                                                      COMMAND                  SERVICE   CREATED          STATUS                 PORTS
job_crawler_app      lms_tp-app                                                                                 "/entrypoint.sh guni…"   app       18 seconds ago   Up 15 seconds          0.0.0.0:8200->8000/tcp, [::]:8200->8000/tcp
job_crawler_db       mariadb:10.5@sha256:a530aeeefd82f4fa5150f391b6c75462140904780338766f6b03acecb1cca3ce       "docker-entrypoint.s…"   db        5 months ago     Up 4 hours (healthy)   0.0.0.0:3308->3306/tcp, [::]:3308->3306/tcp
job_crawler_redis    redis:6.2-alpine@sha256:77697a75da9f94e9357b61fcaf8345f69e3d9d32e9d15032c8415c21263977dc   "docker-entrypoint.s…"   redis     5 months ago     Up 4 hours (healthy)   6379/tcp
job_crawler_worker   lms_tp-worker                                                                              "/entrypoint.sh cele…"   worker    17 seconds ago   Up 14 seconds
```

## Beat Status

```
NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS
```

Beat is not running during validation (required to avoid background schedule interference).

## Django DB Target (sanitized)

```
{'ENGINE': 'django.db.backends.mysql', 'NAME': 'job_data', 'HOST': 'db', 'PORT': '3306', 'USER': 'user'}
```

## Safety Notes

- Docker network `backend_net` exists and is marked external in `docker-compose.yml`.
- This implies potential cross-container visibility; destructive validation operations were constrained to sampled company IDs only.
- No global wipe commands (`down -v`, full table delete) are part of this run plan.
