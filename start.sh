#!/usr/bin/env bash
set -e

ensure_network() {
  if ! docker network ls --format '{{.Name}}' | grep -q '^backend_net$'; then
    echo "➕ Creating external network backend_net ..."
    docker network create --driver bridge backend_net >/dev/null
  else
    echo "✔ Network backend_net exists"
  fi
}

stoprm_if_exists() {
  for n in "$@"; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${n}$"; then
      echo "🛑 Stopping $n ..."
      docker stop "$n" >/dev/null || true
      echo "🧹 Removing $n ..."
      docker rm "$n" >/dev/null || true
    else
      echo "… $n not present (skip)"
    fi
  done
}

wait_healthy() {
  local name="$1" ; local timeout="${2:-120}"
  local start=$(date +%s)
  while true; do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || true)
    if [ "$status" = "healthy" ]; then
      echo "✔ $name healthy"
      break
    fi
    now=$(date +%s)
    if [ $((now-start)) -gt $timeout ]; then
      echo "⛔ Timeout waiting for $name to be healthy"
      break
    fi
    sleep 2
  done
}

is_service_running() {
  local service="$1"
  docker compose ps --services --status running | grep -q "^${service}$"
}

ensure_runtime_services() {
  local missing=()
  for service in app worker; do
    if ! is_service_running "$service"; then
      missing+=("$service")
    fi
  done

  if [ ${#missing[@]} -eq 0 ]; then
    echo "✔ app/worker already running"
    return
  fi

  echo "⚠ Missing runtime services: ${missing[*]}"
  echo "🔁 Recreating missing runtime services ..."
  docker compose up -d --no-build --force-recreate --remove-orphans "${missing[@]}"

  for service in "${missing[@]}"; do
    if is_service_running "$service"; then
      echo "✔ ${service} recovered"
    else
      echo "⛔ ${service} still not running"
      docker compose logs --tail=80 "$service" || true
      return 1
    fi
  done
}

echo "== BOOTSTRAP START =="

ensure_network

stoprm_if_exists job_crawler_app job_crawler_worker job_crawler_db job_crawler_redis

echo "🔧 Building images ..."
docker compose build app worker

echo "🚀 Starting stack ..."
docker compose up -d

echo "⏳ Waiting for db/redis to be healthy ..."
wait_healthy job_crawler_db 180
wait_healthy job_crawler_redis 90

echo "🛡 Ensuring runtime services (app/worker) are up ..."
ensure_runtime_services

echo "== BOOTSTRAP DONE =="
echo "Status:"
docker compose ps
echo "Logs:"
echo "  docker compose logs -f app"
echo "  docker compose logs -f worker"
