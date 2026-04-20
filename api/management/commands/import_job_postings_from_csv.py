import csv
from datetime import datetime

from django.core.management.base import BaseCommand

from api.models import Company, JobPosting


def _parse_datetime(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue
    return None


def _parse_bool(value: str) -> bool:
    value = (value or "").strip().lower()
    return value in {"1", "true", "t", "yes", "y"}


class Command(BaseCommand):
    help = "Import JobPosting rows from CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to job postings CSV file")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing job postings when post_url already exists",
        )

    def handle(self, *args, **options):
        csv_file = options["csv_file"]
        update_existing = options.get("update", False)

        self.stdout.write(f"Importing job postings from {csv_file}...")

        created = 0
        updated = 0
        skipped = 0
        missing_company = 0

        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                post_url = (row.get("post_url") or "").strip()
                title = (row.get("title") or "").strip()
                company_id = (row.get("company_id") or "").strip()

                if not post_url or not title or not company_id:
                    skipped += 1
                    continue

                company = Company.objects.filter(id=company_id).first()
                if not company:
                    missing_company += 1
                    continue

                data = {
                    "company": company,
                    "title": title,
                    "job_description": (row.get("job_description") or "").strip() or None,
                    "qualifications": (row.get("qualifications") or "").strip() or None,
                    "preferred_qualifications": (row.get("preferred_qualifications") or "").strip() or None,
                    "hiring_process": (row.get("hiring_process") or "").strip() or None,
                    "benefits": (row.get("benefits") or "").strip() or None,
                    "hiring_message": (row.get("hiring_message") or "").strip() or None,
                    "location": (row.get("location") or "").strip() or None,
                    "employment_type": (row.get("employment_type") or "").strip() or None,
                    "salary": (row.get("salary") or "").strip() or None,
                    "work_hours": (row.get("work_hours") or "").strip() or None,
                    "posted_at": _parse_date(row.get("posted_at") or ""),
                    "deadline_at": _parse_date(row.get("deadline_at") or ""),
                    "status": (row.get("status") or "").strip() or "active",
                    "is_active": _parse_bool(row.get("is_active") or "true"),
                }

                existing = JobPosting.objects.filter(post_url=post_url).first()
                if existing and update_existing:
                    for key, value in data.items():
                        setattr(existing, key, value)
                    first_seen_at = _parse_datetime(row.get("first_seen_at") or "")
                    if first_seen_at:
                        existing.first_seen_at = first_seen_at
                    existing.save()
                    updated += 1
                    continue

                if existing:
                    skipped += 1
                    continue

                job = JobPosting.objects.create(post_url=post_url, **data)
                first_seen_at = _parse_datetime(row.get("first_seen_at") or "")
                if first_seen_at:
                    JobPosting.objects.filter(id=job.id).update(first_seen_at=first_seen_at)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: created={created}, updated={updated}, skipped={skipped}, missing_company={missing_company}"
            )
        )
