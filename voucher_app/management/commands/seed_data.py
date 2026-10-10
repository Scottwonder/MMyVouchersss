from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from voucher_app.models import SellingPoint, VoucherType


class Command(BaseCommand):
    help = 'Seed default voucher data'

    def handle(self, *args, **options):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        if not VoucherType.objects.filter(name='1 Day').exists():
            VoucherType.objects.create(name='1 Day', price=1000)
        if not VoucherType.objects.filter(name='Weekly').exists():
            VoucherType.objects.create(name='Weekly', price=5000)
        if not SellingPoint.objects.exists():
            SellingPoint.objects.create(name='Main Market', phone_number='0770000000', location='Kampala', contact_person='Jane', status='active')
            SellingPoint.objects.create(name='Airport Road', phone_number='0771111111', location='Kampala', contact_person='John', status='active')
        self.stdout.write(self.style.SUCCESS('Seed data created.'))
