from django import forms
from eduweb.models import ApplicationPayment


# ==================== PAYMENT FORMS ====================

class PaymentFilterForm(forms.Form):
    """Filter form for payment management"""

    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    METHOD_CHOICES = [
        ('', 'All Methods'),
        ('paystack', 'Paystack'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]

    _cls = (
        'w-full px-4 py-2.5 border border-gray-300 '
        'rounded-lg focus:ring-2 focus:ring-primary-500 '
        'focus:border-primary-500'
    )

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': _cls + ' bg-white'})
    )

    payment_method = forms.ChoiceField(
        choices=METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': _cls + ' bg-white'})
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': _cls,
            'placeholder': 'Search by reference or name...'
        })
    )

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': _cls,
            'type': 'date'
        })
    )

    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': _cls,
            'type': 'date'
        })
    )


class RefundForm(forms.Form):
    """
    Form for processing refunds.
    Accepts optional payment instance to pre-fill amount and enforce max.
    """

    _cls = (
        'w-full px-4 py-2.5 border border-gray-300 '
        'rounded-lg focus:ring-2 focus:ring-primary-500 '
        'focus:border-primary-500'
    )

    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': _cls,
            'rows': 3,
            'placeholder': 'Reason for refund...'
        })
    )

    refund_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': _cls,
            'placeholder': 'Refund amount',
            'step': '0.01',
            'min': '0.01',
        })
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': _cls,
            'rows': 2,
            'placeholder': 'Additional notes (optional)...'
        })
    )

    def __init__(self, *args, payment=None, **kwargs):
        super().__init__(*args, **kwargs)
        if payment:
            self.payment = payment
            self.fields['refund_amount'].initial = payment.amount
            self.fields['refund_amount'].widget.attrs['max'] = (
                float(payment.amount)
            )

    def clean_refund_amount(self):
        amount = self.cleaned_data['refund_amount']
        payment = getattr(self, 'payment', None)

        if amount <= 0:
            raise forms.ValidationError(
                'Refund amount must be greater than zero.'
            )

        if payment and amount > payment.amount:
            raise forms.ValidationError(
                f'Refund cannot exceed the original '
                f'payment amount of {payment.amount}.'
            )

        return amount


# ==================== INVOICE FORMS ====================

class InvoiceGenerateForm(forms.Form):
    """Form to select a successful payment for invoice generation"""

    payment = forms.ModelChoiceField(
        queryset=ApplicationPayment.objects.filter(
            status='success'
        ).select_related(
            'application__user',
            'application__course'
        ),
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        }),
        empty_label="Select a payment..."
    )