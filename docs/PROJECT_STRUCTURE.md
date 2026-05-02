# Job Crawler 프로젝트 구조 분석 문서

## 1. 프로젝트 개요

### 1.1 프로젝트 목표

- **목표**: 한국 IT/제조업체의 채용 공고 자동 수집 및 매칭 시스템
- **데이터 소스**: OSM (OpenStreetMap), SWDB (소프트웨어DB), DART (금융감독원)
- **기술 스택**: Django + DRF, Scrapy, Celery, Redis, MariaDB

### 1.2 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
├─────────────┬─────────────┬─────────────┬───────────────────────┤
│   MariaDB   │    Redis    │   Django    │   Celery Worker/Beat  │
│   (DB)      │   (Broker)  │   (API)     │   (Background Jobs)   │
└─────────────┴─────────────┴─────────────┴───────────────────────┘
         │                  │              │                │
         ▼                  ▼              ▼                ▼
   ┌──────────┐      ┌──────────┐   ┌──────────┐    ┌──────────────┐
   │ Companies │      │  Tasks   │   │ REST API │    │   Scrapy     │
   │ JobPosting│      │  Queue   │   │ Endpoints│    │   Spiders    │
   └──────────┘      └──────────┘   └──────────┘    └──────────────┘
```

---

## 2. 디렉토리 구조

```
lms_tp/
├── api/                        # Django App (메인 로직)
│   ├── models.py               # Company, JobPosting, Trainee 모델
│   ├── tasks.py                # Celery 태스크 정의
│   ├── views.py                # REST API 뷰 (CrawlTrigger, CrawlStatus)
│   ├── urls.py                 # URL 라우팅
│   ├── serializers.py          # DRF 시리얼라이저
│   ├── permissions.py          # API 권한 설정
│   ├── matching.py             # 학생-공고 매칭 알고리즘
│   ├── company_sources.py      # OSM/SWDB/DART 데이터 수집
│   ├── llm_parser.py           # (선택) LLM 기반 파싱
│   ├── company_sources.py      # 외부DB 연동 (SWDB, DART)
│   └── management/commands/    # Django management commands
│       ├── import_companies_from_csv.py
│       ├── export_companies_to_csv.py
│       └── ...
│
├── crawler/                    # Scrapy 크롤러
│   └── crawler/
│       ├── settings.py         # Scrapy 설정
│       └── spiders/
│           ├── discover_careers.py  # 채용 페이지 탐색 스파이더
│           └── job_collector.py     # 채용 공고 수집 스파이더
│
├── config/                    # Django 프로젝트 설정
│   ├── settings.py            # 메인 settings
│   ├── celery.py              # Celery 설정
│   ├── urls.py                # 프로젝트 URLs
│   └── wsgi.py                # WSGI 설정
│
├── tests/                     # 테스트 코드
│   └── test_spiders.py        # 스파이더 단위 테스트
│
├── docs/                      # 문서
│   ├── RUNBOOK.md             # 운영 매뉴얼
│   ├── TECHNICAL.md           # 기술 문서
│   └── DATA_SOURCES.md        # 데이터 소스 설명
│
├── models/                    # 로컬 모델 다운로드 경로 (git 미추적)
├── scripts/                   # 보조 스크립트 (예: 모델 다운로드)
│   └── download_models.py     # Hugging Face에서 모델 파일 bootstrap
│
├── manage.py                  # Django management CLI
├── docker-compose.yml         # 컨테이너 정의
├── requirements.txt           # Python 의존성
└── README.md                  # 프로젝트 개요
```

---

## 3. 핵심 파일 역할

### 3.1 데이터 모델 (`api/models.py`)

#### Company 모델
| 필드 | 설명 |
|------|------|
| `name` | 회사명 (unique) |
| `homepage_url` | 회사 홈페이지 URL |
| `homepage_url_status` | 페이지 상태 (`alive`/`dead`/`unknown`) |
| `homepage_last_status_code` | 마지막 HTTP 상태 코드 |
| `recruits_url` | 채용 페이지 URL |
| `page_type` | 채용 페이지 타입 (`listing`/`one_page`/`main`/`external`) |
| `post_type` | 포스트 타입 (`text`/`image`/`external_link`) |
| `hiring` | 채용 진행 여부 |
| `industry` | 산업 분야 |
| `region` | 지역 |
| `ceo_name`, `bizr_no`, `stock_code`, `dart_corp_code` | DART 정보 |

#### JobPosting 모델
| 필드 | 설명 |
|------|------|
| `company` | Company FK |
| `title` | 공고 제목 |
| `post_url` | 공고 URL |
| `job_description` | 주요 업무 |
| `qualifications` | 자격 요건 |
| `preferred_qualifications` | 우대 사항 |
| `hiring_process` | 채용 절차 |
| `benefits` | 복리후생 |
| `location` | 근무지 |
| `employment_type` | 고용 형태 |
| `salary` | 급여 |
| `posted_at`, `deadline_at` | 게시/마감일 |
| `status` | 공고 상태 |
| `is_active` | 활성 공고 여부 |

#### Trainee 모델
- 훈련생 정보 및 희망 조건 (매칭용)

---

### 3.2 Celery 태스크 (`api/tasks.py`)

| 함수 | 설명 |
|------|------|
| `collect_osm_companies()` | OSM에서 회사 수집 (필터링: IT/제조/태그 기반) |
| `find_missing_homepages()` | homepage_url이 빈 회사 검색 |
| `run_discover_careers_spiders()` | 각 회사별 채용 페이지 탐색 실행 |
| `run_job_collector_spiders()` | 채용 공고 수집 실행 |
| `collect_swdb_companies()` | SWDB CSV에서 회사 수집 |
| `collect_dart_companies()` | DART API에서 상장사 수집 |
| `check_company_homepages()` | homepage_url 상태 체크 |

---

### 3.3 크롤러 스파이더

#### `discover_careers.py` (채용 페이지 탐색)

**역할**: 회사 홈페이지를 탐색하여 채용 페이지 URL 및 타입 발견

**주요 함수**:

| 함수 | 설명 |
|------|------|
| `parse_page()` | 페이지 분석 및 탐색 로직 |
| `select_candidate_links()` | 우선순위 키워드 기반 링크 선택 |
| `has_negative_keywords()` | 부정 키워드 탐지 (인재상/비전/복리후생 페이지 제외) |
| `find_alternative_job_links()` | 부정 키워드 발견 시 대안 채용 링크 탐색 |
| `looks_like_listing()` | 게시판형 목록 페이지 판단 |
| `looks_like_onepage()` | 단일 공고 페이지 판단 |
| `detect_post_type()` | 텍스트 vs 이미지/PDF 기반 공고 판단 |
| `has_job_intent()` | 페이지에 채용 의사가 있는지 확인 |
| `contains_external_job_link()` | 외부 채용 플랫폼 링크 감지 |
| `save_result()` | Company 레코드 업데이트 |

**외부 플랫폼 감지 도메인**:
- `wanted.co.kr`
- `saramin.co.kr`
- `jobkorea.co.kr`

---

#### `job_collector.py` (채용 공고 수집)

**역할**: 채용 페이지에서 실제 공고 정보 추출 및 DB 저장

**주요 함수**:

| 함수 | 설명 |
|------|------|
| `parse_listing()` | 채용 목록 페이지 처리 |
| `parse_onepage()` | 원페이지/메인 페이지 처리 |
| `parse_job_detail()` | 개별 공고 상세 페이지 처리 |
| `extract_job_links()` | 목록에서 채용 링크 추출 |
| `extract_job_from_detail()` | 상세 페이지에서 공고 정보 추출 |
| `extract_all_sections()` | 섹션별 추출 (주요 업무, 자격 요건, 우대 사항 등) |
| `_get_visible_text()` |可见 텍스트 추출 (nav/footer 제외) |
| `_looks_like_job_body()` | 품질 게이트 (순수 탐색 텍스트 방지) |
| `_trim_boilerplate()` | 하단 부가정보 제거 |
| `upsert_jobposting()` | JobPosting upsert |

**필터링 로직**:
- `JOB_ANCHOR_KEYWORDS`: 채용 관련 앵커 텍스트
- `EXCLUDE_ANCHOR_SUBSTRINGS`: 제외할 앵커 (모집 절차, FAQ 등)
- `BENEFIT_KEYWORDS`: 복리후생 키워드

---

### 3.4 매칭 시스템 (`api/matching.py`)

**가중치**:
- `skills`: 30점
- `role`: 20점
- `location`: 10점
- `etc`: 10점
- `employment_type`: 8점
- `welfare`: 8점
- `salary`: 8점
- `company_industry`: 6점

**주요 함수**:
- `top_jobs_for_student()`: 학생별 추천 공고
- `top_students_for_company()`: 회사별 추천 학생
- `batch_match()`: 일괄 매칭 (fallback 스코어링 포함)

---

### 3.5 API 엔드포인트 (`api/views.py`, `api/urls.py`)

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/job-postings/` | GET | 채용 공고 목록 (ReadOnly) |
| `/api/job-postings/{id}/` | GET | 개별 공고 상세 |
| `/api/crawl/run/` | POST | 수동 크롤링 실행 |
| `/api/crawl/status/` | GET | 크롤링 상태 조회 |
| `/api/jobs/` | GET | 채용 공고 필터링 |
| `/api/match/student-top/` | POST | 학생별 매칭 |
| `/api/match/company-top/` | POST | 회사별 매칭 |
| `/api/match/batch/` | POST | 일괄 매칭 |

