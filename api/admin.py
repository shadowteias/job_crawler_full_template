from django.contrib import admin
from .models import Company, JobPosting


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "homepage_url",
        "recruits_url",
        "recruits_url_status",
    )
    search_fields = ("name", "homepage_url", "recruits_url")
    list_filter = ("recruits_url_status",)


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "title",
        "post_url",
        "status",
    )
    search_fields = ("title", "post_url", "company__name")
    list_filter = ("status", "company")
