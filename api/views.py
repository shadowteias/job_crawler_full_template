# api/views.py  — 전체 교체본

import json
import logging
import redis

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets

from .permissions import HasInternalAPIToken
from .models import JobPosting
from .serializers import JobPostingSerializer

# Celery 앱은 프로젝트의 고정 엔트리포인트에서 가져온다.
from config.celery import app as celery_app

logger = logging.getLogger(__name__)

# Redis 클라이언트: settings.REDIS_URL 을 사용 (예: redis://redis:6379/0)
r = redis.from_url(getattr(settings, "REDIS_URL", "redis://redis:6379/0"))

# 상태/락 키(네가 쓰던 이름 유지)
LOCK_KEY = "crawler:lock"
STATUS_KEY = "crawler:status"


def _safe_json_loads(val):
    """bytes/str에 대해 안전하게 JSON 디코드, 실패 시 None"""
    if val is None:
        return None
    try:
        if isinstance(val, bytes):
            val = val.decode("utf-8", "ignore")
        return json.loads(val)
    except Exception:
        return None


class JobPostingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    기존에 urls.py에서 import 하던 ViewSet.
    읽기 전용으로 노출 (list/retrieve).
    """
    queryset = JobPosting.objects.all()
    serializer_class = JobPostingSerializer


class CrawlStatusView(APIView):
    """
    현재 크롤링 상태 조회:
      - running: 락 키 존재 여부
      - status: STATUS_KEY 에 저장된 JSON(payload 미설정 시 기본값)
    """
    permission_classes = [HasInternalAPIToken]

    def get(self, request):
        is_running = bool(r.get(LOCK_KEY))
        payload = _safe_json_loads(r.get(STATUS_KEY)) or {"state": "IDLE"}
        return Response({"running": is_running, "status": payload}, status=200)


class CrawlTriggerView(APIView):
    """
    수동 트리거:
      - 이미 실행 중(LOCK_KEY 존재)면 409 + 현재 상태 반환
      - 아니라면 Celery로 전체 사이클 태스크를 디스패치하고 202
    """
    permission_classes = [HasInternalAPIToken]

    def post(self, request):
        # 이미 실행 중이면 409 반환 (네가 쓰던 동작 유지)
        if r.get(LOCK_KEY):
            detail = _safe_json_loads(r.get(STATUS_KEY)) or {"state": "BUSY"}
            return Response({"detail": "already running", "status": detail}, status=409)

        try:
            # 핵심: 우리 프로젝트의 Celery 앱으로, 기본 큐 "celery"에 태스크 디스패치
            celery_app.send_task("api.tasks.run_full_crawling_cycle", queue="celery")
            return Response({"detail": "started"}, status=202)
        except Exception as e:
            logger.exception("Manual trigger failed")
            return Response({"detail": "failed", "error": str(e)}, status=500)
