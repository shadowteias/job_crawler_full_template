# 2026-04-23 API Surface and Wrap-up Plan

## 목적

이 문서는 현재 프로젝트의 API 제공 범위, 실제 구현 기능, 남은 미진한 부분, 정리 후보, 그리고 마무리 단계 계획을 한 번에 정리하기 위한 문서다.

특히 이번 문서에는 기존 API 목록 정리와 함께, **사용자가 직접 비주기적으로 crawl을 실행할 수 있는 수동 crawl API** 추가 내용도 포함한다.

---

## 현재 제공 API 목록

모든 API는 `config/urls.py` 기준 `/api/` 아래에 마운트된다.

### 1. 채용공고 조회 API

#### `GET /api/job-postings/`
- backing: `api.views.JobPostingViewSet`
- 목적: 채용공고 목록 조회

#### `GET /api/job-postings/{id}/`
- backing: `api.views.JobPostingViewSet`
- 목적: 채용공고 상세 조회

#### `GET /api/jobs`
- backing: `api.views_jobs.JobPostingListView`
- 목적: 필터 가능한 공고 목록 조회
- 지원 query:
  - `active`
  - `q`
  - `company`
  - `region`
  - `page_size`

### 2. 크롤링 제어 API

#### `GET /api/crawl/status/`
- backing: `api.views.CrawlStatusView`
- 인증: `X-Internal-Token`
- 목적: 현재 크롤링 실행 여부 / 상태 확인

#### `POST /api/crawl/trigger/`
- backing: `api.views.CrawlTriggerView`
- 인증: `X-Internal-Token`
- 목적: 기존 full-cycle 트리거
- 성격: legacy 성격이 강함

#### `POST /api/crawl/run/` ✅ 이번 추가
- backing: `api.views.ManualCrawlRunView`
- 인증: `X-Internal-Token`
- 목적: 사용자가 직접 비주기적으로, 원하는 단계만 수동 실행

지원 payload 예시:

```json
{
  "company_id_start": 1,
  "company_id_end": 100,
  "workers": 2,
  "run_homepage_check": true,
  "run_discover": true,
  "run_collect": true,
  "force_homepage_recheck": false,
  "homepage_limit": 100,
  "discover_limit": null,
  "collect_limit": null
}
```

지원 단계:
- homepage check
- recruit-page discovery
- job collection

### 3. 매칭 API

#### `POST /api/match/student-top`
- backing: `api.views_match.student_top_view`
- 목적: 학생 한 명 기준 top jobs 반환

#### `POST /api/match/company-top`
- backing: `api.views_match.company_top_view`
- 목적: 회사 하나 기준 top students 반환

#### `POST /api/match/batch`
- backing: `api.views_match.batch_match_view`
- 목적: batch matching 수행

### 4. 텍스트 정규화 / 추출 API

#### `POST /api/normalize/counseling`
- backing: `api.views_extract.CounselingNormalizeView`
- 목적: 상담 텍스트를 구조화/정규화된 필드로 추출

---

## 현재 코드상 존재하지만 HTTP로 직접 노출되지 않은 기능

### 크롤링 / 수집 task
- `collect_osm_companies`
- `find_missing_homepages`
- `run_discover_careers_spiders`
- `run_discover_careers_spiders_concurrent`
- `run_job_collector_spiders`
- `run_job_collector_spiders_concurrent`
- `run_full_crawling_cycle`
- `run_manual_crawl`

### 회사 소스 / 운영 task
- `collect_swdb_companies`
- `collect_dart_companies`
- `check_company_homepages`
- `setup_company_seed_schedules`

### 운영 command
- `rerun_company_crawl_range`
- `export_snapshot_to_csv`
- `import_companies_from_csv`
- `import_job_postings_from_csv`
- `import_trainees`
- `seed_companies_from_csv`
- `setup_periodic_tasks`
- `init_schedule`
- `run_validation_random_batches`

---

## 현재 프로젝트 기능 축 정리

현재 이 프로젝트는 기능적으로 아래 축을 가진다.

1. **회사 seed 확보**
   - OSM / SWDB / DART

2. **회사 홈페이지 alive/dead 관리**
   - homepage status / checked timestamp / fail count

3. **구인페이지 탐색**
   - `recruits_url`
   - `page_type`
   - `post_type`

