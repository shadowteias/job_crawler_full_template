# api/llm_parser.py
"""
LLM-based job posting parser with Zero-shot classification + LLM post-processing.
Korean and English only. Designed for matching system compatibility.
"""

import os
import re
import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

try:
    from django.conf import settings
except Exception:  # pragma: no cover - allows standalone parser import in tools/tests
    settings = None

logger = logging.getLogger(__name__)

JOB_CLASSIFIER_MODEL = os.getenv(
    "JOB_CLASSIFIER_MODEL",
    "joeddav/xlm-roberta-large-xnli"
)

OPENAI_PARSE_FIELDS = {
    "job_description",
    "qualifications",
    "preferred_qualifications",
    "hiring_process",
    "benefits",
    "location",
    "employment_type",
    "salary",
    "deadline_at",
    "posted_at",
}


def _setting(name: str, default=None):
    if settings is not None:
        return getattr(settings, name, os.getenv(name, default))
    return os.getenv(name, default)


def _openai_api_key() -> str:
    return str(_setting("OPENAI_API_KEY", "") or "").strip()


def _openai_parser_enabled() -> bool:
    return str(_setting("OPENAI_PARSER_ENABLED", "0") or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_iso_date(value) -> str:
    if not value:
        return ""
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ""


def _clean_openai_payload(payload: dict) -> dict:
    cleaned = {}
    for field in OPENAI_PARSE_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if field in {"deadline_at", "posted_at"}:
            value = _coerce_iso_date(value)
        else:
            value = str(value).strip()
        if value:
            cleaned[field] = value
    return cleaned


def _parse_job_details_with_openai(
    text: str,
    url: str = "",
    company_name: str = "",
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    organization: Optional[str] = None,
    model: Optional[str] = None,
    parser_enabled: Optional[bool] = None,
) -> dict:
    parser_is_enabled = _openai_parser_enabled() if parser_enabled is None else parser_enabled
    if not parser_is_enabled:
        return {}

    effective_api_key = (api_key or _openai_api_key()).strip()
    if not effective_api_key:
        logger.warning("OPENAI_PARSER_ENABLED is true but OPENAI_API_KEY is not configured; using fallback parser")
        return {}

    try:
        from openai import OpenAI
    except Exception as e:
        logger.warning("OpenAI parser requested but openai package is unavailable: %s", e)
        return {}

    effective_model = str(model or _setting("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    timeout = float(_setting("OPENAI_TIMEOUT_SECONDS", 30) or 30)
    max_retries = int(_setting("OPENAI_MAX_RETRIES", 2) or 2)
    project = str(project_id or _setting("OPENAI_PROJECT_ID", _setting("OPENAI_PROJECT", "")) or "").strip() or None
    effective_organization = str(organization or _setting("OPENAI_ORGANIZATION", "") or "").strip() or None

    client = OpenAI(
        api_key=effective_api_key,
        project=project,
        organization=effective_organization,
        timeout=timeout,
        max_retries=max_retries,
    )

    prompt = {
        "task": "Extract structured job posting fields from a Korean or English company recruiting page.",
        "rules": [
            "Return JSON only.",
            "Use empty strings for unknown fields.",
            "Do not invent requirements, benefits, dates, salary, or location.",
            "Dates must be YYYY-MM-DD when present.",
            "If the page is not a job posting, return an empty JSON object.",
        ],
        "fields": sorted(OPENAI_PARSE_FIELDS),
        "company_name": company_name,
        "url": url,
        "text": text[:12000],
    }

    response = client.chat.completions.create(
        model=effective_model,
        messages=[
            {
                "role": "system",
                "content": "You are a precise recruiting-page parser. Return compact JSON only.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        return {}
    return _clean_openai_payload(parsed)

# SECTION LABELS (Korean + English only)
SECTION_LABELS = [
    "주요 업무",
    "담당 업무",
    "담당 역할",
    "주요업무",
    "Main Duties",
    "What you will do",
    "Responsibilities",
    "자격 요건",
    "자격요건",
    "필수 요건",
    "Requirements",
    "Qualifications",
    "Must have",
    "우대 사항",
    "우대사항",
    "우대 조건",
    "우대조건",
    "Preferred",
    "Nice to have",
    "전형 절차",
    "채용 절차",
    "전형절차",
    "Process",
    "복리후생",
    "복리 후생",
    "혜택",
    "Benefits",
    "Welfare",
    "근무조건",
    "근무 조건",
    "고용 형태",
    "Employment Type",
    "급여",
    "연봉",
    "급여조건",
    "Salary",
    "근무지",
    "근무 장소",
    "근무지역",
    "Location",
]

# Stop headers to avoid
SECTION_STOP_HEADERS = [
    "개인정보처리방침",
    "이용약관",
    "쿠키",
    "Copyright",
    "채용공고",
    "모집요강",
    "지원하기",
    "apply",
]

# Welfare keywords for matching system (normalized)
WELFARE_CANON = {
    "식대", "재택근무", "건강검진", "교육비", "사내스터디", "컨퍼런스참가비",
    "운동비", "도서구입비", "경조사비", "경조휴가", "스톡옵션", "자율출퇴근제",
    "상여금", "인센티브", "연차수당", "퇴직금",
}

# Location keywords
LOCATION_KEYWORDS = [
    "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
    "충북", "충남", "전북", "전남", "경북", "경남", "강원", "제주",
    "수도권", "지방",
]

# Employment type keywords
EMPLOYMENT_TYPE_KEYWORDS = {
    "정규직": ["정규직", "정규 채용", "permanent", "정식 채용"],
    "계약직": ["계약직", "계약 채용", "계약", "contract"],
    "인턴": ["인턴", "인턴십", "intern"],
    "파트타임": ["파트타임", "아르바이트", "part-time", "시간제"],
}


def _parse_date(year_str: str, month_str: str, day_str: str) -> Optional[datetime]:
    try:
        year = int(year_str)
        month = int(month_str)
        day = int(day_str)
        if 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
            return datetime(year, month, day)
    except (ValueError, OverflowError):
        pass
    return None


def _extract_dates(text: str) -> tuple:
    deadline_at = None
    posted_at = None

    text_combined = ' '.join(text.split())

    deadline_keywords = ["마감", "지원", "截止", "기한", "까지"]
    posted_keywords = ["게시", "등록", "작성", "시작", "작성일"]

    date_patterns = [
        r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
        r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
        r"(\d{4})\s+(\d{1,2})\s+(\d{1,2})",
        r"(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    ]

    candidates = []

    for pattern in date_patterns:
        for match in re.finditer(pattern, text_combined):
            year_str, month_str, day_str = match.groups()
            
            if len(year_str) == 2:
                year_str = "20" + year_str
            
            dt = _parse_date(year_str, month_str, day_str)
            if dt:
                pos = match.start()
                context = text_combined[max(0, pos-10):pos+10].lower()
                
                is_deadline = any(kw in context for kw in deadline_keywords)
                is_posted = any(kw in context for kw in posted_keywords)
                
                candidates.append((dt, pos, is_deadline, is_posted, context))

    candidates.sort(key=lambda x: x[1])

    for dt, pos, is_deadline, is_posted, context in candidates:
        if is_deadline and deadline_at is None:
            deadline_at = dt
        elif is_posted and posted_at is None:
            posted_at = dt
        elif deadline_at is None and posted_at is None:
            deadline_at = dt
            break

    return deadline_at, posted_at


def extract_posting_dates(text: str) -> tuple:
    return _extract_dates(text)


def _extract_salary(text: str) -> str:
    text_lower = text.lower()

    salary_patterns = [
        r"연봉\s*[\d,\.]+\s*만원",
        r"연봉\s*[\d,\.]+\s*억",
        r"연봉\s*협의",
        r"급여\s*[\d,\.]+\s*만원",
        r"급여\s*협의",
        r"월급\s*[\d,\.]+\s*만원",
        r"보상\s*[\d,\.]+\s*만원",
        r"연봉[\s:]*[\d,\.]+\s*(?:만원|억)",
        r"[\d,\.]+\s*만원(?:以上|이상)?",
        r"[\d,\.]+\s*억(?:以上|이상)?",
    ]

    for pattern in salary_patterns:
        m = re.search(pattern, text_lower)
        if m:
            return m.group(0)[:255]

    if "연봉 협의" in text_lower or "급여 협의" in text_lower:
        return "협의"

    return ""


@lru_cache()
def _get_zero_shot_classifier():
    tokenizer = AutoTokenizer.from_pretrained(JOB_CLASSIFIER_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(JOB_CLASSIFIER_MODEL)
    clf = pipeline(
        "zero-shot-classification",
        model=model,
        tokenizer=tokenizer,
        device=-1,
    )
    return clf


def is_job_posting(text: str, threshold: float = 0.65) -> bool:
    if not text:
        return False

    snippet = text[:2000]
    clf = _get_zero_shot_classifier()

    labels = ["채용공고", "채용공고 아님"]
    result = clf(
        snippet,
        candidate_labels=labels,
        hypothesis_template="이 문서는 {}이다.",
    )

    top_label = result["labels"][0]
    top_score = float(result["scores"][0])

    return (top_label == "채용공고") and (top_score >= threshold)


def _classify_sections_with_zero_shot(text: str) -> dict:
    if not text or len(text) < 100:
        return {}
    
    text_combined = ' '.join(text.split())
    
    paragraphs = re.split(r'\n\n|\n(?=[^\s])|\t', text_combined)
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 50]
    
    if not paragraphs:
        return {}
    
    candidate_labels = [
        "주요 업무",
        "자격 요건",
        "우대 사항",
        "전형 절차",
        "복리후생",
        "근무조건",
    ]
    
    clf = _get_zero_shot_classifier()
    
    section_contents = {label: [] for label in candidate_labels}
    section_contents["기타"] = []
    
    for para in paragraphs:
        if len(para) < 30:
            continue
        
        try:
            result = clf(para[:500], candidate_labels=candidate_labels, multi_label=False)
            top_label = result["labels"][0]
            top_score = float(result["scores"][0])
            
            if top_score >= 0.3:
                section_contents[top_label].append(para)
            else:
                section_contents["기타"].append(para)
        except Exception:
            section_contents["기타"].append(para)
    
    result = {}
    
    if section_contents.get("주요 업무"):
        combined = "\n".join(section_contents["주요 업무"])
        result["job_description"] = combined[:5000]
    
    if section_contents.get("자격 요건"):
        combined = "\n".join(section_contents["자격 요건"])
        result["qualifications"] = combined[:3000]
    
    if section_contents.get("우대 사항"):
        combined = "\n".join(section_contents["우대 사항"])
        result["preferred_qualifications"] = combined[:2000]
    
    if section_contents.get("전형 절차"):
        combined = "\n".join(section_contents["전형 절차"])
        result["hiring_process"] = combined[:5000]
    
    if section_contents.get("복리후생"):
        combined = "\n".join(section_contents["복리후생"])
        result["benefits"] = combined[:5000]
    
    if section_contents.get("근무조건"):
        combined = "\n".join(section_contents["근무조건"])
        result["work_conditions"] = combined[:5000]
    
    return result


def _normalize_welfare(text: str) -> str:
    found = []
    text_lower = text.lower()
    for wf in WELFARE_CANON:
        if wf.lower() in text_lower:
            found.append(wf)
    return ", ".join(sorted(set(found)))


def _normalize_location(text: str) -> str:
    for loc in LOCATION_KEYWORDS:
        if loc in text:
            return loc
    return ""


def _normalize_employment_type(text: str) -> str:
    for emp_type, keywords in EMPLOYMENT_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return emp_type
    return ""


def parse_job_details_with_llm(
    text: str,
    url: str = "",
    company_name: str = "",
    sections: Optional[dict] = None,
    primary_text: Optional[str] = None
) -> dict:
    if not text or len(text) < 100:
        return {}

    result = {}

    text_combined = ' '.join(text.split())

    try:
        openai_result = _parse_job_details_with_openai(text_combined, url=url, company_name=company_name)
        result.update(openai_result)
    except Exception as e:
        logger.warning("OpenAI job parser failed for url=%s (%s); using fallback parser", url, e)

    deadline_at, posted_at = extract_posting_dates(text)
    if deadline_at and "deadline_at" not in result:
        result["deadline_at"] = deadline_at.strftime("%Y-%m-%d")
    if posted_at and "posted_at" not in result:
        result["posted_at"] = posted_at.strftime("%Y-%m-%d")

    if "salary" not in result:
        result["salary"] = _extract_salary(text)

    zero_shot_sections = _classify_sections_with_zero_shot(text)
    for key, value in zero_shot_sections.items():
        if key not in result:
            result[key] = value

    section_patterns = [
        (r'자격요건\s*(.+?)(?=우대|담당|채용절차|전형|$)', 'qualifications'),
        (r'우대조건\s*(.+?)(?=자격|담당|채용절차|전형|$)', 'preferred_qualifications'),
        (r'담당업무\s*(.+?)(?=자격|우대|채용절차|전형|$)', 'job_description'),
        (r'주요\s*업무\s*(.+?)(?=자격|우대|채용절차|전형|$)', 'job_description'),
        (r'자격\s*요건\s*(.+?)(?=우대|담당|채용절차|전형|$)', 'qualifications'),
    ]

    for pattern, field in section_patterns:
        m = re.search(pattern, text_combined, flags=re.DOTALL)
        if m:
            content = m.group(1).strip()
            content = re.sub(r'[\-\*\•▸▶\s]+', ' ', content)
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'조건\s*$', '', content)
            content = content.strip()

            if len(content) < 10:
                continue

            if field == 'job_description' and 'job_description' not in result:
                result['job_description'] = content[:5000]
            elif field == 'qualifications' and 'qualifications' not in result:
                result['qualifications'] = content[:3000]
            elif field == 'preferred_qualifications' and 'preferred_qualifications' not in result:
                result['preferred_qualifications'] = content[:2000]

    garbage_patterns = [
        r'면접\s*시\s*관련\s*서류',
        r'제출\s*요청',
        r'허위\s*사실',
        r'채용\s*취소',
        r'채용절차',
        r'공정화',
        r'제출하신\s*서류',
        r'입사\s*시\s*제출',
    ]

    if 'preferred_qualifications' in result:
        pref = result['preferred_qualifications']
        for gp in garbage_patterns:
            if re.search(gp, pref):
                pref = re.sub(gp + r'.*?(?=\s*[^\s]|$)', '', pref, flags=re.DOTALL)
        pref = pref.strip()
        if len(pref) < 10:
            result['preferred_qualifications'] = ''
        else:
            result['preferred_qualifications'] = pref[:2000]

    if "benefits" not in result:
        result['benefits'] = _normalize_welfare(text)
    if "location" not in result:
        result['location'] = _normalize_location(text)
    if "employment_type" not in result:
        result['employment_type'] = _normalize_employment_type(text)

    return result
