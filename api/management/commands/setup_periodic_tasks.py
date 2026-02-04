# api/management/commands/setup_periodic_tasks.py
import json
from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule

class Command(BaseCommand):
    help = "Create/update periodic tasks for celery beat (django-celery-beat)."

    def handle(self, *args, **options):
        # 매주 월요일 03:30 (Asia/Seoul 기준, settings의 CELERY_TIMEZONE 사용) :contentReference[oaicite:9]{index=9}
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="30",
            hour="3",
            day_of_week="1",   # Monday
            day_of_month="*",
            month_of_year="*",
            timezone="Asia/Seoul",
        )

        task_name = "api.tasks.collect_osm_companies"

        PeriodicTask.objects.update_or_create(
            name="weekly_collect_osm_companies",
            defaults={
                "crontab": schedule,
                "task": task_name,
                "enabled": True,
                "kwargs": json.dumps({
                    "mode": "wide",
                    "regions": ["서울특별시", "경기도", "대전광역시", "충청남도", "충청북도"],
                }, ensure_ascii=False),
            },
        )

        self.stdout.write(self.style.SUCCESS("OK: weekly_collect_osm_companies scheduled"))
