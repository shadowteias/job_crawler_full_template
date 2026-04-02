# 문서와 실제 코드 비교 문서

## 목적

이 문서는 `docs/` 아래의 현재 Markdown 문서 내용과, 실제 레포지토리에 구현되어 있는 코드를 비교하기 위한 문서다.

이 문서는 아래 두 가지 질문에 답하는 것을 목표로 한다.

1. 현재 문서는 이 프로젝트를 어떻게 설명하고 있는가?
2. 실제 코드에는 무엇이 구현되어 있는가?

---

## 전체 요약

문서와 코드는 프로젝트의 큰 방향에서는 서로 잘 맞는다.

- Django/DRF 기반 백엔드
- Celery + Redis 기반 비동기 작업 처리
- Scrapy 기반 크롤링
- MariaDB 기반 데이터 저장
- `Company`와 `JobPosting` 중심 파이프라인

문서가 설명하는 핵심 목적도 대체로 맞다. 즉, 여러 소스에서 회사 데이터를 확보하고, 홈페이지 상태를 점검하고, 채용 페이지를 찾고, 채용 공고를 수집해서 API로 제공하는 구조다.

다만 세부 구현 설명에서는 문서와 코드 사이에 차이가 있다.

- 일부 함수는 문서에서 `api/tasks.py`에 있다고 설명하지만 실제 구현은 `api/company_sources.py`에 있다.
- 문서에 등장하는 일부 Celery task 이름은 현재 코드베이스에 존재하지 않는다.
- LLM 관련 설명은 문서 쪽이 더 과거 또는 다른 구현을 기준으로 적혀 있고, 현재 체크인된 코드는 `transformers` 기반 분류 + 규칙 기반 추출에 더 가깝다.
- 일부 API 경로 예시는 현재 `api/urls.py`와 완전히 일치하지 않는다.

---

## 프로젝트 목적 비교: 문서 vs 코드

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| 핵심 목표 | 한국 기업 데이터를 확보하고 채용 페이지/공고를 수집한다 | 회사 시드 수집, 홈페이지 점검, 채용 페이지 탐색, 채용 공고 수집으로 구현되어 있다 | 일치 |
| 주요 데이터 소스 | OSM, SWDB, DART를 사용한다 | OSM은 `api/tasks.py`, SWDB/DART는 `api/company_sources.py`에 구현되어 있다 | 일치 |
| 파이프라인 구조 | Company seed → homepage → recruits page → postings | `run_full_crawling_cycle()`, `run_discover_careers_spiders()`, `run_job_collector_spiders()`로 구현되어 있다 | 일치 |
| API 기능 | 채용 공고 조회와 crawl trigger/status API가 있다 | `api/views.py`, `api/views_jobs.py`, `api/urls.py`에 구현되어 있다 | 일치 |
| 매칭 기능 | 학생-공고/회사 매칭 기능이 있다 | `api/matching.py`, `api/views_match.py`에 구현되어 있다 | 일치 |
| LLM 보조 추출 | 로컬 LLM 기반 추출 지원이 있다 | `llm_parser`는 존재하지만 구현 방식은 문서 설명과 다르다 | 부분 일치 |

---

## 기능별 대조표

### 1. 회사 seed 수집

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| OSM 수집 | OSM 기반 지역 회사 수집 기능이 있다 | `collect_osm_companies()`가 `api/tasks.py`에 있고 `api/osm_overpass.py`를 사용한다 | 일치 |
| SWDB 수집 | SWDB 기반 대량 회사 수집 기능이 있다 | `collect_swdb_companies()`가 `api/company_sources.py`에 있고 CSV 파싱 및 홈페이지 정제를 수행한다 | 일치 |
| DART 수집 | DART 기반 상장사 수집/보강 기능이 있다 | `collect_dart_companies()`가 `api/company_sources.py`에 있고 listed-only 필터링을 수행한다 | 일치 |
| 중복 병합 정책 | `corp_code`, `homepage_host`, `name_norm` 등을 기준으로 병합한다 | `api/company_sources.py`의 `upsert_company()`와 `api/tasks.py`의 OSM dedup 로직에 반영되어 있다 | 대체로 일치 |

### 2. 홈페이지 생존 체크

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| alive/dead 점검 | 홈페이지 생존 여부를 주기적으로 확인한다 | `check_company_homepages()`가 `api/company_sources.py`에 있고 상태 코드와 실패 횟수를 갱신한다 | 일치 |
| dead 재검사 생략 | 운영 비용 절감을 위해 dead 재검사를 건너뛸 수 있다 | `skip_dead=True`, `skip_recent_days` 옵션으로 구현되어 있다 | 일치 |
| 구현 위치 설명 | 일부 문서에서는 `api/tasks.py` 중심으로 설명한다 | 실제 구현은 `api/company_sources.py`에 있다 | 불일치 |

