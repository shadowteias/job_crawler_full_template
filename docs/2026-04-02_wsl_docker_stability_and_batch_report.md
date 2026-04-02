# 2026-04-02 WSL / Docker Desktop 안정성 점검 및 배치 재개 보고서

## 0. 목적

이 문서는 아래 내용을 함께 기록하기 위한 보고서다.

1. 이전 작업 중 발생한 WSL / Docker Desktop 불안정 원인
2. 안정성 우선 기준으로 적용한 코드/실행 방식 수정
3. 안전한 재시도 방식으로 다시 수행한 import / crawl 결과
4. 현재 시점에서 확인된 한계와 다음 우선순위

---

## 1. 이번에 확인한 핵심 문제

이번 세션에서 확인된 문제는 크게 2종류였다.

### 1) 환경 문제

- WSL 내부의 `docker` 클라이언트는 `/var/run/docker.sock` 권한 문제로 Docker daemon에 안정적으로 붙지 못했다.
- 반면 `docker.exe --context desktop-linux` 는 Docker Desktop daemon에 정상 연결되었다.
- `docker-compose.yml` 은 external network `backend_net` 을 요구하므로, 이 네트워크가 없으면 `compose up` 자체가 실패한다.
- 실제 사용자 증상인 `WSL integration with distro 'Ubuntu' unexpectedly stopped` 는 Docker Desktop + WSL 연동 계층이 불안정할 때 자주 보이는 패턴과 맞아떨어진다.

### 2) 애플리케이션/컨테이너 기동 문제

WSL 문제와 별개로, 컨테이너 기동 시 아래 문제가 추가로 있었다.

- `app`, `worker`, `beat` 가 모두 같은 `/entrypoint.sh` 를 사용하고 있었다.
- 이 entrypoint 안에서 모든 서비스가 공통으로 아래 작업을 수행했다.
  - `python manage.py migrate`
  - `python manage.py collectstatic`
  - `python manage.py init_schedule`
- 그 결과 `worker`, `beat`, `app` 이 동시에 migration/schedule 초기화를 시도하면서 DB race가 발생했다.

실제 로그에서 확인한 오류:

- `django.db.utils.OperationalError: (1050, "Table 'auth_permission' already exists")`
- `django.db.utils.ProgrammingError: (1146, "Table 'job_data.django_celery_beat_intervalschedule' doesn't exist")`

즉, 이전에 컨테이너가 자꾸 내려간 원인은 단순히 WSL만이 아니라, **서비스 공통 entrypoint의 동시 migration 실행**도 직접적인 원인이었다.

---

## 2. 이번에 반영한 코드 수정

### 2.1 `api/tasks.py`

- wildcard import 제거
- `collect_swdb_companies`, `collect_dart_companies`, `check_company_homepages`, `setup_company_seed_schedules` 를 explicit import 하도록 변경
- `run_discover_careers_spiders*`, `run_job_collector_spiders*` 에 timeout 상수 추가
  - `DISCOVER_SPIDER_TIMEOUT = 120`
  - `JOB_COLLECTOR_TIMEOUT = 300`
- `find_missing_homepages`, `run_discover_careers_spiders`, `run_discover_careers_spiders_concurrent`, `run_job_collector_spiders`, `run_job_collector_spiders_concurrent` 에 `company_id_start`, `company_id_end` 범위 인자 추가

### 2.2 `api/company_sources.py`

- `check_company_homepages()` 에 `company_id_start`, `company_id_end` 추가
- 범위 필터 헬퍼 `_apply_company_id_range()` 추가

### 2.3 `api/views_match.py`

- 내부 인증 헤더를 `X-Internal-Token` 우선으로 맞춤
- 하위 호환으로 `X-API-KEY` fallback 유지

### 2.4 `api/views_extract.py`

- `X-Internal-Token` 우선
- `X-API-KEY`, `Authorization: Bearer ...` 하위 호환 유지

### 2.5 `api/models.py`

- `re.fullmatch(...)` 사용을 위한 `import re` 추가

### 2.6 `scripts/homepage_check_range.py`

- 10000~13000 같은 회사 ID 범위를 빠르게 재검사하기 위한 병렬 홈페이지 상태 점검 스크립트 추가
- 기존 `check_company_homepages()` 의 저장 규칙을 크게 바꾸지 않고, 이번 검증용 범위 실행을 빠르게 수행하기 위한 보조 도구다.

### 2.7 `entrypoint.sh`

