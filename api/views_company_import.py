import csv
import io
import re
from urllib.parse import urlparse

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company
from .permissions import HasInternalAPIToken


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _normalize_name(name: str) -> str:
    text = (name or "").strip().lower()
    if not text:
        return ""
    for token in ["주식회사", "(주)", "㈜", "inc.", "inc", "corp.", "corp", "co., ltd.", "co.,ltd.", "co ltd", "ltd.", "ltd", "llc"]:
        text = text.replace(token, " ")
    text = re.sub(r"[^\w가-힣]+", "", text)
    return text


def _canonical_homepage(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    if not raw:
        return "", ""
    normalized = raw
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "", ""
    canonical = f"https://{host}"
    return canonical, host


def _clean_row_value(row: dict, key: str) -> str:
    return str(row.get(key, "") or "").strip()


class CompanyImportCSVView(APIView):
    permission_classes = [HasInternalAPIToken]

    IMPORTABLE_FIELDS = [
        "recruits_url",
        "page_type",
        "post_type",
        "region",
        "industry",
        "address",
        "external_job_site",
    ]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        csv_text = str(payload.get("csv_text") or "").strip()
        uploaded = request.FILES.get("csv_file") if hasattr(request, "FILES") else None
        if uploaded is not None:
            csv_text = uploaded.read().decode("utf-8-sig", errors="ignore").strip()
        if not csv_text:
            return Response({"detail": "field 'csv_text' or multipart file field 'csv_file' is required"}, status=status.HTTP_400_BAD_REQUEST)

        update_existing = _truthy(payload.get("update_existing", True))
        dry_run = _truthy(payload.get("dry_run", False))

        reader = csv.DictReader(io.StringIO(csv_text))
        columns = reader.fieldnames or []
        if "company_name" not in columns:
            return Response({"detail": "CSV must include 'company_name' column"}, status=status.HTTP_400_BAD_REQUEST)

        created = 0
        updated = 0
        skipped = 0
        invalid = 0
        rows_result = []

        for line_no, row in enumerate(reader, start=2):
            name = _clean_row_value(row, "company_name")
            homepage_url = _clean_row_value(row, "homepage_url")
            canonical_homepage, homepage_host = _canonical_homepage(homepage_url)
            name_norm = _normalize_name(name)

            if not name:
                invalid += 1
                rows_result.append({"line": line_no, "status": "invalid", "reason": "company_name is empty"})
                continue

            candidates = Company.objects.filter(
                Q(name=name)
                | (Q(name_norm=name_norm) if name_norm else Q(pk__in=[]))
                | (Q(homepage_host=homepage_host) if homepage_host else Q(pk__in=[]))
            ).order_by("id")
            company = candidates.first()

            input_data = {
                "name": name,
                "name_norm": name_norm or None,
                "homepage_url": canonical_homepage or None,
                "homepage_host": homepage_host or None,
            }
            for field in self.IMPORTABLE_FIELDS:
                value = _clean_row_value(row, field)
                if value:
                    input_data[field] = value

            hiring_value = _clean_row_value(row, "hiring").lower()
            if hiring_value:
                if hiring_value in {"1", "true", "yes", "y", "t"}:
                    input_data["hiring"] = True
                elif hiring_value in {"0", "false", "no", "n", "f"}:
                    input_data["hiring"] = False

            if company is None:
                if not dry_run:
                    Company.objects.create(**input_data)
                created += 1
                rows_result.append({
                    "line": line_no,
                    "status": "created",
                    "company_name": name,
                    "match_key": "none",
                })
                continue

            if not update_existing:
                skipped += 1
                rows_result.append({
                    "line": line_no,
                    "status": "skipped",
                    "company_id": company.id,
                    "company_name": company.name,
                    "reason": "duplicate found and update_existing=false",
                })
                continue

            changes = {}
            for field, value in input_data.items():
                current = getattr(company, field)
                if value and current != value:
                    changes[field] = {"from": current, "to": value}
                    setattr(company, field, value)

            if changes:
                if not dry_run:
                    company.save()
                updated += 1
                rows_result.append({
                    "line": line_no,
                    "status": "updated",
                    "company_id": company.id,
                    "company_name": company.name,
                    "changes": sorted(changes.keys()),
                })
            else:
                skipped += 1
                rows_result.append({
                    "line": line_no,
                    "status": "skipped",
                    "company_id": company.id,
                    "company_name": company.name,
                    "reason": "duplicate with no changes",
                })

        return Response(
            {
                "summary": {
                    "total_rows": len(rows_result),
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "invalid": invalid,
                    "dry_run": dry_run,
                    "update_existing": update_existing,
                    "dedupe_strategy": ["name exact", "name_norm", "homepage_host"],
                },
                "rows": rows_result,
            },
            status=status.HTTP_200_OK,
        )
