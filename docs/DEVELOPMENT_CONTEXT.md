# Job Crawler 개발 컨텍스트 문서

**최종 업데이트**: 2026-04-01  
**작성자**: Sisyphus (AI Agent)  
**목적**: 다른 환경에서 OpenCode로 개발을 이어가기 위한 컨텍스트 문서

---

## 1. 프로젝트 개요

### 1.1 목표
한국 IT/제조업체의 채용 공고 자동 수집 및 매칭 시스템

### 1.2 기술 스택
- **Backend**: Django + DRF
- **Crawler**: Scrapy
- **Background Jobs**: Celery + Redis
- **Database**: MariaDB (Docker)
- **LLM**: 로컬 (llama-cpp-python + Qwen2.5-0.5B, 모델 파일은 clone 후 별도 다운로드)

---

## 2. 지금까지 개발한 내용

### 2.1 데이터 수집 파이프라인

| 구성요소 | 파일 | 설명 |
|---------|------|------|
| **OSM 수집** | `api/company_sources.py` | OpenStreetMap에서 IT/제조업체 수집 |
| **SWDB 수집** | `api/company_sources.py` | 소프트웨어DB CSV에서 수집 |
| **DART 수집** | `api/company_sources.py` | 금융감독원 API에서 상장사 수집 |
| **Homepage 체크** | `api/tasks.py` | 회사 웹사이트存活 상태 확인 |

### 2.2 채용 페이지 탐색

| 구성요소 | 파일 | 설명 |
|---------|------|------|
| **Discover Careers Spider** | `crawler/crawler/spiders/discover_careers.py` | 채용 페이지 URL 탐색 |
| **_PAGE_TYPE 판단** | 동일 파일 | listing/one_page/main/external 분류 |
| **POST_TYPE 판단** | 동일 파일 | text/image/external_link 분류 |
| **외부 플랫폼 감지** | 동일 파일 | wanted, saramin, jobkorea 감지 |

### 2.3 채용 공고 수집

