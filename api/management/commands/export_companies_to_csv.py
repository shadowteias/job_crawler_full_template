# api/management/commands/export_companies_to_csv.py

from django.core.management.base import BaseCommand
from api.models import Company
import csv
import os


class Command(BaseCommand):
    help = "Company 테이블을 CSV로 덤프합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            default="companies_export.csv",
            help="저장할 CSV 파일 경로 (기본: companies_export.csv)",
        )

    def handle(self, *args, **options):
        output_path = options["output"]

        # docker-compose에서 .:/app 마운트하니까,
        # 상대 경로로 쓰면 호스트 프로젝트 폴더에 바로 생김.
        abs_path = os.path.abspath(output_path)

        fields = [
            "name",
            "homepage_url",
            "recruits_url",
            # 필요하면 여기 회사 모델의 다른 필드들도 추가
            # 예: "memo", "source", ...
        ]

        qs = Company.objects.all().order_by("id")

        with open(abs_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            for c in qs:
                writer.writerow([
                    c.name,
                    c.homepage_url or "",
                    c.recruits_url or "",
                ])

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {qs.count()} companies to {abs_path}"
            )
        )
