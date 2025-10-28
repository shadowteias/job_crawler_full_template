#!/bin/sh
set -e

# Wait for DB if configured
if [ -n "$DB_HOST" ]; then
python - <<'PY'
import os, socket, time
host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "3306"))
print(f"Waiting for database {host}:{port} ...")
for _ in range(90):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("DB is up.")
            break
    except OSError:
        time.sleep(1)
else:
    print("DB wait timeout, continuing anyway...")
PY
fi

if [ -f manage.py ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput || true
  echo "Collecting static files..."
  python manage.py collectstatic --noinput || true
  echo "Initializing schedule..."
  python manage.py init_schedule || true
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 -w 2 -k gthread --threads 4 --timeout 90
fi
