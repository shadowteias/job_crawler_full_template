from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobPostingViewSet, CrawlTriggerView, CrawlStatusView
from .views_jobs import JobPostingListView
from .views_match import student_top_view, company_top_view, batch_match_view


router = DefaultRouter()
router.register(r'job-postings', JobPostingViewSet, basename='job-postings')

urlpatterns = [
    path('', include(router.urls)),
    path('crawl/trigger/', CrawlTriggerView.as_view(), name='crawl-trigger'),
    path('crawl/status/',  CrawlStatusView.as_view(),  name='crawl-status'),

    path("normalize/", include("api.urls_normalize")),
    path("jobs", JobPostingListView.as_view(), name="api-jobs-list"),

    # 매칭 API
    path("match/student-top", student_top_view, name="api-match-student-top"),
    path("match/company-top", company_top_view, name="api-match-company-top"),
    path("match/batch", batch_match_view, name="api-match-batch"),
]
