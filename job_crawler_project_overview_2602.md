# Job Crawler Project Overview

## 1. 프로젝트 개요

### 1.1 프로젝트 성격 · 목적

- **목적**  
  한국 기업들의 **자사 채용 페이지**에서 채용공고를 자동 수집 →  
  공통 스키마로 정규화 →  
  외부 팀/시스템이 사용할 수 있는 **공용 채용 데이터 인프라 + 매칭 API** 제공.

- **역할**  
  1. **회사 DB + 메타데이터**: 회사 기본 정보, 지도/산업/DART/SWDB 등 메타 보유  
  2. **채용공고 수집 파이프라인**: 기업 자사 채용 페이지 크롤링(Scrapy)  
  3. **텍스트 정제/후처리**: HTML/JSON/노이즈 제거, 필드 간 재분배  
  4. **매칭 엔진**: 학생/구직자 JSON ↔ DB의 JobPosting 가중치 기반 스코어링  
  5. **API 서버**: 매칭/조회/상담 텍스트 정규화 API 제공

- **정책/제약**
  - 사람인/잡코리아/인크루트/워크넷 등 **외부 채용 플랫폼 직접 크롤링 금지**  
    → 발견 시 즉시 중단 + 로그.
  - **robots.txt, 저작권, 약관 준수**.
  - LLM/BERT는 **보조 판단**에만 사용(분류/필드 추출 등), 실패 시 룰 기반 폴백.

---

## 2. 기술 스택 및 인프라

- **언어·프레임워크**
  - Python 3.10
  - Django 5.x, Django REST Framework
  - Scrapy 2.13.x
  - Celery + Redis (비동기 작업)
  - MariaDB 10.5

- **배포/실행 환경**
  - Docker / docker-compose
  - 대표 서비스
    - `app`: Django + Gunicorn (컨테이너 내부 포트 8000, 현재 호스트 매핑 8200:8000)
    - `db`: MariaDB 10.5
    - `redis`: Redis 6.x
    - `worker`, `beat`: Celery worker/beat
  - 공통 네트워크: 예) `job_crawler_full_template_internal_net`

- **인증/환경 변수**
  - `API_INTERNAL_TOKEN` : 내부용 API 키 (`X-API-KEY` 헤더로 사용)
  - DB: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - Django: `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DEBUG` …

---

## 3. 데이터 소스

### 3.1 회사 데이터 (이미 구현 완료, 수정 금지 영역)

- **오픈소스 지도 데이터**
  - 주소/좌표/지역 구분 등으로 **회사 위치 메타데이터** 보강
- **DART (전자공시) 데이터**
  - 상장/비상장 법인 코드, 사업자등록번호, 업종 등
  - Company 모델에 DART 관련 필드 (예: `dart_corp_code`, `stock_code`, `bizr_no`) 보유
- **SWDB (소프트웨어 개발 업체 DB)**
  - 소프트웨어 회사 목록 + 재무/규모 정보
  - Company 모델에 `swdb_fin_year` 등 SWDB 관련 필드 포함

→ 이 세 가지를 활용해서 **Company 테이블을 시딩 및 enrich**하는 파이프라인은 이미 구현 끝.  
이제 이 부분은 수정하지 않고 그대로 유지할 것.

### 3.2 채용 데이터

- **자사 채용 페이지·Career 페이지**
  - 회사 홈페이지 기반으로 TI/크롤러가 파악한 `recruits_url`
  - `page_type` (`listing`, `one_page`, `main`)에 따라 파싱 로직 분기
- **금지된 소스**
  - 외부 채용 플랫폼(사람인, JobKorea, 인크루트, 워크넷 등)은 **직접 크롤링하지 않음**  
    → 해당 도메인/패턴 발견 시 **즉시 스파이더 중단**.

---

## 4. 프로젝트 구조 (요지)

