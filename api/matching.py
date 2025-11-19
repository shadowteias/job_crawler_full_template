# api/matching.py
from __future__ import annotations
import heapq
import itertools
import math
import re
from typing import Dict, Any, Iterable, List, Tuple

from django.db.models import Q
from django.utils.timezone import now

from .models import JobPosting, Company

# ------------ 가중치(요청 표 그대로) ------------
WEIGHTS = {
    "role": 20,
    "skills": 30,
    "location": 10,
    "employment_type": 8,
    "welfare": 8,
    "salary": 8,
    "company_industry": 6,
    "etc": 10,
}

# ------------ 헬퍼 ------------
_KRX_METRO = {"서울", "경기", "인천", "수도권"}
_WELFARE_CANON = {
    "식대","재택근무","건강검진","교육비","사내스터디","컨퍼런스참가비",
    "운동비","도서구입비","경조사비","경조휴가","스톡옵션","자율출퇴근제"
}

def _to_set(obj) -> set[str]:
    if obj is None:
        return set()
    if isinstance(obj, (list, tuple, set)):
        return {str(x).strip().lower() for x in obj if str(x).strip()}
    s = str(obj).strip()
    if not s:
        return set()
    toks = re.split(r"[,/\|\s]+", s)
    return {t.strip().lower() for t in toks if t.strip()}

def _canon_welfare(obj) -> set[str]:
    items = set()
    for t in _to_set(obj):
        if "재택" in t: items.add("재택근무")
        elif "검진" in t: items.add("건강검진")
        elif "자율" in t and "출퇴근" in t: items.add("자율출퇴근제")
        elif "식" in t and "대" in t: items.add("식대")
        elif "컨퍼런스" in t: items.add("컨퍼런스참가비")
        elif "스터디" in t: items.add("사내스터디")
        elif "도서" in t: items.add("도서구입비")
        elif "운동" in t: items.add("운동비")
        elif "경조" in t and "휴" in t: items.add("경조휴가")
        elif "경조" in t: items.add("경조사비")
        elif "스톡" in t: items.add("스톡옵션")
        elif "교" in t and "육" in t and "비" in t: items.add("교육비")
    return items & _WELFARE_CANON

def _parse_salary_min(v) -> int | None:
    if v is None:
        return None
    s = str(v)
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{2,}", s)]
    if not nums:
        return None
    return min(nums)

def _loc_match(student_loc: str | None, job_loc: str | None) -> float:
    if not student_loc or not job_loc:
        return 0.0
    s = student_loc.strip()
    jl = job_loc.strip()
    if s == "지역 무관":
        return 1.0
    if s == "지방 가능":
        return 0.6
    if s == "수도권":
        jl_tokens = set(re.split(r"[,\s/·]+", jl))
        if _KRX_METRO & jl_tokens:
            return 1.0
        if any(k in jl for k in _KRX_METRO):
            return 1.0
        return 0.0
    return 1.0 if s in jl else 0.0

def _etype_match(student_et: str | None, job_et: str | None) -> float:
    if not student_et or not job_et:
        return 0.0
    s = student_et
    j = job_et
    j_new = ("신입" in j) or ("new" in j.lower())
    j_exp = ("경력" in j) or ("experience" in j.lower())
    if s == "신입":
        return 1.0 if j_new else 0.0
    if s == "신입+경력":
        return 1.0 if (j_new or j_exp) else 0.0
    if "경력" in s:
        return 1.0 if j_exp else 0.0
    return 0.0

def _role_score(student: dict, job: JobPosting) -> float:
    skills = _to_set(student.get("기술스택"))
    if not skills:
        return 0.0
    text = " ".join(filter(None, [job.title or "", job.job_description or "", job.preferred_qualifications or ""])).lower()
    if not text:
        return 0.0
    hit = sum(1 for k in skills if k in text)
    return min(1.0, hit / max(1, len(skills)))

def _skills_score(student: dict, job: JobPosting) -> Tuple[float, List[str]]:
    want = _to_set(student.get("기술스택"))
    have = _to_set(job.job_description) | _to_set(job.preferred_qualifications) | _to_set(job.qualifications)
    if not want or not have:
        return 0.0, []
    inter = [k for k in want if k in have]
    score = min(1.0, len(inter) / max(1, len(want)))
    return score, inter

