# api/tasks.py
from celery import shared_task, chain
from .models import Company
import subprocess
import os
from config.settings import BASE_DIR
from .utils import find_homepage_for_company
import logging
import time

logger = logging.getLogger(__name__)

@shared_task
def find_missing_homepages():
    qs = Company.objects.filter(homepage_url__isnull=True)
    total = qs.count()
    logger.info("find_missing_homepages: start (targets=%d)", total)
    updated = 0
    for company in qs:
        homepage_url = find_homepage_for_company(company.name)
        if homepage_url:
            company.homepage_url = homepage_url
            company.save(update_fields=["homepage_url"])
            updated += 1
            logger.info("find_missing_homepages: updated %s -> %s", company.name, homepage_url)
    logger.info("find_missing_homepages: done (updated=%d/%d)", updated, total)

@shared_task
def run_discover_careers_spiders():
    qs = Company.objects.filter(homepage_url__isnull=False, recruits_url__isnull=True)
    total = qs.count()
    logger.info("discover_careers: start (targets=%d)", total)

    scrapy_project_path = os.path.join(BASE_DIR, 'crawler')
    for company in qs:
        cmd = [
            'scrapy', 'crawl', 'discover_careers',
            '-a', f'company_name={company.name}',
            '-a', f'homepage_url={company.homepage_url}',
        ]
        logger.info("discover_careers: run spider for %s (%s)", company.name, company.homepage_url)
        # stdout/stderr도 워커 로그에 섞여 보이게 한다면 capture_output=False 유지
        subprocess.run(cmd, cwd=scrapy_project_path, check=False)
    logger.info("discover_careers: done")

@shared_task
def run_job_collector_spiders():
    qs = Company.objects.filter(recruits_url_status='CONFIRMED')
    total = qs.count()
    logger.info("job_collector: start (targets=%d)", total)

    scrapy_project_path = os.path.join(BASE_DIR, 'crawler')
    for company in qs:
        cmd = [
            'scrapy', 'crawl', 'job_collector',
            '-a', f"company_id={company.id}",
            '-a', f"company_name={company.name}",
            '-a', f"recruits_url={company.recruits_url}",
        ]
        logger.info("job_collector: run spider for %s (%s)", company.name, company.recruits_url)
        subprocess.run(cmd, cwd=scrapy_project_path, check=False)
    logger.info("job_collector: done")

@shared_task(name="api.tasks.run_full_crawling_cycle")
def run_full_crawling_cycle():
    logger.info("full_cycle: dispatch chain")
    workflow = chain(
        find_missing_homepages.si(),
        run_discover_careers_spiders.si(),
        run_job_collector_spiders.si(),
    )
    workflow.apply_async()
    logger.info("full_cycle: chain dispatched")

@shared_task  # 이름 생략하면 자동으로 api.tasks.hello 로 등록됨
def hello():
    logger.info("hello task start")
    time.sleep(1)
    logger.info("hello task done")
    return "ok"
