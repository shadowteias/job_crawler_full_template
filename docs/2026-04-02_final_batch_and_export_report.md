# 2026-04-02 최종 배치 실행 및 CSV Export 보고서

## 1. 작업 목적

이번 작업의 목적은 아래 4가지를 실제로 완료하는 것이었다.

1. `Company` 기준 `id 10000~13000` 범위(총 3001개 회사)에 대해 홈페이지 생존 여부를 반영한 상태에서 채용 페이지를 다시 탐색
2. 기존에 `recruits_url` 이 저장되어 있었더라도 다시 탐색하도록 범위 내 discovery 상태를 초기화한 뒤 재실행
3. 해당 범위 회사들에 대해 채용 공고를 다시 수집하고 `JobPosting` DB에 저장
4. `Company` / `JobPosting` 데이터를 날짜 포함 CSV 파일로 `data/` 에 저장하고, CSV 형식이 실제로 깨지지 않는지 검증

---

## 2. 이번에 사용한 실행 방식

환경 안정성을 위해 아래 조건으로 실행했다.

- Docker client: `docker.exe --context desktop-linux`
- 긴 작업은 app 컨테이너 내부 background 프로세스로 실행
- `rerun_company_crawl_range` 관리 명령 사용
- chunk size: `50`
- workers: `4`
- chunk 사이 sleep: `0.5s`

실행 명령의 핵심 동작은 다음과 같다.

- 범위 내 `recruits_url`, `page_type`, `post_type`, `recruits_url_status`, `recruits_url_score`, `external_job_site`, `hiring` 을 chunk 단위로 초기화
- `run_discover_careers_spiders_concurrent(...)` 재실행
- 이어서 `run_job_collector_spiders_concurrent(...)` 실행
- `JobPosting` 은 `post_url` 기준 upsert 되므로 기존 데이터와 충돌 없이 갱신 가능

---

## 3. 최종 집계 결과

범위: `Company.id 10000~13000`

### 회사 기준 집계

- 총 회사 수: `3001`
- 홈페이지 alive 상태 회사 수: `2448`
- `recruits_url` 확보 회사 수: `472`

### 채용 공고 기준 집계

- 저장된 `JobPosting` 수: `342`

---

## 4. 파싱 품질 집계

`JobPosting(company.id 10000~13000)` 기준 필드 커버리지:

- `job_description` 있음: `342`
- `qualifications` 있음: `29`
- `preferred_qualifications` 있음: `59`
- `location` 있음: `167`
- `salary` 있음: `9`
- `deadline_at` 있음: `132`

### 해석

- 최소한의 공고 본문(`job_description`)은 대부분 저장되었다.
- `location`, `deadline_at` 은 일부 의미 있는 결과가 나왔다.
- 그러나 `qualifications`, `preferred_qualifications`, `salary` 의 구조화 비율은 아직 낮다.
- 샘플 확인 결과, 일부 공고는 여전히 메뉴/회사소개/채용안내 문구가 많이 섞여 있어서 본문 품질이 균일하지 않다.

즉, 이번 작업으로 **대상 범위 재탐색 + 재수집 + DB 저장 + 안정적 export** 는 달성했지만, **파싱 품질 자체는 후속 개선 과제**로 남아 있다.

---

## 5. CSV Export 결과

생성한 최종 파일:

- `data/2026-04-02_companies_snapshot.csv`
- `data/2026-04-02_job_postings_snapshot.csv`

추가로 export 로직 검증용 시험 파일도 생성했지만, 최종 산출물은 위 두 파일이다.

### export 로직 특징

`export_snapshot_to_csv` 관리 명령을 사용했고, 아래 원칙으로 저장했다.

- `utf-8-sig`
- `newline=""`
- `csv.DictWriter`
- `quoting=csv.QUOTE_ALL`
- `lineterminator="\n"`
- `datetime/date` 는 `isoformat()` 으로 직렬화
- `dict/list` 는 JSON 문자열로 직렬화
- 문자열 내부 줄바꿈은 실제 개행 대신 `\n` 문자열로 변환

### 왜 이렇게 저장했는가

이전에는 `.csv` 라는 이름이지만 실제로는 활용이 어려운 경우가 있었다.

- 콤마가 들어간 텍스트 때문에 열이 밀리는 문제
- 따옴표가 섞인 텍스트 때문에 파싱이 깨지는 문제
- 멀티라인 텍스트가 실제 줄바꿈으로 들어가면서 툴에 따라 CSV 구조가 깨져 보이는 문제

이번에는 이를 피하기 위해 **모든 셀을 큰따옴표로 감싸고**, **내부 줄바꿈은 `\n` 문자열로 치환**했다.

따라서 텍스트 안에 `,` 가 있어도 CSV 열 구조가 깨지지 않는다.

---

## 6. CSV 형식 검증 결과

호스트에서 Python `csv.reader` 로 실제 파싱 검증을 수행했다.

### companies CSV

- 파일: `data/2026-04-02_companies_snapshot.csv`
- 헤더 컬럼 수: `30`
- 검사 행 수: `1000`
- 관찰된 row width: `[30]`
- bad row: `None`

### job postings CSV