### 3. 채용 페이지 탐색

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| `discover_careers` 스파이더 | `recruits_url`, `page_type`, `post_type`를 찾는다 | `crawler/crawler/spiders/discover_careers.py`에 구현되어 있다 | 일치 |
| 페이지 분류 | `listing`, `one_page`, `main`, `external` 분류가 있다 | 스파이더 내부 분기와 `Company` 필드 저장으로 구현되어 있다 | 일치 |
| 외부 플랫폼 감지 | `wanted`, `saramin`, `jobkorea` 등을 별도로 처리한다 | `EXTERNAL_JOB_DOMAINS`와 `contains_external_job_link()`로 구현되어 있다 | 일치 |
| 부정 키워드 처리 | 일부 문서는 negative keyword 및 대체 링크 탐색을 강조한다 | 관련 함수는 남아 있지만 현재 핵심 흐름은 direct recruit link, listing/one-page 판단, external link 체크 쪽이 더 중심이다 | 부분 일치 |

### 4. 채용 공고 수집

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| `job_collector` 스파이더 | 실제 채용 공고를 추출하고 `JobPosting`을 저장한다 | `crawler/crawler/spiders/job_collector.py`에 구현되어 있다 | 일치 |
| 구조화 필드 추출 | description, qualifications, preferred, process, benefits, salary, location 등을 뽑는다 | `extract_job_from_detail()`에서 parser + fallback 추출 로직으로 구현되어 있다 | 일치 |
| `post_type` 처리 | `text/image/external` 등에 따라 동작이 달라진다 | `start_requests()`에서 non-text를 skip 한다 | 일치 |
| `post_url` 고유화 | hash 기반 고유 URL 처리 개선이 있다 | `_make_unique_post_url()`로 구현되어 있다 | 일치 |

### 5. 데이터 모델

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| `Company` 모델 | 홈페이지, 채용 URL, 소스 메타데이터, DART/SWDB 필드를 가진다 | `api/models.py`에 구현되어 있다 | 일치 |
| `JobPosting` 모델 | 공고 본문과 메타데이터를 저장한다 | `api/models.py`에 구현되어 있다 | 일치 |
| `Trainee` 모델 | 매칭용 모델이 존재한다 | `api/models.py`에 구현되어 있다 | 일치 |

### 6. API 표면

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| `/api/job-postings/` | 읽기 전용 목록/상세 API | DRF router와 `JobPostingViewSet`으로 구현되어 있다 | 일치 |
| `/api/crawl/trigger/` | 전체 크롤링을 수동으로 트리거한다 | `CrawlTriggerView`에 구현되어 있다 | 일치 |
| `/api/crawl/status/` | 현재 크롤링 상태를 조회한다 | `CrawlStatusView`에 구현되어 있다 | 일치 |
| `/api/jobs/` | 필터 가능한 jobs 목록 API가 있다 | 현재 실제 경로는 `path("jobs", ...)`이며 trailing slash가 없다 | 경미한 불일치 |
| 매칭 API | 학생/회사/배치 매칭 API가 있다 | `api/views_match.py`와 `api/urls.py`에 구현되어 있으며 역시 trailing slash가 없다 | 경미한 불일치 |

### 7. 스케줄링과 운영

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| Celery worker/beat 운영 | 백그라운드 작업과 스케줄링이 있다 | Celery task + `django-celery-beat` 사용으로 구현되어 있다 | 일치 |
| 코드 기반 스케줄 등록 | 코드로 periodic schedule을 생성/갱신할 수 있다 | `setup_company_seed_schedules()`가 `api/company_sources.py`에 있다 | 일치 |
| full crawling cycle | 전체 파이프라인을 하나로 묶는 주기 실행이 있다 | `run_full_crawling_cycle()`이 OSM → optional homepage fill → discover → collect를 dispatch 한다 | 대체로 일치 |

### 8. 매칭 시스템

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| 가중치 기반 매칭 | skills, role, location 등의 가중치 기반 점수 계산이 있다 | `api/matching.py`에 구현되어 있다 | 일치 |
| API 제공 | 매칭 기능을 API로 제공한다 | `api/views_match.py`, `api/urls.py`에 구현되어 있다 | 일치 |

### 9. LLM 보조 추출

