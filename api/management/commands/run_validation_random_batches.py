import json
import random
import time
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from api.models import Company, JobPosting
from api.tasks import run_discover_careers_spiders_concurrent, run_job_collector_spiders_concurrent


DISCOVERY_RESET_FIELDS = {
    "recruits_url": None,
    "page_type": None,
    "post_type": None,
    "recruits_url_status": None,
    "recruits_url_score": None,
    "external_job_site": None,
    "hiring": False,
}


def _alive_homepage_q() -> Q:
    return (
        Q(homepage_url_status="alive")
        | Q(homepage_last_status_code__gte=200, homepage_last_status_code__lt=400)
        | Q(homepage_last_status_code__in=[401, 403, 405, 406])
    )


def _compress_ranges(company_ids: list[int]) -> list[tuple[int, int]]:
    if not company_ids:
        return []

    sorted_ids = sorted(company_ids)
    ranges: list[tuple[int, int]] = []
    start = sorted_ids[0]
    end = sorted_ids[0]

    for company_id in sorted_ids[1:]:
        if company_id == end + 1:
            end = company_id
            continue
        ranges.append((start, end))
        start = company_id
        end = company_id

    ranges.append((start, end))
    return ranges


class Command(BaseCommand):
    help = (
        "alive 홈페이지 회사를 랜덤 배치로 선택해 discovery reset + 공고 삭제 후 "
        "재탐색/재수집을 반복 실행합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--target-recruits", type=int, default=21)
        parser.add_argument("--target-jobs", type=int, default=31)
        parser.add_argument("--max-iterations", type=int, default=5)
        parser.add_argument("--max-hours", type=float, default=8.0)
        parser.add_argument("--workers", type=int, default=2)
        parser.add_argument("--sleep-seconds", type=float, default=1.0)
        parser.add_argument("--seed", type=int, default=20260420)
        parser.add_argument(
            "--pool-mode",
            type=str,
            default="alive",
            choices=["alive", "alive_with_recruits", "alive_with_jobs"],
            help="sampling pool strategy",
        )
        parser.add_argument(
            "--evidence-dir",
            type=str,
            default=".sisyphus/evidence/validation-rerun",
            help="iteration evidence file output directory",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        target_recruits = options["target_recruits"]
        target_jobs = options["target_jobs"]
        max_iterations = options["max_iterations"]
        max_hours = options["max_hours"]
        workers = options["workers"]
        sleep_seconds = options["sleep_seconds"]
        seed = options["seed"]
        pool_mode = options["pool_mode"]
        evidence_dir = Path(options["evidence_dir"])

        if batch_size <= 0:
            raise CommandError("--batch-size must be > 0")
        if target_recruits <= 0:
            raise CommandError("--target-recruits must be > 0")
        if target_jobs <= 0:
            raise CommandError("--target-jobs must be > 0")
        if max_iterations <= 0:
            raise CommandError("--max-iterations must be > 0")
        if max_hours <= 0:
            raise CommandError("--max-hours must be > 0")
        if workers <= 0:
            raise CommandError("--workers must be > 0")

        evidence_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now()
        rnd = random.Random(seed)

        pool_qs = (
            Company.objects.exclude(homepage_url__isnull=True)
            .exclude(homepage_url="")
            .filter(_alive_homepage_q())
        )
        if pool_mode == "alive_with_recruits":
            pool_qs = pool_qs.exclude(recruits_url__isnull=True).exclude(recruits_url="")
        elif pool_mode == "alive_with_jobs":
            pool_qs = pool_qs.filter(job_postings__isnull=False).distinct()

        pool_ids = list(pool_qs.order_by("id").values_list("id", flat=True))

        if not pool_ids:
            raise CommandError("No alive-homepage companies found for sampling")

        used_ids: set[int] = set()
        all_iterations: list[dict] = []
        success_iteration = None

        self.stdout.write(
            self.style.NOTICE(
                f"validation-run start: pool={len(pool_ids)} batch_size={batch_size} "
                f"targets(recruits>{target_recruits-1}, jobs>{target_jobs-1}) "
                f"seed={seed} pool_mode={pool_mode}"
            )
        )

        run_started = time.time()

        for iteration_idx in range(1, max_iterations + 1):
            elapsed_hours = (time.time() - run_started) / 3600.0
            if elapsed_hours > max_hours:
                self.stdout.write(
                    self.style.WARNING(
                        f"stopping: max-hours exceeded ({elapsed_hours:.2f}h > {max_hours}h)"
                    )
                )
                break

            available_ids = [company_id for company_id in pool_ids if company_id not in used_ids]
            if not available_ids:
                self.stdout.write(self.style.WARNING("stopping: sampling pool exhausted"))
                break

            pick_size = min(batch_size, len(available_ids))
            sampled_ids = rnd.sample(available_ids, pick_size)
            sampled_ids.sort()
            used_ids.update(sampled_ids)

            sampled_qs = Company.objects.filter(id__in=sampled_ids)
            before_recruits = sampled_qs.exclude(recruits_url__isnull=True).exclude(recruits_url="").count()
            before_jobs = JobPosting.objects.filter(company_id__in=sampled_ids).count()

            with transaction.atomic():
                reset_count = sampled_qs.update(**DISCOVERY_RESET_FIELDS)
                deleted_jobs_count, _ = JobPosting.objects.filter(company_id__in=sampled_ids).delete()

            ranges = _compress_ranges(sampled_ids)
            discover_results = []
            collector_results = []

            for start_id, end_id in ranges:
                discover_results.append(
                    run_discover_careers_spiders_concurrent(
                        workers=workers,
                        company_id_start=start_id,
                        company_id_end=end_id,
                    )
                )
                collector_results.append(
                    run_job_collector_spiders_concurrent(
                        workers=workers,
                        company_id_start=start_id,
                        company_id_end=end_id,
                    )
                )

            after_recruits = (
                Company.objects.filter(id__in=sampled_ids)
                .exclude(recruits_url__isnull=True)
                .exclude(recruits_url="")
                .count()
            )
            after_jobs = JobPosting.objects.filter(company_id__in=sampled_ids).count()

            iteration_result = {
                "iteration": iteration_idx,
                "sample_size": pick_size,
                "sampled_company_ids": sampled_ids,
                "ranges": [{"start_id": s, "end_id": e} for s, e in ranges],
                "reset_count": reset_count,
                "deleted_job_rows": deleted_jobs_count,
                "before_recruits": before_recruits,
                "after_recruits": after_recruits,
                "before_jobs": before_jobs,
                "after_jobs": after_jobs,
                "new_recruits": after_recruits,
                "new_jobs": after_jobs,
                "discover_results": discover_results,
                "collector_results": collector_results,
                "threshold_recruits_met": after_recruits > (target_recruits - 1),
                "threshold_jobs_met": after_jobs > (target_jobs - 1),
            }
            all_iterations.append(iteration_result)

            evidence_file = evidence_dir / f"iteration-{iteration_idx:02d}.json"
            evidence_file.write_text(
                json.dumps(iteration_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.stdout.write(json.dumps(iteration_result, ensure_ascii=False))

            if (
                iteration_result["threshold_recruits_met"]
                and iteration_result["threshold_jobs_met"]
            ):
                success_iteration = iteration_idx
                self.stdout.write(
                    self.style.SUCCESS(
                        f"threshold met at iteration={iteration_idx} "
                        f"(recruits={after_recruits}, jobs={after_jobs})"
                    )
                )
                break

            if sleep_seconds > 0 and iteration_idx < max_iterations:
                time.sleep(sleep_seconds)

        final_summary = {
            "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "seed": seed,
            "pool_mode": pool_mode,
            "pool_size": len(pool_ids),
            "used_company_count": len(used_ids),
            "batch_size": batch_size,
            "target_recruits_gt": target_recruits - 1,
            "target_jobs_gt": target_jobs - 1,
            "max_iterations": max_iterations,
            "max_hours": max_hours,
            "iterations_run": len(all_iterations),
            "success_iteration": success_iteration,
            "threshold_met": success_iteration is not None,
            "evidence_dir": str(evidence_dir),
        }

        summary_file = evidence_dir / "run-summary.json"
        summary_file.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8")

        if success_iteration is None:
            self.stdout.write(self.style.WARNING(json.dumps(final_summary, ensure_ascii=False)))
            raise CommandError("Thresholds were not met within configured bounds")

        self.stdout.write(self.style.SUCCESS(json.dumps(final_summary, ensure_ascii=False)))
