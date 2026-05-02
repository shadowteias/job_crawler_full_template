from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobPostingViewSet, CrawlStatusView, ManualCrawlRunView
from .views_jobs import JobPostingListView
from .views_match import student_top_view, company_top_view, batch_match_view
from .views_parser import JobParserTestView
from .views_company_import import CompanyImportCSVView


router = DefaultRouter()
router.register(r'job-postings', JobPostingViewSet, basename='job-postings')

urlpatterns = [
    path('', include(router.urls)),
    path('crawl/status/',  CrawlStatusView.as_view(),  name='crawl-status'),
    path('crawl/run/', ManualCrawlRunView.as_view(), name='crawl-run-manual'),

    path("normalize/", include("api.urls_normalize")),
    path("jobs", JobPostingListView.as_view(), name="api-jobs-list"),
    path("parse/job/", JobParserTestView.as_view(), name="api-parse-job-test"),
    path("companies/import-csv/", CompanyImportCSVView.as_view(), name="api-companies-import-csv"),

    # 매칭 API
    path("match/student-top", student_top_view, name="api-match-student-top"),
    path("match/company-top", company_top_view, name="api-match-company-top"),
    path("match/batch", batch_match_view, name="api-match-batch"),
]