- migration / collectstatic / init_schedule 실행 조건을 조정했다.
- 이제 `gunicorn` 으로 시작하는 app 컨테이너에서만 이 초기화 루틴이 돌고, `worker`, `beat` 는 Celery 프로세스만 실행한다.

이 수정은 이번 안정성 확보에서 가장 중요했다.

---

## 3. 기본 검증 결과

호스트 측 기본 검증:

- `python3 -m py_compile` 통과
- `python3 -m unittest tests.test_spiders` 통과 (`34 tests OK`)

컨테이너 재기동 후 확인:

- `job_crawler_app` 정상 기동
- `job_crawler_worker` 정상 기동
- `job_crawler_db` healthy
- `job_crawler_redis` healthy
- 이전처럼 `worker` / `beat` 가 migration race로 즉시 종료되는 현상은 제거됨

---

## 4. WSL / Docker Desktop 안정성 관점에서 이번에 얻은 결론

### 실제로 문제였던 것

1. WSL 내부 `docker` 접근 불안정
2. `backend_net` 미생성 시 compose 실패
3. 서비스 공통 entrypoint로 인한 DB migration race
4. 큰 이미지 빌드 + 긴 exec + 높은 병렬도 작업이 한 세션에서 겹치면 WSL/ Docker Desktop에 부담

### 현재 확인된 환경 조건

- Docker Desktop daemon은 `docker.exe --context desktop-linux` 로 접근 가능
- `.wslconfig` 는 현재 없음
- Docker Desktop 기준 메모리 총량은 약 `7.56GiB`
- 이미지 빌드에는 아래처럼 무거운 의존성이 포함된다.
  - `torch`
  - `transformers`
  - `llama-cpp-python`
  - Qwen GGUF 모델 다운로드

즉, 이 프로젝트는 기본적으로도 Docker/WSL에 가벼운 작업은 아니다.

---

## 5. 안정성 우선 실행 원칙

이번 조사와 실제 재시도 결과를 기준으로, 앞으로는 아래 원칙을 지키는 것이 맞다.

1. Docker 제어는 WSL 내부 `docker` 보다 `docker.exe --context desktop-linux` 기준으로 수행
2. 큰 이미지 빌드와 실제 크롤링 배치를 같은 타이밍에 겹치지 않음
3. 배치는 처음부터 크게 돌리지 않고 작은 범위로 나눔
4. 병렬도는 매우 낮게 시작
5. 컨테이너/WSL 상태를 매 배치 전후로 확인
6. 이상 징후가 보이면 즉시 멈추고 더 큰 범위로 확대하지 않음

이번 세션에서 실제로 사용한 안전 재시도 방식:

- Docker client: `docker.exe --context desktop-linux`
- 작은 회사 ID 범위 단위 실행
- discovery / collector 병렬도: `workers=2`
- 전체 3000개를 한 번에 다시 밀지 않고 작은 표본부터 재개

---

## 6. DB import 결과

실행 명령:

- `python manage.py import_companies_from_csv /app/data/companies_export.csv --update`

결과:

- `created=32609`
- `updated=0`
- `skipped=0`

확인 시점 기준 Company 총 수:

- `32609`

---

## 7. 홈페이지 생존 확인 결과 (10000~13000)

실행 방식:

- `scripts/homepage_check_range.py`
- `--start-id 10000 --end-id 13000 --workers 30 --timeout 5.0`

결과:

- `checked=3001`
- `alive=2322`
- `dead=51`
- `updated=3001`

주의:

- 이 값은 현재 스크립트의 빠른 재검사 기준 결과다.
- timeout을 5초로 두고 병렬 재검사했기 때문에, 느리지만 실제 살아있는 사이트가 일부 dead/unknown 계열로 보수적으로 잡혔을 가능성은 있다.
- 하지만 지금 목적은 **WSL을 다시 죽이지 않으면서 안전하게 다음 단계로 넘어갈 수 있는 운영 확인**이므로, 우선 보수적인 방식으로 재검사를 수행했다.

---

## 8. 조심스러운 재시도 결과

### 8.1 1차 소범위 테스트: 10000~10024

#### discovery

- 실행: `run_discover_careers_spiders_concurrent(workers=2, company_id_start=10000, company_id_end=10024)`
- 결과:
  - `total=20`
  - `saved=20`
  - `failed=0`
  - `elapsed≈36.84s`

#### job collector

