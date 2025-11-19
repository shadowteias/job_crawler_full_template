# api/views_match.py
from __future__ import annotations
import json
from typing import Any, Dict, List
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .matching import top_jobs_for_student, top_students_for_company, batch_match

def _auth_ok(request) -> bool:
    return request.headers.get("X-API-KEY") == getattr(settings, "API_INTERNAL_TOKEN", None)

@csrf_exempt
@require_POST
def student_top_view(request):
    if not _auth_ok(request):
        return HttpResponseForbidden(JsonResponse({"detail": "Unauthorized"}, status=401).content)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(JsonResponse({"detail": f"Bad JSON: {e}"}).content)

    student = payload.get("student")
    limit = int(payload.get("limit", 3))
    if not isinstance(student, dict):
        return HttpResponseBadRequest(JsonResponse({"detail": "field 'student' (object) is required"}).content)

    results = top_jobs_for_student(student, limit=limit)
    return JsonResponse({"results": results}, json_dumps_params={"ensure_ascii": False})

@csrf_exempt
@require_POST
def company_top_view(request):
    if not _auth_ok(request):
        return HttpResponseForbidden(JsonResponse({"detail": "Unauthorized"}, status=401).content)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(JsonResponse({"detail": f"Bad JSON: {e}"}).content)

    company_id = payload.get("company_id")
    students = payload.get("students")
    limit = int(payload.get("limit", 3))

    if not isinstance(company_id, int):
        return HttpResponseBadRequest(JsonResponse({"detail": "field 'company_id' (int) is required"}).content)
    if not isinstance(students, list):
        return HttpResponseBadRequest(JsonResponse({"detail": "field 'students' (array) is required"}).content)

    results = top_students_for_company(company_id, students, limit=limit)
    return JsonResponse({"results": results}, json_dumps_params={"ensure_ascii": False})

@csrf_exempt
@require_POST
def batch_match_view(request):
    if not _auth_ok(request):
        return HttpResponseForbidden(JsonResponse({"detail": "Unauthorized"}, status=401).content)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return HttpResponseBadRequest(JsonResponse({"detail": f"Bad JSON: {e}"}).content)

    students = payload.get("students") or []
    company_ids = payload.get("company_ids")
    topk = int(payload.get("topk", 3))
    if not isinstance(students, list):
        return HttpResponseBadRequest(JsonResponse({"detail": "field 'students' (array) is required"}).content)

    results = batch_match(students, company_ids=company_ids, topk=topk)
    return JsonResponse(results, json_dumps_params={"ensure_ascii": False})
