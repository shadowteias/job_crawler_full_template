import os
import re
from typing import Dict, List, Optional, Set

# ── 제로샷 사용 여부/모델 설정(환경변수로 제어) ─────────────────────────────
ZS_ENABLED = os.getenv("COUNSELING_ZS_ENABLED", "0").lower() in {"1", "true", "yes"}
ZS_MODEL   = os.getenv("COUNSELING_ZS_MODEL", "joeddav/xlm-roberta-base-xnli")  # base로 경량화

_ZS_PIPE = None
def _load_zero_shot():
    global _ZS_PIPE
    if _ZS_PIPE is not None:
        return _ZS_PIPE
    if not ZS_ENABLED:
        return None
    try:
        from transformers import pipeline
        _ZS_PIPE = pipeline(
            "zero-shot-classification",
            model=ZS_MODEL,
            device=-1,  # CPU
        )
    except Exception:
        _ZS_PIPE = None
    return _ZS_PIPE
# ──────────────────────────────────────────────────────────────────────────────

BENEFIT_CANON = [
    "식대","재택근무","건강검진","교육비","사내스터디","컨퍼런스참가비",
    "운동비","도서구입비","경조사비","경조휴가","스톡옵션","자율출퇴근제",
]
BENEFIT_SYNONYM = {
    "재택": "재택근무",
    "원격": "재택근무",
    "리모트": "재택근무",
    "건강 검진": "건강검진",
    "헬스비": "운동비",
    "체력단련비": "운동비",
    "책구입비": "도서구입비",
    "스터디": "사내스터디",
    "컨퍼런스": "컨퍼런스참가비",
    "행사비": "경조사비",
    "경조휴무": "경조휴가",
    "스톡옵션": "스톡옵션",
    "자율 근무제": "자율출퇴근제",
}

LOCATION_BUCKETS = {
    "수도권": ["서울","경기","경기도","인천","수도권","판교","성남","분당","강남","서초","송파","마포","여의도"],
    "지방": ["부산","대구","광주","대전","울산","세종","창원","전주","제주","강원","충북","충남","전북","전남","경북","경남"],
}
CITY_LIST = sum(LOCATION_BUCKETS.values(), [])

TECH_DICT = [
    "python","django","flask","fastapi","celery",
    "java","spring","kotlin","scala",
    "javascript","typescript","node","express","nest","react","vue","svelte","next","nuxt",
    "go","golang","rust","c#",".net","php","laravel",
    "sql","mysql","mariadb","postgres","mongodb","redis","elasticsearch",
    "aws","azure","gcp","docker","kubernetes","linux","git","airflow",
    "pytorch","tensorflow","sklearn","bert","transformers","xgboost","lightgbm",
]

