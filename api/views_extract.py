from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .counseling_field_extractor import extract_from_text  # ← 여기만 변경

def _check_api_key(request):
    want = getattr(settings, "API_INTERNAL_TOKEN", None)
    got = request.headers.get("X-API-KEY") or request.headers.get("Authorization", "").replace("Bearer ", "")
    return bool(want) and want == got

class CounselingNormalizeView(APIView):
    """
    POST /api/normalize/counseling
    헤더: X-API-KEY: <API_INTERNAL_TOKEN>
    바디:
      {
        "text": "...긴 상담 텍스트...",
        "only_fields": ["급여","근무지", ...]   // 선택
      }
    응답: 추출/정규화된 표준 필드 dict
    """
    def post(self, request, *args, **kwargs):
        if not _check_api_key(request):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        text = request.data.get("text") or ""
        only_fields = request.data.get("only_fields")
        try:
            data = extract_from_text(text, only_fields=only_fields)
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": f"extract error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
