# 2026-04-23 Main-Based Selected Integration Summary

## 목적

이 문서는 GitHub 최신 `main` 기준으로 다시 작업 브랜치를 만들고,
우리가 이전 브랜치에서 검증했던 기능들 중 필요한 것만 선별적으로 합친 결과를 기록하기 위한 문서다.

이번 작업의 목표는 아래와 같았다.

1. `origin/main` 최신 기준에서 이후 작업이 이루어지게 할 것
2. 이전 브랜치에서 실험했던 기능 중, 사용자가 지정한 항목만 골라 반영할 것
3. 실제로 약 100개 alive 회사로 다시 검증할 것
4. 정상 동작한다고 판단되면 브랜치에 커밋/푸시할 것

---

## 기준 브랜치

- 기준: `origin/main`
- 작업 브랜치: `main-selected-integration`

중요한 점은, 이 작업은 기존 `listing-date-fallback-validation` 브랜치를 그대로 이어받은 것이 아니라,
**GitHub 최신 `main` 위에서 다시 필요한 기능만 선별적으로 올리는 방식**으로 진행했다는 것이다.

---

## 이번에 선택적으로 반영한 기능 묶음

### 1. 날짜/현재성/정리 묶음

다음 기능은 함께 들어가야 안전하다고 판단해 한 묶음으로 반영했다.

- `listing-date fallback`
  - detail 페이지 날짜가 비어 있을 때 listing 페이지 날짜 사용
- `posting validity gate`
  - `deadline_at >= today`
  - 또는 `deadline_at is null` and `posted_at within 30 days`
- `stale posting expiration`
  - 같은 회사 재실행 시 이번 run에서 다시 확인되지 않은 기존 공고는 `expired / inactive`

관련 파일:

- `api/llm_parser.py`
- `crawler/crawler/spiders/job_collector.py`
- `tests/test_spiders.py`

### 2. discovery 안정화 묶음

다음 기능도 함께 들어가는 것이 맞다고 판단했다.

- `response caching`
- `hard stop after first confident save`
- `direct recruit-link ranking`

관련 파일:

- `crawler/crawler/spiders/discover_careers.py`

### 3. 이미 main에 들어가 있어 별도 반영이 불필요했던 항목

아래는 `origin/main`에 이미 포함되어 있어서 이번 선택 통합 단계에서 별도 반영하지 않았다.

- admin 성능 개선
  - `api/admin.py`
  - `config/settings.py`
- CSV export command
  - `api/management/commands/export_snapshot_to_csv.py`

### 4. 문서

- `docs/2026-04-09_listing_date_fallback_validation.md`

이 문서는 listing-date fallback 검증 근거를 남기는 문서이므로 함께 반영했다.

---

## 반영하지 않은 것

이전 브랜치에서 시도했지만 최종 채택하지 않았던 항목들은 이번에도 반영하지 않았다.

- one_page deeper follow tweak
- aggressive one_page tightening
- lightweight post-discovery verifier
- aggressive collector high-confidence gate

이유는 모두 동일하다.

- 샘플 비교에서 개선 근거가 약했거나
- regression / false negative 위험이 컸기 때문이다.

---

## 검증

### 1. 코드/설정 검증

- `python3 -m py_compile` 통과
- `python3 -m unittest tests.test_spiders` 통과 (`44 tests OK`)
- `python manage.py check` 통과

### 2. 런타임 설정 확인

- `DEBUG False` 확인

### 3. 실제 alive 회사 100개 검증

alive 회사 중 100개를 골라 실제 discovery + collector 검증을 수행했다.

선정 방식:

- alive 회사 리스트에서 `offset 100 ~ 199`
- 실제 이 구간은 기존 active posting이 존재하는 편이라 검증 가치가 있었다.

결과:

- discovery
  - `total = 105`
  - `saved = 105`
  - `failed = 0`

- collector
  - `total = 64`
  - `completed = 63`
  - `failed = 1`

- 최종 active posting 수
  - `active_jobs_after = 92`

추가 집계:

- `with_recruits = 58`
- `listing = 19`
- `one_page = 14`
- `main = 21`
- `external = 4`
- `expired_jobs = 0`

### 해석

이 검증 기준으로는:

- discovery는 정상적으로 완주했고
- collector도 거의 전부 성공했으며
- 통합된 기능 묶음이 전체를 망가뜨리는 징후는 보이지 않았다.

collector 실패 1건은 있었지만, 이 정도는 전체 통합을 되돌릴 수준의 실패로 보지 않았다.

---

## 최종 판단

이번 선택 통합 버전은 아래 이유로 **정상 동작한다고 판단**했다.

1. 최신 `main` 위에서 다시 조립했다.
2. 이전 실험에서 실제 효과가 확인된 묶음만 반영했다.
3. 문법 / 테스트 / Django check / 실제 100개 alive 회사 검증을 통과했다.
4. broad verifier/과도한 tightening처럼 실패한 실험은 포함하지 않았다.

즉, 이 브랜치는 단순히 기능을 많이 가져온 브랜치가 아니라,
**최신 main 기준으로 필요한 것만 신중하게 선별한 안정화 통합 브랜치**라고 보는 것이 맞다.
