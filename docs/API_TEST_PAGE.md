# API Test Page

## URL

```text
http://localhost:8200/api-test/
```

Chrome에서 바로 열 수 있다.

## Internal token

이 페이지는 Django가 렌더링할 때 `settings.API_INTERNAL_TOKEN` 값을 페이지에 주입하고, 브라우저의 `fetch()` 호출마다 아래 헤더를 자동으로 붙인다.

- `X-Internal-Token`
- `X-API-KEY`

따라서 테스트 페이지에서 internal token을 직접 입력하지 않아도 된다.

주의: 이 페이지는 내부 개발/검증용이다. 운영 외부 공개망에 그대로 노출하지 않는다.

## 제공되는 테스트

### 1. Crawl status

```http
GET /api/crawl/status/
```

수동 크롤링 lock/status Redis 값을 확인한다.

### 2. Job listings

```http
GET /api/jobs?active=1&page_size=5&q=Python
GET /api/job-postings/?limit=5
```

상단 query 입력칸에서 예시 값을 바꿔서 조회할 수 있다.

### 3. Counseling normalize

기본 예시 payload:

```json
{
  "text": "신입 백엔드 개발자 포지션을 희망합니다. Python, Django, FastAPI, React 프로젝트 경험이 있고 서울 또는 수도권 근무를 선호합니다. 연봉은 최소 3,700만원 이상이면 좋겠고 재택근무, 건강검진, 교육비 지원을 중요하게 봅니다.",
  "only_fields": ["구인구분", "구인기술", "근무지", "급여", "기술스택", "복리후생", "필수조건"]
}
```

### 4. Matching APIs

엔드포인트 선택값에 따라 payload 예시가 자동으로 바뀐다.

- `/api/match/student-top`
- `/api/match/company-top`
- `/api/match/batch`

예시는 Python/Django 백엔드, Java/Spring, React/TypeScript 학생 프로필을 포함한다.

### 5. GPT/job parser test

```http
POST /api/parse/job/
```

DB 저장 없이 GPT/OpenAI parser 설정과 smoke-test 상태를 확인한다. ChatGPT Plus 로그인만으로는 API 호출이 되지 않고 OpenAI Platform API key가 필요하다. `OPENAI_PROJECT_ID`는 OpenAI Platform project를 분리해서 쓰는 경우 입력하며, 단순 첫 테스트에서는 비워도 된다. 기존 `OPENAI_PROJECT`도 호환되지만 새 설정은 `OPENAI_PROJECT_ID`를 권장한다.

브라우저 테스트 페이지에는 OpenAI key 입력칸을 두지 않는다. `OPENAI_PARSER_ENABLED=1`이고 서버/container 환경에 `OPENAI_API_KEY`가 있으면 GPT 파서를 호출한다. 둘 중 하나가 꺼져 있으면 `parsed`는 비어 있고 `skipped_reason`에 설정 누락 사유가 표시된다. 이 테스트는 무거운 로컬 zero-shot fallback 모델을 로드하지 않는다.

실제 GPT 호출을 하려면 `.env` 또는 배포 secret에 아래 값을 넣고 app을 재생성한다.

```env
OPENAI_PARSER_ENABLED=1
OPENAI_API_KEY=...
OPENAI_PROJECT_ID=   # optional
OPENAI_MODEL=gpt-4o-mini
```

```bash
docker compose up -d --force-recreate app worker
```

기본 예시 payload:

```json
{
  "company_name": "샘플소프트",
  "url": "https://example.com/careers/backend-python",
  "text": "백엔드 개발자 채용. 주요 업무: Django/FastAPI 기반 API 개발, MySQL 데이터 모델링, 배치 작업 운영. 자격 요건: Python 2년 이상, REST API 설계 경험, Git 협업 경험. 우대 사항: React 경험, AWS 배포 경험. 근무지: 서울 강남구. 고용 형태: 정규직. 연봉: 4,000만원 이상 협의. 복리후생: 재택근무, 건강검진, 교육비 지원. 접수 마감: 2026-06-30."
}
```

실제 URL 기반 smoke-test payload:

```json
{
  "company_name": "Python Software Foundation",
  "url": "https://www.python.org/jobs/",
  "fetch_url": true,
  "text": ""
}
```

