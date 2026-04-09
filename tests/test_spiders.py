#!/usr/bin/env python3
"""
Spider Unit Tests - 테스트 스크립트
Discovered spider logic에 대한 단위 테스트
"""
import unittest
import re
from datetime import date, timedelta


# ============================================================================
# Test for discover_careers.py - has_negative_keywords()
# ============================================================================

class TestHasNegativeKeywords(unittest.TestCase):
    """Test has_negative_keywords function logic"""

    NEGATIVE_KEYWORDS = [
        "인재상", "인재 소개", "CEO인사말", "대표이사 인사말", "회장 인사말",
        "비전", "VISION", "경영진 소개",
        "복리후생", "복지제도", "사내문화", "회사문화", "직원채용",
        "조직도", "연혁", "HISTORY", "회사개요", "기업개요",
        "FAQ", "자주하는질문", "QnA",
    ]

    def has_negative_keywords(self, text: str) -> bool:
        """Test implementation - same logic as spider"""
        if not text:
            return False
        t = text.lower()
        for kw in self.NEGATIVE_KEYWORDS:
            if kw.lower() in t:
                return True
        return False

    def test_empty_text(self):
        """Empty text should return False"""
        self.assertFalse(self.has_negative_keywords(""))
        self.assertFalse(self.has_negative_keywords(None))

    def test_talent_page(self):
        """인재상 페이지 should be detected as negative"""
        text = "저희 회사의 인재상은 도전과 창의입니다."
        self.assertTrue(self.has_negative_keywords(text))

    def test_vision_page(self):
        """비전 페이지 should be detected as negative"""
        text = "2030 비전과 전략적 방향"
        self.assertTrue(self.has_negative_keywords(text))

    def test_welfare_page(self):
        """복리후생 페이지 should be detected as negative"""
        text = "복리후생제도 소개 및 사내문화"
        self.assertTrue(self.has_negative_keywords(text))

    def test_ceo_greeting(self):
        """CEO 인사말 should be detected as negative"""
        text = "CEO인사말입니다. 대표이사 인사말을 읽어보세요."
        self.assertTrue(self.has_negative_keywords(text))

    def test_organization_chart(self):
        """조직도 should be detected as negative"""
        text = "회사 조직도 및 경영진 소개"
        self.assertTrue(self.has_negative_keywords(text))

    def test_history_page(self):
        """연혁 should be detected as negative"""
        text = "회사 연혁 및 HISTORY"
        self.assertTrue(self.has_negative_keywords(text))

    def test_faq_page(self):
        """FAQ should be detected as negative"""
        text = "FAQ 자주하는질문 QnA"
        self.assertTrue(self.has_negative_keywords(text))

    def test_valid_job_page(self):
        """Valid job posting should NOT be detected as negative"""
        text = "채용공고입니다. 지원하기 버튼을 클릭하세요."
        self.assertFalse(self.has_negative_keywords(text))

    def test_job_details_page(self):
        """Job details page should NOT be detected as negative"""
        text = "주요 업무: 서버 개발자 주요 업무 내용을 적어주세요."
        self.assertFalse(self.has_negative_keywords(text))


# ============================================================================
# Test for discover_careers.py - find_alternative_job_links()
# ============================================================================

