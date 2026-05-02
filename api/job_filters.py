from __future__ import annotations

from datetime import date

from django.db.models import Q, QuerySet


def boolish(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def apply_jobseeker_recommendation_active_filter(qs: QuerySet) -> QuerySet:
    """
    Jobseeker recommendation active rule:
    - is_active must be True
    - deadline_at is today-or-future OR deadline_at is null
    (same-day deadline is included)
    """
    today = date.today()
    return qs.filter(is_active=True).filter(Q(deadline_at__isnull=True) | Q(deadline_at__gte=today))