---

## 4. 주요 명령어 모음

### 4.1 Docker 관련

```bash
# Docker 네트워크 생성 (처음 한 번)
docker network create backend_net

# 빌드 및 실행
docker compose build
docker compose up -d

# 로그 확인
docker compose logs -f app        # Django 앱 로그
docker compose logs -f worker     # Celery 워커 로그

# 컨테이너 상태 확인
docker compose ps

# 재시작
docker compose restart app worker
```

### 4.2 Django Management Commands

```bash
# 마이그레이션
docker compose exec app python manage.py makemigrations
docker compose exec app python manage.py migrate

# 개발 서버 실행 (로컬)
python manage.py runserver

# Django Shell
docker compose exec app python manage.py shell
```

### 4.3 Celery 태스크 실행

```bash
# 수동 크롤링 API 호출
curl -X POST "http://localhost:8200/api/crawl/run/" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: internal_token_8h_7Kifc0r" \
  -d '{"company_id_start":1,"company_id_end":10,"workers":2,"run_homepage_check":true,"run_discover":true,"run_collect":true}'

# OSM 회사 수집
docker compose exec app python manage.py shell -c "
from api.tasks import collect_osm_companies
collect_osm_companies.delay(regions=['서울특별시'], mode='medium', limit=50)
print('queued')
"

# 채용 페이지 탐색 (개별)
docker compose exec app python manage.py shell -c "
from api.tasks import run_discover_careers_spiders
run_discover_careers_spiders.delay(limit=10)
print('queued')
"

# 채용 공고 수집 (개별)
docker compose exec app python manage.py shell -c "
from api.tasks import run_job_collector_spiders
run_job_collector_spiders.delay(limit=10)
print('queued')
"

# Homepage 상태 체크
docker compose exec app python manage.py shell -c "
from api.tasks import check_company_homepages
check_company_homepages.delay(limit=100)
print('queued')
"
```

