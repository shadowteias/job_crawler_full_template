# api/company_sources.py
import csv
import io
import json
import os
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from api.models import Company


# =========================
# Common helpers
# =========================

REGION_PREFIXES = [
    "서울", "서울특별시",
    "경기", "경기도",
    "대전", "대전광역시",
    "충남", "충청남도",
    "충북", "충청북도",
    "인천", "인천광역시",
    "부산", "부산광역시",
    "대구", "대구광역시",
    "광주", "광주광역시",
    "울산", "울산광역시",
    "세종", "세종특별자치시",
    "강원", "강원특별자치도",
    "전남", "전라남도",
    "전북", "전북특별자치도",
    "경남", "경상남도",
    "경북", "경상북도",
    "제주", "제주특별자치도",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_TOKEN_RE = re.compile(r"(https?://[^\s]+|www\.[^\s]+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s]*)")

# 괄호/주석/수정중 같은 꼬리표 제거
TRAILING_JUNK_RE = re.compile(r"(\(.*?\)|\[.*?\]|{.*?}|수정중|수정\s*중|준비중|준비\s*중)", re.IGNORECASE)


def normalize_company_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("\u3000", " ")
    s = s.lower()
    # (주), 주식회사, ㈜ 등 정규화 (너무 공격적이지 않게)
    s = s.replace("주식회사", "")
    s = s.replace("(주)", "")
    s = s.replace("㈜", "")
    s = s.replace("유한회사", "")
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_region(address: Optional[str]) -> Optional[str]:
    if not address:
        return None
    a = address.strip()
    for p in REGION_PREFIXES:
        if a.startswith(p):
            # 표준형을 최대한 유지
            if p in ("서울",):
                return "서울특별시"
            if p in ("경기",):
                return "경기도"
            if p in ("대전",):
                return "대전광역시"
            if p in ("충남",):
                return "충청남도"
            if p in ("충북",):
                return "충청북도"
            return p
    # 두 글자 시도/도만 있는 케이스 대응
    head = a.split()[0]
    if head in ("서울", "경기", "대전", "충남", "충북"):
        return extract_region(head)
    return None


def _url_host(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        u = url.strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            u = "https://" + u
        p = urlparse(u)
        host = (p.netloc or "").lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def _canonicalize_url(url: str) -> Optional[str]:
    """
    - scheme 강제(기본 https)
    - netloc 없으면 https:// 붙임
    - 경로/쿼리/프래그먼트는 보존하되, 마지막에 공백/주석 제거
    """
    if not url:
        return None
    u = url.strip()
    u = TRAILING_JUNK_RE.sub("", u).strip()
    u = u.strip(" ,;|")

    # 이메일이면 버림
    if EMAIL_RE.fullmatch(u):
        return None

    # "http://"만 있는 경우 같은 쓰레기 값 제거
    if u.lower() in ("http://", "https://"):
        return None

    if not (u.startswith("http://") or u.startswith("https://")):
        u = "https://" + u

    try:
        p = urlparse(u)
        if not p.netloc:
            return None
        scheme = p.scheme or "https"
        netloc = p.netloc
        # netloc 내부 공백 제거(예: "www.sunwooit.co.kr     (수정중)")
        netloc = netloc.strip()
        # www 정규화는 host 필드에서만, url은 그대로 둬도 됨 (원하면 여기도 제거 가능)
        # 도메인 최소 검증
        host = _url_host(netloc)
        if not host or "." not in host:
            return None

        return urlunparse((scheme, netloc, p.path or "", p.params or "", p.query or "", ""))
    except Exception:
        return None


def clean_homepage(raw: Optional[str]) -> Optional[str]:
    """
    SWDB의 '홈페이지' 컬럼이 매우 지저분한 케이스를 최대한 살리는 정제기.
    - 복수 URL: 가장 그럴듯한 1개 선택
    - www.* / 스킴 없음: 살림
    - 이메일/잡문: 제거
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None

    s = TRAILING_JUNK_RE.sub("", s).strip()
    # 'http://'만 있거나 공백만 있는 경우
    if s.lower() in ("http://", "https://"):
        return None

    # 토큰 후보 추출
    candidates: List[str] = []
    for m in URL_TOKEN_RE.finditer(s):
        token = m.group(0).strip().strip(" ,;|")
        if not token:
            continue
        # 괄호/주석 꼬리 제거
        token = TRAILING_JUNK_RE.sub("", token).strip().strip(" ,;|")
        if not token:
            continue
        # 이메일 제거
        if EMAIL_RE.search(token):
            continue
        candidates.append(token)

    # 토큰이 없으면 전체를 한번 시도
    if not candidates:
        u = _canonicalize_url(s)
        return u

    # 우선순위: https:// > http:// > www. > 도메인
    def score(tok: str) -> int:
        t = tok.lower()
        sc = 0
        if t.startswith("https://"):
            sc += 30
        if t.startswith("http://"):
            sc += 20
        if t.startswith("www."):
            sc += 10
        if "." in t:
            sc += 5
        # 너무 긴 쓰레기(경로/쿼리 과다)는 감점
        if len(t) > 120:
            sc -= 5
        return sc

    candidates = sorted(set(candidates), key=score, reverse=True)

    for tok in candidates:
        u = _canonicalize_url(tok)
        if u:
            return u
    return None


# =========================
# Simple file lock (avoid overlapping runs)
# =========================

class FileLock:
    def __init__(self, path: str):
        self.path = path
        self.fd = None

    def __enter__(self):
        # 매우 단순: lock 파일 생성 시도
        # 이미 있으면 대기(최대 10분)
        start = time.time()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if time.time() - start > 600:
                    raise RuntimeError(f"Lock wait timeout: {self.path}")
                time.sleep(0.5)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass


# =========================
# Upsert logic
# =========================

@dataclass
class UpsertResult:
    created: bool
    updated: bool
    skipped: bool
    company_id: Optional[int] = None


def upsert_company(
    *,
    name: str,
    homepage_url: Optional[str] = None,
    address: Optional[str] = None,
    region: Optional[str] = None,
    ceo_name: Optional[str] = None,
    bizr_no: Optional[str] = None,
    stock_code: Optional[str] = None,
    dart_corp_code: Optional[str] = None,
    dart_modify_date: Optional[str] = None,
    swdb_fin_year: Optional[int] = None,
    est_dt: Optional[str] = None,
    acc_mt: Optional[str] = None,
    source: str,
    source_meta: Optional[Dict[str, Any]] = None,
    match_by_name_norm: bool = True,
) -> UpsertResult:
    """
    매칭 우선순위:
    1) dart_corp_code
    2) homepage_host (또는 homepage_url contains host)
    3) name_norm (옵션)
    """
    name = (name or "").strip()
    if not name:
        return UpsertResult(created=False, updated=False, skipped=True)

    homepage_clean = clean_homepage(homepage_url) if homepage_url else None
    host = _url_host(homepage_clean) if homepage_clean else None
    name_norm = normalize_company_name(name)

    region = region or extract_region(address)

    qs = Company.objects.all()

    obj: Optional[Company] = None

    if dart_corp_code:
        obj = qs.filter(dart_corp_code=dart_corp_code).first()

    if obj is None and host:
        # homepage_host 컬럼이 있으면 그게 1순위
        obj = qs.filter(homepage_host=host).first()
        if obj is None:
            # 기존 데이터(예: OSM 수집)가 homepage_host를 안 채웠을 수 있으니 fallback
            obj = qs.filter(homepage_url__icontains=host).first()

    if obj is None and match_by_name_norm and name_norm:
        obj = qs.filter(name_norm=name_norm).first()

    created = False
    updated = False

    if obj is None:
        # name unique 이므로, 같은 이름이면 suffix
        final_name = name
        if Company.objects.filter(name=final_name).exists():
            i = 2
            while True:
                cand = f"{name} ({i})"
                if not Company.objects.filter(name=cand).exists():
                    final_name = cand
                    break
                i += 1

        obj = Company(
            name=final_name,
            name_norm=normalize_company_name(final_name),
            source_meta={},
        )
        created = True

    # 업데이트 규칙: 빈 칸이면 채우고, source_meta는 누적
    def set_if_blank(field: str, value: Any):
        nonlocal updated
        if value is None or value == "":
            return
        cur = getattr(obj, field, None)
        if cur is None or cur == "" or (isinstance(cur, dict) and cur == {}):
            setattr(obj, field, value)
            updated = True

    # 항상 갱신하고 싶으면 별도 set_always 만들 것
    set_if_blank("homepage_url", homepage_clean)
    if host:
        set_if_blank("homepage_host", host)

    set_if_blank("address", address)
    set_if_blank("region", region)

    set_if_blank("ceo_name", ceo_name)
    set_if_blank("bizr_no", bizr_no)

    set_if_blank("stock_code", stock_code)
    set_if_blank("dart_corp_code", dart_corp_code)
    set_if_blank("dart_modify_date", dart_modify_date)

    set_if_blank("swdb_fin_year", swdb_fin_year)
    set_if_blank("est_dt", est_dt)
    set_if_blank("acc_mt", acc_mt)

    # source_meta merge
    meta = obj.source_meta or {}
    meta.setdefault("sources", {})
    meta["sources"].setdefault(source, {})
    # 마지막 수집 시각
    meta["sources"][source]["last_seen_at"] = timezone.now().isoformat()
    if source_meta:
        # shallow merge
        for k, v in source_meta.items():
            meta["sources"][source][k] = v
    obj.source_meta = meta

    if created or updated:
        obj.save()

    return UpsertResult(created=created, updated=updated, skipped=(not created and not updated), company_id=obj.id)


# =========================
# SWDB (CSV seed) ingestion
# =========================

DEFAULT_SWDB_CSV_PATH = "/app/data/swdb_seed.csv"


def iter_swdb_csv(csv_path: str) -> Iterable[Dict[str, Any]]:
    # SWDB 파일은 보통 UTF-8-SIG
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


@shared_task(name="api.tasks.collect_swdb_companies")
def collect_swdb_companies(
    *,
    csv_path: Optional[str] = None,
    regions: Optional[List[str]] = None,
    limit: Optional[int] = None,
    only_with_homepage: bool = True,
) -> Dict[str, Any]:
    """
    SWDB CSV 기반 회사 수집.
    - csv_path 기본: /app/data/swdb_seed.csv
    - regions:
        - None 또는 [] => 지역 필터 없음
        - 값 있으면 extract_region(address)로 필터
    - only_with_homepage:
        - True면 clean_homepage 통과한 것만 저장
    """
    csv_path = csv_path or os.getenv("SWDB_CSV_PATH") or DEFAULT_SWDB_CSV_PATH
    regions = regions or []

    created = 0
    updated = 0
    skipped = 0
    processed = 0
    sample_bad_homepage: List[Tuple[str, str]] = []

    lock_path = "/app/.swdb_collect.lock"
    with FileLock(lock_path):
        for row in iter_swdb_csv(csv_path):
            processed += 1
            if limit and processed > limit:
                break

            name = (row.get("회사명") or "").strip()
            ceo = (row.get("대표이사") or "").strip() or None
            raw_home = (row.get("홈페이지") or "").strip()
            address = (row.get("본사주소") or "").strip() or None
            fin_year_raw = (row.get("재무현황연도") or "").strip()

            home = clean_homepage(raw_home) if raw_home else None
            if only_with_homepage and not home:
                if raw_home and len(sample_bad_homepage) < 20:
                    sample_bad_homepage.append((name, raw_home))
                skipped += 1
                continue

            reg = extract_region(address) if address else None
            if regions and reg and reg not in regions:
                skipped += 1
                continue

            fin_year = None
            if fin_year_raw.isdigit():
                fin_year = int(fin_year_raw)

            r = upsert_company(
                name=name,
                homepage_url=home,
                address=address,
                region=reg,
                ceo_name=ceo,
                swdb_fin_year=fin_year,
                source="swdb_csv",
                source_meta={
                    "raw_homepage": raw_home,
                    "fin_year_raw": fin_year_raw,
                },
                match_by_name_norm=True,
            )
            if r.created:
                created += 1
            elif r.updated:
                updated += 1
            else:
                skipped += 1

    return {
        "source": "swdb_csv",
        "csv_path": csv_path,
        "regions": regions,
        "processed": processed,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "sample_bad_homepage": sample_bad_homepage,
    }


# =========================
# DART ingestion (listed-only discovery)
# =========================

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"


def fetch_dart_corp_list(api_key: str) -> List[Dict[str, str]]:
    """
    corpCode.xml(zip) 내려받아 list[] 생성
    """
    resp = requests.get(DART_CORPCODE_URL, params={"crtfc_key": api_key}, timeout=60)
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_bytes = zf.read("CORPCODE.xml")

    # 아주 단순 파서 (정확도 충분)
    text = xml_bytes.decode("utf-8", errors="ignore")
    # <list> ... </list> 블록 분리
    blocks = re.findall(r"<list>(.*?)</list>", text, flags=re.DOTALL)

    out: List[Dict[str, str]] = []
    for b in blocks:
        def get(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", b)
            return (m.group(1).strip() if m else "")

        corp_code = get("corp_code")
        corp_name = get("corp_name")
        stock_code = get("stock_code")
        modify_date = get("modify_date")

        if corp_code and corp_name:
            out.append({
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "modify_date": modify_date,
            })
    return out


def fetch_dart_company_profile(api_key: str, corp_code: str) -> Dict[str, Any]:
    resp = requests.get(DART_COMPANY_URL, params={"crtfc_key": api_key, "corp_code": corp_code}, timeout=30)
    resp.raise_for_status()
    return resp.json()


@shared_task(name="api.tasks.collect_dart_companies")
def collect_dart_companies(
    *,
    mode: str = "discover_listed",
    since_days: int = 14,
    limit: Optional[int] = None,
    only_with_homepage: bool = False,
    regions: Optional[List[str]] = None,
    request_sleep: float = 0.15,
) -> Dict[str, Any]:
    """
    DART 기반 회사 수집/보강.

    mode:
      - "discover_listed": 상장사(stock_code 존재) 중 modify_date가 최근(since_days)인 항목만 신규/보강
    regions:
      - None 또는 [] => 지역 필터 없음(요구사항)
      - 값 있으면 address에서 추출한 region으로 필터
    """
    api_key = os.getenv("OPENDART_API_KEY") or ""
    if not api_key:
        raise RuntimeError("OPENDART_API_KEY is missing")

    regions = regions or []
    cutoff = (datetime.utcnow().date() - timedelta(days=since_days)).strftime("%Y%m%d")

    created = 0
    updated = 0
    skipped = 0
    processed = 0

    lock_path = "/app/.dart_collect.lock"
    with FileLock(lock_path):
        corp_list = fetch_dart_corp_list(api_key)

        # 후보 추리기
        candidates: List[Dict[str, str]] = []
        for c in corp_list:
            if mode == "discover_listed":
                if not c.get("stock_code"):
                    continue
                if c.get("modify_date") and c["modify_date"] < cutoff:
                    continue
                candidates.append(c)
            else:
                raise ValueError(f"Unsupported mode: {mode}")

        if limit:
            candidates = candidates[:limit]

        for c in candidates:
            processed += 1
            corp_code = c["corp_code"]
            corp_name = c["corp_name"]
            stock_code = c.get("stock_code") or None
            modify_date = c.get("modify_date") or None

            prof: Dict[str, Any] = {}
            try:
                prof = fetch_dart_company_profile(api_key, corp_code=corp_code)
            except Exception:
                # company.json이 종종 실패할 수 있음 (일단 corp list 기반으로 최소 생성 가능)
                prof = {}

            # DART profile 주요 필드
            home_raw = (prof.get("hm_url") or "").strip() or None
            home = clean_homepage(home_raw) if home_raw else None
            address = (prof.get("adres") or "").strip() or None
            ceo = (prof.get("ceo_nm") or "").strip() or None
            bizr_no = (prof.get("bizr_no") or "").strip() or None
            est_dt = (prof.get("est_dt") or "").strip() or None
            acc_mt = (prof.get("acc_mt") or "").strip() or None

            if only_with_homepage and not home:
                skipped += 1
                continue

            reg = extract_region(address) if address else None
            if regions and reg and reg not in regions:
                skipped += 1
                continue

            # DART는 “상장사 신규 생성”이 목적이므로, name_norm 매칭은 꺼서 오결합을 줄임
            r = upsert_company(
                name=corp_name,
                homepage_url=home,
                address=address,
                region=reg,
                ceo_name=ceo,
                bizr_no=bizr_no,
                stock_code=stock_code,
                dart_corp_code=corp_code,
                dart_modify_date=modify_date,
                est_dt=est_dt,
                acc_mt=acc_mt,
                source="dart",
                source_meta={
                    "hm_url_raw": home_raw,
                    "corp_code": corp_code,
                    "stock_code": stock_code,
                    "modify_date": modify_date,
                },
                match_by_name_norm=False,
            )

            if r.created:
                created += 1
            elif r.updated:
                updated += 1
            else:
                skipped += 1

            time.sleep(request_sleep)

    return {
        "source": "dart",
        "mode": mode,
        "since_days": since_days,
        "regions": regions,
        "processed": processed,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


# =========================
# Homepage liveness check
# =========================

def _probe_url(session: requests.Session, url: str, timeout: float = 10.0) -> Tuple[str, Optional[int]]:
    """
    반환:
      - status: "alive" | "dead"
      - http_code
    정책:
      - 200~399: alive
      - 401/403: alive (서버는 존재)
      - 404/410: dead
      - 기타/예외: dead (단, fail_count 정책으로 확정)
    """
    # 1) HEAD 먼저
    try:
        r = session.head(url, allow_redirects=True, timeout=timeout)
        code = r.status_code
        if 200 <= code < 400:
            return "alive", code
        if code in (401, 403):
            return "alive", code
        if code in (404, 410):
            return "dead", code
    except Exception:
        pass

    # 2) GET fallback (stream)
    try:
        r = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
        code = r.status_code
        if 200 <= code < 400:
            return "alive", code
        if code in (401, 403):
            return "alive", code
        if code in (404, 410):
            return "dead", code
        return "dead", code
    except Exception:
        return "dead", None


def _apply_company_id_range(qs, company_id_start: Optional[int] = None, company_id_end: Optional[int] = None):
    if company_id_start is not None:
        qs = qs.filter(id__gte=int(company_id_start))
    if company_id_end is not None:
        qs = qs.filter(id__lte=int(company_id_end))
    return qs


@shared_task(name="api.tasks.check_company_homepages")
def check_company_homepages(
    *,
    limit: int = 500,
    skip_dead: bool = True,
    skip_recent_days: int = 365,
    request_timeout: float = 10.0,
    max_fail_before_dead: int = 2,
    company_id_start: Optional[int] = None,
    company_id_end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    homepage_url 생존 여부를 체크해서 homepage_url_status를 갱신.
    - skip_dead=True면 이미 dead인 회사는 재체크 스킵
    - skip_recent_days: 최근에 체크한 회사는 스킵
    - max_fail_before_dead: 연속 실패가 이 값 이상이면 dead 확정
    """
    qs = Company.objects.exclude(homepage_url__isnull=True).exclude(homepage_url="")
    qs = _apply_company_id_range(qs, company_id_start=company_id_start, company_id_end=company_id_end)

    if skip_dead:
        qs = qs.exclude(homepage_url_status="dead")

    if skip_recent_days and skip_recent_days > 0:
        cutoff = timezone.now() - timedelta(days=skip_recent_days)
        qs = qs.exclude(homepage_checked_at__gte=cutoff)

    qs = qs.order_by("id")[:limit]

    checked = 0
    alive = 0
    dead = 0
    updated = 0

    session = requests.Session()
    session.headers.update({
        "User-Agent": os.getenv("HOMEPAGE_CHECK_UA", "job-crawler/1.0 (+contact: admin@example.com)"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    for c in qs:
        checked += 1

        # URL 정규화(스킴 없으면 붙임)
        url = _canonicalize_url(c.homepage_url) or c.homepage_url
        if url != c.homepage_url:
            c.homepage_url = url
            if not c.homepage_host:
                c.homepage_host = _url_host(url)

        status, code = _probe_url(session, url, timeout=request_timeout)

        c.homepage_last_status_code = code
        c.homepage_checked_at = timezone.now()

        if status == "alive":
            c.homepage_url_status = "alive"
            c.homepage_fail_count = 0
            alive += 1
        else:
            # 실패 누적
            c.homepage_fail_count = (c.homepage_fail_count or 0) + 1
            # 즉시 dead로 확정 가능한 코드면 바로 dead
            if code in (404, 410):
                c.homepage_url_status = "dead"
                dead += 1
            else:
                if c.homepage_fail_count >= max_fail_before_dead:
                    c.homepage_url_status = "dead"
                    dead += 1
                else:
                    c.homepage_url_status = c.homepage_url_status or "unknown"

        c.save(update_fields=[
            "homepage_url",
            "homepage_host",
            "homepage_url_status",
            "homepage_checked_at",
            "homepage_last_status_code",
            "homepage_fail_count",
        ])
        updated += 1

    return {
        "checked": checked,
        "alive": alive,
        "dead": dead,
        "updated": updated,
        "skip_dead": skip_dead,
        "skip_recent_days": skip_recent_days,
        "company_id_start": company_id_start,
        "company_id_end": company_id_end,
    }


# =========================
# Periodic schedules
# =========================

@shared_task(name="api.tasks.setup_company_seed_schedules")
def setup_company_seed_schedules() -> Dict[str, Any]:
    """
    - OSM: 주 1회 (기존 tasks.py에서 수행)
    - SWDB: 연 1회 (CSV 파일 기반. 파일은 사용자가 최신 파일로 교체)
    - DART: 주 1회 (상장사, 최근 변경분 위주)
    - Homepage check: 연 1회 (SWDB 이후) + 필요시 수동
    """
    # KST 기준 (django-celery-beat은 settings TIME_ZONE 반영)
    # 화요일 새벽: 월요일 트래픽/점검 변동을 피하고, 주중 초반에 최신화
    weekly, _ = CrontabSchedule.objects.get_or_create(
        minute="20",
        hour="3",
        day_of_week="2",   # Tue
        day_of_month="*",
        month_of_year="*",
    )

    yearly, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="4",
        day_of_month="1",
        month_of_year="2",  # Feb 1
        day_of_week="*",
    )

    yearly_check, _ = CrontabSchedule.objects.get_or_create(
        minute="10",
        hour="5",
        day_of_month="1",
        month_of_year="2",  # Feb 1 05:10
        day_of_week="*",
    )

    # 기존 동일 이름 태스크는 갱신(중복 방지)
    def upsert_periodic(name: str, task: str, schedule: CrontabSchedule, kwargs: Dict[str, Any]):
        PeriodicTask.objects.update_or_create(
            name=name,
            defaults={
                "task": task,
                "crontab": schedule,
                "enabled": True,
                "kwargs": json.dumps(kwargs, ensure_ascii=False),
            },
        )

    # SWDB (CSV)
    upsert_periodic(
        name="seed-swdb-yearly",
        task="api.tasks.collect_swdb_companies",
        schedule=yearly,
        kwargs={
            "csv_path": os.getenv("SWDB_CSV_PATH", DEFAULT_SWDB_CSV_PATH),
            "regions": [],  # no region filter by default
            "limit": None,
            "only_with_homepage": True,
        },
    )

    # DART (listed-only delta)
    upsert_periodic(
        name="seed-dart-listed-weekly",
        task="api.tasks.collect_dart_companies",
        schedule=weekly,
        kwargs={
            "mode": "discover_listed",
            "since_days": 14,
            "limit": None,
            "only_with_homepage": False,
            "regions": [],  # no region filter
        },
    )

    # Homepage liveness check (연 1회)
    upsert_periodic(
        name="check-homepages-yearly",
        task="api.tasks.check_company_homepages",
        schedule=yearly_check,
        kwargs={
            "limit": 2000,            # 너무 무겁게 가지 말고 배치로
            "skip_dead": True,
            "skip_recent_days": 365,
            "request_timeout": 10.0,
            "max_fail_before_dead": 2,
        },
    )

    return {"ok": True}