def _welfare_score(student: dict, job: JobPosting) -> Tuple[float, List[str]]:
    want = _canon_welfare(student.get("복리후생"))
    have = _canon_welfare(job.benefits)
    if not want or not have:
        return 0.0, []
    inter = sorted(list(want & have))
    score = min(1.0, len(inter) / max(1, len(want)))
    return score, inter

def _salary_score(student: dict, job: JobPosting) -> float:
    s_min = student.get("급여")
    if not isinstance(s_min, (int, float)):
        return 0.0
    j_min = _parse_salary_min(job.salary)
    if j_min is None:
        return 0.0
    return 1.0 if j_min >= float(s_min) else 0.0

def _industry_score(student: dict, company: Company | None) -> float:
    if company is None:
        return 0.0
    stu = str(student.get("업종분류") or "").strip()
    if not stu:
        return 0.0
    comp = " ".join(filter(None, [getattr(company, "industry", None), getattr(company, "sector", None), getattr(company, "category", None)]))
    if not comp:
        return 0.0
    return 1.0 if stu in comp else 0.0

def _etc_score(student: dict, job: JobPosting) -> float:
    stu_keys = _to_set(student.get("etc"))
    if not stu_keys:
        return 0.0
    text = " ".join(filter(None, [job.preferred_qualifications or "", job.qualifications or ""])).lower()
    if not text:
        return 0.0
    hits = sum(1 for k in stu_keys if k in text)
    return min(1.0, hits / max(1, len(stu_keys)))

def _enforce_hard_filters(student: dict, job: JobPosting, company: Company | None) -> Tuple[bool, List[str]]:
    reasons = []
    reqs = student.get("필수조건") or []
    reqs = [str(x).strip() for x in reqs if str(x).strip()]

    for r in reqs:
        if r == "근무지":
            if _loc_match(student.get("근무지"), (job.location or "")) < 1.0:
                reasons.append("근무지 불일치")
        elif r == "급여":
            s_min = student.get("급여")
            j_min = _parse_salary_min(job.salary)
            if not (isinstance(s_min, (int, float)) and j_min is not None and j_min >= float(s_min)):
                reasons.append("급여 하한 미충족")
        elif r == "복리후생":
            want = _canon_welfare(student.get("복리후생"))
            have = _canon_welfare(job.benefits)
            if not (want and have and (want <= have)):
                reasons.append("복리후생 포함 불충족")
        elif r == "구인구분":
            if _etype_match(student.get("구인구분"), (job.employment_type or "")) < 1.0:
                reasons.append("고용형태 불일치")
        elif r == "기술스택":
            want = _to_set(student.get("기술스택"))
            have = _to_set(job.job_description) | _to_set(job.preferred_qualifications) | _to_set(job.qualifications)
            if not (want and want <= have):
                reasons.append("기술스택 포함 불충족")

    return (len(reasons) == 0), reasons

def _score_one(student: dict, job: JobPosting, company: Company | None) -> Tuple[float, Dict[str, Any]]:
    ok, hard_fail = _enforce_hard_filters(student, job, company)
    if not ok:
        return 0.0, {"rejects": hard_fail}

    s_role = _role_score(student, job) * WEIGHTS["role"]
    s_skills, hit_skills = _skills_score(student, job); s_skills *= WEIGHTS["skills"]
    s_loc = _loc_match(student.get("근무지"), (job.location or "")) * WEIGHTS["location"]
    s_et = _etype_match(student.get("구인구분"), (job.employment_type or "")) * WEIGHTS["employment_type"]
    s_wel, hit_wel = _welfare_score(student, job); s_wel *= WEIGHTS["welfare"]
    s_sal = _salary_score(student, job) * WEIGHTS["salary"]
    s_ind = _industry_score(student, company) * WEIGHTS["company_industry"]
    s_etc = _etc_score(student, job) * WEIGHTS["etc"]

    score = s_role + s_skills + s_loc + s_et + s_wel + s_sal + s_ind + s_etc

    return score, {
        "role": s_role, "skills": s_skills, "location": s_loc, "employment_type": s_et,
        "welfare": s_wel, "salary": s_sal, "company_industry": s_ind, "etc": s_etc,
        "matched_skills": hit_skills, "matched_welfare": hit_wel
    }