### 4.4 Celery 상태 확인

```bash
# Worker Ping
docker compose exec worker celery -A config inspect ping

# Active Tasks
docker compose exec worker celery -A config inspect active

# Reserved Tasks
docker compose exec worker celery -A config inspect reserved
```

### 4.5 데이터 조회 (Django Shell)

```bash
# 전체 회사 수
docker compose exec app python manage.py shell -c "
from api.models import Company
print('Companies:', Company.objects.count())
"

# 활성 채용 공고 수
docker compose exec app python manage.py shell -c "
from api.models import JobPosting
print('Active Jobs:', JobPosting.objects.filter(is_active=True).count())
"

# Homepage 상태별 개수
docker compose exec app python manage.py shell -c "
from api.models import Company
print('Alive:', Company.objects.filter(homepage_url_status='alive').count())
print('Dead:', Company.objects.filter(homepage_url_status='dead').count())
"

# 채용 페이지 발견된 회사 수
docker compose exec app python manage.py shell -c "
from api.models import Company
print('With recruits_url:', Company.objects.exclude(recruits_url__isnull=True).exclude(recruits_url='').count())
"

# Homepage가 alive인 회사 수 (discover_careers 대상)
docker compose exec app python manage.py shell -c "
from django.db.models import Q
from api.models import Company
alive_q = Q(homepage_url_status='alive') | Q(homepage_last_status_code__gte=200, homepage_last_status_code__lt=400) | Q(homepage_last_status_code__in=[401,403,405,406])
print('Alive companies:', Company.objects.filter(alive_q).count())
"
```

### 4.6 DB 데이터 Export/Import

```bash
# CSV로 회사 내보내기
docker compose exec app python manage.py export_companies_to_csv --output /app/data/companies.csv

# CSV에서 회사 가져오기
docker compose exec app python manage.py import_companies_from_csv --source /app/data/companies.csv
```

### 4.7 테스트 실행

```bash
# 단위 테스트 실행
docker compose exec app python -m pytest tests/ -v

# 또는 unittest 사용
docker compose exec app python -m unittest tests.test_spiders -v
```

