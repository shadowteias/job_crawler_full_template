# api/management/commands/import_trainees.py

import csv
import os
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime, parse_date
from api.models import Trainee

BENEFIT_KEYWORDS = [
    "식대", "재택근무", "건강검진", "교육비", "사내스터디", "컨퍼런스참가비",
    "운동비", "도서구입비", "경조사비", "경조휴가", "스톡옵션", "자율출퇴근제",
]


class Command(BaseCommand):
    help = "IT_직업훈련학교_학생_상담일지 CSV를 Trainee 테이블로 import"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        path = options["csv_path"]
        if not os.path.exists(path):
            self.stderr.write(f"File not found: {path}")
            return

        encodings = ["utf-8-sig", "cp949", "euc-kr"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc) as f:
                    rows = list(csv.DictReader(f))
                self.stdout.write(f"Using encoding: {enc}")
                break
            except UnicodeDecodeError:
                rows = None
        if rows is None:
            self.stderr.write("Failed to decode CSV with utf-8-sig/cp949/euc-kr")
            return

        total = 0
        for idx, row in enumerate(rows, start=1):
            # 복리후생 파싱
            welfare_raw = (row.get("복리후생") or "").replace(" ", "")
            welfare_selected = []
            for b in BENEFIT_KEYWORDS:
                if b in welfare_raw:
                    welfare_selected.append(b)
            welfare_str = ",".join(sorted(set(welfare_selected)))

            # 필수조건 (기본은 raw 저장, 나중에 코드화 룰 추가)
            required_raw = (row.get("필수조건") or "").strip()
            required_codes = []
            if "재택" in required_raw:
                required_codes.append("BENEFIT_재택근무")
            if "식대" in required_raw:
                required_codes.append("BENEFIT_식대")
            # 필요시 규칙 추가
            required_str = ",".join(sorted(set(required_codes)))

            date_raw = row.get("날짜") or ""
            counseling_date = parse_datetime(date_raw) or parse_date(date_raw)

            trainee, _ = Trainee.objects.update_or_create(
                student_code=row.get("학생ID"),
                defaults={
                    "counseling_date": counseling_date,
                    "name_alias": row.get("이름(가명)") or "",
                    "birth_date": parse_date(row.get("생년월일") or "") or None,
                    "gender": self._map_gender(row.get("성별")),
                    "education_level": row.get("학력") or "",
                    "major": row.get("전공") or "",
                    "academy_rank": self._to_int(row.get("학원 성적(등수)")),
                    "career_summary": row.get("경력") or "",
                    "career_months": self._to_int(row.get("경력기간(M)")),
                    "course_name": row.get("과정명") or "",
                    "counseling_summary": row.get("상담내용 요약") or "",
                    "counselor_name": row.get("상담교사") or "",
                    "note": row.get("비고(위험/특이사항)") or "",
                    "preferred_company_size": self._to_int(row.get("근무인원")),
                    "preferred_industry": row.get("업종분류") or "",
                    "preferred_employment_type": row.get("구인구분(신입,경력)") or "",
                    "preferred_job_skill": row.get("구인기술") or "",
                    "preferred_location": row.get("근무지") or "",
                    "preferred_salary": row.get("급여") or "",
                    "tech_stack": row.get("기술스택") or "",
                    "welfare_preferences": welfare_str,
                    "required_conditions": required_str,
                    "lot_number": row.get("lot_number") or "",
                    # is_employed: 기본 False 유지
                },
            )
            total += 1

        self.stdout.write(f"Imported/updated {total} trainees.")

    def _to_int(self, value):
        try:
            return int(str(value).strip())
        except Exception:
            return None

    def _map_gender(self, g):
        g = (g or "").strip()
        if g.startswith("남"):
            return "M"
        if g.startswith("여"):
            return "F"
        return ""
