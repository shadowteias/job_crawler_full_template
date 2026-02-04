# api/postprocess.py

from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup


# --------------------------------------------------------------------
# 기본 유틸
# --------------------------------------------------------------------


def collapse_spaces(text: str) -> str:
    """모든 공백(개행, 탭 포함)을 한 칸으로 줄이고 양 끝 공백 제거."""
    return re.sub(r"\s+", " ", text or "").strip()


# --------------------------------------------------------------------
# JSON / 설정 덩어리 제거
# --------------------------------------------------------------------

JSON_KEYVAL_RE = re.compile(r'"\w+"\s*:')


def _should_treat_as_json(window: str) -> bool:
    """
    주어진 텍스트 조각을 'JSON 오브젝트'로 볼지 여부를 판단하는 보수적 휴리스틱.
    - `"키":` 패턴이 2개 이상
    - 중괄호/따옴표/쉼표 비율이 어느 정도 이상
    """
    if not window:
        return False

    keyvals = JSON_KEYVAL_RE.findall(window)
    if len(keyvals) < 2:
        return False

    specials_set = set('{}[]":,')
    specials = sum(1 for c in window if c in specials_set)
    ratio = specials / max(len(window), 1)

    # JSON/설정 조각이면 특수문자 비율이 꽤 높음
    return ratio > 0.15


def strip_json_like_fragments(text: str) -> str:
    """
    긴 job_description 안에 섞여 있는 JSON/설정 덩어리들을 보수적으로 제거.

    원리:
      - '{'를 만나면, 뒤쪽 200자 정도를 window로 보고
      - 그 안에 `"키":` 패턴이 2개 이상 + 특수문자 비율 > 0.15 이면
        "여기서부터는 JSON" 이라고 판단
      - 중첩되는 중괄호 깊이를 추적해서 짝이 맞는 '}'까지 모두 건너뜀
    안전장치:
      - 최종 결과 길이가 원본의 30% 미만이면, 너무 많이 날렸다고 보고 원본을 그대로 반환
    """
    if not text:
        return ""

    n = len(text)
    i = 0
    in_json = False
    depth = 0
    result_chars: List[str] = []
    removed_len = 0

    while i < n:
        ch = text[i]

        # JSON이 아닌 상태에서 '{'를 발견했을 때만 JSON 후보 검사
        if not in_json and ch == "{":
            window = text[i : i + 200]
            if _should_treat_as_json(window):
                # JSON 덩어리 시작
                in_json = True
                depth = 1
                start_idx = i
                i += 1
                # 이 '{'부터는 결과에 추가하지 않음
                continue
            else:
                # JSON으로 안 보이면 그냥 문자로 취급
                result_chars.append(ch)
                i += 1
                continue

        # JSON 내부: 중괄호 깊이 추적하며 전부 skip
        if in_json:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    # JSON 블록 끝
                    in_json = False
                    removed_len += (i - start_idx + 1)
            i += 1
            continue

        # 평상시: 그대로 결과에 추가
        result_chars.append(ch)
        i += 1

    cleaned = "".join(result_chars)

    # 너무 많이 날렸으면 위험할 수 있으니 원본 유지
    if len(cleaned) < 0.3 * n:
        return text

    return cleaned


# --------------------------------------------------------------------
# 섹션 헤더 주변에 인위적 줄바꿈 삽입
# --------------------------------------------------------------------

SECTION_SPLIT_PATTERNS = [
    # 영어 섹션 헤더 (일반적인 채용 공고 패턴)
    r"\bResponsibilities\b",
    r"\bResponsibility\b",
    r"\bKey Responsibilities\b",
    r"\bWhat you'll do\b",
    r"\bWhat you will do\b",
    r"\bQualifications\b",
    r"\bMinimum Qualifications\b",
    r"\bBasic Qualifications\b",
    r"\bPreferred Qualifications\b",
    r"\bRequirements\b",
    r"\bLocation\b",
    r"\bWorking Mode\b",
    r"\bBenefits\b",
    r"\bPerks\b",
    r"\bAbout\b",

    # 한국어 필드/섹션명
    r"직군",
    r"경력사항",
    r"고용형태",
    r"근무지",
    r"근무 형태",
    r"복리후생",
    r"혜택 및 복지",
    r"전형절차",
    r"채용절차",
    r"전형 절차",
    r"채용 절차",
    r"지원방법",
    r"지원 방법",
]


