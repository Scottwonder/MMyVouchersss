from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

OWNER_ALERT_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('reviewed', 'Seen'),
    ('resolved', 'Completed'),
]


class SellingPoint(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=30, blank=True)
    location = models.CharField(max_length=255, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_selling_points')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    date_created = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_selling_points')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_selling_points')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self):
        return self.total_distributed_value - self.total_payments_received

    @property
    def total_distributed_value(self):
        return sum(distribution.total_value for distribution in self.distributions.all())

    @property
    def total_payments_received(self):
        return sum(payment.amount for payment in self.payments.all())

    @property
    def total_vouchers_distributed(self):
        return sum(distribution.total_quantity for distribution in self.distributions.all())


class VoucherType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_voucher_types')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_voucher_types')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Distribution(models.Model):
    distribution_number = models.CharField(max_length=50, unique=True)
    selling_point = models.ForeignKey(SellingPoint, on_delete=models.CASCADE, related_name='distributions')
    distribution_date = models.DateField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='distributions')
    remarks = models.TextField(blank=True)
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_quantity = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_distributions')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_distributions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-distribution_date', '-created_at']

    def __str__(self):
        return self.distribution_number

    def save(self, *args, **kwargs):
        if not self.distribution_number:
            self.distribution_number = f"DIST-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)


class DistributionItem(models.Model):
    distribution = models.ForeignKey(Distribution, on_delete=models.CASCADE, related_name='items')
    voucher_type = models.ForeignKey(VoucherType, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['voucher_type__name']

    def __str__(self):
        return f"{self.voucher_type.name} x {self.quantity}"


class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
        ('bank', 'Bank'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('admin_confirmed', 'Admin Confirmed'),
        ('owner_disputed', 'Disputed by Owner'),
        ('owner_confirmed', 'Owner Confirmed'),
    ]

    selling_point = models.ForeignKey(SellingPoint, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    payment_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    disputed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dispute_note = models.TextField(blank=True)
    dispute_requested_at = models.DateTimeField(null=True, blank=True)
    admin_confirmed_at = models.DateTimeField(null=True, blank=True)
    owner_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payments')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.selling_point.name} - {self.amount}"


class AuditLog(models.Model):
    action = models.CharField(max_length=200)
    model_name = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.action


class OwnerAlert(models.Model):
    ALERT_TYPE_CHOICES = [
        ('low_vouchers', 'Low Vouchers'),
        ('collection_request', 'Collection Request'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = OWNER_ALERT_STATUS_CHOICES

    selling_point = models.ForeignKey(SellingPoint, on_delete=models.CASCADE, related_name='alerts')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    voucher_type = models.ForeignKey(VoucherType, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.selling_point.name} - {self.get_alert_type_display()}"

    @property
    def has_new_update(self):
        if not self.owner:
            return False
        if self.owner_viewed_at is None:
            return True
        return self.updated_at > self.owner_viewed_at


class OwnerAlertHistory(models.Model):
    owner_alert = models.ForeignKey(OwnerAlert, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.owner_alert} - {self.get_new_status_display()}"
