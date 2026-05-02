# 신규 컴퓨터 셋업 가이드

## Job Crawler 프로젝트 설정 매뉴얼

---

## 1. 필수 요구사항

### 하드웨어
- **OS**: Windows 10/11, macOS, 또는 Linux (Ubuntu 20.04+)
- **RAM**: 최소 8GB (LLM 사용 시 16GB 권장)
- **디스크**: 20GB 이상 여유 공간
- **Docker**: Desktop 또는 Engine 설치 가능

### 필수 소프트웨어
- [Docker Desktop](https://www.docker.com/products/docker-desktop) (Windows/macOS)
- 또는 Docker Engine + Docker Compose (Linux)
- [Git](https://git-scm.com/)

---

## 2. 레포지토리 클론

```bash
# 레포지토리 클론
git clone https://github.com/shadowteias/job_crawler_full_template.git
cd job_crawler_full_template

# 최신 브랜치로 업데이트
git pull origin main
```

---

## 3. Docker 네트워크 생성

```bash
# Docker 네트워크 생성 (처음 한 번만)
docker network create backend_net
```

---

## 4. 환경 설정

### 4.1 .env 파일 생성

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 입력:

```bash
# Database (docker-compose의 db 컨테이너 사용)
DB_NAME=job_data
DB_USER=user
DB_PASSWORD=uR7!fP9v@L3xA2qT#e6K
DB_HOST=db
DB_PORT=3306

# Redis
REDIS_URL=redis://redis:6379/0

# Django
DJANGO_SECRET_KEY=your_secret_key_here_change_in_production
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=*

# API
API_INTERNAL_TOKEN=internal_token_8h_7Kifc0r

# Optional GPT parser for job-posting extraction.
# 개발 테스트: 개발용 GPT/OpenAI 계정 키와 프로젝트를 넣는다.
# 실서비스: 배포 환경에서 별도 production key/project를 주입한다.
OPENAI_PARSER_ENABLED=0
OPENAI_API_KEY=
# Optional OpenAI Platform project id. Blank is OK for first smoke test.
OPENAI_PROJECT_ID=
# Legacy alias; prefer OPENAI_PROJECT_ID for new setups.
OPENAI_PROJECT=
OPENAI_ORGANIZATION=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2

# (선택) DART API - 금융감독원 데이터 수집 시
# OPENDART_API_KEY=your_api_key_here
```

### 4.2 Docker 빌드 및 실행

```bash
# 컨테이너 빌드
docker compose build

# 컨테이너 실행
docker compose up -d

# 상태 확인
docker compose ps
```

---

## 5. 초기 설정

### 5.1 마이그레이션 실행

```bash
# 마이그레이션 적용
docker compose exec app python manage.py migrate
```

### 5.2 초기 데이터 로드 (선택)

```bash
# CSV에서 회사 데이터 로드
docker compose exec app python manage.py import_companies_from_csv --source /app/data/companies_latest.csv
```

---

## 6. 서비스 확인

### 6.1 로그 확인

```bash
# Django 앱 로그
docker compose logs -f app

# Celery 워커 로그
docker compose logs -f worker

```

### 6.2 API 접근

- **Django**: http://localhost:8200
- **API 테스트 페이지**: http://localhost:8200/api-test/ (`API_INTERNAL_TOKEN` 자동 첨부, 예시 payload 포함)
- **JSON API 직접 확인**: http://localhost:8200/api/job-postings/?limit=10

### 6.3 Celery 워커 상태 확인

```bash
docker compose exec worker celery -A config inspect ping
```

---

## 7. 주요 작업

### 7.1 수동 크롤링 파이프라인 실행

```bash
curl -X POST "http://localhost:8200/api/crawl/run/" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: internal_token_8h_7Kifc0r" \
  -d '{
    "company_id_start": 1,
    "company_id_end": 50,
    "workers": 2,
    "run_homepage_check": true,
    "run_discover": true,
    "run_collect": true,
    "force_homepage_recheck": false
  }'
```

### 7.2 개별 작업 실행

```bash
# OSM 회사 수집
docker compose exec app python manage.py shell -c "
from api.tasks import collect_osm_companies
collect_osm_companies.delay(regions=['서울특별시'], mode='medium', limit=50)
print('queued')
"

# 채용 페이지 탐색
docker compose exec app python manage.py shell -c "
from api.tasks import run_discover_careers_spiders
run_discover_careers_spiders.delay(limit=10)
print('queued')
"

# 채용 공고 수집
docker compose exec app python manage.py shell -c "
from api.tasks import run_job_collector_spiders
run_job_collector_spiders.delay(limit=10)
print('queued')
"
```

### 7.3 DB 데이터 CSV로 내보내기

```bash
# 회사 데이터 내보내기
docker compose exec app python manage.py export_companies_to_csv --output /app/data/companies_latest.csv

# 채용 공고 내보내기
docker compose exec app python manage.py shell -c "
import csv
from api.models import JobPosting

with open('/app/data/job_postings_latest.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'company', 'title', 'post_url', 'job_description', 'qualifications', 'preferred_qualifications', 'hiring_process', 'benefits', 'location', 'employment_type', 'salary', 'posted_at', 'deadline_at', 'is_active'])
    for job in JobPosting.objects.all().values_list('id', 'company__name', 'title', 'post_url', 'job_description', 'qualifications', 'preferred_qualifications', 'hiring_process', 'benefits', 'location', 'employment_type', 'salary', 'posted_at', 'deadline_at', 'is_active'):
        writer.writerow(job)
print('Exported')
"
```

### 7.4 GPT 파서 개발/운영 계정 전환

구인페이지 분석(`api/llm_parser.py`)은 기본적으로 로컬/룰 기반 fallback으로 동작한다. GPT 기반 구조화 추출을 테스트할 때만 아래처럼 개발 계정 값을 주입한다.

```bash
OPENAI_PARSER_ENABLED=1
OPENAI_API_KEY=개발용_OpenAI_API_Key
OPENAI_PROJECT_ID=개발용_Project_ID_또는_빈값
OPENAI_PROJECT=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
```

ChatGPT Plus 구독만으로는 서버 API 호출이 되지 않는다. OpenAI Platform에서 API key를 발급해야 하며, `OPENAI_PROJECT_ID`는 project를 분리해서 관리할 때만 넣는다. 운영 전환 시에는 코드 변경 없이 같은 변수명에 실서비스용 key/project를 배포 secret으로 주입한다. 개발/운영 키를 동시에 같은 프로세스에 넣지 말고, 실제 키는 `.env.example`, 문서, git commit, 로그에 남기지 않는다. 키 변경 후에는 `docker compose up -d --force-recreate app worker`로 app/worker에 새 환경변수를 반영한다.

---

## 8. 로컬 개발 (선택)

### 8.1 Docker 없이 Django만 실행 (테스트용)

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r requirements.txt

# SQLite로 마이그레이션
setx DJANGO_USE_SQLITE 1  # Windows
export DJANGO_USE_SQLITE=1  # Linux/macOS
python manage.py migrate
python manage.py runserver
```

---

## 9. 문제 해결

### 9.1 Docker 메모리 부족

Docker Desktop 설정 → Resources → Memory → 4GB 이상으로 증가

### 9.2 컨테이너 충돌 시

```bash
# 모든 컨테이너 중지 및 제거
docker compose down

# 볼륨도 함께 제거 (데이터 초기화)
docker compose down -v

# 다시 빌드 및 실행
docker compose build
docker compose up -d
```

### 9.3 DB 연결 오류

```bash
# DB 컨테이너 상태 확인
docker compose ps db

# DB 컨테이너 로그
docker compose logs db
```

---

## 10. Git 업데이트

```bash
# 변경사항 확인
git status

# 변경사항 확인 (상세)
git diff

# 커밋 (필요시)
git add .
git commit -m "Description of changes"

# 원격에 푸시
git push origin main
```

---

## 참고 문서

- `docs/PROJECT_STRUCTURE.md`: 프로젝트 구조 상세 문서
- `docs/RUNBOOK.md`: 운영 매뉴얼
- `docs/TECHNICAL.md`: 기술 상세 문서
- `README.md`: 프로젝트 개요
