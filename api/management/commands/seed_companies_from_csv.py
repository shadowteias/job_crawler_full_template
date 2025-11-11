import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from api.models import Company


# 여러 인코딩을 시도해서 CSV 파일을 여는 유틸
POSSIBLE_ENCODINGS = (
    "utf-8-sig",  # UTF-8 with BOM (엑셀 등)
    "cp949",      # 윈도우 한글
    "euc-kr",     # 구형 한글
)


def open_csv_safely(csv_path: Path):
    """
    여러 인코딩을 시도해서 CSV 파일을 연는다.
    모두 실패하면 utf-8(errors=ignore)로 연다.
    """
    last_err = None

    for enc in POSSIBLE_ENCODINGS:
        try:
            f = csv_path.open(encoding=enc, newline="")
            # 한 줄 읽어보고 문제 없으면 채택
            f.readline()
            f.seek(0)
            return f
        except UnicodeDecodeError as e:
            last_err = e

    # 최후 수단: 문제 되는 글자는 버리고 진행
    f = csv_path.open(encoding="utf-8", errors="ignore", newline="")
    return f


class Command(BaseCommand):
    help = (
        "data/companies.csv 로 Company 테이블을 시딩/업데이트합니다.\n"
        "- 컬럼: company_name, homepage_url, recruits_url, page_type, post_type, hiring, region\n"
        "- 기존 레코드는 유지하고, CSV에 값이 있는 컬럼만 갱신합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            help="CSV 파일 경로 (기본: BASE_DIR/data/companies.csv)",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        csv_path = Path(options["path"]) if options.get("path") else (base_dir / "data" / "companies.csv")

        if not csv_path.exists():
            raise CommandError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

        self.stdout.write(self.style.NOTICE(f"CSV 로딩: {csv_path}"))

        # 파일 열기 (인코딩 자동 판단)
        f = open_csv_safely(csv_path)

        created = 0
        updated = 0
        skipped = 0

        with f:
            reader = csv.DictReader(f)

            # 컬럼 체크 (정확한 이름만 사용)
            required = ["company_name"]
            for col in required:
                if col not in (reader.fieldnames or []):
                    raise CommandError(f"CSV에 필수 컬럼이 없습니다: {col}")

            for idx, row in enumerate(reader, start=2):  # 2행부터 데이터
                name = (row.get("company_name") or "").strip()
                if not name:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(f"[line {idx}] company_name 비어있음 -> 건너뜀")
                    )
                    continue

                company, created_flag = Company.objects.get_or_create(name=name)
                if created_flag:
                    created += 1
                else:
                    updated += 1

                # homepage_url
                homepage = (row.get("homepage_url") or "").strip()
                if homepage:
                    company.homepage_url = homepage

                # recruits_url
                recruits = (row.get("recruits_url") or "").strip()
                if recruits:
                    company.recruits_url = recruits

                # page_type (값이 있으면 그대로 사용)
                page_type = (row.get("page_type") or "").strip()
                if page_type:
                    company.page_type = page_type

                # post_type (값이 있으면 그대로 사용)
                post_type = (row.get("post_type") or "").strip()
                if post_type:
                    company.post_type = post_type

                # hiring (간단한 bool 파싱)
                hiring_raw = (row.get("hiring") or "").strip().lower()
                if hiring_raw:
                    if hiring_raw in ("1", "y", "yes", "true", "t"):
                        company.hiring = True
                    elif hiring_raw in ("0", "n", "no", "false", "f"):
                        company.hiring = False
                    # 애매하면 그냥 건너뜀 (기존 값 유지)

                # region
                region = (row.get("region") or "").strip()
                if region:
                    company.region = region

                company.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: created={created}, updated={updated}, skipped={skipped}"
            )
        )