---

## 5. 크롤링 파이프라인 흐름

```
┌──────────────────────────────────────────────────────────────────────┐
│                        run_manual_crawl()                            │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │ homepage     │ │ discover     │ │ collect      │
           │ check        │ │ careers      │ │ job postings │
           └──────────────┘ └──────────────┘ └──────────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  Company / JobPosting DB    │
                    │  - alive 상태 반영           │
                    │  - recruits_url/page_type    │
                    │  - JobPosting upsert         │
                    └─────────────────────────────┘
```

---

## 6. 주요 개선 사항 (최근 작업)

### 6.1 Alive 필터 추가 (`api/tasks.py`)
- `run_discover_careers_spiders()`에서 `homepage_url_status='alive'` 또는 2xx/3xx 상태 코드 필터 추가

### 6.2 텍스트 vs 이미지 Detection (`discover_careers.py`)
- `detect_post_type()` 함수 추가
- PDF 임베드, 포스터 이미지, 텍스트 길이 기반 판단

### 6.3 부정 키워드 및 대안 링크 (`discover_careers.py`)
- `has_negative_keywords()`: 인재상, 비전, 복리후생 페이지 탐지
- `find_alternative_job_links()`: 부정 키워드 발견 시 대안 채용 링크 탐색

### 6.4 품질 게이트 (`job_collector.py`)
- `_looks_like_job_body()`: nav/sitemap 텍스트 저장 방지
- `has_job_intent()`: 채용 의사가 없는 listing-like 페이지 제외

### 6.5 외부 플랫폼 처리 개선 (`job_collector.py`)
- 외부 플랫폼 링크가 footer에 있는 것만 무시
- 페이지 자체가 외부 플랫폼일 때만 중단

### 6.6 로컬 LLM 통합 (2026)
- `api/llm_parser.py`: LLM 기반 콘텐츠 추출
- `requirements.txt`: torch, transformers, llama-cpp-python 추가
- `Dockerfile`: llama-cpp-python 및 Qwen2.5 GGUF 모델 추가
- 로컬 LLM으로 구조화된 채용 정보 추출

### 6.7 날짜 추출 기능
- `llm_parser.py`: `_extract_dates()` 함수
- 한국어 날짜 패턴 지원 (2026.04.02, 2026년 04월 02일, 26년 04월 02일)
- `deadline_at`, `posted_at` 필드 추출

### 6.8 급여 추출 기능
- `llm_parser.py`: `_extract_salary()` 함수
- 연봉, 월급, 급여 패턴 매칭

### 6.9 post_url 고유성 개선
- `job_collector.py`: `_make_unique_post_url()` 함수 추가
- 각 채용 공고별 고유 URL 생성 (#job-{md5_hash}-{index})

### 6.10 Celery 태스크 통합
- `api/tasks.py`: LLM 기반 콘텐츠 추출 태스크 추가
- `crawl_company_careers`: 여러 회사 채용 페이지 크롤링
- `crawl_single_company_career`: 개별 회사 크롤링
- `extract_job_content`: 로컬 LLM으로 콘텐츠 추출

---

## 7. 환경 변수 (.env 예시)

```bash
# Database
DB_NAME=job_data
DB_USER=user
DB_PASSWORD=your_password
DB_HOST=db
DB_PORT=3306

# Redis
REDIS_URL=redis://redis:6379/0

# Django
DJANGO_SECRET_KEY=your_secret_key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=*

# API
API_INTERNAL_TOKEN=internal_token_8h_7Kifc0r

# DART (금융감독원)
OPENDART_API_KEY=your_api_key
```

---

## 8. 문제 해결 (Troubleshooting)

### 8.1 Worker가 동작하지 않을 때
```bash
# Celery 워커 상태 확인
docker compose exec worker celery -A config inspect ping

# 로그 확인
docker compose logs -f worker
```

### 8.2 크롤링이 너무 느릴 때
- `DOWNLOAD_DELAY` 조정 (`crawler/crawler/settings.py`)
- `CONCURRENT_REQUESTS` 증가

### 8.3 DB 연결 오류
```bash
# DB 상태 확인
docker compose exec db mysqladmin ping -h localhost

# 마이그레이션 상태 확인
docker compose exec app python manage.py showmigrations
```

---

## 9. 참고 문서

- `docs/RUNBOOK.md`: 운영 매뉴얼
- `docs/TECHNICAL.md`: 기술 상세 문서
- `docs/DATA_SOURCES.md`: 데이터 소스 설명
- `API_Usage_Guide_v3.md`: API 사용 가이드
