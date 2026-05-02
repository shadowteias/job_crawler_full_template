from django.shortcuts import render
from django.conf import settings


def api_test_page(request):
    return render(
        request,
        "api_test.html",
        {
            "api_internal_token": getattr(settings, "API_INTERNAL_TOKEN", ""),
        },
    )
