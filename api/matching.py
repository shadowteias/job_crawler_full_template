from typing import List, Tuple
from .models import Trainee, JobPosting, Company

# 가중치는 추후 조정
WEIGHTS = {
    "location": 1.0,
    "employment_type": 1.0,
    "skills": 1.5,
    "salary": 0.5,
    "benefit": 0.5,
    "company_size": 0.5,
}

def score_job_for_trainee(trainee: Trainee, job: JobPosting, company: Company) -> float:
    score = 0.0

    # 지역
    if trainee.preferred_location and trainee.preferred_location in (job.location or ""):
        score += WEIGHTS["location"]

    # 구인구분
    if trainee.preferred_employment_type and trainee.preferred_employment_type in (job.employment_type or ""):
        score += WEIGHTS["employment_type"]

    # 기술 매칭
    if trainee.tech_stack and job.required_skills:
        t = set(map(str.lower, trainee.tech_stack.split(",")))
        j = set(map(str.lower, job.required_skills.split(",")))
        if t & j:
            score += WEIGHTS["skills"]

    # 급여(아주 단순히 '협의 아니고 뭔가 있음' 정도만)
    if trainee.preferred_salary and (job.salary or "").strip():
        score += WEIGHTS["salary"]

    # 복리후생
    if trainee.welfare_preferences:
        want = set(trainee.welfare_preferences.split(","))
        have = set((job.benefits or "").split(","))
        if have & want:
            score += WEIGHTS["benefit"]

    # 회사 규모/기타는 Company에 필드 생기면 확장

    return score


def recommend_trainees_for_company(company: Company, top_n: int = 20) -> List[Tuple[Trainee, float]]:
    jobs = JobPosting.objects.filter(company=company, is_active=True)
    trainees = Trainee.objects.filter(is_employed=False)
    results = []
    for t in trainees:
        best = 0.0
        for j in jobs:
            s = score_job_for_trainee(t, j, company)
            if s > best:
                best = s
        if best > 0:
            results.append((t, best))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


def recommend_companies_for_trainee(trainee: Trainee, top_n: int = 20) -> List[Tuple[Company, float]]:
    results = {}
    for j in JobPosting.objects.filter(is_active=True):
        s = score_job_for_trainee(trainee, j, j.company)
        if s <= 0:
            continue
        results[j.company_id] = max(results.get(j.company_id, 0.0), s)
    pairs = [(Company.objects.get(id=cid), sc) for cid, sc in results.items()]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:top_n]
