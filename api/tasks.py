from celery import shared_task, chain
from celery.utils.log import get_task_logger
from django.conf import settings
from .models import Company
from .utils import find_homepage_for_company
import subprocess
import os

logger = get_task_logger(__name__)

SCRAPY_PROJECT_PATH = os.path.join(settings.BASE_DIR, "crawler")


@shared_task
def find_missing_homepages():
    qs = Company.objects.filter(homepage_url__isnull=True)
    total = qs.count()
    logger.info("find_missing_homepages: start (targets=%s)", total)

    updated = 0
    for company in qs:
        url = find_homepage_for_company(company.name)
        if url:
            company.homepage_url = url
            company.save(update_fields=["homepage_url"])
            updated += 1

    logger.info("find_missing_homepages: done (updated=%s/%s)", updated, total)
    return {"targets": total, "updated": updated}


# @shared_task
# def run_discover_careers_spiders():
#     qs = Company.objects.filter(
#         homepage_url__isnull=False,
#         recruits_url__isnull=True,
#     )
#     total = qs.count()
#     logger.info("discover_careers: start (targets=%s)", total)

#     for company in qs:
#         cmd = [
#             "scrapy",
#             "crawl",
#             "discover_careers",
#             "-a",
#             f"company_name={company.name}",
#             "-a",
#             f"homepage_url={company.homepage_url}",
#         ]
#         subprocess.run(cmd, cwd=SCRAPY_PROJECT_PATH)

#     logger.info("discover_careers: done")
#     return {"targets": total}

@shared_task
def run_discover_careers_spiders():
    from .models import Company
    from config.settings import BASE_DIR
    import subprocess
    import os

    companies = Company.objects.filter(
        homepage_url__isnull=False,
        recruits_url__isnull=True,
    )

    for c in companies:
        scrapy_project_path = os.path.join(BASE_DIR, "crawler")
        cmd = [
            "scrapy", "crawl", "discover_careers",
            "-a", f"company_id={c.id}",
            "-a", f"homepage_url={c.homepage_url}",
        ]
        subprocess.run(cmd, cwd=scrapy_project_path)

@shared_task
def run_job_collector_spiders():
    qs = Company.objects.filter(recruits_url__isnull=False)
    total = qs.count()
    logger.info("job_collector: start (targets=%s)", total)

    for company in qs:
        cmd = [
            "scrapy",
            "crawl",
            "job_collector",
            "-a",
            f"company_id={company.id}",
            "-a",
            f"company_name={company.name}",
            "-a",
            f"recruits_url={company.recruits_url}",
        ]
        subprocess.run(cmd, cwd=SCRAPY_PROJECT_PATH)

    logger.info("job_collector: done")
    return {"targets": total}


@shared_task(name="api.tasks.run_full_crawling_cycle")
def run_full_crawling_cycle():
    logger.info("full_cycle: dispatch chain")
    workflow = chain(
        find_missing_homepages.s(),
        run_discover_careers_spiders.s(),
        run_job_collector_spiders.s(),
    )
    workflow.apply_async()
    logger.info("full_cycle: chain dispatched")
    return "queued"
