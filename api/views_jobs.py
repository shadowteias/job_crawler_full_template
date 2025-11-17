# api/views_jobs.py
from django.db.models import Q
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer

from api.models import JobPosting
from api.serializers import JobPostingSerializer


class JobsPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100
    page_size = 20


class JobPostingListView(ListAPIView):
    """
    읽기 전용 구인공고 목록 API
    - 쿼리:
      * active=1|0 (is_active 필터)
      * q=검색어 (title/job_description/qualifications/ preferred_qualifications)
      * company=회사명 부분일치
      * region=회사 region 부분일치
      * page_size=페이지 크기(기본 20, 최대 100)
    - 항상 JSON으로 응답
    """
    serializer_class = JobPostingSerializer
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    pagination_class = JobsPagination

    def get_queryset(self):
        qs = JobPosting.objects.select_related("company").order_by("-id")

        active = self.request.query_params.get("active")
        if active in ("1", "true", "True", "t", "yes", "y"):
            qs = qs.filter(is_active=True)
        elif active in ("0", "false", "False", "f", "no", "n"):
            qs = qs.filter(is_active=False)

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(job_description__icontains=q)
                | Q(qualifications__icontains=q)
                | Q(preferred_qualifications__icontains=q)
            )

        company = self.request.query_params.get("company")
        if company:
            qs = qs.filter(company__name__icontains=company)

        region = self.request.query_params.get("region")
        if region:
            qs = qs.filter(company__region__icontains=region)

        return qs
