
# 채용 데이터 플랫폼 API 가이드 (요약판 · Windows 전용 명령 포함)

> API_INTERNAL_TOKEN=internal_token_8h_7Kifc0r

> 이 문서는 **두 가지 엔드포인트**를 다룹니다.  
> 1) **상담내용 정규화 API** (`POST /api/normalize/counseling`)  
> 2) **구인공고 조회 API** (`GET /api/jobs`)  
> 각 항목은 **내부(토큰 보유)**, **외부(다른 프로그램)** 관점으로 분리하여 사용법을 제공합니다.

---

## 목차
1. 상담내용 정규화 API  
   1.1 내부 사용법 (X-API-KEY 필요)  
   1.2 외부 사용법 (다른 프로그램에서 호출 시)  
   1.3 요청/응답 스키마  
   1.4 트러블슈팅

2. 구인공고 조회 API  
   2.1 내부 사용법 (X-API-KEY 선택)  
   2.2 외부 사용법 (토큰 없이 조회 가능)  
   2.3 쿼리 파라미터  
   2.4 응답 예시  
   2.5 트러블슈팅

---

## 1. 상담내용 정규화 API

**Endpoint**
- `POST /api/normalize/counseling`
- 기능: 긴 상담 텍스트를 표준 필드로 추출/정규화하여 반환

> ⚠️ 보안 정책상 이 엔드포인트는 **기본적으로 내부 전용**입니다.  
> 외부 프로그램이 호출할 수는 있으나, **유효한 X-API-KEY 헤더**를 반드시 포함해야 합니다(내부 토큰을 전달받아 사용하거나, 역프록시/게이트웨이에서 헤더를 주입).

### 1.1 내부 사용법 (X-API-KEY 필요)

**사전 조건**
- `.env` 내 `API_INTERNAL_TOKEN` 값 확인 (컨테이너 내부에서 확인 예: `docker compose exec app python -c "import os; print(os.getenv('API_INTERNAL_TOKEN'))"`)

**Windows(Anaconda Prompt) 한 줄 테스트**  
(UTF-8/BOM 문제를 피하기 위해 먼저 페이로드 파일을 생성 후 전송)

1) **payload.json 생성 (BOM 없는 UTF-8)**
```powershell
powershell -NoProfile -Command "$p=@{text='신입 위주로 수도권 근무 희망. 연봉 최소 3,700 이상. Python/Django, React 경험. 재택/건강검진/자율출퇴근제 선호. 반드시 수도권.'}|ConvertTo-Json -Compress; $enc=New-Object System.Text.UTF8Encoding($false); [IO.File]::WriteAllText('payload.json',$p,$enc)"
```

2) **요청 전송**
```bat
set "TOKEN=내부_토큰값" && curl.exe -s -X POST "http://localhost:8000/api/normalize/counseling" -H "Content-Type: application/json; charset=utf-8" -H "X-API-KEY: %TOKEN%" --data-binary @payload.json
```

### 1.2 외부 사용법 (다른 프로그램에서 호출 시)

- **권장 방식 1:** 사내 API 게이트웨이/역프록시가 **X-API-KEY 주입** 후 내부 서비스로 전달
- **권장 방식 2:** 신뢰하는 외부 파트너에 한해 **내부 토큰을 발급**(단, 회수/로테이션 정책 필수)

**외부에서의 요청 예 (동일)**
```bat
set "TOKEN=발급받은_토큰" && curl.exe -s -X POST "https://<공개도메인>/api/normalize/counseling" -H "Content-Type: application/json; charset=utf-8" -H "X-API-KEY: %TOKEN%" --data-binary @payload.json
```

### 1.3 요청/응답 스키마

**Request (JSON)**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `text` | string | ✅ | 상담 원문 텍스트(한국어 우선).

**Response (JSON)** – 예시
```json
{
  "근무인원": null,
  "업종분류": null,
  "구인구분": "신입",
  "구인기술": "Python, Django, React",
  "근무지": "수도권",
  "급여": 3500,
  "기술스택": ["Python", "Django", "React"],
  "복리후생": ["재택근무", "건강검진", "자율출퇴근제"],
  "필수조건": ["근무지", "급여", "복리후생", "구인구분", "기술스택"]
}
```

> 주의: 내부 설정에 따라 **필수조건 자동 판정 강도**가 달라질 수 있습니다(최근 완화 설정 반영).