| 항목 | 문서 설명 | 실제 코드 상태 | 판단 |
|---|---|---|---|
| 로컬 LLM 통합 | local llama-cpp/Qwen 스타일 설명이 있다 | 현재 `api/llm_parser.py`는 `transformers` 기반 import를 사용하며 `llama_cpp`는 보이지 않는다 | 불일치 |
| 파서 역할 | 공고 텍스트에서 구조화된 필드를 추출한다 | `_extract_dates()`, `_extract_salary()`, `parse_job_details_with_llm()`이 존재한다 | 부분 일치 |
| 전용 Celery task | `crawl_company_careers`, `crawl_single_company_career`, `extract_job_content` 같은 task가 있다고 설명한다 | 현재 `api/tasks.py`에서는 해당 task 이름을 찾을 수 없다 | 불일치 |

---

## 문서에서 우선 수정해야 할 불일치 지점

### 1. task 구현 위치 설명이 어긋난다

문서 여러 곳에서 SWDB, DART, homepage check, schedule setup이 `api/tasks.py` 중심인 것처럼 설명되어 있다.

하지만 현재 코드 기준으로 실제 구현 위치는 다음과 같다.

- `api/company_sources.py`
  - `collect_swdb_companies()`
  - `collect_dart_companies()`
  - `check_company_homepages()`
  - `setup_company_seed_schedules()`

반면 `api/tasks.py`는 OSM 수집과 crawling orchestration 쪽 역할이 더 크다.

### 2. LLM 설명이 현재 코드와 다르다

문서는 local llama-cpp/Qwen 기반 설명을 포함하고 있지만, 현재 체크인된 `api/llm_parser.py`는 다음과 같은 성격에 더 가깝다.

- `transformers` 기반 분류 모델 사용
- `is_job_posting()` 기반 zero-shot 분류
- 정규식/섹션 추출 기반 후처리

즉, 문서의 LLM 설명은 현재 코드 기준으로는 과장되었거나 오래된 설명일 가능성이 높다.

### 3. 문서에 있는 task 이름 일부가 현재 코드에 없다

문서에는 아래 task들이 현재 구현된 것처럼 등장한다.

- `crawl_company_careers`
- `crawl_single_company_career`
- `extract_job_content`

하지만 현재 확인한 `api/tasks.py`에는 이 이름들이 없다.

### 4. API 경로 예시가 현재 URL 설정과 완전히 같지 않다

문서에서는 trailing slash 형태 예시가 자주 보이지만, 현재 `api/urls.py`는 다음처럼 등록되어 있다.

- `path("jobs", ...)`
- `path("match/student-top", ...)`
- `path("match/company-top", ...)`
- `path("match/batch", ...)`

즉, 문서 예시를 현재 코드 기준으로 맞추거나, 반대로 라우팅 정책을 통일할 필요가 있다.

### 5. 현재 체크아웃에는 없는 경로가 한 번 탐지되었다

초기 탐색 결과 중 `src/dashboard/` 관련 경로가 언급되었지만, 현재 이 체크아웃에서는 해당 경로가 존재하지 않았다.

따라서 현 시점 문서에는 이 경로를 현재 시스템 일부처럼 적지 않는 것이 안전하다.

---

## 권장 문서 정리 방향

문서를 현재 코드에 맞추는 것이 목적이라면, 우선순위는 아래와 같다.

1. 회사 소스 수집과 homepage check 관련 설명을 `api/company_sources.py` 기준으로 수정한다.
2. LLM 관련 설명을 현재 `transformers` + 규칙 기반 추출 구조에 맞게 다시 쓴다.
3. 현재 존재하지 않는 task 이름은 삭제하거나, 과거 문맥이라면 별도 표기를 한다.
4. API 예시는 현재 `api/urls.py` 기준으로 통일한다.
5. `docs/TECHNICAL.md`를 운영 기준 문서로 두고, 다른 문서의 중복/오래된 세부 구현 설명은 줄인다.

---

## 근거로 확인한 파일 목록

이번 비교에서 직접 확인한 주요 구현 파일:

- `api/tasks.py`
- `api/company_sources.py`
- `api/models.py`
- `api/views.py`
- `api/views_jobs.py`
- `api/views_match.py`
- `api/urls.py`
- `api/matching.py`
- `api/llm_parser.py`
- `crawler/crawler/spiders/discover_careers.py`
- `crawler/crawler/spiders/job_collector.py`

비교 대상으로 읽은 주요 문서 파일:

- `docs/TECHNICAL.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/DEVELOPMENT_CONTEXT.md`
- `docs/RUNBOOK.md`
- `docs/SETUP_GUIDE.md`
- `docs/DATA_SOURCES.md`
- `docs/DOCS_CODEBASE_COMPARISON.md`
