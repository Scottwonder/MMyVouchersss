from django.db import models
from .models import OwnerAlert


def pending_alerts_count(request):
    if not request.user.is_authenticated:
        return {'pending_alerts_count': 0}

    if request.user.is_staff or request.user.is_superuser:
        pending_count = OwnerAlert.objects.filter(status='pending').count()
        low_voucher_alert_count = OwnerAlert.objects.filter(status='pending', alert_type='low_vouchers').count()
    else:
        pending_count = request.user.alerts.filter(status='pending').count()
        low_voucher_alert_count = 0

    new_update_count = 0
    if request.user.is_authenticated and not (request.user.is_staff or request.user.is_superuser):
        new_update_count = request.user.alerts.filter(updated_at__gt=models.F('owner_viewed_at')).count() + request.user.alerts.filter(owner_viewed_at__isnull=True).count()

    return {
        'pending_alerts_count': pending_count,
        'new_alerts_count': new_update_count,
        'low_voucher_alert_count': low_voucher_alert_count,
    }