def inject_virtual_newlines(text: str) -> str:
    """
    줄바꿈이 거의 없는 원시 텍스트 안에서,
    섹션 헤더나 필드명처럼 보이는 부분 앞뒤로 강제로 newline 삽입.
    Responsibilities / Qualifications / 근무지 / 고용형태 등에서
    블록이 끊어지도록 도와준다.
    """
    if not text:
        return ""

    # 섹션 헤더 앞뒤에 줄바꿈 삽입
    for pattern in SECTION_SPLIT_PATTERNS:
        text = re.sub(
            pattern,
            lambda m: "\n" + m.group(0) + "\n",
            text,
        )

    # '-Required', '-Preferred' 같은 것들을 줄 시작 불릿 형태로 정리
    text = re.sub(r"\s*-\s*(Required|Preferred)\b", r"\n- \1", text)

    return text


# --------------------------------------------------------------------
# HTML → plain text
# --------------------------------------------------------------------


def html_to_plain_text(text: str) -> str:
    """
    HTML이든 아니든 상관없이 BeautifulSoup에 한 번 태워서:
      - script/style/noscript/iframe 등 제거
      - <br> → 줄바꿈
      - get_text(separator="\\n") 로 큰 덩어리를 줄바꿈 포함 텍스트로 변환
    """
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")

    # 노이즈 태그 제거
    for tag_name in [
        "script",
        "style",
        "noscript",
        "svg",
        "meta",
        "link",
        "iframe",
        "form",
        "input",
        "button",
    ]:
        for t in soup.find_all(tag_name):
            t.decompose()

    # <br>는 줄바꿈으로
    for br in soup.find_all("br"):
        br.replace_with("\n")

    plain = soup.get_text(separator="\n")
    # 아직은 줄 단위 분할 전에, 전체 공백을 살짝 정리
    return plain


# --------------------------------------------------------------------
# 블록 분할 / 노이즈 필터 / 라벨링
# --------------------------------------------------------------------

CODE_CHARS = set("{};:()[]=<>")
JSON_KEY_PATTERN = re.compile(r'"\w+"\s*:')


def is_code_like_block(text: str) -> bool:
    """
    CSS/JS/JSON/추적 코드처럼 보이는 블록을 걸러낸다.
    사이트 특화 없이 '형태'만 기준으로 판단.
    """
    if not text:
        return False

    # 너무 짧고 특수문자만 많은 경우
    if len(text) < 12 and any(c in text for c in "{};"):
        return True

    # 특수문자 비율
    specials = sum(1 for c in text if c in CODE_CHARS)
    if specials and specials / max(len(text), 1) > 0.18:
        return True

    # JSON 스타일 key:value
    if JSON_KEY_PATTERN.search(text):
        return True

    lower = text.lower()

    # 전형적인 CSS/JS 키워드
    css_js_keywords = [
        "function(",
        "var ",
        "let ",
        "const ",
        "=>",
        "px",
        "font-size",
        "color:",
        "border:",
        "background:",
        "display:",
        "gtag(",
        "fbq(",
    ]
    if any(kw in lower for kw in css_js_keywords):
        return True

    # URL이 과도하게 많은 경우 (링크 리스트/로그 등)
    url_count = lower.count("http://") + lower.count("https://")
    if url_count >= 3 and url_count / max(len(text), 1) > 0.02:
        return True

    return False