`fetch_url=true`이면 서버가 URL을 직접 요청하고 HTML에서 visible text를 추출한 뒤 GPT parser에 전달한다. 안전을 위해 public `http/https` URL만 허용하고, localhost/private/link-local 주소와 비텍스트 응답은 거부한다. 응답의 `source.fetch_result`에서 fetch 성공 여부, HTTP status, content type, 추출 텍스트 길이, 짧은 preview를 확인할 수 있다.

응답의 `parser_config`에서 현재 app 컨테이너에 OpenAI parser 설정이 반영됐는지 확인할 수 있다.

- `smoke_status=configuration_only`: 설정 확인만 수행, 실제 OpenAI 호출 없음.
- `smoke_status=real_openai_call_attempted`: 실제 OpenAI API 호출 시도.
- `openai_api_key_configured=true`: 서버/container에 OpenAI API key가 설정됨.
- `source.fetched=true`: `fetch_url=true` 요청에서 실제 URL text 추출 성공.
- `parsed`가 비어 있지 않으면 실제 GPT 응답으로 구조화 필드가 추출된 practical evidence로 본다.

### 6. Manual crawl run

기본 예시 payload:

```json
{
  "company_id_start": null,
  "company_id_end": null,
  "run_homepage_check": false,
  "run_discover": true,
  "run_collect": true,
  "discover_limit": 2,
  "collect_limit": 2,
  "workers": 1
}
```

주의: 이 버튼은 실제 Celery 작업을 큐잉한다. 기본값은 작은 검증용이다.

### 7. Company CSV import

```http
POST /api/companies/import-csv/
```

회사명/홈페이지 CSV를 Company 테이블로 가져와 크롤링 시작점(회사 목록)을 늘릴 때 사용한다. 두 가지 입력 방식을 지원한다.

1. JSON body의 `csv_text`
2. `multipart/form-data` 업로드의 `csv_file`

중복 방지 전략(순서):

1. `name` exact match
2. `name_norm` match (법인 접미어 제거 + lower/문자 정규화)
3. `homepage_host` match (`www.` 제거 host 기준)

요청 옵션:

- `update_existing` (default: true): 중복 매칭 시 값이 달라진 필드 갱신
- `dry_run` (default: false): DB 저장 없이 created/updated/skipped 결과만 시뮬레이션

예시 payload:

```json
{
  "update_existing": true,
  "dry_run": false,
  "csv_text": "company_name,homepage_url,recruits_url,page_type,post_type,hiring,region,industry,address,external_job_site\n파이썬랩,https://pythonlab.co.kr,https://pythonlab.co.kr/careers,listing,text,true,서울,소프트웨어,서울 강남구 테헤란로 100,"
}
```

multipart 예시:

- field: `csv_file` (업로드 파일)
- field: `update_existing=true|false`
- field: `dry_run=true|false`

샘플 파일:

- `data/company_import_example.csv`

응답:

- `summary.created|updated|skipped|invalid`
- `rows[]` 라인별 처리 상태 (`created`, `updated`, `skipped`, `invalid`) 및 사유/변경 필드

## Docker 접속 문제 재발 방지

이번 `localhost:8200` 접속 실패의 직접 원인은 Docker Desktop 자체가 아니라 `app`/`worker` 컨테이너가 오래된 이미지 안의 `/entrypoint.sh`를 실행하면서 삭제된 `init_schedule` 명령을 호출하고 종료된 것이었다.

방지 조치:

- `docker-compose.yml`의 `app`/`worker`에 `entrypoint: ["/app/entrypoint.sh"]`를 명시했다.
- repo가 `/app`에 bind mount되므로, 컨테이너 재생성 시 현재 repo의 최신 entrypoint를 사용한다.
- `app`/`worker`에 `restart: unless-stopped`를 추가했다.
- 오래된 `beat` orphan 컨테이너를 `--remove-orphans`로 제거했다.
- DB healthcheck가 root 비밀번호를 사용하도록 수정했다.

상태 확인 명령:

```bash
docker compose ps
docker compose logs --tail=100 app worker
docker compose up -d --no-build --force-recreate --remove-orphans app worker
```