```text
project_root/
├─ config/
│  ├─ settings.py
│  ├─ urls.py
│  └─ ...
├─ api/
│  ├─ models.py
│  ├─ serializers.py
│  ├─ views_jobs.py        # GET /api/job-postings/
│  ├─ views_match.py       # 매칭 API 3종
│  ├─ matching.py          # 매칭 로직(가중치 매트릭스)
│  ├─ counseling_field_extractor.py  # 상담 텍스트 정규화
│  ├─ postprocess.py       # JobPosting 텍스트 후처리(현재 v1/진행중)
│  ├─ management/commands/
│  │  ├─ seed_companies_from_csv.py  # 회사 시딩 (회사 파트)
│  │  ├─ run_job_collector_spiders.py# 전사 크롤링 스케줄 (스켈레톤/진행중)
│  │  └─ (추가 예정: job_posting 후처리용 명령)
│  └─ ...
└─ crawler/
   ├─ scrapy.cfg
   └─ crawler/
      ├─ settings.py
      └─ spiders/
         ├─ job_collector.py        # 채용공고 수집 스파이더
         └─ (company/homepage 관련 스파이더: 이미 구현, 수정 금지 영역)
```

---

## 5. 현재까지 구현된 기능

### 5.1 Company / 회사 관련 (완료, 수정 금지 영역)

- Company 모델:
  - `name`, `name_norm` (정규화된 이름)
  - `homepage_url`, `homepage_host`
  - 데이터 출처/상태(`source_meta`, `homepage_url_status`, 체크 메타데이터)
  - DART 관련 필드 (`dart_corp_code`, `stock_code`, `bizr_no`)
  - SWDB 관련 필드 (`swdb_fin_year`) 등
- 시딩/수집
  - `seed_companies_from_csv` : CSV 기반 초기 시딩
  - 오픈소스 지도, DART, SWDB 데이터를 이용해 enrich
- 리치 로직
  - dead 회사 판별, 도메인 기반 dedupe, 상태 관리 로직 이미 구현

> 이 부분은 리팩터링/삭제하지 말고, 필요 시 참고만 할 것.

### 5.2 JobPosting / 채용공고 모델

- 핵심 필드:
  - `company` (FK), `title`, `post_url`
  - `job_description`, `location`
  - `posted_at`, `deadline_at`
  - `employment_type` (신입, 신입+경력 등)
  - `salary`
  - `benefits`
  - `qualifications`, `preferred_qualifications`
  - `hiring_process`, `hiring_message`, `work_hours`
  - `status`, `crawled_at`
  - `is_active` (bool), `first_seen_at` (datetime, auto_now_add)

### 5.3 크롤러: job_collector

- 스파이더 인자:
  - `company_id=<int>`
  - `recruits_url=<str>`
  - `page_type=listing|one_page|main`
  - `post_type=text` (현재 text만)
- 기능:
  - 목록형 / 단일 / 메인 페이지 구조에 따라 링크 탐색
  - `채용, 모집, 인턴, 구인, 경력, 신입, 구합니다` 등의 **한글 앵커 텍스트** +  
    `job, jobs, recruit, position, career` 등의 **URL 토큰**을 OR로 사용해 채용 공고/리스트 링크 후보 선택
  - “지원서 수정/채용 절차/공통 안내” 류는 제외
  - 외부 채용 플랫폼 링크(Saramin, JobKorea 등) 발견 시 **즉시 중단**
  - 개별 공고 페이지 파싱 → JobPosting 스키마로 **업서트(upsert)**

### 5.4 Django API

- `GET /api/job-postings/`
  - JobPosting 리스트 조회
  - 검색/필터/페이지네이션
  - 토큰 없이 읽기 전용(현재 정책)
- `POST /api/normalize/counseling`
  - 상담 텍스트 → 표준 필드(`근무지`, `급여`, `구인구분`, `기술스택`, `복리후생`, `필수조건`…) 추출
- `POST /api/match/student-top`
  - 학생 1명 JSON → 상위 N개 JobPosting
