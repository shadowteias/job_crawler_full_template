import logging
import time
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ko,en;q=0.8",
}

# 검색엔진/포털/채용/기업정보 사이트는 제외 (회사 공식 홈페이지 아님)
BLOCK_DOMAINS = {
    # 검색
    "duckduckgo.com", "www.duckduckgo.com",
    "google.com", "www.google.com",
    "naver.com", "www.naver.com", "search.naver.com",
    "bing.com", "www.bing.com",
    # 채용/기업정보
    "jobkorea.co.kr", "www.jobkorea.co.kr",
    "saramin.co.kr", "www.saramin.co.kr",
    "rocketpunch.com", "www.rocketpunch.com",
    "linkedin.com", "www.linkedin.com", "kr.linkedin.com",
    "thevc.kr", "www.thevc.kr",
    "nextunicorn.kr", "www.nextunicorn.kr",
    "bizno.net", "www.bizno.net",
    "nicebizinfo.com", "www.nicebizinfo.com",
    "incruit.com", "www.incruit.com",
    "jobplanet.co.kr", "www.jobplanet.co.kr",
    "weverse.io", "www.weverse.io",
}

def _normalize_url(raw: str | None) -> str | None:
    """텍스트/리다이렉트/상대 URL을 정규화해서 최종 후보 URL로 만든다."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # //domain 형태 허용
    if raw.startswith("//"):
        raw = "https:" + raw

    # 스킴 없으면 https 가정
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw

    try:
        p = urlparse(raw)
    except Exception:
        return None

    if not p.netloc:
        return None

    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    # 블록 리스트 도메인은 제외
    if host in BLOCK_DOMAINS:
        return None

    scheme = p.scheme if p.scheme in ("http", "https") else "https"
    return f"{scheme}://{p.netloc}"

def _extract_candidates_from_html(html: str) -> list[str]:
    """DuckDuckGo HTML에서 가능한 홈페이지 후보 URL들을 추출."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    # 1) 초록 url (`a.result__url`) 우선
    for a in soup.select("a.result__url"):
        txt = (a.get_text() or "").strip()
        href = a.get("href") or ""
        target = None

        # /l/?uddg= 실제 URL 형태
        if "uddg=" in href:
            try:
                qs = urlparse(href).query
                uddg = parse_qs(qs).get("uddg", [""])[0]
                target = unquote(uddg)
            except Exception:
                target = None

        if not target:
            # 텍스트가 도메인처럼 생겼으면 그것도 후보
            target = txt or href

        norm = _normalize_url(target)
        if norm:
            candidates.append(norm)

    # 2) 제목 링크 (`a.result__a`)에서도 후보 수집 (부족할 때)
    if not candidates:
        for a in soup.select("a.result__a"):
            href = a.get("href") or ""
            if not href:
                continue

            target = href
            if "uddg=" in href:
                try:
                    qs = urlparse(href).query
                    uddg = parse_qs(qs).get("uddg", [""])[0]
                    target = unquote(uddg)
                except Exception:
                    pass

            norm = _normalize_url(target)
            if norm:
                candidates.append(norm)

    return candidates

def find_homepage_for_company(company_name: str) -> str | None:
    """
    DuckDuckGo HTML 결과에서 회사 홈페이지를 추정.

    - 회사명과 도메인 매칭 안 본다 (요청대로).
    - DDG가 202를 주면, 약간 기다렸다가 몇 번 재시도 후 그래도 200이 아니면 포기.
    - 200 + HTML이 왔으면:
        - result__url / result__a 에서 추출한 후보들 중
        - 블록리스트에 안 걸리는 첫 번째 URL을 반환.
    - 절대 '무조건 찾는다'고 가정하면 안 된다.
    """
    query = f"{company_name} 공식 홈페이지"
    search_url = "https://html.duckduckgo.com/html/"

    max_attempts = 3
    delay_seconds = 3

    last_status = None
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(
                search_url,
                params={"q": query},
                headers=HEADERS,
                timeout=10,
            )
            last_status = resp.status_code
        except requests.RequestException as e:
            last_error = e
            logger.info(
                "[find_homepage] request error (%s/%s) for %s: %s",
                attempt, max_attempts, company_name, e,
            )
            time.sleep(delay_seconds)
            continue

        # 200이면 바로 파싱 시도
        if resp.status_code == 200:
            candidates = _extract_candidates_from_html(resp.text)

            if not candidates:
                logger.info(
                    "[find_homepage] no candidates in html for %s (attempt %s)",
                    company_name, attempt,
                )
                return None

            picked = candidates[0]
            logger.info(
                "[find_homepage] picked for %s: %s (attempt %s)",
                company_name, picked, attempt,
            )
            return picked

        # 202 등: 잠깐 쉬고 다시 시도
        logger.info(
            "[find_homepage] ddg status=%s for %s (attempt %s/%s)",
            resp.status_code, company_name, attempt, max_attempts,
        )
        time.sleep(delay_seconds)

    # 여기까지 오면 여러 번 시도해도 200 HTML을 못 받은 것
    if last_status is not None:
        logger.info(
            "[find_homepage] giving up for %s after %s attempts (last status=%s)",
            company_name, max_attempts, last_status,
        )
    elif last_error is not None:
        logger.info(
            "[find_homepage] giving up for %s after %s attempts (last error=%s)",
            company_name, max_attempts, last_error,
        )
    else:
        logger.info(
            "[find_homepage] giving up for %s: no response",
            company_name,
        )

    return None
