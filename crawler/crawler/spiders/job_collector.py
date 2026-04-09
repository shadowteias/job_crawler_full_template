import hashlib
import os
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import django
from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider

# ===== Django 초기화 =====
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
django.setup()

from api.models import Company, JobPosting  # noqa: E402
from django.utils import timezone  # noqa: E402

logger = logging.getLogger(__name__)

# 이 스파이더는 text 기반 채용공고만 다룬다.
TEXT_POST_TYPE = "text"
TEXT_PAGE_TYPES = {"listing", "one_page", "main"}

# listing 페이지에서 "사람이 보기에도 채용처럼 보이는" 앵커 텍스트 키워드
JOB_ANCHOR_KEYWORDS = [
    "채용", "모집", "인턴", "구인", "경력", "신입", "구합니다",
    "recruit", "recruitment", "job", "jobs", "career", "careers",
    "position", "positions", "open position", "open positions", "role", "roles", "apply",
]

# 목록에서 아예 빼버릴 앵커(전형 절차/지원서/FAQ 등)
EXCLUDE_ANCHOR_SUBSTRINGS = [
    "모집절차",
    "모집 절차",
    "채용 절차",
    "전형 절차",
    "지원 절차",
    "지원서 수정",
    "지원서 확인",
    "나의 지원서",
    "지원 현황",
    "faq",
]

# 외부 상용 플랫폼: 발견 시 로그 남기고 중단
EXTERNAL_JOB_DOMAINS = [
    "wanted.co.kr",
    "saramin.co.kr",
    "jobkorea.co.kr",
]

BENEFIT_KEYWORDS = [
    "식대", "재택근무", "건강검진", "교육비", "사내스터디", "컨퍼런스참가비",
    "운동비", "도서구입비", "경조사비", "경조휴가", "스톡옵션", "자율출퇴근제",
]


def _has_digit(s: str) -> bool:
    return any(ch.isdigit() for ch in s)


def _make_unique_post_url(base_url: str, title: str, index: int = 0) -> str:
    title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
    clean_url = base_url.rstrip("/")
    return f"{clean_url}#job-{title_hash}-{index}"


# ===== LLM/BERT 훅 (옵션) =====
try:
    from api.llm_parser import parse_job_details_with_llm, is_job_posting, extract_posting_dates  # type: ignore
except Exception:  # pragma: no cover
    parse_job_details_with_llm = None
    is_job_posting = None
    extract_posting_dates = None