# ------------ 공개 함수 (동점 안전: tie-breaker 추가) ------------
def top_jobs_for_student(student: dict, limit: int = 3) -> List[Dict[str, Any]]:
    qs = JobPosting.objects.all()
    if hasattr(JobPosting, "is_active"):
        qs = qs.filter(is_active=True)
    qs = qs.select_related("company").order_by("-id")

    heap: List[Tuple[float, int, Dict[str, Any]]] = []
    counter = itertools.count()

    for job in qs.iterator(chunk_size=200):
        comp = getattr(job, "company", None)
        score, detail = _score_one(student, job, comp)
        if score <= 0:
            continue
        item = {
            "job_id": job.id,
            "company_id": getattr(comp, "id", None),
            "company_name": getattr(comp, "name", None),
            "title": job.title,
            "post_url": job.post_url,
            "score": round(score, 4),
            "components": detail,
        }
        tie = next(counter)  # 동점 방지
        if len(heap) < limit:
            heapq.heappush(heap, (score, tie, item))
        else:
            heapq.heappushpop(heap, (score, tie, item))

    return [x for _, _, x in sorted(heap, key=lambda t: -t[0])]

def top_students_for_company(company_id: int, students: List[dict], limit: int = 3) -> List[Dict[str, Any]]:
    qs = JobPosting.objects.filter(company_id=company_id)
    if hasattr(JobPosting, "is_active"):
        qs = qs.filter(is_active=True)
    qs = qs.select_related("company")

    company = Company.objects.filter(id=company_id).first()

    heap: List[Tuple[float, int, Dict[str, Any]]] = []
    counter = itertools.count()

    for stu in students:
        best_score = 0.0
        best_job = None
        best_detail = {}
        for job in qs.iterator(chunk_size=200):
            score, detail = _score_one(stu, job, company)
            if score > best_score:
                best_score, best_job, best_detail = score, job, detail
        if best_score > 0 and best_job is not None:
            item = {
                "student": stu,
                "best_job_id": best_job.id,
                "best_job_title": best_job.title,
                "best_job_url": best_job.post_url,
                "score": round(best_score, 4),
                "components": best_detail,
            }
            tie = next(counter)
            if len(heap) < limit:
                heapq.heappush(heap, (best_score, tie, item))
            else:
                heapq.heappushpop(heap, (best_score, tie, item))

    return [x for _, _, x in sorted(heap, key=lambda t: -t[0])]


# 다대다 매칭 알고리즘 개선