- `POST /api/match/company-top`
  - 특정 회사 + 학생 리스트 → 상위 N명
- `POST /api/match/batch`
  - 학생들 × JobPosting들 다대다 매칭 (Top-K 약간 완화)

#### 매칭 가중치 (고정)

| key              | weight |
| ---------------- | -----: |
| role             |     20 |
| skills           |     30 |
| location         |     10 |
| employment_type  |      8 |
| welfare          |      8 |
| salary           |      8 |
| company_industry |      6 |
| etc              |     10 |

- Trainee/학생은 DB로 저장하지 않고 **요청 시 JSON으로만 들어옴**.

### 5.5 텍스트 후처리 (현재 v1, 진행 중)

파일: `api/postprocess.py`, 클래스: `JobPostingNormalizer`

- 현재 구현된 것:
  - **HTML → 텍스트 변환**
    - BeautifulSoup로 `script/style/meta/link/form/iframe` 제거
    - `<br>` → 줄바꿈
  - **JSON/설정/스크립트 노이즈 제거**
    - `{` + `"키":` 패턴이 여러 개 있고 특수문자 비율 높은 블록만 **보수적으로 제거**  
      (greetingHR/React/설정 JSON, `link":{"type":"url"...}` 등)
      - 너무 많이 삭제되면 원본을 유지하는 안전장치 있음.
  - **섹션 헤더 기반 줄바꿈 삽입**
    - `Responsibilities`, `Qualifications`, `Location`, `Benefits`,
      `직군`, `경력사항`, `고용형태`, `근무지`, `복리후생`, `전형절차` 등 앞뒤에 인위적 `\n` 삽입
  - **블록 분할 + 노이즈 필터**
    - 줄바꿈 기준 블록화
    - CSS/JS/JSON처럼 보이는 블록, 네비/푸터/지원하기 버튼 등 제거
  - **섹션 라벨링**
    - 블록을 보고 `main_tasks`, `requirements`, `preferred`, `benefits`, `process`, `application` 등으로 태깅
    - 현재는 job_description용으로 **“명확히 자격/우대/복리/절차/지원 섹션은 제외”**하는 데 사용
  - **중복 제거 + 문장 끝 정리**
    - 동일/유사 블록 제거
    - 블록 끝에 마침표 등 없으면 붙여서 이어붙일 때 붙어 보이지 않게 처리

- 아직 **연결되지 않은 상태**:
  - `JobPostingNormalizer`는 **유틸 수준**이며,
    - `job_collector.py`에서 자동 호출하지 않고
    - DB에 저장된 JobPosting을 일괄 후처리하는 **management command / Celery 태스크도 아직 없음**.
  - job_description 외에 `qualifications/benefits/hiring_process` 같은 필드 간 **재분배 로직도 설계만 있고 구현 전**.

---

## 6. 앞으로 해야 할 개발 과제

### 6.1 텍스트 후처리 고도화

1. `JobPostingNormalizer.normalize_all_fields(posting)` 구현
   - 입력: JobPosting 인스턴스
   - 내부 로직:
     - 각 필드(`job_description`, `qualifications`, `preferred_qualifications`, `benefits`, `hiring_process`, `hiring_message` 등)를 세그먼트로 모으기
     - HTML/JSON/노이즈 제거 → 블록 분해 → 라벨링 (`main_tasks`, `requirements`, `preferred`, `benefits`, `process`, `application`, `company_intro`, `other`)
     - 라벨별로 필드를 재구성:
       - `main_tasks` → `job_description`
       - `requirements` → `qualifications`
       - `preferred` → `preferred_qualifications`
       - `benefits` → `benefits`
       - `process` → `hiring_process`
       - `application` → 별도 필드 or `hiring_message`
   - 출력: 정제된 필드 딕셔너리 (`dict`) 또는 직접 model 필드를 업데이트

