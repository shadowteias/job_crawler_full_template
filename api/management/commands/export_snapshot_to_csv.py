import csv
import json
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import Company, JobPosting


def normalize_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    text = str(value)
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


class Command(BaseCommand):
    help = "Company / JobPosting 데이터를 날짜 포함 CSV 파일로 data/ 아래에 내보냅니다."

    company_fields = [
        "id",
        "name",
        "name_norm",
        "homepage_url",
        "homepage_host",
        "homepage_url_status",
        "homepage_checked_at",
        "homepage_last_status_code",
        "homepage_fail_count",
        "recruits_url",
        "page_type",
        "post_type",
        "hiring",
        "recruits_url_status",
        "recruits_url_score",
        "external_job_site",
        "ceo_name",
        "bizr_no",
        "stock_code",
        "dart_corp_code",
        "dart_modify_date",
        "est_dt",
        "acc_mt",
        "swdb_fin_year",
        "industry",
        "address",
        "region",
        "source_meta",
        "created_at",
        "updated_at",
    ]

    job_fields = [
        "id",
        "company_id",
        "company_name",
        "title",
        "post_url",
        "job_description",
        "qualifications",
        "preferred_qualifications",
        "hiring_process",
        "benefits",
        "hiring_message",
        "location",
        "employment_type",
        "salary",
        "work_hours",
        "posted_at",
        "deadline_at",
        "status",
        "crawled_at",
        "first_seen_at",
        "is_active",
    ]

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="date_str", required=True, help="파일명에 넣을 날짜 문자열 (예: 2026-04-02)")
        parser.add_argument("--company-output", dest="company_output")
        parser.add_argument("--job-output", dest="job_output")

    def handle(self, *args, **options):
        date_str = options["date_str"]
        base_dir = Path(settings.BASE_DIR) / "data"
        base_dir.mkdir(parents=True, exist_ok=True)

        company_path = Path(options["company_output"]) if options.get("company_output") else (base_dir / f"{date_str}_companies_snapshot.csv")
        job_path = Path(options["job_output"]) if options.get("job_output") else (base_dir / f"{date_str}_job_postings_snapshot.csv")

        self.export_companies(company_path)
        self.export_job_postings(job_path)

        self.stdout.write(self.style.SUCCESS(f"company_csv={company_path}"))
        self.stdout.write(self.style.SUCCESS(f"job_csv={job_path}"))

    def export_companies(self, output_path: Path):
        qs = Company.objects.all().order_by("id")
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=self.company_fields,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
                extrasaction="ignore",
            )
            writer.writeheader()
            for company in qs.iterator(chunk_size=500):
                row = {field: normalize_csv_value(getattr(company, field, "")) for field in self.company_fields}
                writer.writerow(row)

    def export_job_postings(self, output_path: Path):
        qs = JobPosting.objects.select_related("company").order_by("id")
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=self.job_fields,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
                extrasaction="ignore",
            )
            writer.writeheader()
            for job in qs.iterator(chunk_size=500):
                row = {
                    "id": normalize_csv_value(job.id),
                    "company_id": normalize_csv_value(job.company_id),
                    "company_name": normalize_csv_value(job.company.name if job.company_id else ""),
                    "title": normalize_csv_value(job.title),
                    "post_url": normalize_csv_value(job.post_url),
                    "job_description": normalize_csv_value(job.job_description),
                    "qualifications": normalize_csv_value(job.qualifications),
                    "preferred_qualifications": normalize_csv_value(job.preferred_qualifications),
                    "hiring_process": normalize_csv_value(job.hiring_process),
                    "benefits": normalize_csv_value(job.benefits),
                    "hiring_message": normalize_csv_value(job.hiring_message),
                    "location": normalize_csv_value(job.location),
                    "employment_type": normalize_csv_value(job.employment_type),
                    "salary": normalize_csv_value(job.salary),
                    "work_hours": normalize_csv_value(job.work_hours),
                    "posted_at": normalize_csv_value(job.posted_at),
                    "deadline_at": normalize_csv_value(job.deadline_at),
                    "status": normalize_csv_value(job.status),
                    "crawled_at": normalize_csv_value(job.crawled_at),
                    "first_seen_at": normalize_csv_value(job.first_seen_at),
                    "is_active": normalize_csv_value(job.is_active),
                }
                writer.writerow(row)
