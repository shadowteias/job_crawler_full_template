# api/management/commands/seed_companies_from_csv.py

import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings

from api.models import Company


POSSIBLE_ENCODINGS = (
    "utf-8-sig",  # UTF-8 with BOM (요즘 에디터/엑셀)
    "cp949",      # 윈도우 한글 기본
    "euc-kr",     # 예전 한글 인코딩
)


def open_csv_safely(csv_path: Path):
    """
    여러 인코딩을 시도해서 CSV 파일을 연다.
    모두 실패하면 utf-8(errors=ignore)로라도 연다.
    """
    last_err = None

    for enc in POSSIBLE_ENCODINGS:
        try:
            f = csv_path.open(encoding=enc)
            # 한 줄 읽어보고 문제 없으면 그 인코딩 채택
            f.readline()
            f.seek(0)
            return f
        except UnicodeDecodeError as e:
            last_err = e

    # 여기까지 오면 전부 실패한 것 → 최후 수단
    # (문제 되는 글자는 날리고라도 진행)
    f = csv_path.open(encoding="utf-8", errors="ignore")
    return f


class Command(BaseCommand):
    help = "Seed Company table from CSV (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="data/companies.csv",
            help="CSV 경로 (프로젝트 BASE_DIR 기준)",
        )

    def handle(self, *args, **options):
        csv_path = Path(settings.BASE_DIR) / options["path"]

        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV not found: {csv_path}"))
            return

        # 모델에 필드 있는지 확인 후, 있을 때만 세팅
        has_has_answer = hasattr(Company, "has_answer")
        has_answer_url = hasattr(Company, "answer_url")
        has_recruits_status = hasattr(Company, "recruits_url_status")

        created = 0
        updated = 0

        with open_csv_safely(csv_path) as f:
            reader = csv.DictReader(f)

            for row in reader:
                # 회사 이름 컬럼: name / company_name / 회사명 등 다양성 고려 가능
                name = (
                    row.get("name")
                    or row.get("company_name")
                    or row.get("회사명")
                    or ""
                ).strip()
                if not name:
                    continue

                homepage_url = (
                    row.get("homepage_url")
                    or row.get("homepage")
                    or ""
                ).strip() or None

                recruits_url = (
                    row.get("recruits_url")
                    or row.get("recruits.url")
                    or row.get("채용URL")
                    or ""
                ).strip() or None

                has_answer_val = (row.get("has_answer") or "").strip().lower()
                answer_url_val = (row.get("answer_url") or "").strip() or None

                defaults = {}

                # homepage_url 있으면 저장
                if homepage_url:
                    defaults["homepage_url"] = homepage_url

                # recruits_url 있으면 저장 + 상태를 CONFIRMED로 (필드 있으면)
                if recruits_url:
                    defaults["recruits_url"] = recruits_url
                    if has_recruits_status:
                        defaults["recruits_url_status"] = "CONFIRMED"

                # 정답 레이블 (있을 때만)
                if has_has_answer and has_answer_val in ("1", "true", "y", "yes"):
                    defaults["has_answer"] = True
                if has_answer_url and answer_url_val:
                    defaults["answer_url"] = answer_url_val

                obj, is_created = Company.objects.update_or_create(
                    name=name,
                    defaults=defaults,
                )

                if is_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completed. created={created}, updated={updated}"
            )
        )
