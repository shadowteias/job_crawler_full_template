import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import django
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/app")
django.setup()

from django.utils import timezone

from api.company_sources import _canonicalize_url, _probe_url, _url_host
from api.models import Company


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-id", type=int, required=True)
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-fail-before-dead", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()

    companies = list(
        Company.objects.filter(id__gte=args.start_id, id__lte=args.end_id)
        .exclude(homepage_url__isnull=True)
        .exclude(homepage_url="")
        .order_by("id")
        .only(
            "id",
            "homepage_url",
            "homepage_host",
            "homepage_url_status",
            "homepage_checked_at",
            "homepage_last_status_code",
            "homepage_fail_count",
        )
    )

    def check_one(company):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": os.getenv("HOMEPAGE_CHECK_UA", "job-crawler/1.0 (+contact: admin@example.com)"),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        url = _canonicalize_url(company.homepage_url) or company.homepage_url
        status, code = _probe_url(session, url, timeout=args.timeout)
        return company.id, url, status, code

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(check_one, company): company.id for company in companies}
        for future in as_completed(futures):
            results.append(future.result())

    checked = 0
    alive = 0
    dead = 0
    updated = 0

    by_id = {company.id: company for company in companies}
    now = timezone.now()

    for company_id, url, status, code in results:
        company = by_id[company_id]
        checked += 1

        if url != company.homepage_url:
            company.homepage_url = url
            if not company.homepage_host:
                company.homepage_host = _url_host(url)

        company.homepage_last_status_code = code
        company.homepage_checked_at = now

        if status == "alive":
            company.homepage_url_status = "alive"
            company.homepage_fail_count = 0
            alive += 1
        else:
            company.homepage_fail_count = (company.homepage_fail_count or 0) + 1
            if code in (404, 410) or company.homepage_fail_count >= args.max_fail_before_dead:
                company.homepage_url_status = "dead"
                dead += 1

        company.save(
            update_fields=[
                "homepage_url",
                "homepage_host",
                "homepage_url_status",
                "homepage_checked_at",
                "homepage_last_status_code",
                "homepage_fail_count",
            ]
        )
        updated += 1

    print(
        {
            "checked": checked,
            "alive": alive,
            "dead": dead,
            "updated": updated,
            "start_id": args.start_id,
            "end_id": args.end_id,
            "workers": args.workers,
            "timeout": args.timeout,
        }
    )


if __name__ == "__main__":
    main()
