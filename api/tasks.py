# api/tasks.py

import os
import subprocess
import logging

from celery import shared_task, chain
from django.db import close_old_connections
from django.conf import settings

from .models import Company
from .utils import find_homepage_for_company

logger = logging.getLogger(__name__)

BASE_DIR = settings.BASE_DIR


@shared_task
def find_missing_homepages(limit=None):
    """
    homepage_url 이 비어있는 회사들에 대해 검색으로 홈페이지를 찾아 채워 넣는다.
    limit: 개발 단계에서 상위 N개만 시도하고 싶을 때 사용 (None이면 전체)
    """
    qs_all = Company.objects.filter(homepage_url__isnull=True).order_by("id")
    total_all = qs_all.count()

    if limit:
        qs = qs_all[:limit]
    else:
        qs = qs_all

    total = qs.count()
    updated = 0

    logger.info(
        "find_missing_homepages: start (targets=%s/%s, limit=%s)",
        total,
        total_all,
        limit,
    )

    for company in qs:
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
def run_discover_careers_spiders(limit=None):
    """
    homepage_url은 있지만 recruits_url이 없는 회사들에 대해
    discover_careers 스파이더를 실행.
    limit: 개발용 옵션. None이면 전체, 숫자면 상위 N개만.
    """
    from django.db.models import Q

    qs = Company.objects.filter(
        homepage_url__isnull=False
    ).filter(
        Q(recruits_url__isnull=True) | Q(recruits_url="")
    ).order_by("id")

    if limit:
        qs = qs[:int(limit)]

    scrapy_project_path = os.path.join(settings.BASE_DIR, "crawler")

    for company in qs:
        close_old_connections()

        env = os.environ.copy()
        # Scrapy 프로세스 안에서 Django ORM 사용 허용
        env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        env.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

        cmd = [
            "scrapy", "crawl", "discover_careers",
            "-a", f"company_id={company.id}",
            "-a", f"company_name={company.name}",
            "-a", f"homepage_url={company.homepage_url}",
        ]

        logger.info(
            "run_discover_careers_spiders: company_id=%s name=%s url=%s",
            company.id, company.name, company.homepage_url,
        )

        result = subprocess.run(
            cmd,
            cwd=scrapy_project_path,
            env=env,
        )

        if result.returncode != 0:
            logger.warning(
                "discover_careers spider failed for company_id=%s (exit=%s)",
                company.id, result.returncode
            )



@shared_task
def run_job_collector_spiders(limit=None):
    """
    Company에 저장된 recruits_url 정보를 기반으로
    job_collector 스파이더를 회사별로 실행한다.

    설계 원칙:
    - 외부 플랫폼(external) 타입은 여기서 수집하지 않는다.
    - post_type='text' 인 회사만 대상.
    - page_type in ('listing', 'one_page', 'main') 만 대상.
    - recruits_url 이 비어있지 않은 회사만 대상.
    - limit 가 주어지면, id 기준 상위 N개 회사만 실행 (디버그/부분 실행용).
    - 각 회사는 별도 Scrapy 프로세스로 실행.
    """

    # queryset: "지금 우리가 진짜 돌리고 싶은 회사들"
    qs = Company.objects.filter(
        recruits_url__isnull=False,
    ).exclude(
        recruits_url="",
    ).filter(
        page_type__in=["listing", "one_page", "main"],
        post_type="text",
    )

    # (이전 템플릿에서 recruits_url_status='CONFIRMED' 로 너무 좁게 잡혀 있던 부분을 완화한 것.
    #  필드는 그대로 두되, 지금은 조건에서 빼서 실제로 돌도록 한다.)

    qs = qs.order_by("id")

    if limit is not None:
        try:
            limit = int(limit)
            if limit > 0:
                qs = qs[:limit]
        except (TypeError, ValueError):
            logger.warning("run_job_collector_spiders: invalid limit=%r (ignored)", limit)

    targets = list(qs.values("id", "name", "recruits_url", "page_type", "post_type"))
    logger.info("run_job_collector_spiders: start (targets=%s)", len(targets))

    if not targets:
        logger.info("run_job_collector_spiders: no targets (nothing to run)")
        return

    # Scrapy 실행 환경 설정
    base_env = os.environ.copy()
    base_env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    base_env.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    for t in targets:
        company_id = t["id"]
        name = t["name"]
        url = t["recruits_url"]
        page_type = (t.get("page_type") or "").lower()
        post_type = (t.get("post_type") or "").lower()

        logger.info(
            "run_job_collector_spiders: run spider for company_id=%s name=%s page_type=%s post_type=%s url=%s",
            company_id,
            name,
            page_type,
            post_type,
            url,
        )

        # company 개별 실행
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
            )
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

@shared_task(name="api.tasks.run_full_crawling_cycle")
def run_full_crawling_cycle():
    """
    전체 파이프라인:
      1) find_missing_homepages    - homepage_url 채우기
      2) run_discover_careers_spiders - recruits_url / page_type / post_type 등 찾기 (스파이더 책임)
      3) run_job_collector_spiders - 실제 채용공고 수집

    여기서는 limit 사용하지 않고 전체 대상 기준으로 돈다.
    (개발용 limit 테스트는 각 task를 개별 호출할 때만 사용)
    """
    logger.info("full_cycle: dispatch chain")

    workflow = chain(
        find_missing_homepages.s(),          # limit=None
        run_discover_careers_spiders.s(),    # limit=None
        run_job_collector_spiders.s(),       # limit=None
    )
    workflow.apply_async()

    logger.info("full_cycle: chain dispatched")


@shared_task
def hello():
    logger.info("hello task start")
    import time
    time.sleep(1)
    logger.info("hello task done")
    return "ok"