def is_nav_or_footer_block(text: str) -> bool:
    """
    상단/하단 네비, 푸터, 단순 버튼 텍스트 등 job_description에 필요 없는 블록 필터.
    사이트 특화가 아니라, 매우 일반적인 패턴만 사용.
    """
    stripped = text.strip()
    if not stripped:
        return True

    if len(stripped) <= 2 and stripped in {"|", "·", "•"}:
        return True

    lower = stripped.lower()

    # 공통 네비게이션/푸터 용어
    nav_words = [
        "로그인",
        "회원가입",
        "개인정보처리방침",
        "개인정보 처리방침",
        "이용약관",
        "쿠키",
        "copyright",
        "all rights reserved",
        "faq",
    ]
    # 단일 CTA 버튼류
    cta_words = [
        "지원하기",
        "지원 하기",
        "공유하기",
        "공유 하기",
        "apply now",
        "apply",
        "share",
    ]

    if len(stripped) < 30 and any(w in stripped for w in nav_words + cta_words):
        return True

    return False


def normalize_block_for_dedup(text: str) -> str:
    """
    중복 블록 제거용 정규화 문자열 생성.
    """
    t = collapse_spaces(text).lower()
    # 기호/구두점은 어느 정도 제거
    t = re.sub(r"[^\w\s가-힣]", "", t)
    return t.strip()


def ensure_sentence_ending(text: str) -> str:
    """
    서로 다른 블록이 붙어버리지 않도록 각 블록의 끝을 문장처럼 마무리.
    """
    if not text:
        return ""

    s = text.rstrip()
    if not s:
        return s

    last = s[-1]

    # 이미 문장/구문 끝으로 보이는 경우
    if last in ".!?)]”’\"'」』":
        return s
    # 한국어 문장 종결 어미로 끝나는 짧은 문장
    if last in {"다", "요", "함"}:
        return s

    return s + "."


def _split_plain_text_into_blocks(text: str) -> List[str]:
    """
    plain text를 줄바꿈 기준으로 블록 단위 분할.
    """
    raw_lines = re.split(r"[\r\n]+", text or "")
    blocks: List[str] = []
    for line in raw_lines:
        line = collapse_spaces(line)
        if not line:
            continue
        blocks.append(line)
    return blocks


def detect_section_label_for_job_description(text: str) -> Optional[str]:
    """
    job_description 정리용 섹션 라벨 감지.
    v1에서는 '업무/역할' 섹션만 긍정적으로 인식하고,
    명확한 자격요건/우대/복리/절차/지원 섹션은 job_description에서 제외하는 용도로만 사용.
    """
    stripped = text.strip()
    if not stripped:
        return None

    # 너무 긴 문단은 제목으로 보지 않는다.
    first_line = stripped.splitlines()[0]
    if len(first_line) > 80:
        return None

    lower = first_line.lower()

    def contains_any(words: List[str]) -> bool:
        for w in words:
            if w in first_line or w.lower() in lower:
                return True
        return False

    # 1) 주요 업무/역할 섹션
    main_tasks_keywords = [
        "주요업무",
        "담당업무",
        "하는 일",
        "맡게 될 업무",
        "역할",
        "업무 내용",
        "responsibilities",
        "responsibility",
        "what you'll do",
        "what you will do",
        "key responsibilities",
        "role & responsibilities",
    ]
    if contains_any(main_tasks_keywords):
        return "main_tasks"

    # 2) 자격요건(필수)
    requirements_keywords = [
        "자격요건",
        "지원자격",
        "필수요건",
        "필수 요건",
        "필수 사항",
        "requirements",
        "required",
        "minimum qualifications",
        "basic qualifications",
        "qualifications",
    ]
    if contains_any(requirements_keywords):
        return "requirements"

    # 3) 우대사항
    preferred_keywords = [
        "우대사항",
        "우대조건",
        "우대 요건",
        "preferred",
        "nice to have",
        "preferred qualifications",
    ]
    if contains_any(preferred_keywords):
        return "preferred"

    # 4) 복리후생/혜택
    benefits_keywords = [
        "복리후생",
        "혜택 및 복지",
        "급여 및 복리후생",
        "benefits",
        "perks",
    ]
    if contains_any(benefits_keywords):
        return "benefits"

    # 5) 전형/채용 절차
    process_keywords = [
        "전형절차",
        "전형 절차",
        "채용절차",
        "채용 절차",
        "hiring process",
        "interview process",
        "recruitment process",
        "application process",
    ]
    if contains_any(process_keywords):
        return "process"

    # 6) 지원 방법/서류
    application_keywords = [
        "지원방법",
        "지원 방법",
        "지원 서류",
        "제출 서류",
        "how to apply",
        "application",
    ]
    if contains_any(application_keywords):
        return "application"

    # 회사 소개(About)는 아직 job_description에서 강하게 제외하지 않는다 (v1).
    return None


