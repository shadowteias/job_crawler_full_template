from django.contrib import admin
from django.urls import path, include
from api.views_ui import api_test_page

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api-test/', api_test_page, name='api-test-page'),
    path('api/', include('api.urls')),
]
