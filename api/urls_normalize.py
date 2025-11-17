from django.urls import path
from .views_extract import CounselingNormalizeView

urlpatterns = [
    path("counseling", CounselingNormalizeView.as_view(), name="normalize_counseling"),
]
