import json
import time

from django.core.management.base import BaseCommand
from django.db.models import Count

from api.models import Company, JobPosting
from api.tasks import run_discover_careers_spiders_concurrent, run_job_collector_spiders_concurrent


class Command(BaseCommand):
    help = (
        "지정한 회사 ID 범위에 대해 채용 페이지 탐색과 채용공고 수집을 안정 모드로 다시 실행합니다.\n"
        "- discovery 관련 필드(recruits_url/page_type/post_type 등)를 chunk 단위로 초기화 후 다시 탐색\n"
        "- job collector는 기존 JobPosting을 upsert 하므로 안전하게 재실행 가능\n"
        "- WSL/Docker 안정성을 위해 작은 chunk + 낮은 workers 사용 권장"
    )

    def add_arguments(self, parser):
        parser.add_argument("--start-id", type=int, required=True)
        parser.add_argument("--end-id", type=int, required=True)
        parser.add_argument("--chunk-size", type=int, default=25)
        parser.add_argument("--workers", type=int, default=2)
        parser.add_argument("--sleep-seconds", type=float, default=1.0)

    def handle(self, *args, **options):
        start_id = options["start_id"]
        end_id = options["end_id"]
        chunk_size = options["chunk_size"]
        workers = options["workers"]
        sleep_seconds = options["sleep_seconds"]

        summary = {
            "start_id": start_id,
            "end_id": end_id,
            "chunk_size": chunk_size,
            "workers": workers,
            "chunks": [],
        }

        for chunk_start in range(start_id, end_id + 1, chunk_size):
            chunk_end = min(chunk_start + chunk_size - 1, end_id)

            before_jobs = JobPosting.objects.filter(company__id__gte=chunk_start, company__id__lte=chunk_end).count()

            reset_count = Company.objects.filter(id__gte=chunk_start, id__lte=chunk_end).update(
                recruits_url=None,
                page_type=None,
                post_type=None,
                recruits_url_status=None,
                recruits_url_score=None,
                external_job_site=None,
                hiring=False,
            )

            self.stdout.write(
                self.style.NOTICE(
                    f"[chunk {chunk_start}-{chunk_end}] discovery reset applied to {reset_count} companies"
                )
            )

            discover_result = run_discover_careers_spiders_concurrent(
                workers=workers,
                company_id_start=chunk_start,
                company_id_end=chunk_end,
            )

            collector_result = run_job_collector_spiders_concurrent(
                workers=workers,
                company_id_start=chunk_start,
                company_id_end=chunk_end,
            )

            recruits_found = Company.objects.filter(id__gte=chunk_start, id__lte=chunk_end).exclude(
                recruits_url__isnull=True
            ).exclude(recruits_url="").count()

            jobs_after = JobPosting.objects.filter(company__id__gte=chunk_start, company__id__lte=chunk_end).count()

            chunk_summary = {
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "discover": discover_result,
                "collector": collector_result,
                "recruits_found": recruits_found,
                "job_postings_total_after": jobs_after,
                "job_postings_delta": jobs_after - before_jobs,
            }
            summary["chunks"].append(chunk_summary)

            self.stdout.write(json.dumps(chunk_summary, ensure_ascii=False))

            if sleep_seconds > 0 and chunk_end < end_id:
                time.sleep(sleep_seconds)

        aggregate = Company.objects.filter(id__gte=start_id, id__lte=end_id).aggregate(total=Count("id"))
        summary["total_companies"] = aggregate["total"] or 0
        summary["alive_companies"] = Company.objects.filter(
            id__gte=start_id,
            id__lte=end_id,
            homepage_url_status="alive",
        ).count()
        summary["recruits_found_total"] = Company.objects.filter(id__gte=start_id, id__lte=end_id).exclude(
            recruits_url__isnull=True
        ).exclude(recruits_url="").count()
        summary["job_postings_total"] = JobPosting.objects.filter(
            company__id__gte=start_id,
            company__id__lte=end_id,
        ).count()

        self.stdout.write(self.style.SUCCESS(json.dumps(summary, ensure_ascii=False)))