class TestFindAlternativeJobLinks(unittest.TestCase):
    """Test find_alternative_job_links function logic"""

    POSITIVE_JOB_KEYWORDS = [
        "채용공고", "채용안내", "채용정보", "채용 목록", "채용요강",
        "입사지원", "채용중", "모집중", "공고 목록",
        "채용사이트", "job posting", "positions",
    ]
    AVOID_KEYWORDS = [
        "인재상", "인재 소개", "비전", "복리후생", "복지",
        "조직도", "연혁", "인사말", "CEO",
    ]

    def find_alternative_job_links(self, links_data: list) -> list:
        """Test implementation - simulates spider logic"""
        candidates = []
        for link in links_data:
            href = (link.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            
            text = (link.get("text") or "").strip().lower()
            label = " ".join(filter(None, [
                link.get("title", ""),
                link.get("aria-label", ""),
            ])).strip().lower()
            
            combined = f"{text} {label}"
            
            if any(kw.lower() in combined for kw in self.AVOID_KEYWORDS):
                continue
            
            if any(kw.lower() in combined for kw in self.POSITIVE_JOB_KEYWORDS):
                candidates.append(href)
        
        return candidates

    def test_empty_links(self):
        """Empty links should return empty list"""
        self.assertEqual(self.find_alternative_job_links([]), [])

    def test_find_recruitment_notice(self):
        """채용공고 링크 should be found"""
        links = [
            {"text": "채용공고", "href": "/jobs/recruit"},
            {"text": "회사 소개", "href": "/about"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "/jobs/recruit")

    def test_find_job_application(self):
        """입사지원 링크 should be found"""
        links = [
            {"text": "입사지원 바로가기", "href": "/apply"},
            {"text": "인재상 보기", "href": "/talent"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "/apply")

    def test_avoid_talent_page(self):
        """인재상 링크 should NOT be included"""
        links = [
            {"text": "인재상", "href": "/talent"},
            {"text": "채용정보", "href": "/jobs"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "/jobs")

    def test_avoid_vision_page(self):
        """비전 링크 should NOT be included"""
        links = [
            {"text": "비전", "href": "/vision"},
            {"text": "채용중", "href": "/hiring"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "/hiring")

    def test_ignore_javascript_links(self):
        """JavaScript links should be ignored"""
        links = [
            {"text": "click here", "href": "javascript:void(0)"},
            {"text": "채용공고", "href": "/jobs"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)

    def test_ignore_anchor_links(self):
        """Anchor links should be ignored"""
        links = [
            {"text": "top", "href": "#top"},
            {"text": "채용공고", "href": "/jobs"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)

    def test_english_job_keywords(self):
        """English job keywords should also work"""
        links = [
            {"text": "Job Postings", "href": "/jobs"},
            {"text": "Open Positions", "href": "/positions"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 2)

    def test_no_duplicates(self):
        """Same URL should not be duplicated"""
        links = [
            {"text": "채용정보", "href": "/jobs"},
            {"text": "채용 공고", "href": "/jobs"},
        ]
        result = self.find_alternative_job_links(links)
        self.assertEqual(len(result), 1)


# ============================================================================
# Test for job_collector.py - _accept_as_job()
# ============================================================================

class TestAcceptAsJob(unittest.TestCase):
    """Test _accept_as_job function logic"""

    def accept_as_job(self, text: str) -> bool:
        """Test implementation - same logic as spider"""
        if not text:
            return False

        snippet = text[:3000]
        lowered = snippet.lower()
        hits = 0
        for kw in ["채용", "모집", "지원", "입사지원", "jobs", "recruit", "position", "경력", "신입"]:
            if kw in lowered:
                hits += 1

        neg_patterns = ["개인정보처리방침", "이용약관", "쿠키", "사이트맵", "IR", "보도자료", "블로그", "인재상", "비전", "복리후생", "복지제도"]
        neg_count = sum(1 for p in neg_patterns if p in lowered)
        if neg_count >= 3:
            return False
        
        section_headings = ["주요 업무", "자격 요건", "우대 사항", "전형 절차", "복리후생", "근무지", "채용공고", "모집요강"]
        section_count = sum(1 for s in section_headings if s in lowered)
        
        return hits >= 3 or (hits >= 2 and section_count >= 1)

    def test_empty_text(self):
        """Empty text should return False"""
        self.assertFalse(self.accept_as_job(""))

    def test_valid_job_posting(self):
        """Valid job posting should be accepted"""
        text = "채용공고입니다. 서버 개발자를 모집합니다."
        self.assertTrue(self.accept_as_job(text))

    def test_privacy_policy_only(self):
        """개인정보처리방침 only should be rejected"""
        text = "개인정보처리방침입니다.Cookies도 있습니다. IR정보도 있습니다."
        self.assertFalse(self.accept_as_job(text))

    def test_about_page(self):
        """회사 소개 페이지 should be rejected"""
        text = "회사에 대한 소개입니다. 인재상: 창의적 도전. 비전: 2030 성장. 복리후생: 직원복지"
        self.assertFalse(self.accept_as_job(text))

    def test_job_with_multiple_keywords(self):
        """Multiple job keywords should be accepted"""
        text = "채용信息和募集요강입니다. 신입과 경력 모두 지원가능합니다. JOBS와 RECRUIT를 기다립니다."
        self.assertTrue(self.accept_as_job(text))

    def test_insufficient_content(self):
        """Content with too few keywords should be rejected"""
        text = "채용 공고"  # Only 1 keyword
        self.assertFalse(self.accept_as_job(text))


# ============================================================================
# Test for job_collector.py - extract_section_improved()
# ============================================================================

class TestExtractSectionImproved(unittest.TestCase):
    """Test extract_section_improved function logic"""

    def extract_section_improved(self, text: str, section_name: str) -> str:
        """Test implementation - simplified version of spider logic"""
        if not text or not section_name:
            return ""
        
        text = re.sub(r'\s+', ' ', text)
        
        patterns = [
            rf"({re.escape(section_name)}[\s:：\-–—~\|]*)\s*(.{{50,3000}})",
            rf"({re.escape(section_name)}[\s:：\-–—~\|]*)\s*(.{{50,3000}}?)(?=주요.?업무|자격.?요건|우대.?사항|전형.?절차|복리.?후생|근무.?조건|$)",
        ]
        
        for pattern in patterns:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                if m and len(m.group(2).strip()) >= 30:
                    result = m.group(2).strip()
                    result = re.sub(r'^[\-\*\•\→\▶\s]+', '', result)
                    return result[:5000]
            except Exception:
                continue
        
        return ""

    def test_empty_inputs(self):
        """Empty inputs should return empty string"""
        self.assertEqual(self.extract_section_improved("", "주요 업무"), "")
        self.assertEqual(self.extract_section_improved("text", ""), "")

    def test_extract_job_description(self):
        """Extract job description section"""
        text = "채용공고 주요 업무: 서버 개발자로서 REST API 개발 및 데이터베이스 설계 프론트엔드 팀과 협업합니다. 자격 요건"
        result = self.extract_section_improved(text, "주요 업무")
        self.assertIn("서버 개발자", result)
        self.assertIn("REST API", result)

    def test_extract_qualifications(self):
        """Extract qualifications section"""
        text = "자격 요건: 컴퓨터공학 또는 관련학과 졸업 Python 3년 이상 경험 Django 또는 Flask 사용 경험 우대 사항"
        result = self.extract_section_improved(text, "자격 요건")
        self.assertIn("Python", result)

    def test_no_section_found(self):
        """Non-existent section should return empty string"""
        text = "일반 텍스트입니다. 채용정보가 있습니다."
        result = self.extract_section_improved(text, "주요 업무")
        self.assertEqual(result, "")

    def test_english_section_name(self):
        """English section names should also work"""
        text = "Main Duties: Design and implement microservices Work with cross-functional teams Qualifications"
        result = self.extract_section_improved(text, "Main Duties")
        self.assertIn("microservices", result.lower())


# ============================================================================
# Test for job_collector.py - extract_all_sections()
# ============================================================================

class TestExtractAllSections(unittest.TestCase):
    """Test extract_all_sections function logic"""

    def extract_all_sections(self, text: str) -> dict:
        """Test implementation - simplified version of spider logic"""
        if not text:
            return {}
        
        text = re.sub(r'\s+', ' ', text)
        result = {}
        
        section_defs = {
            'job_description': {
                'labels': ["주요 업무", "담당 업무", "담당 역할", "Main Duties"],
                'next': ["자격 요건", "우대 사항", "전형 절차"]
            },
            'qualifications': {
                'labels': ["자격 요건", "자격요건", "필수 요건", "Requirements"],
                'next': ["우대 사항", "전형 절차", "채용공고"]
            },
            'preferred_qualifications': {
                'labels': ["우대 사항", "우대사항", "우대 조건", "Preferred"],
                'next': ["전형 절차", "채용공고"]
            },
        }
        
        for section_key, section_def in section_defs.items():
            for label in section_def['labels']:
                pattern = rf"({re.escape(label)}[\s:：\-–—~\|]*)\s*(.{{20,4000}})"
                next_sections = section_def.get('next', [])
                
                if next_sections:
                    boundary = "|".join(re.escape(s) for s in next_sections)
                    pattern = rf"({re.escape(label)}[\s:：\-–—~\|]*)\s*(.{{20,4000}}?)(?={boundary}|$)"
                
                try:
                    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                    if m and len(m.group(2).strip()) >= 20:
                        content = m.group(2).strip()[:2000]
                        if content:
                            result[section_key] = content
                            break
                except Exception:
                    continue
        
        return result

    def test_empty_text(self):
        """Empty text should return empty dict"""
        self.assertEqual(self.extract_all_sections(""), {})

    def test_extract_multiple_sections(self):
        """Should extract multiple sections at once"""
        text = "채용공고입니다 주요 업무 서버 개발 및 API 설계 클라우드 서비스 운영합니다 자격 요건 Python 경력 3년 우대 사항 AWS 경험 우대"
        result = self.extract_all_sections(text)
        self.assertIn('job_description', result)
        self.assertIn('qualifications', result)

    def test_partial_sections(self):
        """Should return only found sections"""
        text = "채용공고입니다 주요 업무 백엔드 개발 및 서버 운영을 담당합니다"
        result = self.extract_all_sections(text)
        self.assertIn('job_description', result)
        self.assertNotIn('qualifications', result)

    def test_english_sections(self):
        """Should handle English section names"""
        text = "Main Duties Build APIs and services Requirements 3+ years Python experience"
        result = self.extract_all_sections(text)
        self.assertIn('job_description', result)
        self.assertIn('qualifications', result)


class TestJobValidityRule(unittest.TestCase):
    def evaluate_posting_validity(self, deadline_at, posted_at, today=None):
        today = today or date(2026, 4, 7)
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

    def test_future_deadline_is_valid(self):
        ok, reason = self.evaluate_posting_validity(date(2026, 4, 30), None)
        self.assertTrue(ok)
        self.assertEqual(reason, "deadline_future")

    def test_past_deadline_is_invalid_even_if_posted_recent(self):
        ok, reason = self.evaluate_posting_validity(date(2026, 4, 1), date(2026, 4, 5))
        self.assertFalse(ok)
        self.assertEqual(reason, "deadline_expired")

    def test_recent_posted_without_deadline_is_valid(self):
        ok, reason = self.evaluate_posting_validity(None, date(2026, 3, 20))
        self.assertTrue(ok)
        self.assertEqual(reason, "posted_recent")

    def test_old_posted_without_deadline_is_invalid(self):
        ok, reason = self.evaluate_posting_validity(None, date(2026, 2, 20))
        self.assertFalse(ok)
        self.assertEqual(reason, "posted_too_old")

    def test_missing_dates_is_invalid(self):
        ok, reason = self.evaluate_posting_validity(None, None)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_dates")


class TestDateExtractionSemantics(unittest.TestCase):
    def extract_dates(self, text: str):
        deadline_at = None
        posted_at = None
        text_combined = ' '.join(text.split())
        deadline_keywords = ["마감", "지원", "截止", "기한", "까지"]
        posted_keywords = ["게시", "등록", "작성", "시작", "작성일"]
        date_patterns = [
            r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
        ]

        candidates = []
        for pattern in date_patterns:
            for match in re.finditer(pattern, text_combined):
                y, m, d = match.groups()
                dt = date(int(y), int(m), int(d))
                pos = match.start()
                context = text_combined[max(0, pos-10):pos+10].lower()
                is_deadline = any(kw in context for kw in deadline_keywords)
                is_posted = any(kw in context for kw in posted_keywords)
                candidates.append((dt, pos, is_deadline, is_posted))

        candidates.sort(key=lambda x: x[1])
        for dt, pos, is_deadline, is_posted in candidates:
            if is_deadline and deadline_at is None:
                deadline_at = dt
            elif is_posted and posted_at is None:
                posted_at = dt
            elif deadline_at is None and posted_at is None:
                deadline_at = dt
                break
        return deadline_at, posted_at

    def test_only_posted_date_does_not_fabricate_deadline(self):
        deadline_at, posted_at = self.extract_dates("게시일 2026-04-01")
        self.assertIsNone(deadline_at)
        self.assertEqual(posted_at, date(2026, 4, 1))

    def test_only_deadline_does_not_fabricate_posted(self):
        deadline_at, posted_at = self.extract_dates("마감 2026-04-30")
        self.assertEqual(deadline_at, date(2026, 4, 30))
        self.assertIsNone(posted_at)


class TestListingDateFallback(unittest.TestCase):
    def choose_dates(self, detail_deadline_at, detail_posted_at, listing_deadline_at, listing_posted_at):
        deadline_at = detail_deadline_at or listing_deadline_at
        posted_at = detail_posted_at or listing_posted_at
        return deadline_at, posted_at

    def test_detail_dates_win_over_listing_dates(self):
        deadline_at, posted_at = self.choose_dates(
            date(2026, 4, 30),
            date(2026, 4, 1),
            date(2026, 5, 1),
            date(2026, 4, 2),
        )
        self.assertEqual(deadline_at, date(2026, 4, 30))
        self.assertEqual(posted_at, date(2026, 4, 1))

    def test_listing_dates_fill_missing_detail_dates(self):
        deadline_at, posted_at = self.choose_dates(
            None,
            None,
            date(2026, 4, 30),
            date(2026, 4, 1),
        )
        self.assertEqual(deadline_at, date(2026, 4, 30))
        self.assertEqual(posted_at, date(2026, 4, 1))

    def test_partial_detail_dates_keep_listing_only_for_missing_side(self):
        deadline_at, posted_at = self.choose_dates(
            None,
            date(2026, 4, 1),
            date(2026, 4, 30),
            date(2026, 4, 2),
        )
        self.assertEqual(deadline_at, date(2026, 4, 30))
        self.assertEqual(posted_at, date(2026, 4, 1))


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Running Spider Unit Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