2. 후처리 실행 방식
   - **Step 1: 수동/배치용 management command**
     - 예: `python manage.py normalize_job_posting --id 2410`
       - before/after를 콘솔에 찍어서 튜닝에 사용
     - 예: `python manage.py normalize_job_posting --all`
       - 전체 JobPosting에 대해 일괄 후처리 (주의: 배치 작업, Celery로 넘기는 게 이상적)
   - **Step 2: Celery 태스크 연계**
     - JobPosting 생성/업데이트 후, 비동기로 후처리 태스크 발행
     - 실패 시 재시도/로그 기록

3. 라벨링 패턴 튜닝
   - 실제 데이터 여러 건에 대해:
     - 여전히 남아 있는 JS/추적코드/메뉴 조각 제거 패턴 추가
     - 자격/우대/복리/절차/지원 문장이 섞여 들어가는 경우 라벨링 규칙 보완

---

### 6.2 크롤러(구인공고) 쪽 개선

> 회사/홈페이지 수집 파트는 수정 금지.  
> 아래는 구인 페이지 파악 & 구인 정보 수집 파트만.

1. 동적 렌더링 페이지 대응
   - `crawler/spiders/job_collector.py`에 Playwright 또는 Splash 기반 렌더링 레이어 추가
   - 동적 페이지 감지 조건(ex: 초기 HTML에 내용 부족 + script-heavy)일 때만 렌더링 사용
   - 타임아웃, 재시도, 실패 시 일반 HTTP HTML 처리로 폴백

2. 링크 탐색/판별 개선
   - 앵커 텍스트, URL 토큰뿐 아니라:
     - DOM 위치, 주변 문맥, 버튼/메뉴/푸터 여부를 반영한 간단한 스코어링
   - “지원서 수정”, “FAQ”, “회사 소개”, “팀 소개” 등은 강한 exclude 패턴 유지/확장

3. 에러/로그 개선
   - 외부 플랫폼 감지 시 CloseSpider + 명확한 로그
   - 특정 회사별 예외(특이한 구조) 처리용 hook 확보

---

### 6.3 운영/스케줄링

1. `run_job_collector_spiders` 구현
   - 활성 Company 목록 조회
   - 각 회사에 대한 job_collector 실행(or Celery 태스크 발행)
   - 너무 많은 동시 실행 방지를 위한 rate limiting/큐 관리

2. Celery Beat 스케줄 설정
   - 예: 매일 새벽 전사 크롤링 1회
   - 또는 회사별 주기(일/주 단위) 설정 가능하게

---

### 6.4 테스트 및 문서

1. 테스트
   - `JobPostingNormalizer`에 대한 단위 테스트 (입력 → 정제 결과 스냅샷)
   - 매칭 엔진(`matching.py`) 결과 안정성 테스트
   - 상담 텍스트 정규화(`counseling_field_extractor`) 샘플 테스트

2. 문서
   - `TECHNICAL.md` / `API_Usage_Guide.md` / `Crawling_Playbook.md` 최신화:
     - 현재 파이프라인 설명
     - 금지 도메인 정책
     - 후처리 파이프라인 설명
     - 운영 명령어 정리

---

## 7. 핵심 요약

1. **Company/홈페이지 수집 및 DART/SWDB/지도데이터 연계 로직은 이미 잘 동작 중이며, 변경하지 않는다.**  
   필요 시 파일을 참고만 할 것.

2. 앞으로 중점 개발 영역은:
   - **구인공고 텍스트 후처리 고도화**
     - HTML/JSON/스크립트/노이즈 제거
     - 필드 간 오분류된 텍스트 재분배 (`job_description`, `qualifications`, `benefits`, `hiring_process` 등)
   - **job_collector 스파이더 개선**
     - 동적 렌더링 페이지 처리
     - 링크 탐색 정확도 향상

3. 후처리는 **“수집 후 별도 실행(batch 또는 Celery)”** 전략을 기본으로 한다.  
   우선 management command 형태로 구현하고, 이후 Celery로 확장한다.