def batch_match(students: List[dict], company_ids: List[int] | None = None, topk: int = 3) -> Dict[str, Any]:
    """
    [변경 요약]
    - 기존 동작은 보존.
    - 학생별 추천이 0개가 되는 케이스를 줄이기 위해, 2단계 "완화(fallback) 스코어링" 추가.
      (1) 1차: 기존 _score_one(필수조건 포함) 결과로 topk 힙 구성.
      (2) 2차: topk 미달 시, 학생 사본에서 '필수조건'을 제거(또는 비우고), 필요 시 근무지를 더 관대하게 해석하여
               동일한 _score_one으로 재스코어링 → 힙 보충.
      (3) 그래도 모자라면 최근 공고(또는 높은 id) 위주로 0점이라도 채워 'top' 슬롯을 비우지 않음.
    - 위치 매칭 “완화”는 _score_one 내부를 건드릴 수 없으므로,
      fallback 단계에서 학생 사본의 '근무지'를 '지역 무관'으로 완화(필요한 경우에만)하여 간접적으로 완화.
      (프로젝트에 _KRX_METRO 등이 이미 있으므로, 이 함수는 상수/기존 로직을 변경하지 않습니다.)
    """

    # --- 기존 쿼리 구성: 그대로 ---
    if company_ids:
        qs = JobPosting.objects.filter(company_id__in=company_ids)
    else:
        qs = JobPosting.objects.all()
    if hasattr(JobPosting, "is_active"):
        qs = qs.filter(is_active=True)
    qs = qs.select_related("company").order_by("-id")

    result = {"student_top": [], "stats": {"students": len(students), "jobs": qs.count()}}

    # 내부 유틸: topk 힙에 안전하게 넣기
    import heapq, itertools
    def _push_topk(heap: List[Tuple[float, int, Dict[str, Any]]], score: float, item: Dict[str, Any], counter: itertools.count):
        tie = next(counter)
        if len(heap) < topk:
            heapq.heappush(heap, (score, tie, item))
        else:
            heapq.heappushpop(heap, (score, tie, item))

    # 내부 유틸: 점수>0 인 것만 item 생성
    def _make_item(job: JobPosting, score: float, detail: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "job_id": job.id,
            "company_id": job.company_id,
            "company_name": getattr(job.company, "name", None),
            "title": job.title,
            "post_url": job.post_url,
            "score": round(score, 4),
            "components": detail,
        }

    for stu in students:
        heap: List[Tuple[float, int, Dict[str, Any]]] = []
        counter = itertools.count()

        # -----------------------------
        # 1) 1차: "기존 기준" 스코어링 (필수조건 그대로)
        # -----------------------------
        for job in qs.iterator(chunk_size=200):
            score, detail = _score_one(stu, job, getattr(job, "company", None))
            if score <= 0:
                continue
            _push_topk(heap, score, _make_item(job, score, detail), counter)

        # ----------------------------------------
        # 2) 2차: "완화 기준" 스코어링으로 보충 (핵심 수정)
        #    - 원인 가설 #1: 필수조건이 너무 빡빡하여 0개가 나오는 케이스
        #    - 조치: 학생 사본에서 '필수조건' 제거
        #    - 원인 가설 #2: 근무지 매칭이 과도(직접 로직 수정 불가)
        #           → 사본에서 '근무지'를 '지역 무관'으로 완화 (필요할 때만)
        # ----------------------------------------
        if len(heap) < topk:
            relaxed = dict(stu)

            # (A) 필수조건 제거(완화). 기존 필수조건 로직은 _score_one 내부에 있으므로
            #     사본에서만 비워서 동일 _score_one을 재사용.
            if isinstance(relaxed.get("필수조건"), list) and relaxed["필수조건"]:
                relaxed["필수조건"] = []  # 완화 포인트

            # (B) 근무지 완화: 명시적으로 '수도권', '지방 가능' 등일 때만 완화.
            #     _score_one을 고치지 않고 '지역 무관'으로 바꿔 간접 완화.
            #     (기존 상수/로직을 건드리지 않으려는 의도)
            loc = relaxed.get("근무지")
            if isinstance(loc, str) and loc.strip() and loc.strip() != "지역 무관":
                # 너무 공격적으로 풀지 않도록, 흔한 제약어들에서만 완화
                if loc.strip() in {"수도권", "지방 가능"}:
                    relaxed["근무지"] = "지역 무관"

            # 재스코어링
            for job in qs.iterator(chunk_size=200):
                # 이미 담긴 공고는 중복 피하기 (job_id로 확인)
                if any(job.id == x[2]["job_id"] for x in heap):
                    continue
                score, detail = _score_one(relaxed, job, getattr(job, "company", None))
                if score <= 0:
                    continue
                _push_topk(heap, score, _make_item(job, score, detail), counter)
                if len(heap) >= topk:
                    break  # 필요한 만큼 채우면 중단

        # -------------------------------------------------
        # 3) 3차: 그래도 모자라면 "안전 보충" (최신 공고 id 우선)
        #    - 점수 0이라도 슬록을 채워 'top'이 비지 않도록
        # -------------------------------------------------
        if len(heap) < topk:
            # 이미 담긴 job_id 집합
            picked = {x[2]["job_id"] for x in heap}
            for job in qs.iterator(chunk_size=200):
                if job.id in picked:
                    continue
                # components는 빈 골격으로
                blank_detail = {
                    "role": 0.0, "skills": 0.0, "location": 0.0,
                    "employment_type": 0.0, "welfare": 0.0, "salary": 0.0,
                    "company_industry": 0.0, "etc": 0.0,
                    "matched_skills": [], "matched_welfare": []
                }
                _push_topk(heap, 0.0, _make_item(job, 0.0, blank_detail), counter)
                if len(heap) >= topk:
                    break

        result["student_top"].append({
            "student": stu,
            "top": [x for _, _, x in sorted(heap, key=lambda t: -t[0])]
        })

    return result