4. **구인공고 수집**
   - `JobPosting`
   - listing-date fallback
   - validity date filtering
   - stale posting expiration

5. **공고 조회 API**

6. **학생-회사/공고 매칭 API**

7. **상담 텍스트 정규화 API**

8. **수동/비주기 crawl 제어 API**

---

## 미진하거나 더 다듬어야 할 부분

### 1. crawl API 이원화

현재 crawl 제어는 두 가지 방식이 공존한다.

- `POST /api/crawl/trigger/`
- `POST /api/crawl/run/`

앞으로는 `crawl/run/`를 표준 수동 실행 API로 삼고,
`crawl/trigger/`는 legacy 처리하거나 제거 여부를 정하는 것이 좋다.

### 2. periodic scheduling 흔적 정리 필요

비주기/수동 실행 방향으로 바꾸려면 아래는 정리 대상이다.

- `setup_periodic_tasks.py`
- `init_schedule.py`
- `setup_company_seed_schedules()`

### 3. 문서상 오래된 task 이름

일부 문서에는 아래 같은 오래된 task 이름이 남아 있다.

- `crawl_company_careers`
- `crawl_single_company_career`
- `extract_job_content`

이건 실제 코드 기준으로 다시 정리해야 한다.

### 4. discovery 품질은 아직 완벽하지 않음

현재 recruit-page discovery는 baseline 대비 충분히 안정화됐지만,
generic HR / 인재채용 안내 페이지 false positive는 여전히 일부 남는다.

다만 반복 실험 결과:
- aggressive verifier
- aggressive one-page tightening
- collector-level aggressive confidence gate

는 regression이나 false negative가 커서 채택하지 않았다.

즉 discovery는 지금 크게 더 흔들기보다, 추천/노출 단계에서 신뢰도를 더 조이는 방향이 맞다.

### 5. recommendation-grade filtering은 아직 별도 없음

현재 active posting은 많이 정제됐지만,
**“추천에 보여줄 만큼 충분히 믿을 수 있는 posting subset”** 을 별도로 가르는 레이어는 아직 없다.

이건 프로젝트 마무리 단계에서 중요한 다음 과제다.

---

## 정리 후보 / cleanup 대상

### 즉시 정리 후보
1. `POST /api/crawl/trigger/`의 역할 축소 또는 제거
2. `hello` task (`api.tasks.hello`) 제거
3. periodic scheduling scaffold 정리
4. 오래된 docs task 이름 정리

### 유지하되 문서화가 필요한 것
1. 날짜 유효성 규칙
2. listing-date fallback
3. stale posting expire
4. discovery hard stop
5. direct recruit-link ranking

---

## 마무리 단계 계획

### 1단계: API surface 확정
- `crawl/run/`를 표준 수동 crawl API로 확정
- `crawl/trigger/` 정리 방향 결정
- API 문서 최신화

### 2단계: stale/legacy 정리
- periodic schedule 관련 코드/문서 정리
- old task name 정리
- 실험 잔재 코드 제거

### 3단계: recommendation trust layer 추가
- active posting 전체를 그대로 추천하지 않고
- high-trust 추천 후보만 골라내는 레이어 설계

### 4단계: 운영성 문서 강화
- admin 사용 방식
- export 절차
- manual crawl API 사용 예시
- known limitations 정리

---

## 이번 수동 crawl API 추가 검증

### 코드 검증
- `python3 -m py_compile` 통과
- `python manage.py check` 통과

### 실제 API 검증

#### `GET /api/crawl/status/`
- 응답: `200`
- 상태 확인 가능

#### `POST /api/crawl/run/`
- 응답: `202`
- 수동 crawl 실행 시작 응답 확인

즉, 수동 crawl API는 **연결/실행 응답까지 실제로 확인 완료**된 상태다.

---

## 최종 요약

현재 프로젝트는 기능적으로:

- 회사 수집
- 홈페이지 alive check
- recruit page discovery
- job collection
- 공고 조회
- 매칭
- 텍스트 정규화
- 수동 crawl 실행

까지 갖춘 상태다.

지금 이후의 핵심은 “더 많은 공고 수집”보다,

- **legacy 정리**
- **API 표면 단순화**
- **추천에 노출되는 공고의 신뢰도 강화**

쪽에 있다.
