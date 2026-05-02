# Job Crawler Full Template — TECHNICAL (Handover Doc)

## 0. 이 문서의 목적
- 신규 담당자(사람) 또는 GPT가 이 문서만 읽고,
  - 프로젝트 구조/역할을 이해한다.
  - 어디를 수정해야 하는지 바로 찾는다.
  - 수동 실행/운영 점검/장애 대응까지 가능하게 한다.

---

## 1. 프로젝트 목표(현재 범위)
### 1) Company(회사) 데이터 확보
- 회사 목록을 대량 확보한다.
- 소스는 3개.
  - OSM(Overpass) 기반 지역 사업체.
  - SWDB(정보통신산업진흥원 SW사업자 DB) 기반 대량 시드.
  - DART(OpenDART) 기반 상장사(신규 생성 + 보강).

### 2) 채용 수집 파이프라인
- 회사 홈페이지 → 채용 페이지 탐색(discover) → 공고 수집(collector).
- 비동기 실행은 Celery로 한다.
- 운영은 수동 실행(`POST /api/crawl/run/` 또는 명령 기반) 중심이다.

### 3) 홈페이지 생존 체크(dead 처리)
- 회사 homepage_url이 죽었는지 주기적으로 체크한다.
- dead는 재체크 스킵 옵션이 있다(운영 비용 절감).

---

## 2. 실행 환경/스택
- OS: Linux Docker(운영), Windows에서 docker compose로 개발
- Backend: Django + DRF
- Queue: Celery + Redis
- DB: MariaDB 10.5
- Crawling: Scrapy(스파이더는 별도 프로세스로 실행)

---

## 3. 서비스 구성(docker-compose)
### 컨테이너
- `db`
  - MariaDB.
  - 외부 접근 포트는 보통 `3308:3306`.
- `redis`
  - Celery broker.
- `app`
  - Django API(gunicorn).
  - 보통 `8200:8000`.
  - `volumes: .:/app` 로 로컬 코드가 컨테이너에 반영된다.
- `worker`
  - Celery worker.

### 네트워크
- `internal_net`: 내부 전용
- `backend_net`: 외부팀 공유용 external network(필요 시)

---

## 4. 레포 구조(핵심만)
- `config/`
  - Django settings/urls/wsgi/celery 초기화.
  - `config/celery.py`에서 Celery autodiscover + imports 설정.
- `api/`
  - `models.py`: Company/JobPosting 등 모델.
  - `tasks.py`: “크롤링 파이프라인” task(홈페이지 찾기/스파이더 실행/수동 실행 경로).
  - `company_sources.py`: “회사 시드 수집” task(OSM/SWDB/DART) + upsert 로직 + 홈페이지 dead 체크.
  - `utils.py`: 홈페이지 검색 보조(예: `find_homepage_for_company`).
- `crawler/`
  - Scrapy 프로젝트(스파이더들: discover_careers, job_collector 등)

> 실제 함수 정의 파일은 아래로 확정 가능  
> `python manage.py shell -c "import inspect; from api.tasks import check_company_homepages; print(inspect.getsourcefile(check_company_homepages))"`

---

## 5. 데이터 모델(Company 중심)
### Company 필드(운영 핵심)
- 식별/정규화
  - `name` (회사명)
  - `name_norm` (정규화된 키. 중복 방지에 사용)
- 홈페이지
  - `homepage_url`
  - `homepage_host` (도메인 정규화)
- 홈페이지 상태(Dead 체크)
  - `homepage_url_status` (`alive`/`dead`/`unknown` 등)
  - `homepage_checked_at`
  - `homepage_last_status_code`
  - `homepage_fail_count`
- 채용 탐색/수집
  - `recruits_url`
  - `page_type` (listing/one_page/main/external 등)
  - `post_type` (text/image/external_link)
  - `recruits_url_status`
- 소스/보강 데이터
  - `source_meta` (JSON. 소스별 원천값/보강값 저장)
- DART
  - `dart_corp_code`
  - `stock_code`
  - `bizr_no`(있으면)
  - `dart_modify_date`(있으면)
- SWDB
  - `swdb_fin_year`(재무현황연도)