class JobCollectorSpider(Spider):
    """
    Company.recruits_url / page_type / post_type 기반으로
    실제 JobPosting 레코드를 생성/업데이트하는 스파이더.

    정책 요약:
    - post_type='text' 만 대상 (유지)
    - page_type in ['listing', 'one_page', 'main'] 만 처리 (유지)
    - listing:
        - URL 모양 집착하지 않고,
          앵커 텍스트에 채용 관련 키워드가 보이면 일단 "채용 같네" 하고 상세 페이지로 들어감.
        - 모집절차/지원서/FAQ 같은 건 앵커로 걸러서 제외.
        - from_listing=True 플래그를 줘서 상세 페이지에서 너무 빡세게 재필터링하지 않음.
    - one_page/main:
        - 페이지 내 블록 분리 후 채용공고로 보이는 것만 저장.
    - 외부 플랫폼 링크(wanted/saramin/jobkorea) 발견 시: 그 회사는 수집 중단.
    - LLM/BERT는 있으면 "추가로 통과시켜주는 용도"로만 사용.
      (False라고 해서 버리지 않고, 항상 로컬 키워드 룰도 같이 봄)
    """
    name = "job_collector"

    custom_settings = {
        "LOG_LEVEL": "INFO",
        "DOWNLOAD_DELAY": 0.3,
        "CONCURRENT_REQUESTS": 4,
    }

    # ============== 초기화 ==============

    def __init__(self, company_id=None, recruits_url=None,
                 page_type=None, post_type=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not company_id or not recruits_url:
            raise ValueError("company_id와 recruits_url은 필수 인자입니다.")

        self.company_id = int(company_id)
        self.recruits_url = recruits_url
        self.page_type = (page_type or "").lower()
        self.post_type = (post_type or "").lower()

        try:
            self.company = Company.objects.get(id=self.company_id)
        except Company.DoesNotExist:
            raise CloseSpider(f"Company {self.company_id} does not exist")

        # 이미 처리한 상세 URL 중복 방지용
        self.seen_urls = set()
        self.saved_post_urls = set()

    # ============== 시작 ==============

    def start_requests(self):
        # ✅ 여전히 유지: text 아닌 post_type은 스킵
        if self.post_type and self.post_type != TEXT_POST_TYPE:
            logger.info(
                "job_collector: skip company_id=%s (post_type=%s != text)",
                self.company_id,
                self.post_type,
            )
            raise CloseSpider("non_text_post_type")

        # ✅ 여전히 유지: 지원하지 않는 page_type은 스킵
        if self.page_type and self.page_type not in TEXT_PAGE_TYPES:
            logger.info(
                "job_collector: skip company_id=%s (page_type=%s not supported)",
                self.company_id,
                self.page_type,
            )
            raise CloseSpider("unsupported_page_type")

        target_type = self.page_type or "listing"

        logger.info(
            "job_collector: start company_id=%s page_type=%s post_type=%s url=%s",
            self.company_id,
            target_type,
            self.post_type or TEXT_POST_TYPE,
            self.recruits_url,
        )

        if target_type == "listing":
            yield Request(
                url=self.recruits_url,
                callback=self.parse_listing,
                dont_filter=True,
            )
        else:
            yield Request(
                url=self.recruits_url,
                callback=self.parse_onepage,
                dont_filter=True,
            )

    def _get_visible_text(self, response) -> str:
        def _texts(root_xpath: str) -> str:
            parts = response.xpath(
                root_xpath
                + "//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript) and normalize-space()]"
            ).getall()
            text = " ".join((p or "").strip() for p in parts if p and p.strip())
            return re.sub(r"\s+", " ", text).strip()

        # Prefer likely main content containers to avoid nav/footer boilerplate.
        candidates = []
        for xp in [
            "//main",
            "//article",
            "//*[@id='content' or @id='contents' or contains(@class,'content') or contains(@class,'contents') or contains(@class,'view') or contains(@class,'board') or contains(@class,'recruit') or contains(@class,'career') or contains(@class,'job')]",
        ]:
            try:
                t = _texts(xp)
                if len(t) >= 200:
                    candidates.append(t)
            except Exception:
                continue

        if candidates:
            # pick the longest content-like block
            return max(candidates, key=len)

        return _texts("//body")

    def _trim_boilerplate(self, text: str) -> str:
        if not text:
            return ""
        t = re.sub(r"\s+", " ", text).strip()
        cut_markers = [
            "개인정보처리방침",
            "이용약관",
            "쿠키",
            "Copyright",
            "All Rights Reserved",
            "사이트맵",
        ]
        low = t.lower()
        cut_at = None
        for m in cut_markers:
            idx = low.find(m.lower())
            if idx != -1:
                cut_at = idx if cut_at is None else min(cut_at, idx)
        if cut_at is not None and cut_at >= 200:
            t = t[:cut_at].strip()
        return t

    def _looks_like_job_body(self, text: str) -> bool:
        """Best-effort quality gate to avoid saving pure navigation/sitemap text."""
        if not text:
            return False
        t = re.sub(r"\s+", " ", text).strip()
        if len(t) < 200:
            return False

        lowered = t.lower()
        # Hard negatives that frequently show up in global nav dumps.
        if any(bad in lowered for bad in [
            "전체메뉴",
            "gnb",
            "사이트맵",
            "all rights reserved",
        ]):
            return False

        # Positive signals: sections / hiring intent / structured content.
        signals = 0
        for kw in [
            "주요 업무",
            "자격 요건",
            "우대 사항",
            "전형 절차",
            "근무조건",
            "근무지",
            "급여",
            "연봉",
            "지원방법",
            "지원하기",
            "apply",
            "responsibilities",
            "qualifications",
            "benefits",
        ]:
            if kw.lower() in lowered:
                signals += 1
        # Also allow bullet-like density.
        if re.search(r"(\n|\r|\s)[\-\*\u2022]\s*", text):
            signals += 1

        return signals >= 1

    def _pick_title(self, response) -> str:
        candidates = [
            (response.css("h1::text").get() or "").strip(),
            (response.css("h2::text").get() or "").strip(),
            (response.css("title::text").get() or "").strip(),
        ]
        bad = {
            "전체메뉴",
            "하단메뉴 및 카피라이트",
            "고객지원",
            "contact us",
            "download",
            "careers",
        }
        for c in candidates:
            if not c:
                continue
            if c.strip().lower() in bad:
                continue
            if len(c.strip()) < 2:
                continue
            return c[:255]
        # fallback
        for c in candidates:
            if c:
                return c[:255]
        return "채용 공고"

    # ============== 공통: 외부 플랫폼 감지 ==============

    def _check_external_platform(self, response):
        # We must not crawl external job platforms.
        # However, many company pages include external job-platform links in footers or references.
        # Abort only if the current page itself is an external platform; otherwise, ignore external links.
        page_lower = (response.url or "").lower()
        if any(d in page_lower for d in EXTERNAL_JOB_DOMAINS):
            logger.warning(
                "job_collector: external platform page detected company_id=%s page=%s -> abort",
                self.company_id,
                response.url,
            )
            raise CloseSpider("external_job_platform_page")

        # Just log if external links are present.
        for href in response.css("a::attr(href)").getall():
            if not href:
                continue
            url = response.urljoin(href.strip())
            lower = url.lower()
            if any(d in lower for d in EXTERNAL_JOB_DOMAINS):
                logger.info(
                    "job_collector: external platform link ignored company_id=%s page=%s target=%s",
                    self.company_id,
                    response.url,
                    url,
                )
                # Do not abort; ignore.
                return

    # ============== listing 처리 ==============

    def parse_listing(self, response):
        self._check_external_platform(response)

        links = self.extract_job_links(response)
        if not links:
            logger.info(
                "job_collector: found 0 candidate detail links on listing; fallback to one_page parser"
            )
            # listing 페이지 전체를 one_page처럼 해석 시도
            self.parse_onepage(response)
            return

        for link_data in links:
            yield Request(
                url=link_data["url"],
                callback=self.parse_job_detail,
                cb_kwargs={
                    "from_listing": True,
                    "listing_deadline_at": link_data.get("deadline_at"),
                    "listing_posted_at": link_data.get("posted_at"),
                },
                dont_filter=True,
            )

    def extract_job_links(self, response):
        """
        listing 페이지에서 '사람 기준으로 채용처럼 보이는' 링크를 느슨하게 수집.
        - URL 패턴은 최소한만 사용 (같은 회사 도메인 여부 + 외부 플랫폼 필터)
        - 핵심은 앵커 텍스트의 채용 관련 키워드.
        - 전형절차/지원서/FAQ는 앵커 텍스트로 제거.
        """
        base = urlparse(response.url)
        base_domain = base.netloc

        seen = set()
        candidates = []

        for a in response.css("a"):
            href = (a.attrib.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue

            full = response.urljoin(href)
            full_clean = full.rstrip("/")

            parsed = urlparse(full)

            # 외부 플랫폼 -> 정책상 크롤링 안 함 (skip link only)
            if any(d in parsed.netloc.lower() for d in EXTERNAL_JOB_DOMAINS):
                continue

            # 같은 조직 도메인(또는 동일 최상위 도메인)만 본다
            if not self._same_org(base_domain, parsed.netloc):
                continue

            anchor_text_raw = " ".join(a.css("::text").getall()).strip()
            if not anchor_text_raw:
                # icon-only links often rely on title/aria-label
                anchor_text_raw = " ".join(
                    filter(
                        None,
                        [
                            (a.attrib.get("title") or "").strip(),
                            (a.attrib.get("aria-label") or "").strip(),
                        ],
                    )
                ).strip()
            if not anchor_text_raw:
                continue

            anchor_text = anchor_text_raw.lower()

            # 모집절차/FAQ/지원서 등은 제외
            if any(bad in anchor_text for bad in EXCLUDE_ANCHOR_SUBSTRINGS):
                continue

            # 채용/모집/인턴/경력/신입/구인/구합니다 등 포함되면 후보 인정
            by_text = any(kw in anchor_text for kw in JOB_ANCHOR_KEYWORDS)

            # Anchor text가 job keyword를 포함하지 않는 경우라도,
            # URL path가 job detail로 강하게 보이면 후보로 포함 (JS/ATS 랜딩 대응).
            path = (parsed.path or "").lower()
            url_positive = any(p in path for p in [
                "/recruit",
                "/recruitment",
                "/career",
                "/careers",
                "/job",
                "/jobs",
                "/position",
                "/positions",
                "/opening",
                "/openings",
            ])
            url_negative = any(p in path for p in [
                "/privacy",
                "/terms",
                "/sitemap",
                "/ir",
                "/contact",
                "/about",
            ])

            if by_text or (url_positive and not url_negative and len(path) >= 5):
                if full_clean not in seen:
                    seen.add(full_clean)
                    deadline_at, posted_at = self.extract_listing_dates_for_anchor(a)
                    candidates.append(
                        {
                            "url": full_clean,
                            "deadline_at": deadline_at,
                            "posted_at": posted_at,
                        }
                    )
                    logger.info(
                        "job_collector: listing candidate by text company_id=%s url=%s text=%s",
                        self.company_id,
                        full_clean,
                        anchor_text_raw[:80],
                    )

        logger.info(
            "job_collector: found %s candidate detail links on listing page",
            len(candidates),
        )
        return candidates

    # ============== one_page / main 처리 ==============

    def parse_onepage(self, response):
        self._check_external_platform(response)

        url = response.url
        headings = response.css("h2, h3")
        full_text_body = self._get_visible_text(response)

        jobs = []

        if not headings:
            if len(full_text_body) >= 80 and self._accept_as_job(full_text_body):
                parsed = {}
                if parse_job_details_with_llm:
                    try:
                        parsed = parse_job_details_with_llm(
                            full_text_body,
                            url=url,
                            company_name=self.company.name,
                        ) or {}
                    except Exception as e:
                        logger.warning("job_collector: parser failed for onepage %s (%s)", url, e)
                        parsed = {}
                sections = self.extract_all_sections(full_text_body)
                desc = (
                    parsed.get("job_description")
                    or sections.get("job_description")
                    or sections.get("qualifications")
                    or ""
                ).strip()
                if not desc:
                    desc = self._trim_boilerplate(full_text_body)
                if len(desc) < 120 or not self._looks_like_job_body(desc):
                    return
                title = self._pick_title(response)
                deadline_at, posted_at = self.extract_posting_dates_for_text(desc, fallback_text=full_text_body)
                jobs.append({
                    "post_url": _make_unique_post_url(url, title),
                    "title": title,
                    "job_description": desc[:20000],
                    "qualifications": (parsed.get("qualifications") or sections.get("qualifications") or "")[:2000],
                    "preferred_qualifications": (parsed.get("preferred_qualifications") or sections.get("preferred_qualifications") or "")[:2000],
                    "hiring_process": (parsed.get("hiring_process") or "")[:2000],
                    "location": parsed.get("location") or "",
                    "benefits": parsed.get("benefits") or "",
                    "employment_type": parsed.get("employment_type") or "",
                    "salary": parsed.get("salary") or "",
                    "deadline_at": deadline_at,
                    "posted_at": posted_at,
                })
        else:
            for i, h in enumerate(headings):
                title = " ".join(h.css("::text").getall()).strip()
                if not title:
                    continue

                texts = []
                for elem in h.xpath("./following-sibling::*"):
                    tag = elem.root.tag.lower()
                    if tag in ["h1", "h2", "h3"]:
                        break
                    texts.extend(elem.css("::text").getall())
                desc = " ".join(texts).strip()
                desc = re.sub(r"\s+", " ", desc)

                if len(desc) < 80:
                    continue

                if not self._accept_as_job(desc):
                    continue

                parsed = {}
                if parse_job_details_with_llm:
                    try:
                        parsed = parse_job_details_with_llm(
                            desc,
                            url=_make_unique_post_url(url, title, i),
                            company_name=self.company.name,
                        ) or {}
                    except Exception as e:
                        logger.warning("job_collector: parser failed for onepage block %s (%s)", url, e)
                        parsed = {}
                deadline_at, posted_at = self.extract_posting_dates_for_text(desc, fallback_text=full_text_body)
                else:
                    parsed = {}

                deadline_at = self.coerce_date(parsed.get("deadline_at"))
                posted_at = self.coerce_date(parsed.get("posted_at"))
                if not deadline_at and not posted_at:
                    deadline_at, posted_at = self.extract_posting_dates_for_text(desc, fallback_text=full_text_body)

                jobs.append({
                    "post_url": _make_unique_post_url(url, title, i),
                    "title": title,
                    "job_description": (parsed.get("job_description") or self._trim_boilerplate(desc))[:20000],
                    "qualifications": (parsed.get("qualifications") or "")[:2000],
                    "preferred_qualifications": (parsed.get("preferred_qualifications") or "")[:2000],
                    "hiring_process": (parsed.get("hiring_process") or "")[:2000],
                    "location": parsed.get("location") or "",
                    "benefits": parsed.get("benefits") or "",
                    "employment_type": parsed.get("employment_type") or "",
                    "salary": parsed.get("salary") or "",
                    "deadline_at": deadline_at,
                    "posted_at": posted_at,
                })

        logger.info(
            "job_collector: parsed %s job blocks from one_page/main",
            len(jobs),
        )

        for data in jobs:
            post_url = data.get("post_url")
            deadline_at = self.coerce_date(data.get("deadline_at"))
            posted_at = self.coerce_date(data.get("posted_at"))
            is_valid, invalid_reason = self.evaluate_posting_validity(deadline_at, posted_at)
            if not is_valid:
                self.deactivate_existing_posting(post_url, invalid_reason)
                logger.info(
                    "job_collector: skip invalid one_page/main posting company_id=%s url=%s reason=%s deadline_at=%s posted_at=%s",
                    self.company_id,
                    post_url,
                    invalid_reason,
                    deadline_at,
                    posted_at,
                )
                continue

            data["deadline_at"] = deadline_at
            data["posted_at"] = posted_at
            self.upsert_jobposting(data)

    # ============== 상세 페이지 처리 ==============

    def parse_job_detail(self, response, from_listing=False, listing_deadline_at=None, listing_posted_at=None):
        self._check_external_platform(response)

        url = response.url.rstrip("/")
        if url in self.seen_urls:
            logger.info("job_collector: skipping duplicate url=%s", url)
            return
        self.seen_urls.add(url)

        data = self.extract_job_from_detail(
            response,
            from_listing=from_listing,
            listing_deadline_at=listing_deadline_at,
            listing_posted_at=listing_posted_at,
        )
        if not data:
            logger.info("job_collector: extract_job_from_detail returned None for url=%s", url)
            return

        self.upsert_jobposting(data)

    def extract_job_from_detail(self, response, from_listing=False, listing_deadline_at=None, listing_posted_at=None):
        url = response.url.rstrip("/")

        title = self._pick_title(response)

        full_text = self._get_visible_text(response)
        if len(full_text) < 40:
            return None

        # from_listing:
        # - 이미 listing에서 '채용 같아 보이는' 앵커로 1차 필터된 상태
        # - 여기서는 너무 빡세게 거르지 않고, 극단적인 비채용 페이지만 막는다.
        if not from_listing:
            # one_page 등에서 직접 들어온 경우만 엄격 필터
            if not self._accept_as_job(full_text):
                logger.info("job_collector: skip non-job page by filter url=%s", url)
                return None
        else:
            # listing에서 온 경우:
            # 모집절차/지원서/FAQ 링크는 이미 extract_job_links에서 제거했으므로,
            # 여기서는 굳이 _accept_as_job으로 다시 떨어뜨리지 않는다.
            pass

        parsed = {}
        if parse_job_details_with_llm:
            try:
                parsed = parse_job_details_with_llm(
                    full_text,
                    url=url,
                    company_name=self.company.name,
                ) or {}
            except Exception as e:
                logger.warning(
                    "job_collector: LLM parser failed for %s (%s)",
                    url,
                    e,
                )
                parsed = {}

        deadline_at = parsed.get("deadline_at")
        posted_at = parsed.get("posted_at")
        job_desc = parsed.get("job_description") or ""
        qualifications = parsed.get("qualifications") or ""
        preferred = parsed.get("preferred_qualifications") or ""
        process = parsed.get("hiring_process") or ""
        benefits = parsed.get("benefits") or ""
        employment_type = parsed.get("employment_type") or ""
        salary = parsed.get("salary") or ""
        location = parsed.get("location") or ""

        # section extraction (more robust than a single label)
        if not job_desc:
            sections = self.extract_all_sections(full_text)
            job_desc = (sections.get("job_description") or "").strip()
            if not qualifications:
                qualifications = (sections.get("qualifications") or "").strip()
            if not preferred:
                preferred = (sections.get("preferred_qualifications") or "").strip()

        if not job_desc:
            main = self.extract_labeled_block(
                full_text,
                ["주요 업무", "담당 업무", "Main Duties", "What you will do"],
            )
            if main and len(main) >= 50:
                job_desc = main[:20000]
            else:
                # If extraction failed, only accept a minimal fallback when the page strongly looks like a job posting.
                trimmed = self._trim_boilerplate(full_text)
                if self._accept_as_job(trimmed) and len(trimmed) >= 300:
                    job_desc = trimmed[:5000]
                else:
                    return None

        # Final quality gate: avoid saving pure nav/sitemap text.
        # For extracted content, be more lenient since we already have parsed fields.
        job_desc_clean = re.sub(r"\s+", " ", job_desc).strip() if job_desc else ""
        has_meaningful_content = len(job_desc_clean) >= 50
        
        # Additional check: avoid pure navigation/sitemap text
        if has_meaningful_content:
            bad_patterns = ["전체메뉴", "gnb", "사이트맵", "all rights reserved"]
            if any(bad in job_desc_clean.lower() for bad in bad_patterns):
                has_meaningful_content = False
        
        if not job_desc or not has_meaningful_content:
            logger.info("job_collector: quality gate failed url=%s job_desc_len=%s", 
                       url, len(job_desc) if job_desc else 0)
            return None

        if not qualifications:
            qualifications = self.extract_labeled_block(
                full_text,
                ["자격 요건", "자격요건", "필수 요건", "Requirements"],
            )[:2000]

        if not preferred:
            preferred = self.extract_labeled_block(
                full_text,
                ["우대 사항", "우대사항", "우대 조건", "Preferred"],
            )[:2000]

        if not process:
            process = self.extract_labeled_block(
                full_text,
                ["전형 절차", "채용 절차", "전형절차", "Process"],
            )[:2000]

        if not benefits:
            benefits = self.extract_benefits(full_text)

        if not employment_type:
            employment_type = self.extract_employment_type(full_text)

        if not salary:
            salary = self.extract_salary(full_text)

        if not location:
            location = self.extract_location(full_text)

        deadline_at = self.coerce_date(deadline_at)
        posted_at = self.coerce_date(posted_at)
        if not deadline_at and not posted_at:
            deadline_at, posted_at = self.extract_posting_dates_for_text(job_desc or full_text, fallback_text=full_text)
        original_deadline_at = deadline_at
        original_posted_at = posted_at
        if not deadline_at and listing_deadline_at:
            deadline_at = self.coerce_date(listing_deadline_at)
        if not posted_at and listing_posted_at:
            posted_at = self.coerce_date(listing_posted_at)
        if (not original_deadline_at and deadline_at) or (not original_posted_at and posted_at):
            logger.info(
                "job_collector: applied listing-date fallback company_id=%s url=%s deadline_at=%s posted_at=%s",
                self.company_id,
                url,
                deadline_at,
                posted_at,
            )

        is_valid, invalid_reason = self.evaluate_posting_validity(deadline_at, posted_at)
        if not is_valid:
            self.deactivate_existing_posting(url, invalid_reason)
            logger.info(
                "job_collector: skip invalid/stale detail posting company_id=%s url=%s reason=%s deadline_at=%s posted_at=%s",
                self.company_id,
                url,
                invalid_reason,
                deadline_at,
                posted_at,
            )
            return None
        return {
            "post_url": url,
            "title": title,
            "job_description": job_desc,
            "qualifications": qualifications,
            "preferred_qualifications": preferred,
            "hiring_process": process,
            "benefits": benefits,
            "employment_type": employment_type,
            "salary": salary,
            "location": location,
            "deadline_at": deadline_at,
            "posted_at": posted_at,
        }

    def coerce_date(self, value):
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            for fmt in ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None

    def extract_posting_dates_for_text(self, text: str, fallback_text: str = ""):
        if extract_posting_dates:
            try:
                deadline_at, posted_at = extract_posting_dates(text or "")
                deadline_at = self.coerce_date(deadline_at)
                posted_at = self.coerce_date(posted_at)
                if deadline_at or posted_at:
                    return deadline_at, posted_at
            except Exception as e:
                logger.debug("job_collector: extract_posting_dates failed for primary text (%s)", e)

            if fallback_text and fallback_text != text:
                try:
                    deadline_at, posted_at = extract_posting_dates(fallback_text)
                    return self.coerce_date(deadline_at), self.coerce_date(posted_at)
                except Exception as e:
                    logger.debug("job_collector: extract_posting_dates failed for fallback text (%s)", e)

        return None, None

    def extract_listing_dates_for_anchor(self, anchor):
        contexts = []

        anchor_text = " ".join(anchor.css("::text").getall()).strip()
        if anchor_text:
            contexts.append(anchor_text)

        parent_text = " ".join(anchor.xpath("parent::*//text()").getall()).strip()
        if parent_text:
            contexts.append(parent_text)

        container_xpaths = [
            "ancestor::*[self::li or self::tr or self::article][1]//text()",
            "ancestor::*[self::div][1]//text()",
        ]
        for xpath_expr in container_xpaths:
            text = " ".join(anchor.xpath(xpath_expr).getall()).strip()
            if text:
                contexts.append(text)

        seen = set()
        for text in contexts:
            normalized = re.sub(r"\s+", " ", text).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deadline_at, posted_at = self.extract_posting_dates_for_text(normalized)
            if deadline_at or posted_at:
                return deadline_at, posted_at

        return None, None

    def evaluate_posting_validity(self, deadline_at, posted_at):
        today = timezone.now().date()
        one_month_ago = today - timedelta(days=30)

        if deadline_at:
            if deadline_at >= today:
                return True, "deadline_future"
            return False, "deadline_expired"

        if posted_at:
            if posted_at >= one_month_ago:
                return True, "posted_recent"
            return False, "posted_too_old"

        return False, "missing_dates"

    def deactivate_existing_posting(self, post_url: str, reason: str):
        if not post_url:
            return
        updated = JobPosting.objects.filter(post_url=post_url).exclude(status="expired", is_active=False).update(
            status="expired",
            is_active=False,
        )
        if updated:
            logger.info(
                "job_collector: marked existing posting expired company_id=%s url=%s reason=%s",
                self.company_id,
                post_url,
                reason,
            )

    # ============== classifier 래퍼 ==============

    def _accept_as_job(self, text: str) -> bool:
        """
        이 텍스트를 '채용공고'로 볼지 결정.

        - is_job_posting(text)가 True면 바로 True
        - False라고 해서 버리지 않고, 항상 로컬 룰로 다시 본다
        """
        if not text:
            return False

        snippet = text[:3000]

        if is_job_posting:
            try:
                if is_job_posting(snippet):
                    return True
            except Exception as e:
                logger.warning(
                    "job_collector: is_job_posting failed, fallback to rules (%s)",
                    e,
                )

        lowered = snippet.lower()
        hits = 0
        for kw in ["채용", "모집", "지원", "입사지원", "jobs", "recruit", "position", "경력", "신입"]:
            if kw in lowered:
                hits += 1

        # Stricter check - require more keywords OR section headings
        
        # Add negative filters
        neg_patterns = ["개인정보처리방침", "이용약관", "쿠키", "사이트맵", "IR", "보도자료", "블로그", "인재상", "비전", "복리후생", "복지제도"]
        neg_count = sum(1 for p in neg_patterns if p in lowered)
        if neg_count >= 3:
            return False
        
        # Check for section headings
        section_headings = ["주요 업무", "자격 요건", "우대 사항", "전형 절차", "복리후생", "근무지", "채용공고", "모집요강"]
        section_count = sum(1 for s in section_headings if s in lowered)
        
        return hits >= 3 or (hits >= 2 and section_count >= 1)

    def extract_section_improved(self, text: str, section_name: str) -> str:
        """
        Improved section extraction with better boundary detection.
        Handles various Korean/English label formats and stops at next section.
        """
        if not text or not section_name:
            return ""
        
        # Normalize text
        text = re.sub(r'\s+', ' ', text)
        
        # Build patterns for section names (Korean + English)
        patterns = [
            # Direct pattern: label followed by content
            rf"({re.escape(section_name)}[\s:：\-–—~\|]*)\s*(.{{50,3000}})",
            # With next section boundary
            rf"({re.escape(section_name)}[\s:：\-–—~\|]*)\s*(.{{50,3000}}?)(?=주요.?업무|자격.?요건|우대.?사항|전형.?절차|복리.?후생|근무.?조건|Employment|Salary|Location|$)",
        ]
        
        for pattern in patterns:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                if m and len(m.group(2).strip()) >= 30:
                    result = m.group(2).strip()
                    # Clean up common prefixes
                    result = re.sub(r'^[\-\*\•\→\▶\s]+', '', result)
                    return result[:5000]
            except Exception:
                continue
        
        return ""

    # ===== Multi-Section Extractor =====
    def extract_all_sections(self, text: str) -> dict:
        """
        Extract all job posting sections at once for better accuracy.
        Returns dict with section_name -> content mapping.
        """
        if not text:
            return {}
        
        # Normalize
        text = re.sub(r'\s+', ' ', text)
        
        result = {}
        
        # Define section patterns with labels and next section boundaries
        section_defs = {
            'job_description': {
                'labels': ["주요 업무", "담당 업무", "담당 역할", "Main Duties", "What you will do", "Responsibilities"],
                'next': ["자격 요건", "우대 사항", "전형 절차", "복리후생", "근무조건", " Qualifications", "Benefits"]
            },
            'qualifications': {
                'labels': ["자격 요건", "자격요건", "필수 요건", "Requirements", "Qualifications", "Must have"],
                'next': ["우대 사항", "전형 절차", "복리후생", "채용공고", " Preferred", "Benefits"]
            },
            'preferred_qualifications': {
                'labels': ["우대 사항", "우대사항", "우대 조건", "Preferred", "Nice to have", "우대"],
                'next': ["전형 절차", "복리후생", "채용공고", " Benefits", " Process"]
            },
        }
        
        for section_key, section_def in section_defs.items():
            for label in section_def['labels']:
                # Try to find this section
                pattern = rf"({re.escape(label)}[\s:：\-–—~\|]*)\s*(.{{20,4000}})"
                
                # Add next section boundary if available
                next_sections = section_def.get('next', [])
                if next_sections:
                    next_pattern = "|".join(re.escape(s) for s in next_sections)
                    pattern = rf"({re.escape(label)}[\s:：\-–—~\|]*)\s*(.{{20,4000}}?)(?= {next_pattern}|$)"
                
                try:
                    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                    if m:
                        content = m.group(2).strip()
                        if len(content) >= 20:
                            # Clean up
                            content = re.sub(r'^[\-\*\•\→\▶\s]+', '', content)
                            result[section_key] = content[:5000]
                            break
                except Exception:
                    continue
        
        return result

#ZN|
#SR|    def extract_labeled_block(self, text: str, labels) -> str:

    def extract_labeled_block(self, text: str, labels) -> str:
        for label in labels:
            pattern = (
                rf"{label}\s*[:\-]?\s*(.+?)"
                r"(?=(주요 업무|담당 업무|자격 요건|자격요건|우대 사항|우대사항|"
                r"전형 절차|채용 절차|복리후생|혜택|근무 조건|Requirements|Preferred|Process|$))"
            )
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def extract_benefits(self, text: str) -> str:
        found = [b for b in BENEFIT_KEYWORDS if b in text]
        return ", ".join(sorted(set(found)))

    def extract_location(self, text: str) -> str:
        for kw in [
            "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
            "충북", "충남", "전북", "전남", "경북", "경남", "강원", "제주",
        ]:
            if kw in text:
                return kw
        return ""

    def extract_employment_type(self, text: str) -> str:
        if "정규직" in text:
            return "정규직"
        if "계약직" in text:
            return "계약직"
        if "인턴" in text:
            return "인턴"
        if "파트타임" in text:
            return "파트타임"
        return ""

    def extract_salary(self, text: str) -> str:
        m = re.search(r"(연봉|급여)[^\d]*(\d[\d,\.]+ ?만원|\d[\d,\.]+ ?억|협의)", text)
        if m:
            return m.group(0).strip()
        if "연봉 협의" in text or "급여 협의" in text:
            return "협의"
        return ""

    # ============== DB upsert ==============

    def upsert_jobposting(self, data: dict):
        post_url = data.get("post_url")
        if not post_url:
            return

        defaults = {
            "company": self.company,
            "title": (data.get("title") or "")[:255],
            "status": "active",
            "is_active": True,
        }

        field_limits = {
            "job_description": 20000,
            "qualifications": 10000,
            "preferred_qualifications": 10000,
            "hiring_process": 5000,
            "benefits": 5000,
            "hiring_message": 5000,
            "location": 255,
            "employment_type": 50,
            "salary": 255,
            "work_hours": 100,
        }

        for field, max_len in field_limits.items():
            if hasattr(JobPosting, field) and data.get(field):
                defaults[field] = str(data[field])[:max_len]

        date_fields = ["deadline_at", "posted_at"]
        for field in date_fields:
            val = data.get(field)
            if val:
                try:
                    if isinstance(val, str):
                        from datetime import datetime
                        defaults[field] = datetime.strptime(val, "%Y-%m-%d").date()
                    elif hasattr(val, 'date'):
                        defaults[field] = val.date()
                    else:
                        defaults[field] = val
                except (ValueError, TypeError) as e:
                    logger.debug("Could not parse date %s=%s: %s", field, val, e)

        obj, created = JobPosting.objects.get_or_create(
            post_url=post_url,
            defaults=defaults,
        )

        logger.info(
            "job_collector: upsert attempt company_id=%s url=%s created=%s",
            self.company_id,
            post_url,
            created,
        )

        if created:
            self.saved_post_urls.add(post_url)
            logger.info(
                "job_collector: created JobPosting company_id=%s id=%s url=%s",
                self.company_id,
                obj.id,
                post_url,
            )
            return

        changed = False

        new_title = (data.get("title") or "").strip()
        if new_title and obj.title != new_title[:255]:
            obj.title = new_title[:255]
            changed = True

        for field, max_len in field_limits.items():
            if not hasattr(obj, field):
                continue
            new_val = (data.get(field) or "").strip()
            if new_val and getattr(obj, field) != new_val[:max_len]:
                setattr(obj, field, new_val[:max_len])
                changed = True

        for field in date_fields:
            val = data.get(field)
            if val:
                try:
                    if isinstance(val, str):
                        from datetime import datetime
                        new_date = datetime.strptime(val, "%Y-%m-%d").date()
                    elif hasattr(val, 'date'):
                        new_date = val.date()
                    else:
                        new_date = val

                    current = getattr(obj, field, None)
                    if current != new_date:
                        setattr(obj, field, new_date)
                        changed = True
                        logger.info("job_collector: updating date field %s from %s to %s", field, current, new_date)
                except (ValueError, TypeError) as e:
                    logger.debug("Date parse error for %s: %s", field, e)

        if obj.status != "active":
            obj.status = "active"
            changed = True

        if not obj.is_active:
            obj.is_active = True
            changed = True

        if changed:
            obj.save()
            logger.info(
                "job_collector: updated JobPosting id=%s url=%s",
                obj.id,
                post_url,
            )

        self.saved_post_urls.add(post_url)

    # ============== 종료 ==============

    def closed(self, reason):
        if reason == "finished":
            stale_qs = JobPosting.objects.filter(company=self.company)
            if self.saved_post_urls:
                stale_qs = stale_qs.exclude(post_url__in=self.saved_post_urls)
            expired_count = stale_qs.exclude(status="expired", is_active=False).update(
                status="expired",
                is_active=False,
            )
            logger.info(
                "job_collector: expired stale postings company_id=%s count=%s kept=%s",
                self.company_id,
                expired_count,
                len(self.saved_post_urls),
            )

        logger.info(
            "job_collector: finished company_id=%s reason=%s seen=%s",
            self.company_id,
            reason,
            len(self.seen_urls),
        )

    # ============== 도메인 비교 ==============

    def _same_org(self, base_domain: str, target_domain: str) -> bool:
        """
        도메인 기준으로 '같은 회사' 범위인지 대충 판단.
        URL 패턴 집착은 줄이되, 완전 딴 사이트는 거른다.
        """
        if not base_domain or not target_domain:
            return False

        base_domain = base_domain.split(":")[0]
        target_domain = target_domain.split(":")[0]

        if base_domain == target_domain:
            return True

        b = base_domain.split(".")
        t = target_domain.split(".")
        if len(b) >= 2 and len(t) >= 2:
            return ".".join(b[-2:]) == ".".join(t[-2:])
        return False