def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _normalize_salary_500(text: str) -> Optional[int]:
    t = text.lower().replace(",", "")
    m_uk = re.search(r"(\d+)\s*억", t)
    candidates = []
    if m_uk:
        candidates.append(int(m_uk.group(1)) * 10000)
    for m in re.findall(r"(\d{3,5})\s*만", t):
        candidates.append(int(m))
    for n in re.findall(r"\b(\d{3,5})\b", t):
        candidates.append(int(n))
    if not candidates:
        return None
    base = max(candidates)
    return (base // 500) * 500

def _extract_benefits(text: str) -> List[str]:
    low = text.lower()
    found: Set[str] = set()
    for k, v in BENEFIT_SYNONYM.items():
        if k in low:
            found.add(v)
    for b in BENEFIT_CANON:
        if b in text:
            found.add(b)
    return [b for b in BENEFIT_CANON if b in found]

def _extract_location(text: str) -> Optional[str]:
    t = text.lower()
    if "지역 무관" in text or "전국" in text or "리모트" in t or "원격" in t:
        return "지역 무관"
    if "지방 가능" in text:
        return "지방 가능"
    for bucket, names in LOCATION_BUCKETS.items():
        if any(n in text for n in names):
            return "수도권" if bucket == "수도권" else "지방 가능"
    for city in CITY_LIST:
        if city in text:
            return city
    return None

def _extract_company_size(text: str) -> Optional[int]:
    m = re.findall(r"(\d{1,5})\s*(명|인)", text)
    if not m:
        return None
    nums = sorted({int(x[0]) for x in m})
    return nums[-1] if nums else None

def _extract_industry(text: str) -> Optional[str]:
    candidates = [
        ("클라우드", ["cloud","클라우드","saas"]),
        ("플랫폼", ["플랫폼","platform"]),
        ("이커머스", ["커머스","e-commerce","ecommerce","쇼핑몰"]),
        ("핀테크", ["핀테크","fintech","결제"]),
        ("게임", ["game","게임"]),
        ("ai", ["ai","머신러닝","인공지능","딥러닝"]),
        ("백엔드", ["backend","백엔드"]),
        ("데이터", ["data","데이터"]),
    ]
    low = text.lower()
    for label, keys in candidates:
        if any(k in low for k in keys):
            return label
    return None

def _extract_stack(text: str) -> List[str]:
    low = text.lower()
    got = []
    for k in TECH_DICT:
        if k in low:
            got.append(k.upper() if k in {"aws","gcp","sql"} else k.capitalize())
    out = []
    for g in got:
        if g not in out:
            out.append(g)
    return out[:15]

def _extract_hiring_type(text: str) -> str:
    has_new = "신입" in text
    has_exp = "경력" in text
    return "신입+경력" if has_exp else "신입"

# def _extract_required_fields(text: str) -> List[str]:
#     t = text
#     candidates = []
#     if re.search(r"(반드시|필수|꼭|무조건)", t):
#         mapping = {
#             "근무지": ["근무지","지역","위치","재택","원격"],
#             "급여": ["급여","연봉","연봉협상","보상"],
#             "복리후생": ["복지","복리","식대","재택","건강검진","자율출퇴근"],
#             "근무인원": ["규모","인원","명","사원수"],
#             "구인구분": ["신입","경력"],
#             "구인기술": ["업무","역할","기술","스킬"],
#             "기술스택": [*TECH_DICT],
#             "업종분류": ["업종","도메인","산업","클라우드","플랫폼","핀테크","이커머스","게임","ai"],
#         }
#         for key, keys in mapping.items():
#             if any(k in t for k in keys):
#                 if key not in candidates:
#                     candidates.append(key)
#     return candidates

# 검색조건 강화하여 '필수조건' 걸리는거 덜 나오게 하는 버전
def _extract_required_fields(text: str) -> List[str]:
    """
    상담 텍스트에서 '필수'로 요구되는 항목을 보다 엄격하게 추출.
    - 강한 트리거(반드시/필수/꼭/무조건/필히)가 들어간 문장에서만 판정
    - 같은 문장 안에 해당 항목을 뒷받침하는 키워드/증거가 있을 때만 필수로 인정
    - 약한 트리거(원함/희망/필요/요구 등)는 무시하여 과검출 10~20% 정도 감소
    """
    import re

    t = text

    # 강한 트리거만 사용 (기존 유지 + 엄격화)
    STRONG_TRIGGERS = ("반드시", "필수", "꼭", "무조건", "필히")

    # 필드별 키워드 매핑 (기존 맥락 유지)
    mapping = {
        "근무지": ["근무지","지역","위치","재택","원격","수도권","지방 가능","지역 무관"],
        "급여": ["급여","연봉","보상","최소","이상","이하"],
        "복리후생": ["복지","복리","식대","재택","건강검진","자율출퇴근","교육비","사내스터디","컨퍼런스","도서구입비","경조휴가","경조사비","스톡옵션"],
        "근무인원": ["규모","인원","사원수","명"],
        "구인구분": ["신입","경력"],
        "구인기술": ["업무","역할","기술","스킬"],
        "기술스택": list(TECH_DICT),
        "업종분류": ["업종","도메인","산업","클라우드","플랫폼","핀테크","이커머스","게임","ai","머신러닝","인공지능","딥러닝"],
    }

    # 문장 단위로 나눠서 '강한 트리거가 있는 문장'만 검사
    # ※ 필요 시 WINDOW 값을 1로 늘리면 ±1문장까지 허용(조금 느슨)
    WINDOW = 0  # CHANGED: 기본은 같은 문장 내에서만 인정 (더 엄격)
    sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!]|[。？！]|[\n\r])', t) if s.strip()]

    required: List[str] = []

    def in_window(i, j) -> bool:
        return abs(i - j) <= WINDOW

    # 각 문장에 강한 트리거가 있는지 먼저 찾고, 같은(또는 인접) 문장 범위에서 증거 키워드 확인
    strong_idxs = [i for i, s in enumerate(sentences) if any(w in s for w in STRONG_TRIGGERS)]
    if not strong_idxs:
        return []  # 강한 트리거 자체가 없으면 필수조건 없음(엄격화 포인트)

    # 간단 헬퍼
    num_pat = re.compile(r'\d[\d,\.]*')  # 숫자 존재 검사용
    def sentence_window(i):
        for j, s in enumerate(sentences):
            if in_window(i, j):
                yield s

    # 강트리거 문장들 기준으로 필수항목 판정
    for idx in strong_idxs:
        scope_text = " ".join(sentence_window(idx))  # WINDOW=0이면 해당 문장만

        # 근무지
        if any(k in scope_text for k in mapping["근무지"]):
            if "근무지" not in required:
                required.append("근무지")

        # 급여: '연봉/급여/보상' + (숫자 또는 '최소/이상/이하' 같은 한정어) 동시 충족 시에만
        if any(k in scope_text for k in ["연봉", "급여", "보상"]) and (num_pat.search(scope_text) or any(k in scope_text for k in ["최소","이상","이하"])):
            if "급여" not in required:
                required.append("급여")

        # 복리후생: 사전 정의된 복지 키워드가 1개 이상 실제로 등장
        # (_extract_benefits는 정규화된 복지 집합을 주므로, scope_text에서도 직접 키워드 확인)
        if any(k in scope_text for k in mapping["복리후생"]) or _extract_benefits(scope_text):
            if "복리후생" not in required:
                required.append("복리후생")

        # 구인구분: 신입/경력 키워드가 같은 문장 내에 있을 때만
        if any(k in scope_text for k in mapping["구인구분"]):
            if "구인구분" not in required:
                required.append("구인구분")

        # 기술스택: 사전 기술 키워드가 2개 이상(과검출 방지 위해 수량 요건 강화)
        stack_in_sent = _extract_stack(scope_text)
        if len(stack_in_sent) >= 2:
            if "기술스택" not in required:
                required.append("기술스택")
            # 기술 명시가 뚜렷할 때만 '구인기술'도 필수로 간주
            if "구인기술" not in required:
                required.append("구인기술")

        # 근무인원: 명/인 패턴 등으로 크기 감지되면
        if _extract_company_size(scope_text) is not None:
            if "근무인원" not in required:
                required.append("근무인원")

        # 업종분류: 간단 도메인 키워드 포착될 때만
        if _extract_industry(scope_text) is not None:
            if "업종분류" not in required:
                required.append("업종분류")

    return required