### 1.4 트러블슈팅
- **401 Unauthorized**: `X-API-KEY` 누락/오타. 컨테이너 내부에서 환경변수 확인 후 재시도.
- **400 JSON parse error**: Windows에서 BOM 이슈일 확률 높음 → 위 PowerShell로 **BOM 없는 UTF-8**로 파일 생성.
- **Worker timeout / OOM**: 텍스트가 매우 길거나 모델 부하로 인한 메모리 부족.  
  - 짧은 텍스트로 분할 전송
  - (옵션) 분석 강도 낮추기(제로샷 비활성화 등) – 운영자 문의

---

## 2. 구인공고 조회 API

**Endpoint**
- `GET /api/jobs`
- 기능: 수집된 구인공고를 페이징/검색/정렬하여 반환

### 2.1 내부 사용법 (X-API-KEY 선택)
- 이 엔드포인트는 **기본 공개**입니다. 내부망에서 호출 시 토큰 없이 사용 가능.
- 필요하면 API 게이트웨이에서 **토큰 요구**로 변경 가능(정책에 따름).

**Windows(Anaconda Prompt) 한 줄 예시**
```bat
curl.exe -s "http://localhost:8000/api/jobs?active=1&q=python&page_size=5&format=json"
```

### 2.2 외부 사용법 (토큰 없이 조회 가능)
- 기본 공개 설정이라면, 외부에서도 동일한 쿼리로 조회 가능:
```bat
curl.exe -s "https://<공개도메인>/api/jobs?q=%EC%88%98%EB%8F%84%EA%B6%8C&active=1&page_size=5&format=json"
```

### 2.3 쿼리 파라미터

| 파라미터 | 타입 | 기본 | 설명 |
|---|---:|---:|---|
| `q` | string |  | 제목/내용/기술스택/지역 등 전방위 간단 검색 키워드 |
| `active` | 0/1 |  | `1`=진행중(`is_active=true`), `0`=마감 포함 |
| `company_id` | int |  | 특정 회사 공고만 조회 |
| `page` | int | 1 | 페이지 번호 |
| `page_size` | int | 20 | 1~100 권장 |
| `ordering` | string |  | 정렬키(예: `-posted_at`, `-first_seen_at`, `salary`) |

### 2.4 응답 예시
```json
{
  "count": 123,
  "next": "http://localhost:8000/api/jobs?active=1&page=2&page_size=5",
  "previous": null,
  "results": [
    {
      "id": 987,
      "company_id": 243,
      "company_name": "가비아",
      "title": "백엔드 엔지니어 (Python/Django)",
      "post_url": "https://careers.example.com/recruit/view?id=12345",
      "location": "서울",
      "employment_type": "정규직",
      "salary": "면접 후 협의",
      "is_active": true,
      "first_seen_at": "2025-11-12T07:37:08Z",
      "posted_at": "2025-11-10T00:00:00Z",
      "deadline_at": "2025-11-30T23:59:00Z",
      "job_description": "주요 업무: ... 자격 요건: ...",
      "preferred_qualifications": "우대 사항: ...",
      "hiring_process": "서류-면접-발표",
      "benefits": ["재택근무","건강검진","자율출퇴근제"],
      "work_hours": "주 40시간"
    }
  ]
}
```

### 2.5 트러블슈팅
- **빈 배열/건수 0**: 수집 데이터가 적거나, 필터가 너무 강함 → `active` 제거, `q` 완화, `page_size` 확대.
- **정렬 미적용**: `ordering` 키 오탈자 확인(`-posted_at`, `-first_seen_at` 등).
- **특정 회사만 보고 싶을 때**: `company_id=<숫자>` 추가.

---

## 부록 · 운영 팁 (선택)

- **UTF-8/BOM 에러를 반복 회피하려면**
  - 항상 PowerShell로 `UTF8Encoding($false)`을 사용해 페이로드 파일 생성
  - `curl --data-binary @payload.json` 사용

- **토큰 확인**
```bat
docker compose exec app python -c "import os; print(os.getenv('API_INTERNAL_TOKEN'))"
```

- **헬스체크**
```bat
curl.exe -s "http://localhost:8000/api/jobs?page_size=1&format=json"
```

---

문의/이슈: 운영자에게 로그 스니펫과 함께 요청(시간대/요청URL/응답코드 포함).