EXCLUDED_SECTIONS_FOR_JOB_DESC = {
    "requirements",
    "preferred",
    "benefits",
    "process",
    "application",
}


# --------------------------------------------------------------------
# 메인 클래스
# --------------------------------------------------------------------


class JobPostingNormalizer:
    """
    채용공고 텍스트 정리용 유틸리티.

    v1: job_description(주요 업무)만 정리.
    이후 normalize_all_fields 에서 다른 필드까지 확장 예정.
    """

    def __init__(self, use_llm: bool = False) -> None:
        # 아직은 사용하지 않지만, 확장성을 위해 인터페이스만 잡아둠.
        self.use_llm = use_llm

    # --- public API -----------------------------------------------------

    def normalize_job_description(self, html_or_text: str) -> str:
        """
        job_description(주요 업무) 칸 정리를 수행.

        파이프라인:
          1) HTML 태그/스크립트 제거 → plain text
          2) 텍스트 안의 대형 JSON/설정 덩어리 제거 (보수적)
          3) 섹션 헤더 주변에 인위적 줄바꿈 삽입
          4) 줄바꿈 기준 블록 분할
          5) 코드/JSON/네비/푸터 노이즈 블록 필터링
          6) 섹션 라벨링으로 자격요건/우대/복리/절차/지원 섹션 제거
          7) 중복 블록 제거 + 문장 끝 정리
        """
        if not html_or_text:
            return ""

        # 1) HTML → plain text (항상 수행)
        text = html_to_plain_text(html_or_text)

        # 2) JSON/설정 덩어리 제거
        text = strip_json_like_fragments(text)

        # 3) 섹션 헤더 주변에 줄바꿈 삽입
        text = inject_virtual_newlines(text)

        # 4) plain text를 줄바꿈 기준으로 블록 분할
        blocks = _split_plain_text_into_blocks(text)
        if not blocks:
            return ""

        # 5) 노이즈 필터링 (코드/JSON/네비/푸터)
        clean_blocks: List[str] = []
        for raw in blocks:
            t = collapse_spaces(raw)
            if not t:
                continue
            if is_code_like_block(t):
                continue
            if is_nav_or_footer_block(t):
                continue
            clean_blocks.append(t)

        if not clean_blocks:
            # 너무 공격적으로 필터링되면 원래 분할 결과를 사용
            clean_blocks = blocks[:]

        # 6) 섹션 라벨링 & job_description 후보 선택
        job_blocks: List[str] = []
        seen_norm = set()
        current_section: Optional[str] = None

        for block in clean_blocks:
            label = detect_section_label_for_job_description(block)
            if label:
                current_section = label

            # 명확히 자격요건/우대/복리/절차/지원 섹션으로 분류된 경우는 제외
            if current_section in EXCLUDED_SECTIONS_FOR_JOB_DESC:
                continue

            # 중복 블록 제거
            norm = normalize_block_for_dedup(block)
            if not norm:
                continue
            if norm in seen_norm:
                continue
            seen_norm.add(norm)

            job_blocks.append(ensure_sentence_ending(block))

        # 7) 모두 제거되었다면 최소한 fallback으로라도 돌려줌
        if not job_blocks:
            fallback = " ".join(clean_blocks)
            return ensure_sentence_ending(collapse_spaces(fallback))

        return "\n".join(job_blocks).strip()

    def normalize_all_fields(self, posting) -> dict:
        """
        앞으로 확장용 인터페이스.
        v1에서는 job_description만 정리해서 반환.
        """
        desc = self.normalize_job_description(
            getattr(posting, "job_description", "") or ""
        )
        return {
            "job_description": desc,
        }
