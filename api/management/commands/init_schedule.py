from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django_celery_beat.models import IntervalSchedule, PeriodicTask
import os

class Command(BaseCommand):
    help = "Create or update the periodic task for full crawling"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=None, help="Interval in hours")

    @transaction.atomic
    def handle(self, *args, **opts):
        hours = opts.get("hours") or int(os.getenv("CRAWL_INTERVAL_HOURS", 8))
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=hours,
            period=IntervalSchedule.HOURS,
        )
        name = f"Full crawling every {hours}h"
        obj, created = PeriodicTask.objects.update_or_create(
            name=name,
            defaults={
                "task": "api.tasks.run_full_crawling_cycle",
                "interval": interval,
                "crontab": None,
                "start_time": timezone.now(),
                "enabled": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"✅ Periodic task set: {name} (created={created})"
        ))
