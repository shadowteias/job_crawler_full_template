import os
import logging
import re
from urllib.parse import urlparse

import django
from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider

# ===== Django 초기화 =====
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
django.setup()

from api.models import Company, JobPosting  # noqa: E402

logger = logging.getLogger(__name__)

# 이 스파이더는 text 기반 채용공고만 다룬다.
TEXT_POST_TYPE = "text"
TEXT_PAGE_TYPES = {"listing", "one_page", "main"}

# listing 페이지에서 "사람이 보기에도 채용처럼 보이는" 앵커 텍스트 키워드
JOB_ANCHOR_KEYWORDS = [
    "채용", "모집", "인턴", "구인", "경력", "신입", "구합니다",
    "recruit", "recruitment", "job", "jobs", "career", "careers",
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


# ===== LLM/BERT 훅 (옵션) =====
try:
    from api.llm_parser import parse_job_details_with_llm, is_job_posting  # type: ignore
except Exception:  # pragma: no cover
    parse_job_details_with_llm = None
    is_job_posting = None


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

    # ============== 공통: 외부 플랫폼 감지 ==============

    def _check_external_platform(self, response):
        for href in response.css("a::attr(href)").getall():
            if not href:
                continue
            url = response.urljoin(href.strip())
            lower = url.lower()
            if any(d in lower for d in EXTERNAL_JOB_DOMAINS):
                logger.warning(
                    "job_collector: external platform link detected "
                    "company_id=%s page=%s target=%s -> abort",
                    self.company_id,
                    response.url,
                    url,
                )
                raise CloseSpider("external_job_platform_detected")

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

        for url in links:
            yield Request(
                url=url,
                callback=self.parse_job_detail,
                cb_kwargs={"from_listing": True},
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

            # 외부 플랫폼 -> 정책상 크롤링 안 함
            if any(d in parsed.netloc.lower() for d in EXTERNAL_JOB_DOMAINS):
                logger.warning(
                    "job_collector: external platform link on listing "
                    "company_id=%s target=%s -> abort",
                    self.company_id,
                    full_clean,
                )
                raise CloseSpider("external_job_platform_detected")

            # 같은 조직 도메인(또는 동일 최상위 도메인)만 본다
            if not self._same_org(base_domain, parsed.netloc):
                continue

            anchor_text_raw = " ".join(a.css("::text").getall()).strip()
            if not anchor_text_raw:
                continue

            anchor_text = anchor_text_raw.lower()

            # 모집절차/FAQ/지원서 등은 제외
            if any(bad in anchor_text for bad in EXCLUDE_ANCHOR_SUBSTRINGS):
                continue

            # 채용/모집/인턴/경력/신입/구인/구합니다 등 포함되면 후보 인정
            if any(kw in anchor_text for kw in JOB_ANCHOR_KEYWORDS):
                if full_clean not in seen:
                    seen.add(full_clean)
                    candidates.append(full_clean)
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
        full_text_body = " ".join(response.css("body ::text").getall())
        full_text_body = re.sub(r"\s+", " ", full_text_body).strip()

        jobs = []

        # 헤딩이 없는 경우: 페이지 전체를 하나의 공고 후보로
        if not headings:
            if len(full_text_body) >= 80 and self._accept_as_job(full_text_body):
                jobs.append({
                    "post_url": url,
                    "title": response.css("title::text").get(default="채용 공고").strip(),
                    "job_description": full_text_body[:20000],
                    "location": self.extract_location(full_text_body),
                    "benefits": self.extract_benefits(full_text_body),
                })
        else:
            # 헤딩 기준으로 블록 분할
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

                jobs.append({
                    "post_url": f"{url}#job-{i}",
                    "title": title,
                    "job_description": desc[:20000],
                    "location": self.extract_location(desc),
                    "benefits": self.extract_benefits(desc),
                })

        logger.info(
            "job_collector: parsed %s job blocks from one_page/main",
            len(jobs),
        )

        for data in jobs:
            self.upsert_jobposting(data)

    # ============== 상세 페이지 처리 ==============

    def parse_job_detail(self, response, from_listing=False):
        self._check_external_platform(response)

        url = response.url.rstrip("/")
        if url in self.seen_urls:
            return
        self.seen_urls.add(url)

        data = self.extract_job_from_detail(response, from_listing=from_listing)
        if not data:
            return

        self.upsert_jobposting(data)

    def extract_job_from_detail(self, response, from_listing=False):
        url = response.url.rstrip("/")

        title = (
            response.css("h1::text").get()
            or response.css("h2::text").get()
            or response.css("title::text").get()
            or ""
        ).strip()
        if not title:
            return None

        full_text = " ".join(response.css("body ::text").getall())
        full_text = re.sub(r"\s+", " ", full_text).strip()
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

        job_desc = parsed.get("job_description") or ""
        qualifications = parsed.get("qualifications") or ""
        preferred = parsed.get("preferred_qualifications") or ""
        process = parsed.get("hiring_process") or ""
        benefits = parsed.get("benefits") or ""
        employment_type = parsed.get("employment_type") or ""
        salary = parsed.get("salary") or ""
        location = parsed.get("location") or ""

        if not job_desc:
            main = self.extract_labeled_block(
                full_text,
                ["주요 업무", "담당 업무", "Main Duties", "What you will do"],
            )
            job_desc = (main or full_text)[:20000]

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
        }

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

        return hits >= 2

    # ============== 텍스트 파싱 헬퍼 ==============

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

        if obj.status != "active":
            obj.status = "active"
            changed = True

        if changed:
            obj.save()
            logger.info(
                "job_collector: updated JobPosting id=%s url=%s",
                obj.id,
                post_url,
            )

    # ============== 종료 ==============

    def close(self, reason):
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