- 파일: `data/2026-04-02_job_postings_snapshot.csv`
- 헤더 컬럼 수: `21`
- 검사 행 수: `342`
- 관찰된 row width: `[21]`
- bad row: `None`

즉, 적어도 이번 최종 export 파일들은 **CSV 파서 기준으로 열 수가 일정했고, 콤마 때문에 구조가 깨진 행은 확인되지 않았다.**

---

## 7. 기능적으로 확인된 점

### 잘 된 점

- `10000~13000` 범위에 대해 채용 페이지 재탐색을 실제로 다시 수행했다.
- 기존에 데이터가 있더라도 discovery 상태를 초기화하고 다시 저장했다.
- 재탐색 결과를 바탕으로 `JobPosting` 수집을 다시 수행했다.
- 최종 데이터를 실제 사용 가능한 CSV로 내보냈다.

### 아직 부족한 점

- 공고 본문 품질이 uneven 하다.
- 일부 결과는 navigation-heavy 텍스트가 섞여 있다.
- `salary`, `qualifications`, `preferred_qualifications` 추출률은 아직 낮다.

---

## 8. 결론

이번 작업으로 아래는 완료되었다.

- 범위 회사 재탐색
- 범위 공고 재수집
- DB 저장
- 날짜 포함 CSV export
- CSV 형식 검증

최종적으로 보면, 이번 세션의 핵심 성과는 단순 수집량보다도 아래에 있다.

1. 불안정한 WSL/Docker 환경에서도 안전한 실행 경로를 찾음
2. 범위 재실행이 가능한 관리 명령을 추가함
3. CSV 활용성을 실제로 보장하는 export 로직을 추가함

남은 과제는 **공고 저장량 확대**보다 **파싱 품질 개선** 쪽이 더 중요하다.

---

## 9. 2026-04-07 보수적 discovery 최적화 및 추가 검증

### 적용한 최적화

`crawler/crawler/spiders/discover_careers.py` 에서 정확도에 영향을 주지 않는 보수적 최적화만 적용했다.

1. response 단위 anchor cache 추가
   - 같은 페이지에서 `<a>` 태그를 여러 번 다시 순회하지 않도록 `href`, `full_url`, `text`, `label`, `combined_lower` 를 한 번만 구성해서 재사용
   - 적용 대상:
     - `find_direct_recruit_link()`
     - `contains_external_job_link()`
     - `select_candidate_links()`
     - `find_alternative_job_links()`
     - `looks_like_listing()`

2. response 단위 text cache 추가
   - `_get_text()` 와 `_get_visible_text()` 의 결과를 response 기준으로 캐시해서 재사용

3. `looks_like_listing()` 조기 종료
   - listing 판정 threshold(`depth=0 -> 5`, `depth>=1 -> 3`)를 넘는 순간 바로 `True` 반환
   - threshold를 넘은 뒤에도 남은 링크를 계속 스캔하던 비용 제거

4. `detect_post_type()` 조기 종료
   - `visible_text` 길이가 `500` 이상이면 기존 로직상 어차피 `text` 이므로, poster image 스캔 전에 바로 `"text"` 반환

이 변경들은 keyword, threshold, depth, 분기 조건 자체를 바꾸지 않고 **중복 파싱 비용만 줄이도록** 설계했다.

### 검증

- `python3 -m py_compile crawler/crawler/spiders/discover_careers.py` 통과
- `python3 -m unittest tests.test_spiders` 통과 (`34 tests OK`)

### 추가 실배치 테스트 범위

이전까지 테스트하지 않았던 범위에서 약 30분 분량에 해당하는 구간으로 아래 범위를 선택했다.

- `Company.id 23000~24099`
- 총 `1100`개 회사
- 실행 설정:
  - `workers=2`
  - `chunk_size=50`
  - `sleep_seconds=0.5`

### 단계별 결과

#### 1) 홈페이지 생존 확인

- 대상 회사 수: `1100`
- `alive`: `481`
- `dead`: `15`
- 기타 상태: `604`

#### 2) 구인페이지 탐색(discovery)

- discovery 대상 수: `485`
- `saved`: `485`
- `failed`: `0`

#### 3) 구인정보 크롤링(collector)

- collector 대상 수: `62`
- `completed`: `62`
- `failed`: `0`

#### 4) 최종 결과물

- `recruits_url` 확보 회사 수: `62`
- `JobPosting` 저장 수: `98`

### 소요 시간

청크 로그 기준 누적 시간:

- discovery 합계: `1055.35초` (약 `17분 35초`)
- collector 합계: `453.92초` (약 `7분 34초`)
- 합계: `1509.27초` (약 `25분 9초`)

즉, 목표했던 “약 30분 정도 작업시간”에 맞는 규모로 실제 검증을 마쳤다.

### 해석

- 이번 추가 범위에서는 discovery/collector 모두 `failed=0` 이었다.
- 컨테이너도 작업 종료 후 계속 `Up` 상태를 유지했다.
- 따라서 이번 보수적 최적화는 적어도 이 추가 실배치 범위에서는 **정확도를 떨어뜨리는 징후 없이, 안정적으로 동작**했다고 판단할 수 있다.
