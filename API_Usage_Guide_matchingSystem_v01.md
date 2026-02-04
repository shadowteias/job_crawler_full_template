# 채용 **매칭 & 조회 API** 사용 가이드

**Base URL**: `http://localhost:8000` (배포 시 실제 도메인/포트로 교체)  
**인증(내부 호출)**: `X-API-KEY: <내부토큰>` 헤더 **필수** — *매칭 API만 필요*, 조회 API는 기본 공개(변경 시 문서/코드 동기화 요망).  
**문자 인코딩**: 예시 명령은 **모두 한 줄**이며, 한글 깨짐을 막기 위해 `python -c ... ensure_ascii=False`를 사용합니다.

---

## 목차
1. [학생 → 상위 회사 Top-N (`POST /api/match/student-top`)](#1-학생--상위-회사-top-n-post-apimatchstudent-top)  
   1.1 [내부 사용법(토큰) · 1-라인 테스트](#11-내부-사용법토큰--1-라인-테스트)  
   1.2 [요청/응답 스키마 & 예시](#12-요청응답-스키마--예시)  
   1.3 [에러 & 트러블슈팅](#13-에러--트러블슈팅)
2. [회사 → 상위 학생 Top-N (`POST /api/match/company-top`)](#2-회사--상위-학생-top-n-post-apimatchcompany-top)  
   2.1 [내부 사용법(토큰) · 1-라인 테스트](#21-내부-사용법토큰--1-라인-테스트)  
   2.2 [요청/응답 스키마 & 예시](#22-요청응답-스키마--예시)  
   2.3 [에러 & 트러블슈팅](#23-에러--트러블슈팅)
3. [다대다 매칭(학생들 × 공고들) (`POST /api/match/batch`)](#3-다대다-매칭학생들--공고들-post-apimatchbatch)  
   3.1 [내부 사용법(토큰) · 1-라인 테스트](#31-내부-사용법토큰--1-라인-테스트)  
   3.2 [요청/응답 스키마 & 예시](#32-요청응답-스키마--예시)  
   3.3 [에러 & 트러블슈팅](#33-에러--트러블슈팅)
4. [구인공고 조회(읽기 전용) (`GET /api/job-postings/`)](#4-구인공고-조회읽기-전용-get-apijob-postings)  
   4.1 [외부 소비자 사용법(토큰 불필요) · 1-라인 테스트](#41-외부-소비자-사용법토큰-불필요--1-라인-테스트)  
   4.2 [쿼리 파라미터 & 예시](#42-쿼리-파라미터--예시)
5. [가중치 매트릭스(점수 산정 개요)](#5-가중치-매트릭스점수-산정-개요)
6. [빠른 점검 & 헬스체크](#6-빠른-점검--헬스체크)

---

## 1) 학생 → 상위 회사 Top-N (`POST /api/match/student-top`)

**기능**: 단일 학생 프로필을 현재 DB의 **모든 구인공고**와 매칭하여 상위 N개 추천.

### 1.1 내부 사용법(토큰) · 1-라인 테스트
> Windows **Anaconda Prompt**에서 그대로 실행 (요청/응답 한글 안전)

python -c "import requests,json;print(json.dumps(requests.post('http://localhost:8000/api/match/student-top',headers={'X-API-KEY':'<내부토큰>'},json={'student':{'근무지':'수도권','급여':3500,'구인구분':'신입','기술스택':['Python','Django','React'],'복리후생':['재택근무','건강검진'],'필수조건':['근무지','급여']},'limit':3}).json(),ensure_ascii=False,indent=2))"


### 1.2 요청/응답 스키마 & 예시

**Request(JSON)**

- `student` (object) — 필드 예:
    - `근무지`: `"수도권" | "지역 무관" | "지방 가능" | "<특정지역명>"`
    - `급여`: **정수(만원)**, 예: `2500 | 3000 | 3500 | 4000 ...`
    - `구인구분`: `"신입"` 또는 `"신입+경력"`
    - `기술스택`: `["Python","Django","React", ...]`
    - `복리후생`: `["재택근무","건강검진","자율출퇴근제", ...]`
    - `필수조건`: 위 칼럼명 배열(예: `["근무지","급여"]`)
- `limit` (int, 기본 3

**Response(JSON) 예시**

```json
{
  "results": [
    {
      "job_id": 325,
      "company_id": 100,
      "company_name": "가상의회사",
      "title": "백엔드 엔지니어",
      "post_url": "https://example.com/jobs/325",
      "score": 55.33,
      "components": {
        "role": 13.33,
        "skills": 20.0,
        "location": 10.0,
        "employment_type": 0.0,
        "welfare": 4.0,
        "salary": 8.0,
        "company_industry": 0.0,
        "etc": 0.0,
        "matched_skills": ["python","react"],
        "matched_welfare": ["건강검진"]
      }
    }
  ]
}

```

### 1.3 에러 & 트러블슈팅

- **401 Unauthorized** → `X-API-KEY` 누락/오타
- **400 Bad JSON** → JSON 형식/인코딩 문제. *반드시* 위 **python 1-라인** 사용 권장
- **500** → 입력 스키마/타입 확인(예: `급여`는 정수), 일시적 부담 시 재시도

---

## 2) 회사 → 상위 학생 Top-N (`POST /api/match/company-top`)

**기능**: 특정 `company_id`의 공고(들)를 기준으로 **입력된 학생 후보들**을 스코어링하여 상위 N명 반환.

### 2.1 내부 사용법(토큰) · 1-라인 테스트

```bash
python -c "import requests,json; students=[{'id':'s01','근무지':'수도권','급여':3500,'구인구분':'신입','기술스택':['Python','Django'],'복리후생':['재택근무']},{'id':'s02','근무지':'지역 무관','급여':3000,'구인구분':'신입+경력','기술스택':['React','Node'],'복리후생':[]}]; print(json.dumps(requests.post('http://localhost:8000/api/match/company-top',headers={'X-API-KEY':'<내부토큰>'},json={'company_id':243,'students':students,'limit':3}).json(),ensure_ascii=False,indent=2))"

```

### 2.2 요청/응답 스키마 & 예시

**Request(JSON)**

- `company_id` (int) — 회사 ID
- `students` (array of student object) — 1.2의 `student` 스키마 동일(추가로 `id` 권장)
- `limit` (int, 기본 3)

**Response(JSON) 예시**

```json
{
  "results": [
    {
      "student_id": "s01",
      "score": 48.5,
      "components": {
        "role": 10.0,
        "skills": 18.5,
        "location": 10.0,
        "employment_type": 2.0,
        "welfare": 4.0,
        "salary": 4.0,
        "company_industry": 0.0,
        "etc": 0.0
      },
      "matched_jobs_sample": [
        { "job_id": 901, "title": "백엔드", "post_url": "https://..." }
      ]
    }
  ]
}

```

### 2.3 에러 & 트러블슈팅

- `company_id`가 숫자 아님/존재하지 않음 → 400/빈 결과
- 학생 JSON 인코딩 이슈 → 위 **python 1-라인** 사용

---

## 3) 다대다 매칭(학생들 × 공고들) (`POST /api/match/batch`)

**기능**: 여러 학생을 한 번에 매칭. 각 학생별 Top-K 반환.

최신 버전은 **Top-K 보장(완화 규칙)** 적용으로 *빈 추천* 최소화.

### 3.1 내부 사용법(토큰) · 1-라인 테스트

> 예시: 학생 30명을 랜덤 생성하여 Top-3 매칭
> 

```bash
python -c "import requests,json,random; random.seed(42); TOKEN='<내부토큰>'; skills=['Python','Django','React','Go','Node','Java','AWS','Docker']; welfare=['재택근무','건강검진','자율출퇴근제','식대','교육비','도서구입비']; musts=['근무지','급여','복리후생','구인구분','기술스택']; mk=lambda i:{'id':f's{i:02d}','근무지':random.choice(['수도권','지역 무관','지방 가능']),'급여':random.choice([2500,3000,3500,4000,4500]),'구인구분':random.choice(['신입','신입+경력']),'기술스택':random.sample(skills,k=random.randint(2,4)),'복리후생':random.sample(welfare,k=random.randint(0,3)),'필수조건':random.sample(musts,k=random.randint(0,3))}; students=[mk(i) for i in range(1,31)]; body={'students':students,'topk':3}; print(json.dumps(requests.post('http://localhost:8000/api/match/batch',headers={'X-API-KEY':TOKEN},json=body).json(),ensure_ascii=False,indent=2))"

```

> 특정 회사만 대상으로 제한하려면 body에 "company_ids":[243,100,...] 추가.
> 

### 3.2 요청/응답 스키마 & 예시

**Request(JSON)**

- `students` (array, 필수) — 1.2의 `student` 스키마 동일(각 학생은 `id` 권장)
- `company_ids` (array<int>, 선택) — 지정된 회사들만 대상
- `topk` (int, 기본 3)

**Response(JSON) 예시**

```json
{
  "student_top": [
    {
      "student": { "id": "s01", "근무지": "수도권", "급여": 3500 },
      "top": [
        { "job_id": 101, "company_id": 10, "company_name": "A사", "title": "백엔드", "post_url": "https://...", "score": 52.0, "components": {} },
        { "job_id": 88,  "company_id":  9, "company_name": "B사", "title": "플랫폼", "post_url": "https://...", "score": 44.0, "components": {} },
        { "job_id": 33,  "company_id":  7, "company_name": "C사", "title": "서버",   "post_url": "https://...", "score": 40.0, "components": {} }
      ]
    }
  ],
  "stats": { "students": 30, "jobs": 1000 }
}

```

### 3.3 에러 & 트러블슈팅

- **500/Internal Server Error**
    - 학생 JSON 필드 오타/타입(FE가 문자열로 보낸 `급여` 등) → 정수로 보정
    - 메모리 압박/대상 과다 → `company_ids`로 축소, `topk` 축소 후 재시도
- **응답 한글 깨짐** → 반드시 문서의 **python 1-라인** 사용

---

## 4) 구인공고 조회(읽기 전용) (`GET /api/job-postings/`)

**기능**: 현재 DB에 저장된 구인공고 목록 조회(읽기 전용). **기본 공개**.

### 4.1 외부 소비자 사용법(토큰 불필요) · 1-라인 테스트

```bash
python -c "import requests,json;print(json.dumps(requests.get('http://localhost:8000/api/job-postings/',params={'active':1,'q':'python','page_size':5}).json(),ensure_ascii=False,indent=2))"

```

### 4.2 쿼리 파라미터 & 예시

- `q` (str): 제목/내용 키워드 검색(예: `q=python`)
- `active` (0|1): 활성 공고만(예: `active=1`)
- `company_id` (int): 특정 회사 공고만
- `employment_type` (str): 고용형태 필터(예: `신입`, `신입+경력`)
- `page_size` (int, 기본 20), `page` (int): 페이지네이션

예시:

```bash
python -c "import requests,json;print(json.dumps(requests.get('http://localhost:8000/api/job-postings/',params={'active':1,'company_id':243,'page_size':10}).json(),ensure_ascii=False,indent=2))"

```

---

## 5) 가중치 매트릭스(점수 산정 개요)

| key | 설명 | 가중치 |
| --- | --- | --- |
| `role` | 직무/역할 적합도 | 20 |
| `skills` | 기술/경력 적합도 | 30 |
| `location` | 근무지 일치 | 10 |
| `employment_type` | 고용형태 일치 | 8 |
| `welfare` | 복리후생 일치 | 8 |
| `salary` | 급여 조건 | 8 |
| `company_industry` | 업종/회사 적합도 | 6 |
| `etc` | 기타(성적/경력 등) | 10 |

> 필수조건 처리: 학생의 필수조건은 강하게 반영.
> 
> 
> **다대다(batch)**: *Top-K 보장 완화 규칙*으로 빈 추천 최소화.
> 

---

## 6) 빠른 점검 & 헬스체크

- **토큰 확인(내부)**:
    
    ```bash
    docker compose exec app python -c "import os; print(os.getenv('API_INTERNAL_TOKEN'))"
    
    ```
    
- **매칭 API 엔드포인트**:
    - `POST /api/match/student-top`
    - `POST /api/match/company-top`
    - `POST /api/match/batch`
- **조회 API 확인**:
    
    ```bash
    python -c "import requests,json;print(json.dumps(requests.get('http://localhost:8000/api/job-postings/',params={'page_size':1}).json(),ensure_ascii=False,indent=2))"
    
    ```
    

> 다른 터미널에서 사용할 경우 동일 파라미터로 실행하되, 한글 출력 시 `ensure_ascii=False`를 유지하세요.