# Windows PowerShell용: start.ps1
# 참고: PowerShell 실행 정책 때문에 막히면 한 번만 Set-ExecutionPolicy -Scope CurrentUser RemoteSigned 실행.


# start.ps1  — 이름 충돌 자동 정리 + 빌드 + 기동 + 헬스체크 대기

$ErrorActionPreference = "SilentlyContinue"

function Ensure-Network($name) {
  $exists = docker network ls --format "{{.Name}}" | Select-String -SimpleMatch $name
  if (-not $exists) {
    Write-Host "➕ Creating external network $name ..."
    docker network create --driver bridge $name | Out-Null
  } else {
    Write-Host "✔ Network $name exists"
  }
}

function StopRm-IfExists([string[]]$names) {
  foreach ($n in $names) {
    $c = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $n
    if ($c) {
      Write-Host "🛑 Stopping $n (if running) ..."
      docker stop $n | Out-Null
      Write-Host "🧹 Removing $n ..."
      docker rm $n | Out-Null
    } else {
      Write-Host "… $n not present (skip)"
    }
  }
}

function Wait-Healthy($name, $timeoutSec=120) {
  $start = Get-Date
  while ($true) {
    $status = docker inspect -f "{{.State.Health.Status}}" $name 2>$null
    if ($status -eq "healthy") { Write-Host "✔ $name healthy"; break }
    if ((Get-Date) - $start -gt (New-TimeSpan -Seconds $timeoutSec)) {
      Write-Error "⛔ Timeout waiting for $name to be healthy"
      break
    }
    Start-Sleep -Seconds 2
  }
}

Write-Host "== BOOTSTRAP START =="

# 1) 외부 공유 네트워크 보장
Ensure-Network "backend_net"

# 2) 이름 충돌 방지: 기존 컨테이너 정리(데이터는 볼륨에 남음)
$names = @(
  "job_crawler_app","job_crawler_worker","job_crawler_beat",
  "job_crawler_db","job_crawler_redis"
)
StopRm-IfExists $names

# 3) 빌드(코드/의존 변경 시) + 기동
Write-Host "🔧 Building images ..."
docker compose build app worker beat

Write-Host "🚀 Starting stack ..."
docker compose up -d

# 4) 헬스체크 대상 대기
Write-Host "⏳ Waiting for db/redis to be healthy ..."
Wait-Healthy "job_crawler_db" 180
Wait-Healthy "job_crawler_redis" 90

Write-Host "== BOOTSTRAP DONE =="
Write-Host "Tips:"
Write-Host "  - Logs (app):   docker compose logs -f app"
Write-Host "  - Logs (worker): docker compose logs -f worker"
Write-Host "  - Logs (beat):   docker compose logs -f beat"
