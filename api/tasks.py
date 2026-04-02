# api/tasks.py

import os
import re
import time
import subprocess
import logging
from urllib.parse import urlparse, urlunparse

from celery import shared_task, chain
from django.db import close_old_connections, IntegrityError, transaction
from django.conf import settings

from .models import Company
from .utils import find_homepage_for_company
from .osm_overpass import iter_region_records
from .company_sources import (
    collect_swdb_companies,
    collect_dart_companies,
    check_company_homepages,
    setup_company_seed_schedules,
)


logger = logging.getLogger(__name__)
FILTER_VERSION = "2026-02-02-is_target_industry-v2"
DISCOVER_SPIDER_TIMEOUT = 120
JOB_COLLECTOR_TIMEOUT = 300

BASE_DIR = settings.BASE_DIR


def _apply_company_id_range(qs, company_id_start=None, company_id_end=None):
    if company_id_start is not None:
        qs = qs.filter(id__gte=int(company_id_start))
    if company_id_end is not None:
        qs = qs.filter(id__lte=int(company_id_end))
    return qs

# =========================
# 0) 공통 유틸: URL / 이름 정규화
# =========================

_HTTP_SCHEMES = ("http://", "https://")


def canonicalize_homepage(url: str | None) -> str | None:
    """
    홈페이지 URL을 중복 비교용 canonical 형태로 정규화.
    - scheme 보정 (없으면 https)
    - 소문자 도메인
    - 기본 포트 제거
    - path/fragment/query 제거 (도메인까지만)
    - www. 제거 (중복 방지용; 원 URL은 그대로 저장해도 됨)
    """
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    if not u.lower().startswith(_HTTP_SCHEMES):
        u = "https://" + u

    try:
        p = urlparse(u)
    except Exception:
        return None

    host = (p.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]

    # 기본 포트 제거
    port = p.port
    netloc = host
    if port and not ((p.scheme == "http" and port == 80) or (p.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    # 도메인까지만 남김
    canon = urlunparse((p.scheme, netloc, "", "", "", ""))
    return canon


def domain_of(url: str | None) -> str | None:
    canon = canonicalize_homepage(url)
    if not canon:
        return None
    try:
        return urlparse(canon).hostname
    except Exception:
        return None


def make_unique_company_name(base_name: str) -> str:
    """
    Company.name 이 unique=True라서,
    동일명이 이미 있으면 ' (2)', ' (3)' 방식으로 유니크하게 만든다.
    """
    base_name = (base_name or "").strip()
    if not base_name:
        base_name = "Unknown"

    if not Company.objects.filter(name=base_name).exists():
        return base_name

    i = 2
    while True:
        cand = f"{base_name} ({i})"
        if not Company.objects.filter(name=cand).exists():
            return cand
        i += 1


# =========================
# 1) OSM 수집: 필터링 / 업종 판정 / 중복 방지
# =========================

# “기관/부동산/행정” 등 제외 키워드 (필요하면 계속 추가)
_NAME_BLOCKLIST_RE = re.compile(
    r"(동사무소|주민센터|행정복지센터|면사무소|읍사무소|구청|시청|군청|도청|"
    r"주민자치|보건소|소방서|경찰서|우체국|법원|등기소|"
    r"부동산|공인중개|중개사무소|"
    r"마을회관|경로당|"
    r"초등학교|중학교|고등학교|대학교|"
    r"교회|성당|사찰)",
    flags=re.IGNORECASE,
)

# 태그 기반 제외
_TAG_BLOCKLIST = {
    ("office", "government"),
    ("office", "estate_agent"),
    ("shop", "real_estate"),
    ("amenity", "townhall"),
    ("amenity", "community_centre"),
}

# 관심 업종 키워드 (회사명에만 의존하면 오탐이 늘어서, 태그 판정 + 보조로만 사용)
_INTEREST_NAME_HINT_RE = re.compile(
    r"(IT|테크|테크놀|소프트|SW|시스템|솔루션|플랫폼|클라우드|데이터|AI|인공지능|"
    r"전자|전기|반도체|센서|로봇|기계|자동화|제조|공업|통신|네트워크|보안)",
    flags=re.IGNORECASE,
)

# OSM 태그 -> (대략) industry 문자열
_TAG_INDUSTRY_MAP = [
    (("office", "it"), "IT"),
    (("shop", "electronics"), "Electronics"),
    (("craft", "electronics"), "Electronics"),
    (("industrial", "electronics"), "Electronics manufacturing"),
    (("industrial", "manufacturing"), "Manufacturing"),
    (("industrial", "machine_shop"), "Manufacturing"),
]


def is_unwanted_place(name: str | None, tags: dict | None) -> bool:
    tags = tags or {}
    nm = (name or "").strip()
    if nm and _NAME_BLOCKLIST_RE.search(nm):
        return True

    for k, v in _TAG_BLOCKLIST:
        if tags.get(k) == v:
            return True

    return False


def is_target_industry(name: str | None, tags: dict | None) -> bool:
    """
    목표: IT / 전자 / 제조 계열만 통과.
    - Overpass에서 이미 government/estate_agent/real_estate 일부는 제외
    - 여기서는 '관심 업종' 범위를 medium답게 확장
    """
    tags = tags or {}
    nm = (name or "").strip()

    office = (tags.get("office") or "").strip()
    shop = (tags.get("shop") or "").strip()
    industrial = (tags.get("industrial") or "").strip()
    manufacturing = (tags.get("manufacturing") or "").strip()
    craft = (tags.get("craft") or "").strip()
    man_made = (tags.get("man_made") or "").strip()

    # 1) 명확한 IT/연구/통신
    if office in {"it", "research", "telecommunication"}:
        return True

    # 2) 전자/컴퓨터/휴대폰 판매점도 전자/IT 후보로 포함
    if shop in {"electronics", "computer", "mobile_phone"}:
        return True

    # 3) 산업/제조는 태그만 있어도 포함(원치 않는 건 블랙리스트에서 이미 걸러짐)
    if industrial:
        return True
    if manufacturing:
        return True
    if man_made == "works":
        return True

    # 4) craft는 너무 넓어서 조건부로만 포함
    #    (제조/전자 쪽 craft 값은 통과, 그 외는 이름 힌트가 있을 때만 통과)
    craft_allow = {
        "electronics", "metalworking", "machinist", "toolmaker", "engineer",
        "electrical", "industrial", "automation"
    }
    if craft in craft_allow:
        return True
    if craft and _INTEREST_NAME_HINT_RE.search(nm):
        return True

    # 5) office=company는 잡음이 많아서 이름 힌트 있을 때만 포함
    # if office == "company" and _INTEREST_NAME_HINT_RE.search(nm):
    if office == "company": # 수집되는게 적어서 수정
        return True

    # 6) 태그가 빈약한데 이름만 강하게 IT/전자/제조 힌트면 포함
    if nm and _INTEREST_NAME_HINT_RE.search(nm):
        return True

    return False



def infer_industry_from_tags(tags: dict | None) -> str | None:
    tags = tags or {}
    for (k, v), ind in _TAG_INDUSTRY_MAP:
        if tags.get(k) == v:
            return ind
    # industrial=*가 있으면 그대로 넣기 (너무 길면 잘림)
    if tags.get("industrial"):
        return f"industrial:{tags.get('industrial')}"[:100]
    if tags.get("office"):
        return f"office:{tags.get('office')}"[:100]
    if tags.get("craft"):
        return f"craft:{tags.get('craft')}"[:100]
    if tags.get("shop"):
        return f"shop:{tags.get('shop')}"[:100]
    return None


def build_address_from_tags(tags: dict | None) -> str | None:
    """
    OSM 주소 태그가 있으면 최대한 조합.
    없는 경우 None.
    """
    tags = tags or {}
    if tags.get("addr:full"):
        return tags.get("addr:full")[:255]

    parts = []
    for key in ("addr:province", "addr:city", "addr:district", "addr:subdistrict", "addr:street", "addr:housenumber"):
        v = tags.get(key)
        if v:
            parts.append(v)

    if parts:
        return " ".join(parts)[:255]

    return None


def upsert_company_with_dedup(
    *,
    name: str,
    homepage_url: str | None,
    region: str | None = None,
    address: str | None = None,
    industry: str | None = None,
    logo_url: str | None = None,
    domain_map: dict[str, Company] | None = None,
) -> tuple[str, Company]:
    """
    중복 방지 전략 (우선순위):
    1) canonical 도메인이 동일하면 같은 회사로 보고 update (필드가 비어있을 때만 채움)
    2) canonical 도메인이 없거나 매칭 실패:
       - name 이 이미 있으면 (2)(3)... suffix 붙여 새 레코드 생성
       - name 이 없으면 그대로 생성

    return: ("created"|"updated"|"skipped", company)
    """
    dom = domain_of(homepage_url)

    # 1) 도메인 기반 병합
    if dom:
        # task 시작 시 미리 만들어둔 domain_map을 쓰면 O(N^2) 폭증을 피할 수 있음
        if domain_map is None:
            domain_map = {}

        c = domain_map.get(dom)
        if c is None:
            # domain_map이 비어 있거나 누락된 경우를 대비해 1회만 DB에서 찾는다.
            candidates = Company.objects.filter(homepage_url__isnull=False).only(
                "id", "homepage_url", "name", "region", "address", "industry", "logo_url"
            )
            for cand in candidates:
                d = domain_of(cand.homepage_url)
                if d:
                    domain_map.setdefault(d, cand)
            c = domain_map.get(dom)

        if c is not None:
            changed = False
            fields = []
            if not c.homepage_url and homepage_url:
                c.homepage_url = homepage_url
                fields.append("homepage_url")
                changed = True
            if (not c.region) and region:
                c.region = region
                fields.append("region")
                changed = True
            if (not c.address) and address:
                c.address = address
                fields.append("address")
                changed = True
            if (not c.industry) and industry:
                c.industry = industry
                fields.append("industry")
                changed = True
            if (not c.logo_url) and logo_url:
                c.logo_url = logo_url
                fields.append("logo_url")
                changed = True

            if changed:
                c.save(update_fields=fields)
                return "updated", c
            return "skipped", c

    # 2) 이름 unique 충돌 처리
    final_name = name.strip() if name else "Unknown"
    if Company.objects.filter(name=final_name).exists():
        final_name = make_unique_company_name(final_name)

    data = {
        "name": final_name,
        "homepage_url": homepage_url,
        "region": region,
        "address": address,
        "industry": industry,
        "logo_url": logo_url,
    }

    try:
        with transaction.atomic():
            obj = Company.objects.create(**data)
        # domain_map 갱신
        if dom and domain_map is not None:
            domain_map[dom] = obj
        return "created", obj
    except IntegrityError:
        # 동시성으로 name 충돌 등 발생 시 재시도
        final_name = make_unique_company_name(final_name)
        data["name"] = final_name
        obj = Company.objects.create(**data)
        if dom and domain_map is not None:
            domain_map[dom] = obj
        return "created", obj

import fcntl
import time
from celery import shared_task
from django.db import close_old_connections

@shared_task
def collect_osm_companies(
    regions=None,
    mode="medium",
    limit=None,
    require_homepage=True,
):
    lock_path = "/app/.osm_collect.lock"

    # 락 대기 자체가 길어질 수 있으니, 락 잡기 전 로그를 남김
    logger.info("collect_osm_companies: waiting lock path=%s", lock_path)

    with open(lock_path, "w") as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        try:
            if not regions:
                regions = ["서울특별시", "경기도", "대전광역시", "충청남도", "충청북도"]

            logger.info(
                "collect_osm_companies: start regions=%s mode=%s limit=%s filter=%s",
                regions, mode, limit, FILTER_VERSION
            )

            # 기존 데이터 도메인 캐시
            domain_map: dict[str, Company] = {}
            for c in Company.objects.exclude(homepage_url__isnull=True).only("id", "homepage_url"):
                d = domain_of(c.homepage_url)
                if d:
                    domain_map.setdefault(d, c)

            processed = 0
            created = 0
            updated = 0

            skip_no_homepage = 0
            skip_unwanted = 0
            skip_not_target = 0
            skip_duplicate_nochange = 0

            sample_unwanted = []
            sample_not_target = []

            t0 = time.monotonic()

            for region in regions:
                logger.info("collect_osm_companies: region=%s start", region)

                for rec in iter_region_records(region, mode=mode, limit=limit):
                    processed += 1

                    # DB 커넥션 정리: 매 레코드마다 하면 느려질 수 있어 주기적으로만
                    if processed % 200 == 0:
                        close_old_connections()
                        elapsed = time.monotonic() - t0
                        logger.info(
                            "collect_osm_companies: progress processed=%s created=%s updated=%s "
                            "skip_no_homepage=%s skip_unwanted=%s skip_not_target=%s skip_dup_nochange=%s elapsed=%.1fs",
                            processed, created, updated,
                            skip_no_homepage, skip_unwanted, skip_not_target, skip_duplicate_nochange,
                            elapsed,
                        )

                    name = (rec.get("name") or "").strip() or "Unknown"
                    tags = rec.get("tags") or {}
                    homepage = rec.get("website")

                    if require_homepage and not homepage:
                        skip_no_homepage += 1
                        continue

                    if is_unwanted_place(name, tags):
                        skip_unwanted += 1
                        if len(sample_unwanted) < 10:
                            sample_unwanted.append((name, tags.get("office"), tags.get("shop"), tags.get("amenity")))
                        continue

                    if not is_target_industry(name, tags):
                        skip_not_target += 1
                        if len(sample_not_target) < 10:
                            sample_not_target.append((name, tags.get("office"), tags.get("shop"), tags.get("industrial"), tags.get("craft")))
                        continue

                    address = build_address_from_tags(tags)
                    industry = infer_industry_from_tags(tags)
                    logo_url = tags.get("logo") or tags.get("brand:logo") or tags.get("image")

                    status, _obj = upsert_company_with_dedup(
                        name=name,
                        homepage_url=homepage,
                        region=region,
                        address=address,
                        industry=industry,
                        logo_url=logo_url,
                        domain_map=domain_map,
                    )

                    if status == "created":
                        created += 1
                    elif status == "updated":
                        updated += 1
                    else:
                        skip_duplicate_nochange += 1

                logger.info("collect_osm_companies: region=%s done", region)

            skipped_total = skip_no_homepage + skip_unwanted + skip_not_target + skip_duplicate_nochange

            logger.info(
                "collect_osm_companies: done processed=%s created=%s updated=%s "
                "skip_no_homepage=%s skip_unwanted=%s skip_not_target=%s skip_dup_nochange=%s",
                processed, created, updated,
                skip_no_homepage, skip_unwanted, skip_not_target, skip_duplicate_nochange
            )
            if sample_unwanted:
                logger.info("sample_unwanted=%s", sample_unwanted)
            if sample_not_target:
                logger.info("sample_not_target=%s", sample_not_target)

            return {
                "processed": processed,
                "created": created,
                "updated": updated,
                "skipped": skipped_total,
                "skip_detail": {
                    "no_homepage": skip_no_homepage,
                    "unwanted": skip_unwanted,
                    "not_target": skip_not_target,
                    "dup_nochange": skip_duplicate_nochange,
                },
            }

        finally:
            # 예외가 나도 락 해제 보장
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)




# =========================
# 2) 기존 파이프라인 (homepage -> discover -> job_collector)
# =========================

@shared_task
def find_missing_homepages(limit=None, company_id_start=None, company_id_end=None):
    """
    homepage_url 이 비어있는 회사들에 대해 검색으로 홈페이지를 찾아 채워 넣는다.
    limit: 개발 단계에서 상위 N개만 시도하고 싶을 때 사용 (None이면 전체)
    """
    qs_all = Company.objects.filter(homepage_url__isnull=True).order_by("id")
    qs_all = _apply_company_id_range(qs_all, company_id_start=company_id_start, company_id_end=company_id_end)
    total_all = qs_all.count()

    if limit:
        qs = qs_all[:limit]
    else:
        qs = qs_all

    total = qs.count()
    updated = 0

    logger.info(
        "find_missing_homepages: start (targets=%s/%s, limit=%s, company_id_start=%s, company_id_end=%s)",
        total,
        total_all,
        limit,
        company_id_start,
        company_id_end,
    )

    for company in qs:
        close_old_connections()
        homepage = find_homepage_for_company(company.name)
        if homepage:
            company.homepage_url = homepage
            company.save(update_fields=["homepage_url"])
            updated += 1

    logger.info(
        "find_missing_homepages: done (updated=%s, scanned=%s, total_pending=%s)",
        updated,
        total,
        total_all,
    )


@shared_task
def run_discover_careers_spiders(limit=None, company_id_start=None, company_id_end=None):
    """
    homepage_url은 있지만 recruits_url이 없는 회사들에 대해
    discover_careers 스파이더를 실행.
    limit: 개발용 옵션. None이면 전체, 숫자면 상위 N개만.
    """
    from django.db.models import Q

    # NOTE: discovery should only run for companies whose homepage is considered "alive".
    # We treat 2xx/3xx and common access/behavioral blocks (401/403/405/406) as alive.
    alive_q = (
        Q(homepage_url_status="alive")
        | Q(homepage_last_status_code__gte=200, homepage_last_status_code__lt=400)
        | Q(homepage_last_status_code__in=[401, 403, 405, 406])
    )

    qs = (
        Company.objects.exclude(homepage_url__isnull=True)
        .exclude(homepage_url="")
        .filter(alive_q)
        .filter(Q(recruits_url__isnull=True) | Q(recruits_url=""))
        .order_by("id")
    )
    qs = _apply_company_id_range(qs, company_id_start=company_id_start, company_id_end=company_id_end)

    if limit:
        qs = qs[:int(limit)]

    total = qs.count()
    logger.info(
        "run_discover_careers_spiders: start (targets=%s, limit=%s, company_id_start=%s, company_id_end=%s)",
        total,
        limit,
        company_id_start,
        company_id_end,
    )

    for company in qs:
        close_old_connections()

        company_id = company.id
        homepage_url = company.homepage_url

        # company 개별 실행
        cmd = [
            "scrapy",
            "crawl",
            "discover_careers",
            "-a",
            f"company_id={company_id}",
            "-a",
            f"homepage_url={homepage_url}",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd="/app/crawler",
                capture_output=True,
                text=True,
                check=False,
                timeout=DISCOVER_SPIDER_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "run_discover_careers_spiders: spider timed out for company_id=%s (timeout=%ss)",
                company_id,
                DISCOVER_SPIDER_TIMEOUT,
            )
            continue
        except Exception as e:
            logger.warning(
                "run_discover_careers_spiders: failed to start spider for company_id=%s (%s)",
                company_id,
                e,
            )
            continue

        if result.returncode != 0:
            logger.warning(
                "run_discover_careers_spiders: spider failed for company_id=%s (exit=%s)\nstdout=%s\nstderr=%s",
                company_id,
                result.returncode,
                (result.stdout or "")[:4000],
                (result.stderr or "")[:4000],
            )
        else:
            logger.info(
                "run_discover_careers_spiders: spider done for company_id=%s",
                company_id,
            )

    logger.info("run_discover_careers_spiders: finished all targets")


@shared_task
def run_discover_careers_spiders_concurrent(limit=None, workers=20, company_id_start=None, company_id_end=None):
    """
    Concurrent version of run_discover_careers_spiders.
    Runs multiple spider subprocesses in parallel using ThreadPoolExecutor.
    workers: number of concurrent spider processes (default 20).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.db.models import Q

    alive_q = (
        Q(homepage_url_status="alive")
        | Q(homepage_last_status_code__gte=200, homepage_last_status_code__lt=400)
        | Q(homepage_last_status_code__in=[401, 403, 405, 406])
    )

    qs = (
        Company.objects.exclude(homepage_url__isnull=True)
        .exclude(homepage_url="")
        .filter(alive_q)
        .filter(Q(recruits_url__isnull=True) | Q(recruits_url=""))
        .order_by("id")
        .values_list("id", "homepage_url")
    )
    qs = _apply_company_id_range(qs, company_id_start=company_id_start, company_id_end=company_id_end)

    if limit:
        qs = list(qs[: int(limit)])
    else:
        qs = list(qs)

    total = len(qs)
    saved = 0
    failed = 0

    def run_one(company_id, homepage_url):
        cmd = [
            "scrapy", "crawl", "discover_careers",
            "-a", f"company_id={company_id}",
            "-a", f"homepage_url={homepage_url}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd="/app/crawler",
                capture_output=True,
                text=True,
                check=False,
                timeout=DISCOVER_SPIDER_TIMEOUT,
            )
            return company_id, result.returncode == 0, homepage_url
        except subprocess.TimeoutExpired:
            logger.warning("Spider timed out for company_id=%s (timeout=%ss)", company_id, DISCOVER_SPIDER_TIMEOUT)
            return company_id, False, homepage_url
        except Exception as e:
            logger.warning("Spider failed for company_id=%s (%s)", company_id, e)
            return company_id, False, homepage_url

    start = time.time()
    logger.info("run_discover_careers_spiders_concurrent: starting %d companies with %d workers", total, workers)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_one, cid, hurl): (cid, hurl)
            for cid, hurl in qs
        }
        for future in as_completed(futures):
            cid, ok, hurl = future.result()
            close_old_connections()
            if ok:
                saved += 1
                logger.info("  [saved] company_id=%s url=%s", cid, hurl)
            else:
                failed += 1

            # Progress log every 100 completed
            done = saved + failed
            if done % 100 == 0:
                elapsed = time.time() - start
                rate = done / elapsed
                eta = (total - done) / rate if rate > 0 else 0
                logger.info("  progress: %d/%d saved=%d failed=%d (%.1f co/s, ETA %.0fs)",
                            done, total, saved, failed, rate, eta)

    elapsed = time.time() - start
    logger.info(
        "run_discover_careers_spiders_concurrent: DONE total=%d saved=%d failed=%d elapsed=%.1fs",
        total, saved, failed, elapsed,
    )
    return {"total": total, "saved": saved, "failed": failed, "elapsed": elapsed}


@shared_task
def run_job_collector_spiders(limit=None, company_id_start=None, company_id_end=None):
    """
    recruits_url이 있고 회사들에 대해 job_collector 스파이더를 실행.
    """
    qs = Company.objects.filter(
        recruits_url__isnull=False
    ).exclude(
        recruits_url=""
    ).order_by("id")
    qs = _apply_company_id_range(qs, company_id_start=company_id_start, company_id_end=company_id_end)

    if limit:
        qs = qs[:int(limit)]

    total = qs.count()
    logger.info(
        "run_job_collector_spiders: start (targets=%s, limit=%s, company_id_start=%s, company_id_end=%s)",
        total,
        limit,
        company_id_start,
        company_id_end,
    )

    base_env = os.environ.copy()

    for company in qs:
        close_old_connections()

        company_id = company.id
        url = company.recruits_url
        page_type = company.page_type
        post_type = company.post_type

        cmd = [
            "scrapy",
            "crawl",
            "job_collector",
            "-a",
            f"company_id={company_id}",
            "-a",
            f"recruits_url={url}",
            "-a",
            f"page_type={page_type or 'listing'}",
            "-a",
            f"post_type={post_type or 'text'}",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd="/app/crawler",
                env=base_env,
                capture_output=True,
                text=True,
                check=False,
                timeout=JOB_COLLECTOR_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "run_job_collector_spiders: spider timed out for company_id=%s (timeout=%ss)",
                company_id,
                JOB_COLLECTOR_TIMEOUT,
            )
            continue
        except Exception as e:
            logger.warning(
                "run_job_collector_spiders: failed to start spider for company_id=%s (%s)",
                company_id,
                e,
            )
            continue

        if result.returncode != 0:
            logger.warning(
                "run_job_collector_spiders: spider failed for company_id=%s (exit=%s)\nstdout=%s\nstderr=%s",
                company_id,
                result.returncode,
                (result.stdout or "")[:4000],
                (result.stderr or "")[:4000],
            )
        else:
            logger.info(
                "run_job_collector_spiders: spider done for company_id=%s",
                company_id,
            )

    logger.info("run_job_collector_spiders: finished all targets")


@shared_task
def run_job_collector_spiders_concurrent(limit=None, workers=10, company_id_start=None, company_id_end=None):
    """
    Concurrent version of run_job_collector_spiders.
    Runs multiple job_collector spider subprocesses in parallel using ThreadPoolExecutor.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    qs = (
        Company.objects.filter(recruits_url__isnull=False)
        .exclude(recruits_url="")
        .order_by("id")
        .values_list("id", "recruits_url", "page_type", "post_type")
    )
    qs = _apply_company_id_range(qs, company_id_start=company_id_start, company_id_end=company_id_end)

    if limit:
        qs = list(qs[: int(limit)])
    else:
        qs = list(qs)

    total = len(qs)
    completed = 0
    failed = 0

    base_env = os.environ.copy()

    def run_one(company_id, recruits_url, page_type, post_type):
        cmd = [
            "scrapy", "crawl", "job_collector",
            "-a", f"company_id={company_id}",
            "-a", f"recruits_url={recruits_url}",
            "-a", f"page_type={page_type or 'listing'}",
            "-a", f"post_type={post_type or 'text'}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd="/app/crawler",
                env=base_env,
                capture_output=True,
                text=True,
                check=False,
                timeout=JOB_COLLECTOR_TIMEOUT,
            )
            return company_id, result.returncode == 0, recruits_url
        except subprocess.TimeoutExpired:
            logger.warning("job_collector timed out for company_id=%s (timeout=%ss)", company_id, JOB_COLLECTOR_TIMEOUT)
            return company_id, False, recruits_url
        except Exception as e:
            logger.warning("job_collector failed for company_id=%s (%s)", company_id, e)
            return company_id, False, recruits_url

    start = time.time()
    logger.info(
        "run_job_collector_spiders_concurrent: starting %d companies with %d workers",
        total, workers,
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_one, cid, url, pt, pst): (cid, url)
            for cid, url, pt, pst in qs
        }
        for future in as_completed(futures):
            cid, ok, url = future.result()
            close_old_connections()
            if ok:
                completed += 1
            else:
                failed += 1

            done = completed + failed
            if done % 200 == 0:
                elapsed = time.time() - start
                rate = done / elapsed
                eta = (total - done) / rate if rate > 0 else 0
                logger.info(
                    "  progress: %d/%d completed=%d failed=%d (%.1f co/s, ETA %.0fs)",
                    done, total, completed, failed, rate, eta,
                )

    elapsed = time.time() - start
    logger.info(
        "run_job_collector_spiders_concurrent: DONE total=%d completed=%d failed=%d elapsed=%.1fs",
        total, completed, failed, elapsed,
    )
    return {"total": total, "completed": completed, "failed": failed, "elapsed": elapsed}


