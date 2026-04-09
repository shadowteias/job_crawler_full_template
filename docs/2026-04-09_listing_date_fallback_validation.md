# 2026-04-09 Listing Date Fallback 검증 메모

## 목적

이번 메모는 아래 두 가지를 확인하기 위해 작성했다.

1. 목록 페이지에는 날짜가 있지만 상세 페이지에는 날짜가 없는 공고를 현재 크롤러가 어떻게 처리하는지
2. 새로 추가한 listing-date fallback 이 실제로 유효 공고를 살리는지

---

## 구현한 변경

### 1. detail 우선, listing fallback

`crawler/crawler/spiders/job_collector.py` 에서 목록 페이지(`parse_listing`)가 detail 링크를 넘길 때, 링크 주변에서 읽은 날짜 힌트도 함께 넘기도록 수정했다.

- `extract_job_links()` 는 이제 각 후보 링크에 대해 아래 값을 함께 반환한다.
  - `url`
  - `deadline_at`
  - `posted_at`
- `parse_job_detail()` 는 `listing_deadline_at`, `listing_posted_at` 를 받아 detail 처리로 전달한다.
- `extract_job_from_detail()` 는 아래 우선순위로 날짜를 확정한다.
  1. detail 페이지에서 직접 추출한 날짜
  2. detail 날짜가 비었을 때 listing 에서 넘긴 날짜

즉, 상세 페이지 날짜가 있으면 항상 상세 페이지 값을 우선한다.

### 2. 유효 공고 판단 규칙

유효성 판단은 collector 저장 직전(`evaluate_posting_validity`)에 적용한다.

- `deadline_at` 가 있으면 현재 시점 이후여야 유효
- `deadline_at` 가 없으면 `posted_at` 가 최근 30일 이내여야 유효
- 둘 다 없으면 무효

### 3. stale posting 정리

같은 회사를 collector 가 정상 종료했을 때,

- 이번 실행에서 다시 확인된 `post_url` 만 active 유지
- 다시 확인되지 않은 기존 공고는 `expired / inactive` 처리

---

## 검증 과정

### 먼저 확인한 케이스: expired list-only

`10880 주식회사 미래전파공학연구소`

- listing page 에서는 날짜가 잡힘
  - `listing_hint = (2025-01-24, None)`
- detail page 에서는 날짜가 잡히지 않음
  - `detail_dates = (None, None)`

이 케이스는 listing-date fallback 대상은 맞지만,
listing 날짜 자체가 이미 지난 시점이라 최종적으로는 expired 처리되는 것이 맞다.

즉, 이 예시는 “fallback 구조가 필요한 유형”은 보여주지만,
유효 공고를 살리는 사례는 아니다.

---

## 실제로 유효 공고를 살린 케이스

### 회사

- `23048 (주)시큐인`
- `listing_url = http://www.secuin.co.kr/?pid=recruit_list`

### 관찰된 패턴

자동 탐색 결과, 아래 detail 링크들은:

- 목록 페이지에서는 `listing_dates = (2026-04-09, None)` 으로 잡혔고
- 상세 페이지에서는 `detail_dates = (None, None)` 이었다.

예시 detail URL:

- `http://www.secuin.co.kr/?pid=recruit_view&bid=17728`
- `http://www.secuin.co.kr/?pid=recruit_view&bid=17725`
- `http://www.secuin.co.kr/?pid=recruit_view&bid=17724`

즉 이 회사는 실제로:

- 목록 페이지 날짜는 있음
- 상세 페이지 날짜는 없음

이라는 우리가 찾고 있던 대표적인 valid list-only 케이스였다.

### rerun 후 DB 상태

`23048` 회사를 새 로직으로 다시 실행한 뒤 상태를 확인했다.

결과:

- 총 `JobPosting`: `49`
- `active`: `17`
- `with_any_date`: `17`
- `undated`: `32`

상세 내용을 보면:

- 기존 날짜 없는 32건은 모두 `False expired`
- 새로 유지된 17건은 모두
  - `posted_at = None`
  - `deadline_at = 2026-04-09`
  - `is_active = True`
  - `status = active`

즉 detail 페이지 자체는 날짜를 주지 않았지만,
listing page 에서 읽은 날짜가 fallback 으로 들어가면서
유효 공고로 남아야 할 항목들이 실제로 살아났다.

---

## 결론

이번 검증으로 확인된 사실은 아래와 같다.

1. 목록 페이지 날짜만 있고 상세 페이지 날짜가 없는 케이스는 실제로 존재한다.
2. 기존 로직은 그런 케이스를 놓칠 수 있었다.
3. 새로 넣은 listing-date fallback 은 실제 valid 케이스(`23048`)에서 작동했다.
4. 동시에 stale / undated posting 은 같은 회사 rerun 시 `expired / inactive` 로 정리되었다.

즉 현재 기준으로는:

- detail 날짜 우선
- listing 날짜 fallback
- 저장 직전 validity 판단
- 회사 단위 stale 정리

의 조합이 적절하게 동작한다고 볼 수 있다.

---

## 남은 caveat

listing-date fallback 은 유효한 보완이지만, listing 구조가 지저분한 사이트에서는 여전히 아래 리스크가 있다.

- 링크 주변의 날짜가 실제 해당 공고 날짜가 아니라 게시판 공통 날짜일 수 있음
- `posted_at` / `deadline_at` 구분이 약한 게시판에서는 한쪽만 잡힐 수 있음
- 회사 단위 rerun 이 정상 종료해야 stale 정리가 완전히 반영됨

하지만 이번에 확인한 `23048` 사례는, 이 fallback 이 단순 이론이 아니라 실제로 유효 공고를 살리는 데 도움이 된다는 근거로 충분하다.