def extract_from_text(text: str, only_fields: Optional[List[str]] = None) -> Dict:
    """상담 텍스트 → 표준 항목 사전으로 정규화 (기본: 규칙 기반, 옵션: 제로샷 보정)"""
    raw = text or ""
    clean = _clean_html(raw)
    result = {
        "근무인원": _extract_company_size(clean),
        "업종분류": _extract_industry(clean),
        "구인구분": _extract_hiring_type(clean),
        "구인기술": None,
        "근무지": _extract_location(clean),
        "급여": _normalize_salary_500(clean),
        "기술스택": _extract_stack(clean),
        "복리후생": _extract_benefits(clean),
        "필수조건": _extract_required_fields(clean),
    }
    result["구인기술"] = ", ".join(result["기술스택"][:5]) if result["기술스택"] else None

    # ── 옵션: 제로샷 보정 (환경변수로 켜진 경우에만) ─────────────────────────
    zs = _load_zero_shot()
    if zs is not None:
        try:
            loc_hypo = ["수도권", "지방 가능", "지역 무관"]
            out = zs(clean, loc_hypo, multi_label=False)
            if out and out.get("labels"):
                top = out["labels"][0]
                if top in loc_hypo and result["근무지"] is None:
                    result["근무지"] = top
            gt_hypo = ["신입", "신입+경력"]
            out2 = zs(clean, gt_hypo, multi_label=False)
            if out2 and out2.get("labels"):
                top2 = out2["labels"][0]
                if top2 in gt_hypo:
                    result["구인구분"] = top2
        except Exception:
            pass
    # ────────────────────────────────────────────────────────────────────────

    if only_fields:
        return {k: result.get(k) for k in only_fields if k in result}
    return result