@shared_task(name="api.tasks.run_full_crawling_cycle")
def run_full_crawling_cycle():
    """
    전체 파이프라인 (권장 순서):
      0) collect_osm_companies           - 회사 seed 자동 추가 (홈페이지 있는 것 위주)
      1) find_missing_homepages (옵션)  - homepage_url 비어있는 회사 채우기
      2) run_discover_careers_spiders   - recruits_url / page_type / post_type 탐색
      3) run_job_collector_spiders      - 실제 채용공고 수집

    IMPORTANT
    - chain()에 .s()를 쓰면 이전 task의 return값이 다음 task의 첫 인자로 넘어가서
      "limit" 파라미터가 의도치 않게 깨질 수 있음.
    - 따라서 여기서는 전부 .si() (immutable signature)로 고정.
    """
    regions_env = os.getenv("COMPANY_REGIONS", "서울특별시,경기도,대전광역시,충청남도,충청북도")
    regions = [x.strip() for x in regions_env.split(",") if x.strip()]
    osm_mode = os.getenv("OSM_MODE", "medium")
    osm_limit = os.getenv("OSM_LIMIT")
    osm_limit = int(osm_limit) if (osm_limit and osm_limit.isdigit()) else None

    enable_find_missing = os.getenv("ENABLE_FIND_MISSING_HOMEPAGES", "0") == "1"

    logger.info("full_cycle: dispatch chain regions=%s osm_mode=%s", regions, osm_mode)

    tasks = [
        collect_osm_companies.si(regions=regions, mode=osm_mode, limit=osm_limit),
    ]

    if enable_find_missing:
        tasks.append(find_missing_homepages.si())

    tasks.extend([
        run_discover_careers_spiders.si(),
        run_job_collector_spiders.si(),
    ])

    workflow = chain(*tasks)
    workflow.apply_async()

    logger.info("full_cycle: chain dispatched")


@shared_task
def hello():
    logger.info("hello task start")
    time.sleep(1)
    logger.info("hello task done")
    return "ok"