| 구성요소 | 파일 | 설명 |
|---------|------|------|
| **Job Collector Spider** | `crawler/crawler/spiders/job_collector.py` | 채용 공고 정보 추출 |
| **섹션별 추출** | 동일 파일 | 주요 업무, 자격 요건, 우대 사항, 채용 절차, 복리후생 |
| **post_url 고유성** | `_make_unique_post_url()` | 각 공고별 고유 URL 생성 (#job-{md5}-{index}) |
| **품질 게이트** | `_looks_like_job_body()` | 부가정보/네비게이션 텍스트 방지 |

### 2.4 로컬 LLM 통합 (2026)

| 구성요소 | 파일 | 설명 |
|---------|------|------|
| **LLM Parser** | `api/llm_parser.py` | 구조화된 채용 정보 추출 |
| **날짜 추출** | `_extract_dates()` | deadline_at, posted_at (한국어 패턴 지원) |
| **급여 추출** | `_extract_salary()` | 연봉/월급 패턴 매칭 |
| **섹션 경계 수정** | 동일 파일 | preferred_qualifications 오염 방지 |

### 2.5 Celery 태스크

| 태스크 | 파일 | 설명 |
|--------|------|------|
| `crawl_company_careers` | `api/tasks.py` | 여러 회사 채용 페이지 크롤링 |
| `crawl_single_company_career` | `api/tasks.py` | 개별 회사 크롤링 |
| `extract_job_content` | `api/tasks.py` | 로컬 LLM으로 콘텐츠 추출 |

### 2.6 CSV 내보내기

| 파일 | 설명 |
|------|------|
| `data/companies_latest.csv` | 전체 회사 데이터 (65,220행) |
| `data/job_postings_latest.csv` | 채용 공고 데이터 |

---

## 3. 현재 개발해야 할 내용

### 3.1 높은 우선순위

| 항목 | 설명 | 관련 파일 |
|------|------|-----------|
| **급여 추출 개선** | 현재 0% 추출률 - 정규식/LLM 프롬프트 개선 필요 | `api/llm_parser.py` |
| **preferred_qualifications 오염** | 다음 섹션 내용이 섞이는 문제 해결 | `api/llm_parser.py` |
| **전체 회사 크롤링** | 일부 회사만 테스트됨 - 전체 대상으로 실행 | `api/tasks.py` |
| ** date 필터 개선** | 날짜 필터나 _accept_as_job() 통과 못한 건暂无 건드리지 말라 (사용자 요청) | - |

### 3.2 중간 우선순위

| 항목 | 설명 | 관련 파일 |
|------|------|-----------|
| **SM C&C JS 렌더링** | Next.js 기반 페이지 Scrapy로 수집 불가 → 별도 해결책 필요 | `crawler/crawler/spiders/job_collector.py` |
| **LLM 성능 개선** | Qwen2.5-0.5B 지연 (30-60초) - 모델 크기 또는 프롬프트 최적화 | `api/llm_parser.py` |
| **품질 게이트 재검토** | 200자 미만 콘텐츠 거부 → 의도치 않은 공고 제외 가능성 | `crawler/crawler/spiders/job_collector.py` |

### 3.3 낮은 우선순위

| 항목 | 설명 |
|------|------|
| **Playwright 미사용** | 사용자가 명시: "Playwright는 쓰지 말자" |
| **다국어 지원 불필요** | 사용자 요청: "한국 회사 대상이므로 multilingual 필요 없음" |

---

## 4. 미뤄둔 내용 (사용자 요청)

사용자가 명시적으로 **건드리지 말라**고 지시한 사항:

1. **날짜 필터 통과 못한 공고**: `_accept_as_job()`에서 거절한 공고는 수정하지 않음
2. **새로운 모델 학습**: "새로 학습해서 쓰지는 않을거야" - 사전학습 모델 사용
3. **Playwright 사용**: "Playwright는 쓰지 말자" - Scrapy로만 구현
4. **외부 플랫폼 직접 크롤링**: wanted, saramin, jobkorea 등은 제외

---

## 5. 현재 문제점 및 기술적 이슈

### 5.1 추출률 문제

| 필드 | 현재 추출률 | 원인 |
|------|-------------|------|
| `deadline_at` | 15% (5/33) | 날짜 패턴 미인식, 페이지 구조 다양성 |
| `posted_at` | 15% (5/33) | 동일 |
| `salary` | 0% (0/33) | 정규식 패턴 부재 또는 LLM 미추출 |
| `qualifications` | 42% (14/33) | 섹션 경계 오염, 품질 게이트 통과 실패 |

### 5.2 기술적 이슈

| 이슈 | 설명 | 영향 |
|------|------|------|
| **JS 렌더링 페이지** | Next.js 기반 채용 페이 Scrapy로 완전히 수집 불가 | 일부 회사 공고 누락 |
| **LLM 지연** | Qwen2.5-0.5B 생성 30-60초 | 타임아웃 발생 가능 |
| **콘텐츠 오염** | 섹션별 경계模糊 | 잘못된 데이터 저장 |
| **post_url 불일치** | 이전: `#job-{index}` → 이제: `#job-{md5}-{index}` | 중복 공고 발생 가능성 |

### 5.3 데이터 품질 문제

```
- 일부 회사의 채용 페이지 발견 안됨
- 외부 플랫폼 링크는 감지하나 실제 공고 크롤링 안함
- 이미지 기반 채용 공고는 텍스트 추출 불가
```

---

## 6. 데이터베이스 상태

### 6.1 현재 데이터

| 테이블 | 레코드 수 | 최종 업데이트 |
|--------|-----------|---------------|
| Company | ~1,000+ | 2026-04-01 |
| JobPosting | 33 | 2026-04-01 |

### 6.2 DB 접근 정보

```
Host: db (Docker 내부)
Port: 3306 (외부: 3308)
Database: job_data
User: user
Password: uR7!fP9v@L3xA2qT#e6K
```

---

## 7. Git 히스토리 (최근 커밋)

```
2a096b7 Update documentation with latest developments and setup guide
6df008f Remove negative keyword detection from career page discovery
a9c5b05 Export latest DB data to CSV snapshots
0f6298b Add Celery tasks for LLM-based job content extraction
0c31341 Improve job crawler with date extraction and post_url fixes
6a8f68c Add local LLM support with llama-cpp-python and Qwen model
b6465e8 Export latest companies and job postings CSV snapshots
```

---

## 8. 다음 개발자를 위한 가이드

### 8.1 개발 환경 설정

```bash
# 레포지토리 클론
git clone https://github.com/shadowteias/job_crawler_full_template.git
cd job_crawler_full_template

# 모델 다운로드 (git 미포함)
python scripts/download_models.py

# Docker 실행
docker network create backend_net
docker compose build
docker compose up -d

# DB 접근 확인
docker compose exec app python manage.py shell
```

### 8.2 빠른 시작

```bash
# 수동 크롤링 실행
curl -X POST "http://localhost:8200/api/crawl/run/" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: internal_token_8h_7Kifc0r" \
  -d '{"company_id_start":1,"company_id_end":20,"workers":2,"run_homepage_check":true,"run_discover":true,"run_collect":true}'

# CSV 내보내기
docker compose exec app python manage.py export_companies_to_csv --output /app/data/companies_latest.csv
```

### 8.3 주요 디렉토리

```
api/                      # Django 앱 (모델, 뷰, 태스크)
├── models.py            # Company, JobPosting 모델
├── tasks.py             # Celery 태스크
├── llm_parser.py        # LLM 기반 파싱
└── company_sources.py   # OSM/SWDB/DART 수집

crawler/crawler/spiders/ # Scrapy 스파이더
├── discover_careers.py # 채용 페이지 탐색
└── job_collector.py     # 채용 공고 수집

docs/                    # 문서
├── PROJECT_STRUCTURE.md # 프로젝트 구조
├── SETUP_GUIDE.md       # 설정 가이드
└── RUNBOOK.md           # 운영 매뉴얼
```

### 8.4 핵심 함수

| 파일 | 함수 | 용도 |
|------|------|------|
| `job_collector.py` | `upsert_jobposting()` | 채용 공고 DB 저장 |
| `job_collector.py` | `_make_unique_post_url()` | 고유 URL 생성 |
| `llm_parser.py` | `_extract_dates()` | 날짜 추출 |
| `llm_parser.py` | `_extract_salary()` | 급여 추출 |
| `llm_parser.py` | `parse_job_with_llm()` | LLM 파싱 |

---

## 9. 사용자Constraints (명시적 요청)

> **아래 규칙은 반드시 준수할 것**

1. **Git 커밋**: 사용자가 지시할 때까지 기다려라
2. **Playwright**: 사용하지 말자
3. **날짜 필터**: `_accept_as_job()` 통과 못한 건 건드리지 말자
4. **새로운 모델 학습**: 하지 말자 (사전학습 모델 사용)
5. **다국어 지원**: 한국 회사만 대상이므로 불필요
6. **외부 플랫폼**: wanted, saramin, jobkorea 등은 직접 크롤링 안 함

---

## 10. 참고 문서

- `docs/PROJECT_STRUCTURE.md`: 상세 프로젝트 구조
- `docs/SETUP_GUIDE.md`: 신규 컴퓨터 설정 가이드
- `docs/RUNBOOK.md`: 운영 매뉴얼
- `README.md`: 프로젝트 개요

---

## 11. 연락처

**사용자**: shadowteias (teias@kaist.ac.kr)  
**GitHub**: https://github.com/shadowteias/job_crawler_full_template

---

*이 문서는 OpenCode AI Agent가 작성했습니다. 개발 시 참고용으로 활용하세요.*
