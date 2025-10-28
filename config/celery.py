import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")

# (A) 자동 검색
app.autodiscover_tasks()

# (B) 확실히 api.tasks를 로드하도록 강제 임포트 (중요)
app.conf.imports = ("api.tasks",)