> 필드 목록은 운영 DB/코드 기준으로 아래로 확인  
> `python manage.py shell -c "from api.models import Company; print([f.name for f in Company._meta.fields])"`

---

## 6. 회사 “시드 수집” 설계(Company Sources)
### 공통 원칙
- 여러 소스(OSM/SWDB/DART)에서 들어오는 Company를 “중복 없이” 병합한다.
- upsert 핵심 키 우선순위(개념)
  1) `dart_corp_code` (가장 강함)
  2) `homepage_host`
  3) `name_norm`
  4) `name`(fallback)

### 각 소스의 역할
- OSM(Overpass)
  - 지역 기반.
  - 소규모/로컬 사업체 포함.
  - 업종 필터로 IT/전자/제조 쪽만 최대한 남기고 잡음을 제거.
- SWDB
  - 대량 seed(수만 단위 가능).
  - 홈페이지 값이 더럽거나 오래된 경우가 있어 dead 체크로 후처리.
- DART(OpenDART)
  - 상장사 위주.
  - “신규 생성”은 상장사만.
  - “보강”은 기존 회사에 corp_code/stock_code/주소/연락처 등을 채운다.

---

## 7. 크롤링 파이프라인(tasks.py)
### 단계
1) `find_missing_homepages`
- homepage_url이 비어있는 회사에 대해 검색해서 채움.
2) `run_discover_careers_spiders`
- homepage_url은 있지만 recruits_url 없는 회사 대상.
- Scrapy `discover_careers` 실행.
- recruits_url/page_type/post_type 등을 설정하도록 설계.
3) `run_job_collector_spiders`
- recruits_url + page_type/post_type 기반으로 Scrapy `job_collector` 실행.
- 외부 플랫폼(external)은 제외(정책에 따라 변경 가능).
4) `run_manual_crawl`
- 수동 실행 파이프라인.
- `company_id_start/company_id_end`, 단계별 on/off, worker 수를 제어한다.

---

## 8. 환경변수(.env) 핵심
- 모든 컨테이너(app/worker)에 `.env`가 주입된다(`docker-compose.yml`의 `env_file`).
- 키 수정 후에는 worker를 재시작(필요 시 force-recreate)해야 반영되는 경우가 있다.

### 내부 API 인증 헤더
- 내부 관리/운영성 API는 `X-Internal-Token` 을 기준 헤더로 사용한다.
- 일부 기존 엔드포인트는 하위 호환을 위해 `X-API-KEY` 또는 `Authorization: Bearer ...` 도 허용할 수 있다.
- 새로 붙이는 내부 호출 코드는 가능하면 `X-Internal-Token` 기준으로 맞춘다.

### DART
- `OPENDART_API_KEY=...`

### SWDB(ODcloud API 또는 CSV)
- API 모드
  - `SWDB_ODCLOUD_ENDPOINT=...` (실제 호출 URL. 예: /api/15052274/v1/uddi:... )
  - `ODCLOUD_API_KEY=...`
- CSV 모드(권장: “연 1회 스냅샷”)
  - `SWDB_CSV_PATH=/app/data/swdb_seed.csv`
  - 그리고 `./data/swdb_seed.csv`를 레포에 두고 `volumes: .:/app`로 컨테이너에서 읽게 한다.

### GPT/OpenAI 기반 구인공고 파서(선택)
- `api/llm_parser.py`는 `OPENAI_PARSER_ENABLED=1`이고 `OPENAI_API_KEY`가 있을 때만 OpenAI 파서를 먼저 사용한다.
- GPT 응답에서 받은 `job_description`, `qualifications`, `preferred_qualifications`, `hiring_process`, `benefits`, `location`, `employment_type`, `salary`, `deadline_at`, `posted_at`을 정리한 뒤 기존 룰/제로샷 fallback으로 비어 있는 값을 보완한다.
- 개발 테스트는 개발용 OpenAI 계정/key/project를 `.env` 또는 secret에 넣고 app/worker를 재시작한다.
- 실서비스는 같은 변수명에 production key/project를 배포 secret으로 주입한다. 개발/운영 key를 동시에 같은 컨테이너에 넣지 않는다.
- 지원 변수:
  - `OPENAI_PARSER_ENABLED=0|1`
  - `OPENAI_API_KEY`
  - `OPENAI_PROJECT_ID` (권장; 선택)
  - `OPENAI_PROJECT` (legacy alias; 선택)
  - `OPENAI_ORGANIZATION`
  - `OPENAI_MODEL` (기본 `gpt-4o-mini`)
  - `OPENAI_TIMEOUT_SECONDS` (기본 `30`)
  - `OPENAI_MAX_RETRIES` (기본 `2`)
