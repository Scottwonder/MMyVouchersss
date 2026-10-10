from decimal import Decimal, ROUND_DOWN
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import generic

from .forms import AdminUserCreationForm, AdminUserUpdateForm, DistributionForm, LoginForm, OwnerAlertForm, PaymentDisputeForm, PaymentForm, SellingPointForm, UserProfileForm, VoucherTypeForm
from .models import AuditLog, Distribution, DistributionItem, OwnerAlert, OwnerAlertHistory, Payment, SellingPoint, VoucherType

LOW_VOUCHER_THRESHOLDS = {
    '1 day': 10,
    'weekly': 5,
}


def create_low_voucher_alert(selling_point, voucher_type, quantity, created_by=None):
    if not voucher_type or quantity is None:
        return

    threshold = LOW_VOUCHER_THRESHOLDS.get(voucher_type.name.lower())
    if threshold is None or quantity <= 0:
        return

    if quantity < threshold:
        OwnerAlert.objects.create(
            selling_point=selling_point,
            owner=selling_point.owner,
            alert_type='low_vouchers',
            voucher_type=voucher_type,
            quantity=quantity,
            message=f'Low voucher distribution for {voucher_type.name}: {quantity} issued (threshold {threshold}).',
            status='pending',
            created_by=created_by,
        )


class DashboardView(LoginRequiredMixin, generic.TemplateView):
    template_name = 'voucher_app/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start_of_month = today.replace(day=1)

        if self.request.user.is_staff or self.request.user.is_superuser:
            selling_points = SellingPoint.objects.all()
            distributions = Distribution.objects.all()
            payments = Payment.objects.all()
            context['selling_point_name'] = None
            context['selling_point_subtitle'] = 'Selling Points'
        else:
            selling_points = SellingPoint.objects.filter(owner=self.request.user)
            distributions = Distribution.objects.filter(selling_point__in=selling_points)
            payments = Payment.objects.filter(
                selling_point__in=selling_points,
                status__in=['admin_confirmed', 'owner_confirmed'],
            )
            first_sp = selling_points.first()
            if first_sp:
                context['selling_point_name'] = first_sp.name
                context['selling_point_subtitle'] = first_sp.name
            else:
                context['selling_point_name'] = 'Your Voucher Point'
                context['selling_point_subtitle'] = 'No assigned voucher point'

        total_distributed = distributions.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
        total_received = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        context['total_selling_points'] = selling_points.count()
        context['total_distributed'] = total_distributed
        context['total_received'] = total_received
        context['outstanding'] = total_distributed - total_received
        context['todays_collections'] = payments.filter(payment_date=today).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        context['todays_distribution'] = distributions.filter(distribution_date=today).aggregate(total=Sum('total_value'))['total'] or Decimal('0')
        context['monthly_collections'] = payments.filter(payment_date__gte=start_of_month).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        context['monthly_distribution'] = distributions.filter(distribution_date__gte=start_of_month).aggregate(total=Sum('total_value'))['total'] or Decimal('0')

        if self.request.user.is_staff or self.request.user.is_superuser:
            recent_activities = AuditLog.objects.select_related('created_by').all()[:8]
        else:
            recent_activities = AuditLog.objects.select_related('created_by').filter(created_by=self.request.user)[:8]

        context['recent_activities'] = recent_activities
        context['recent_payments'] = payments.select_related('selling_point').all()[:8]
        context['top_selling_points'] = selling_points.annotate(total_received=Sum('payments__amount'), total_distributed=Sum('distributions__total_value')).order_by('-total_received')[:5]
        context['outstanding_alerts'] = selling_points.filter(status='active').order_by('-created_at')[:5]
        context['voucher_types'] = VoucherType.objects.all()

        total_distributed_amount = total_distributed
        voucher_type_balances = []
        distribution_items = DistributionItem.objects.filter(distribution__selling_point__in=selling_points).select_related('voucher_type')
        voucher_type_totals = distribution_items.values('voucher_type__id', 'voucher_type__name').annotate(
            distributed=Sum('value'),
            quantity=Sum('quantity')
        ).order_by('-distributed')

        for item in voucher_type_totals:
            distributed = item['distributed'] or Decimal('0')
            if total_distributed_amount and total_distributed_amount > 0:
                paid_share = (total_received * distributed) / total_distributed_amount
            else:
                paid_share = Decimal('0')
            outstanding_amount = distributed - paid_share
            if outstanding_amount < 0:
                outstanding_amount = Decimal('0')
            voucher_type_balances.append({
                'name': item['voucher_type__name'],
                'distributed': distributed,
                'outstanding': outstanding_amount,
                'quantity': item['quantity'] or 0,
            })

        context['voucher_type_balances'] = voucher_type_balances
        context['selling_point_chart'] = [
            {'name': sp.name, 'value': float(sp.total_payments_received or 0)} for sp in selling_points[:5]
        ]
        context['owner_alerts'] = OwnerAlert.objects.filter(selling_point__in=selling_points)[:8]
        return context


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'voucher_app/profile.html', {'form': form})