- 실행: `run_job_collector_spiders_concurrent(workers=2, company_id_start=10000, company_id_end=10024)`
- 결과:
  - `total=1`
  - `completed=1`
  - `failed=0`
  - `elapsed≈2.46s`

#### 실제 저장 결과

- alive companies: `20`
- recruits_url 확보 회사 수: `1`
- 저장된 `JobPosting`: `0`

즉, 파이프라인은 돌았지만 이 첫 소범위에서는 실제 공고 저장까지 이어진 건 없었다.

---

### 8.2 2차 소범위 테스트: 10025~10074

#### discovery

- 결과:
  - `total=47`
  - `saved=47`
  - `failed=0`
  - `elapsed≈77.85s`

#### job collector

- 결과:
  - `total=10`
  - `completed=10`
  - `failed=0`
  - `elapsed≈215.40s`

---

## 9. 현재까지 누적 결과 (10000~10074 표본)

현재까지 확인한 누적 표본 기준:

- alive companies: `67`
- recruits_url 확보 회사 수: `11`
- 저장된 `JobPosting`: `5`

이 수치는 전체 10000~13000 완료 결과가 아니라, **환경 안정성을 깨지 않도록 작은 범위부터 다시 재개한 표본 결과**다.

---

## 10. 파싱 품질 점검 결과

표본 범위: `company id 10000~10074`

필드 커버리지:

- `job_description` 있음: `5`
- `qualifications` 있음: `0`
- `preferred_qualifications` 있음: `0`
- `location` 있음: `1`
- `salary` 있음: `0`
- `deadline_at` 있음: `0`

샘플 확인 결과:

- 일부 저장된 공고는 실제 채용 상세가 아니라 navigation / 안내성 텍스트가 많이 섞인 상태였다.
- 예시로 `주식회사 첫눈`, `주식회사 청담홀딩스` 표본에서는 `job_description` 필드가 채워졌더라도 실제로는 메뉴/회사소개/채용안내 문구가 많이 포함되어 있었다.
- 즉, 현재 파이프라인은 **“채용 페이지 탐색과 일부 공고 저장” 자체는 수행**하지만, **BERT/LLM/규칙 기반 파싱 품질은 아직 부족**하다고 판단된다.

---

## 11. 현재 시점 판단

### 긍정적인 점

- WSL/ Docker Desktop이 불안정한 상황에서도, 실행 방식을 조심스럽게 바꾸면 작업 재개는 가능했다.
- `entrypoint.sh` 수정으로 컨테이너가 서로 migration을 덮어쓰며 죽는 문제는 해소됐다.
- 작은 범위 + 낮은 병렬도에서는 discovery / collector가 실제로 돌아간다.

### 아직 부족한 점

- 전체 10000~13000 범위를 한 번에 다시 돌리기엔 현재 WSL 안정성이 충분히 입증되지 않았다.
- 파싱 품질은 아직 낮다.
- `qualifications`, `preferred_qualifications`, `salary`, `deadline_at` 같은 핵심 structured field 추출률이 낮다.
- 일부 저장 결과는 navigation-heavy text 오염이 있다.

---

## 12. 다음 우선순위

1. WSL 안정성 강화
   - `.wslconfig` 도입 검토
   - 메모리/CPU/swap 제한과 reclaim 정책 설정
   - 빌드와 대량 배치 실행을 분리

2. 배치 재개 방식 유지
   - `docker.exe --context desktop-linux` 사용
   - 25~50 company 단위 배치
   - `workers=2` 수준으로 시작

3. 파싱 품질 개선
   - collector 품질 게이트 재검토
   - navigation text 제거 강화
   - `qualifications` / `preferred_qualifications` / `salary` / `deadline_at` 추출 로직 개선

---

## 13. 결론

이번 세션의 가장 큰 성과는 단순히 배치 일부를 돌린 것이 아니라, **왜 자꾸 멈췄는지 실제 원인을 분리해낸 것**이다.

정리하면:

- WSL 연동 불안정은 실제 환경 문제였다.
- 동시에 앱 자체에도 `entrypoint.sh` 의 migration race라는 별도의 안정성 문제가 있었다.
- 이 race를 제거하고, Docker Desktop 경로를 일관되게 사용하고, 작은 범위/낮은 병렬도로 바꾸자 다시 작업을 진행할 수 있었다.
- 다만 현재는 “고속 대량 처리”보다 “안전한 소규모 재개” 단계에 가깝고, 파싱 품질은 여전히 후속 개선이 필요하다.