- 실제 키는 git, 문서, 로그에 남기지 않는다.

---

## 9. 운영 확인(최소 체크)
- worker가 task를 등록했는지:
  - `docker compose logs -f worker --tail=200`
  - worker 시작 로그에 `[tasks]` 목록이 찍힌다.
- Company 수:
  - `python manage.py shell -c "from api.models import Company; print(Company.objects.count())"`
- DART 상장사 보강 여부:
  - `python manage.py shell -c "from api.models import Company; print(Company.objects.exclude(stock_code__isnull=True).exclude(stock_code='').count())"`
- 특정 회사 ID 범위만 부분 실행할 때:
  - `check_company_homepages`, `find_missing_homepages`, `run_discover_careers_spiders`, `run_job_collector_spiders` 는 `company_id_start`, `company_id_end` 인자를 받을 수 있다.
  - 수동 운영 기준으로 작은 범위를 먼저 실행해 검증하는 것이 안전하다.
- 브라우저 테스트 페이지:
  - `http://localhost:8200/api-test/`
  - 내부 토큰을 입력해 `/api/crawl/status/`, `/api/jobs`, `/api/job-postings/`, `/api/normalize/counseling`, `/api/match/*`, `/api/crawl/run/`을 확인한다.

---

## 10. 자주 발생한 이슈/해결
### 1) OPENDART_API_KEY missing
- 원인
  - .env 수정 후 worker 컨테이너가 재생성/재시작되지 않아 환경변수가 반영되지 않음.
- 해결
  - `docker compose up -d --force-recreate worker`

### 2) Nominatim 403
- 원인
  - OSM Nominatim은 User-Agent/정책에 민감.
- 대응
  - region bbox 조회 실패 시 fallback 로직(행정구역 relation 기반) 사용.

### 3) Overpass timeout(504/Read timed out)
- 원인
  - 요청 범위가 넓거나 서버가 혼잡.
- 대응
  - 지역을 분할 실행.
  - mode를 좁힘.
  - 재시도/백오프 로직 사용.

### 4) Windows에서 `\` 줄바꿈 SyntaxError
- 원인
  - Windows CMD/Anaconda Prompt는 bash 스타일 줄바꿈 `\`이 깨짐.
- 해결
  - 한 줄로 실행한다.
  - 또는 `.py` 스크립트/management command로 분리한다.

---

## 12. “개발 종료” 판단 기준(현재)
- 회사 목록: SWDB 기반 대량(수만) + OSM/DART 보강 완료.
- 지금 당장 추가 개발 없이 운영 가능.
- 남은 건 운영 정책.
  - dead 체크를 언제/어떻게/얼마나 자주 돌릴지.
  - full crawling 8h를 유지할지(부하 고려).

---

## 13. 다음 사람이 손댈 포인트(수정 위치 가이드)
- 회사 중복 병합 로직 바꾸기
  - `api/company_sources.py`의 `upsert_company()` 및 정규화 함수.
- OSM 필터/업종 분류 바꾸기
  - `api/company_sources.py`의 OSM 쿼리/필터 함수(is_target_industry 등)
- SWDB 홈페이지 정제 강화
  - `api/company_sources.py`의 SWDB record 파싱 구간(홈페이지 문자열 정리)
- DART 신규생성/보강 범위 바꾸기
  - `collect_dart_companies(mode=...)`
- 수동 실행 경로 변경
  - `api/views.py`의 `ManualCrawlRunView`
  - `api/tasks.py`의 `run_manual_crawl`