@login_required
def admin_user_create(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            selling_points = form.cleaned_data.get('selling_points')
            if selling_points is not None:
                SellingPoint.objects.filter(owner=user).update(owner=None)
                selling_points.update(owner=user)
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('user-list')
    else:
        form = AdminUserCreationForm()
    return render(request, 'voucher_app/user_create.html', {'form': form, 'title': 'Create User'})


@login_required
def admin_user_edit(request, user_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = AdminUserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            selling_points = form.cleaned_data.get('selling_points')
            if selling_points is not None:
                SellingPoint.objects.filter(owner=user).update(owner=None)
                selling_points.update(owner=user)
            messages.success(request, f'User {user.username} updated successfully.')
            return redirect('user-list')
    else:
        form = AdminUserUpdateForm(instance=user)
    return render(request, 'voucher_app/user_form.html', {'form': form, 'title': f'Edit User {user.username}'})


@login_required
def admin_user_delete(request, user_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User {username} deleted successfully.')
        return redirect('user-list')
    return render(request, 'voucher_app/user_confirm_delete.html', {'object': user})


@login_required
def user_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    users = User.objects.all()
    return render(request, 'voucher_app/user_list.html', {'users': users})


@login_required
@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'voucher_app/change_password.html', {'form': form})


@login_required
def selling_point_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    qs = SellingPoint.objects.all()
    if request.GET.get('q'):
        qs = qs.filter(Q(name__icontains=request.GET['q']) | Q(location__icontains=request.GET['q']))
    context = {'selling_points': qs}
    return render(request, 'voucher_app/selling_points.html', context)


@login_required
def selling_point_create(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    if request.method == 'POST':
        form = SellingPointForm(request.POST)
        if form.is_valid():
            sp = form.save(commit=False)
            sp.created_by = request.user
            sp.updated_by = request.user
            sp.save()
            AuditLog.objects.create(action='Created selling point', model_name='SellingPoint', details=sp.name, created_by=request.user)
            messages.success(request, 'Selling point created successfully.')
            return redirect('selling-points')
    else:
        form = SellingPointForm()
    return render(request, 'voucher_app/selling_point_form.html', {'form': form, 'title': 'Add Selling Point'})


@login_required
def selling_point_update(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    sp = get_object_or_404(SellingPoint, pk=pk)
    if request.method == 'POST':
        form = SellingPointForm(request.POST, instance=sp)
        if form.is_valid():
            sp = form.save(commit=False)
            sp.updated_by = request.user
            sp.save()
            AuditLog.objects.create(action='Updated selling point', model_name='SellingPoint', details=sp.name, created_by=request.user)
            messages.success(request, 'Selling point updated successfully.')
            return redirect('selling-points')
    else:
        form = SellingPointForm(instance=sp)
    return render(request, 'voucher_app/selling_point_form.html', {'form': form, 'title': 'Edit Selling Point'})


@login_required
def selling_point_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    sp = get_object_or_404(SellingPoint, pk=pk)
    if request.method == 'POST':
        sp.delete()
        messages.success(request, 'Selling point deleted successfully.')
        return redirect('selling-points')
    return render(request, 'voucher_app/selling_point_confirm_delete.html', {'object': sp})


@login_required
def voucher_type_list(request):
    voucher_types = VoucherType.objects.all()
    return render(request, 'voucher_app/voucher_types.html', {'voucher_types': voucher_types})


@login_required
def voucher_type_create(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    if request.method == 'POST':
        form = VoucherTypeForm(request.POST)
        if form.is_valid():
            vt = form.save(commit=False)
            vt.created_by = request.user
            vt.updated_by = request.user
            vt.save()
            messages.success(request, 'Voucher type created successfully.')
            return redirect('voucher-types')
    else:
        form = VoucherTypeForm()
    return render(request, 'voucher_app/voucher_type_form.html', {'form': form, 'title': 'Add Voucher Type'})


@login_required
def voucher_type_update(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    vt = get_object_or_404(VoucherType, pk=pk)
    if request.method == 'POST':
        form = VoucherTypeForm(request.POST, instance=vt)
        if form.is_valid():
            vt = form.save(commit=False)
            vt.updated_by = request.user
            vt.save()
            messages.success(request, 'Voucher type updated successfully.')
            return redirect('voucher-types')
    else:
        form = VoucherTypeForm(instance=vt)
    return render(request, 'voucher_app/voucher_type_form.html', {'form': form, 'title': 'Edit Voucher Type'})


@login_required
def voucher_type_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    vt = get_object_or_404(VoucherType, pk=pk)
    if request.method == 'POST':
        vt.delete()
        messages.success(request, 'Voucher type deleted successfully.')
        return redirect('voucher-types')
    return render(request, 'voucher_app/voucher_type_confirm_delete.html', {'object': vt})


@login_required
def distribution_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    distributions = Distribution.objects.select_related('selling_point', 'user').all()
    if request.GET.get('q'):
        q = request.GET['q']
        distributions = distributions.filter(
            Q(distribution_number__icontains=q) |
            Q(selling_point__name__icontains=q)
        )
    return render(request, 'voucher_app/distributions.html', {'distributions': distributions, 'query': request.GET.get('q', '')})


@login_required
def distribution_create(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    if request.method == 'POST':
        form = DistributionForm(request.POST)
        if form.is_valid():
            distribution = form.save(commit=False)
            distribution.user = request.user
            distribution.created_by = request.user
            distribution.updated_by = request.user
            distribution.total_value = Decimal('0')
            distribution.total_quantity = 0
            distribution.save()

            daily_quantity = form.cleaned_data.get('daily_quantity') or 0
            weekly_quantity = form.cleaned_data.get('weekly_quantity') or 0
            daily_type = VoucherType.objects.filter(name__iexact='1 day').first()
            weekly_type = VoucherType.objects.filter(name__iexact='weekly').first()

            if daily_type:
                item = DistributionItem.objects.create(distribution=distribution, voucher_type=daily_type, quantity=daily_quantity, value=daily_type.price * daily_quantity)
                distribution.total_quantity += item.quantity
                distribution.total_value += item.value
                create_low_voucher_alert(distribution.selling_point, daily_type, item.quantity, created_by=request.user)
            if weekly_type:
                item = DistributionItem.objects.create(distribution=distribution, voucher_type=weekly_type, quantity=weekly_quantity, value=weekly_type.price * weekly_quantity)
                distribution.total_quantity += item.quantity
                distribution.total_value += item.value
                create_low_voucher_alert(distribution.selling_point, weekly_type, item.quantity, created_by=request.user)

            distribution.save(update_fields=['total_value', 'total_quantity'])
            AuditLog.objects.create(action='Created distribution', model_name='Distribution', details=distribution.distribution_number, created_by=request.user)
            messages.success(request, 'Distribution recorded successfully.')
            return redirect('distributions')
    else:
        form = DistributionForm()
    voucher_types = VoucherType.objects.all()
    return render(request, 'voucher_app/distribution_form.html', {'form': form, 'voucher_types': voucher_types, 'title': 'Add Distribution'})


@login_required
def distribution_update(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    distribution = get_object_or_404(Distribution, pk=pk)
    daily_type = VoucherType.objects.filter(name__iexact='1 day').first()
    weekly_type = VoucherType.objects.filter(name__iexact='weekly').first()
    item_quantities = {
        item.voucher_type_id: item.quantity
        for item in distribution.items.all()
    }
    initial = {
        'daily_quantity': item_quantities.get(daily_type.pk, 0) if daily_type else 0,
        'weekly_quantity': item_quantities.get(weekly_type.pk, 0) if weekly_type else 0,
    }

    if request.method == 'POST':
        form = DistributionForm(request.POST, instance=distribution)
        if form.is_valid():
            daily_quantity = form.cleaned_data.get('daily_quantity') or 0
            weekly_quantity = form.cleaned_data.get('weekly_quantity') or 0
            with transaction.atomic():
                distribution = form.save(commit=False)
                distribution.updated_by = request.user
                distribution.save()
                distribution.items.all().delete()
                items = []
                if daily_type:
                    items.append((daily_type, daily_quantity))
                if weekly_type:
                    items.append((weekly_type, weekly_quantity))
                for voucher_type, quantity in items:
                    DistributionItem.objects.create(
                        distribution=distribution,
                        voucher_type=voucher_type,
                        quantity=quantity,
                        value=voucher_type.price * quantity,
                    )
                distribution.total_quantity = sum(quantity for _, quantity in items)
                distribution.total_value = sum(
                    (voucher_type.price * quantity for voucher_type, quantity in items),
                    Decimal('0'),
                )
                distribution.save(update_fields=['total_quantity', 'total_value', 'updated_at'])
                AuditLog.objects.create(
                    action='Updated distribution',
                    model_name='Distribution',
                    details=distribution.distribution_number,
                    created_by=request.user,
                )
            messages.success(request, 'Distribution updated successfully.')
            return redirect('distributions')
    else:
        form = DistributionForm(instance=distribution, initial=initial)

    return render(request, 'voucher_app/distribution_form.html', {
        'form': form,
        'title': 'Edit Distribution',
    })


@login_required
def distribution_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    distribution = get_object_or_404(Distribution, pk=pk)
    if request.method == 'POST':
        AuditLog.objects.create(
            action='Deleted distribution',
            model_name='Distribution',
            details=distribution.distribution_number,
            created_by=request.user,
        )
        distribution.delete()
        messages.success(request, 'Distribution deleted successfully.')
        return redirect('distributions')
    return render(request, 'voucher_app/distribution_confirm_delete.html', {'object': distribution})


@login_required
def payment_list(request):
    if request.user.is_staff or request.user.is_superuser:
        payments = Payment.objects.select_related('selling_point').all()
    else:
        selling_points = SellingPoint.objects.filter(owner=request.user)
        payments = Payment.objects.select_related('selling_point').filter(
            selling_point__in=selling_points,
            status__in=['admin_confirmed', 'owner_disputed', 'owner_confirmed'],
        )
    if request.GET.get('q'):
        q = request.GET['q']
        payments = payments.filter(
            Q(selling_point__name__icontains=q) |
            Q(payment_method__icontains=q) |
            Q(reference_number__icontains=q)
        )
    return render(request, 'voucher_app/payments.html', {'payments': payments, 'query': request.GET.get('q', '')})


@login_required
def payment_admin_confirm(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST' and payment.status == 'pending':
        payment.status = 'admin_confirmed'
        payment.admin_confirmed_at = timezone.now()
        payment.updated_by = request.user
        payment.save(update_fields=['status', 'admin_confirmed_at', 'updated_by', 'updated_at'])
        AuditLog.objects.create(
            action='Admin confirmed payment',
            model_name='Payment',
            details=f'{payment.selling_point.name} - {payment.amount}',
            created_by=request.user,
        )
        messages.success(request, 'Payment confirmed for owner review.')
    return redirect('payments')


@login_required
def payment_dispute(request, pk):
    selling_points = SellingPoint.objects.filter(owner=request.user)
    payment = get_object_or_404(
        Payment,
        pk=pk,
        selling_point__in=selling_points,
        status='admin_confirmed',
    )
    if request.method == 'POST':
        form = PaymentDisputeForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.status = 'owner_disputed'
            payment.dispute_requested_at = timezone.now()
            payment.updated_by = request.user
            payment.save(update_fields=['disputed_amount', 'dispute_note', 'status', 'dispute_requested_at', 'updated_by', 'updated_at'])
            AuditLog.objects.create(
                action='Owner disputed payment',
                model_name='Payment',
                details=f'{payment.selling_point.name} - {payment.disputed_amount}',
                created_by=request.user,
            )
            messages.success(request, 'Dispute submitted to admin for review.')
            return redirect('payments')
    else:
        form = PaymentDisputeForm(instance=payment)
    return render(request, 'voucher_app/payment_dispute_form.html', {'form': form, 'payment': payment})


@login_required
def payment_owner_confirm(request, pk):
    selling_points = SellingPoint.objects.filter(owner=request.user)
    payment = get_object_or_404(
        Payment,
        pk=pk,
        selling_point__in=selling_points,
        status='admin_confirmed',
    )
    if request.method == 'POST':
        payment.status = 'owner_confirmed'
        payment.owner_confirmed_at = timezone.now()
        payment.updated_by = request.user
        payment.save(update_fields=['status', 'owner_confirmed_at', 'updated_by', 'updated_at'])
        AuditLog.objects.create(
            action='Owner confirmed payment',
            model_name='Payment',
            details=f'{payment.selling_point.name} - {payment.amount}',
            created_by=request.user,
        )
        messages.success(request, 'Payment confirmed successfully.')
    return redirect('payments')


@login_required
def payment_admin_review(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    payment = get_object_or_404(Payment, pk=pk, status='owner_disputed')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'accept' and payment.disputed_amount is not None:
            payment.amount = payment.disputed_amount
            payment.status = 'owner_confirmed'
            payment.owner_confirmed_at = timezone.now()
            payment.updated_by = request.user
            payment.save(update_fields=['amount', 'status', 'owner_confirmed_at', 'updated_by', 'updated_at'])
            AuditLog.objects.create(
                action='Admin accepted disputed payment amount',
                model_name='Payment',
                details=f'{payment.selling_point.name} - {payment.amount}',
                created_by=request.user,
            )
            messages.success(request, 'Disputed payment amount accepted.')
        elif action == 'reject':
            payment.status = 'admin_confirmed'
            payment.updated_by = request.user
            payment.save(update_fields=['status', 'updated_by', 'updated_at'])
            AuditLog.objects.create(
                action='Admin rejected disputed payment',
                model_name='Payment',
                details=f'{payment.selling_point.name} - {payment.amount}',
                created_by=request.user,
            )
            messages.success(request, 'Dispute rejected; original payment amount retained.')
    return redirect('payments')


@login_required
def payment_create(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.created_by = request.user
            payment.updated_by = request.user
            payment.save()
            AuditLog.objects.create(action='Created payment', model_name='Payment', details=f"{payment.selling_point.name} - {payment.amount}", created_by=request.user)
            messages.success(request, 'Payment recorded successfully.')
            return redirect('payments')
    else:
        form = PaymentForm()
    return render(request, 'voucher_app/payment_form.html', {'form': form, 'title': 'Add Payment'})


@login_required
def payment_update(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    payment = get_object_or_404(Payment, pk=pk, status='pending')
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.updated_by = request.user
            payment.save()
            AuditLog.objects.create(
                action='Updated payment',
                model_name='Payment',
                details=f'{payment.selling_point.name} - {payment.amount}',
                created_by=request.user,
            )
            messages.success(request, 'Payment updated successfully.')
            return redirect('payments')
    else:
        form = PaymentForm(instance=payment)
    return render(request, 'voucher_app/payment_form.html', {'form': form, 'title': 'Edit Payment'})


@login_required
def payment_delete(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        AuditLog.objects.create(
            action='Deleted payment',
            model_name='Payment',
            details=f'{payment.selling_point.name} - {payment.amount}',
            created_by=request.user,
        )
        payment.delete()
        messages.success(request, 'Payment deleted successfully.')
        return redirect('payments')
    return render(request, 'voucher_app/payment_confirm_delete.html', {'object': payment})


@login_required
def selling_point_detail(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
    selling_point = get_object_or_404(SellingPoint, pk=pk)
    distributions = selling_point.distributions.all()
    payments = selling_point.payments.all()
    recent_transactions = list(distributions[:5]) + list(payments[:5])
    recent_transactions.sort(key=lambda obj: obj.created_at, reverse=True)
    context = {
        'selling_point': selling_point,
        'distributions': distributions,
        'payments': payments,
        'recent_transactions': recent_transactions[:10],
    }
    return render(request, 'voucher_app/selling_point_detail.html', context)


@login_required
def owner_alert_list(request):
    if request.user.is_staff or request.user.is_superuser:
        alerts = OwnerAlert.objects.select_related('selling_point', 'voucher_type', 'owner').all()
    else:
        alerts = OwnerAlert.objects.select_related('selling_point', 'voucher_type', 'owner').filter(owner=request.user)
    return render(request, 'voucher_app/owner_alerts.html', {'alerts': alerts})


@login_required
def owner_alert_create(request):
    if request.method == 'POST':
        form = OwnerAlertForm(request.POST)
        if not (request.user.is_staff or request.user.is_superuser):
            form.fields['selling_point'].queryset = SellingPoint.objects.filter(owner=request.user)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.owner = request.user
            alert.status = 'pending'
            alert.save()
            messages.success(request, 'Alert submitted successfully.')
            staff_users = User.objects.filter(is_staff=True, is_active=True).exclude(email='')
            for staff in staff_users:
                staff.email_user(
                    subject=f'New alert submitted: {alert.get_alert_type_display()}',
                    message=f"A new alert was submitted for {alert.selling_point.name}. Status: {alert.get_status_display()}.",
                )
            return redirect('owner-alerts')
    else:
        form = OwnerAlertForm()
        if not (request.user.is_staff or request.user.is_superuser):
            form.fields['selling_point'].queryset = SellingPoint.objects.filter(owner=request.user)
    return render(request, 'voucher_app/owner_alert_form.html', {'form': form})


@login_required
def owner_alert_detail(request, alert_id):
    alert = get_object_or_404(OwnerAlert.objects.select_related('selling_point', 'voucher_type', 'owner'), pk=alert_id)
    if not (request.user.is_staff or request.user.is_superuser) and alert.owner != request.user:
        return redirect('dashboard')

    if alert.owner == request.user and alert.has_new_update:
        alert.owner_viewed_at = timezone.now()
        alert.save(update_fields=['owner_viewed_at'])

    return render(request, 'voucher_app/owner_alert_detail.html', {'alert': alert})


@login_required
def owner_alert_status_change(request, alert_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    alert = get_object_or_404(OwnerAlert, pk=alert_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = [choice[0] for choice in OwnerAlert.STATUS_CHOICES]
        if new_status in valid_statuses and new_status != alert.status:
            previous_status = alert.status
            alert.status = new_status
            alert.save(update_fields=['status', 'updated_at'])
            OwnerAlertHistory.objects.create(
                owner_alert=alert,
                changed_by=request.user,
                previous_status=previous_status,
                new_status=new_status,
                note=f'Status changed from {previous_status} to {new_status}',
            )
            if alert.owner and alert.owner.email:
                alert.owner.email_user(
                    subject=f'Alert status updated: {alert.get_alert_type_display()}',
                    message=f"Your alert for {alert.selling_point.name} is now {alert.get_status_display()}",
                )
            messages.success(request, f'Alert status updated to {alert.get_status_display()}.')
    return redirect('owner-alerts')


@login_required
def reports_view(request):
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if request.user.is_staff or request.user.is_superuser:
        selling_points = SellingPoint.objects.all()
        distributions = Distribution.objects.all()
        payments = Payment.objects.all()
    else:
        selling_points = SellingPoint.objects.filter(owner=request.user)
        distributions = Distribution.objects.filter(selling_point__in=selling_points)
        payments = Payment.objects.filter(
            selling_point__in=selling_points,
            status__in=['admin_confirmed', 'owner_confirmed'],
        )

    if start_date:
        distributions = distributions.filter(distribution_date__gte=start_date)
        payments = payments.filter(payment_date__gte=start_date)
    if end_date:
        distributions = distributions.filter(distribution_date__lte=end_date)
        payments = payments.filter(payment_date__lte=end_date)

    total_distributed_value = distributions.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
    total_paid_value = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    distribution_items = DistributionItem.objects.filter(distribution__in=distributions).select_related('voucher_type')
    voucher_type_totals = distribution_items.values(
        'voucher_type__id', 'voucher_type__name', 'voucher_type__price'
    ).annotate(
        distributed_value=Sum('value'),
        distributed_quantity=Sum('quantity'),
    ).order_by('voucher_type__name')

    voucher_type_report = []
    for item in voucher_type_totals:
        distributed_value = item['distributed_value'] or Decimal('0')
        distributed_quantity = item['distributed_quantity'] or 0
        price = item['voucher_type__price'] or Decimal('0')
        sold_value = Decimal('0')
        available_value = Decimal('0')
        sold_quantity = 0
        available_quantity = distributed_quantity

        if total_distributed_value > 0:
            sold_value = (total_paid_value * distributed_value) / total_distributed_value
            sold_value = sold_value.quantize(Decimal('0.01'))
            available_value = distributed_value - sold_value
            if available_value < 0:
                available_value = Decimal('0')
            if price > 0:
                sold_quantity = int((sold_value / price).to_integral_value(rounding=ROUND_DOWN))
                available_quantity = distributed_quantity - sold_quantity
                if available_quantity < 0:
                    available_quantity = 0

        voucher_type_report.append({
            'name': item['voucher_type__name'],
            'price': price,
            'distributed_quantity': distributed_quantity,
            'distributed_value': distributed_value,
            'sold_quantity': sold_quantity,
            'available_quantity': available_quantity,
            'sold_value': sold_value,
            'available_value': available_value,
        })

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'selling_points_count': selling_points.count(),
        'total_distributed_value': total_distributed_value,
        'total_paid_value': total_paid_value,
        'total_outstanding_value': total_distributed_value - total_paid_value if total_distributed_value >= total_paid_value else Decimal('0'),
        'voucher_type_report': voucher_type_report,
    }
    if start_date and end_date:
        context['selected_range'] = f"{start_date} to {end_date}"

    return render(request, 'voucher_app/reports.html', context)


@login_required
def export_report(request, report_type):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report.csv"'
    writer = __import__('csv').writer(response)
    if request.user.is_staff or request.user.is_superuser:
        distribution_rows = Distribution.objects.all()
        payment_rows = Payment.objects.all()
    else:
        selling_points = SellingPoint.objects.filter(owner=request.user)
        distribution_rows = Distribution.objects.filter(selling_point__in=selling_points)
        payment_rows = Payment.objects.filter(
            selling_point__in=selling_points,
            status__in=['admin_confirmed', 'owner_confirmed'],
        )

    if report_type == 'distribution':
        rows = distribution_rows
        if start_date:
            rows = rows.filter(distribution_date__gte=start_date)
        if end_date:
            rows = rows.filter(distribution_date__lte=end_date)
        writer.writerow(['Distribution Number', 'Date', 'Selling Point', 'Total Value', 'Quantity'])
        for row in rows.values_list('distribution_number', 'distribution_date', 'selling_point__name', 'total_value', 'total_quantity'):
            writer.writerow(row)
    elif report_type == 'payment':
        rows = payment_rows
        if start_date:
            rows = rows.filter(payment_date__gte=start_date)
        if end_date:
            rows = rows.filter(payment_date__lte=end_date)
        writer.writerow(['Payment Date', 'Selling Point', 'Amount', 'Method', 'Reference'])
        for row in rows.values_list('payment_date', 'selling_point__name', 'amount', 'payment_method', 'reference_number'):
            writer.writerow(row)
    elif report_type == 'voucher-type':
        distribution_items = DistributionItem.objects.filter(distribution__in=distribution_rows)
        voucher_type_totals = distribution_items.values(
            'voucher_type__name',
            'voucher_type__price',
        ).annotate(
            distributed_value=Sum('value'),
            distributed_quantity=Sum('quantity'),
        ).order_by('voucher_type__name')

        total_distributed_value = distribution_items.aggregate(total=Sum('value'))['total'] or Decimal('0')
        total_paid_value = payment_rows.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        writer.writerow(['Voucher Type', 'Unit Price', 'Distributed Quantity', 'Distributed Value', 'Sold Value', 'Available Value'])
        for item in voucher_type_totals:
            distributed_value = item['distributed_value'] or Decimal('0')
            sold_value = Decimal('0')
            if total_distributed_value > 0:
                sold_value = (total_paid_value * distributed_value) / total_distributed_value
                sold_value = sold_value.quantize(Decimal('0.01'))
            available_value = distributed_value - sold_value
            if available_value < 0:
                available_value = Decimal('0')
            writer.writerow([
                item['voucher_type__name'],
                item['voucher_type__price'],
                item['distributed_quantity'],
                distributed_value,
                sold_value,
                available_value,
            ])
    else:
        response.write('No report available')
    return response


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, 'Welcome back!')
            return redirect('dashboard')
    else:
        form = LoginForm()
    return render(request, 'voucher_app/login.html', {'form': form})


def forgot_password_view(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            form.save(request=request, from_email=settings.DEFAULT_FROM_EMAIL, email_template_name='voucher_app/password_reset_email.html')
            messages.success(request, 'Password reset instructions have been sent to your email.')
            return redirect('password-reset-done')
    else:
        form = PasswordResetForm()
    return render(request, 'voucher_app/forgot_password.html', {'form': form})


def password_reset_done_view(request):
    return render(request, 'voucher_app/password_reset_done.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def audit_logs_view(request):
    if request.user.is_staff or request.user.is_superuser:
        logs = AuditLog.objects.select_related('created_by').all()
    else:
        logs = AuditLog.objects.select_related('created_by').filter(created_by=request.user)
    return render(request, 'voucher_app/audit_logs.html', {'logs': logs})
