from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Distribution, OwnerAlert, Payment, SellingPoint, VoucherType


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class AdminUserCreationForm(UserCreationForm):
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter password'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'})
    )
    selling_points = forms.ModelMultipleChoiceField(
        queryset=SellingPoint.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
        label='Assigned Selling Points'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'selling_points']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class AdminUserUpdateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='New Password',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to keep current password'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repeat new password'})
    )
    selling_points = forms.ModelMultipleChoiceField(
        queryset=SellingPoint.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
        label='Assigned Selling Points'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['selling_points'].initial = SellingPoint.objects.filter(owner=self.instance)

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 or password2:
            if password1 != password2:
                self.add_error('password2', 'Passwords do not match.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class SellingPointForm(forms.ModelForm):
    class Meta:
        model = SellingPoint
        fields = ['name', 'phone_number', 'location', 'contact_person', 'owner', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class VoucherTypeForm(forms.ModelForm):
    class Meta:
        model = VoucherType
        fields = ['name', 'price']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class DistributionForm(forms.ModelForm):
    daily_quantity = forms.IntegerField(min_value=0, required=False, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))
    weekly_quantity = forms.IntegerField(min_value=0, required=False, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))

    class Meta:
        model = Distribution
        fields = ['selling_point', 'distribution_date', 'remarks']
        widgets = {
            'selling_point': forms.Select(attrs={'class': 'form-select'}),
            'distribution_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['selling_point', 'amount', 'payment_method', 'reference_number', 'remarks', 'payment_date']
        widgets = {
            'selling_point': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class PaymentDisputeForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['disputed_amount', 'dispute_note']
        labels = {
            'disputed_amount': 'Correct Amount',
            'dispute_note': 'Dispute Note',
        }
        widgets = {
            'disputed_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'dispute_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class OwnerAlertForm(forms.ModelForm):
    class Meta:
        model = OwnerAlert
        fields = ['selling_point', 'alert_type', 'voucher_type', 'quantity', 'message']
        widgets = {
            'selling_point': forms.Select(attrs={'class': 'form-select'}),
            'alert_type': forms.Select(attrs={'class': 'form-select'}),
            'voucher_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
