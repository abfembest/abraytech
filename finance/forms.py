from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from eduweb.models import (
    ApplicationPayment,
    Subscription, 
    CourseApplication,
    StaffPayroll,
)
from decimal import Decimal


# ==================== PAYMENT FORMS ====================

class PaymentFilterForm(forms.Form):
    """Filter form for payment management"""
    
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    METHOD_CHOICES = [
        ('', 'All Methods'),
        ('paystack', 'Paystack'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    method = forms.ChoiceField(
        choices=METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Search by reference or name...'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'type': 'date'
        })
    )


class RefundForm(forms.Form):
    """Form for processing refunds"""
    
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'rows': 3,
            'placeholder': 'Reason for refund...'
        })
    )
    
    refund_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Refund amount'
        })
    )
    
    def __init__(self, *args, payment=None, **kwargs):
        super().__init__(*args, **kwargs)
        if payment:
            self.fields['refund_amount'].initial = payment.amount
            self.fields['refund_amount'].widget.attrs['max'] = (
                float(payment.amount)
            )


# ==================== SUBSCRIPTION FORMS ====================

class SubscriptionFilterForm(forms.Form):
    """Filter form for subscriptions"""
    
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Search by user name or email...'
        })
    )


# ==================== REPORT FORMS ====================

class DateRangeForm(forms.Form):
    """Date range filter for reports"""
    
    RANGE_CHOICES = [
        ('7', 'Last 7 days'),
        ('30', 'Last 30 days'),
        ('90', 'Last 90 days'),
        ('365', 'Last year'),
        ('custom', 'Custom range'),
    ]
    
    range = forms.ChoiceField(
        choices=RANGE_CHOICES,
        required=False,
        initial='30',
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'type': 'date'
        })
    )
    
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'type': 'date'
        })
    )


# ==================== INVOICE FORMS ====================

class InvoiceGenerateForm(forms.Form):
    """Form to select payment for invoice generation"""
    
    payment = forms.ModelChoiceField(
        queryset=ApplicationPayment.objects.filter(
            status='completed'
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


# ==================== PAYROLL FORMS ====================

class PayrollCreateForm(forms.ModelForm):
    """
    Form for creating payroll with integrated file uploads
    Supports up to 5 attachments using individual FileInput widgets
    """
    
    # Individual file upload fields (not in model, handled separately)
    attachment_file_1 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': (
                'block w-full text-sm text-gray-900 border '
                'border-gray-300 rounded-lg cursor-pointer '
                'bg-gray-50 focus:outline-none focus:ring-2 '
                'focus:ring-primary-500 focus:border-primary-500 '
                'file:mr-4 file:py-2 file:px-4 file:rounded-lg '
                'file:border-0 file:text-sm file:font-semibold '
                'file:bg-primary-50 file:text-primary-700 '
                'hover:file:bg-primary-100'
            ),
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png'
        }),
        label='Attachment 1',
        help_text='Salary slip, contract, etc.'
    )
    
    attachment_name_1 = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Document name (optional)'
        }),
        label='Document Name 1'
    )
    
    attachment_file_2 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': (
                'block w-full text-sm text-gray-900 border '
                'border-gray-300 rounded-lg cursor-pointer '
                'bg-gray-50 focus:outline-none'
            ),
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png'
        }),
        label='Attachment 2'
    )
    
    attachment_name_2 = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500'
            ),
            'placeholder': 'Document name (optional)'
        }),
        label='Document Name 2'
    )
    
    attachment_file_3 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': (
                'block w-full text-sm text-gray-900 border '
                'border-gray-300 rounded-lg cursor-pointer bg-gray-50'
            ),
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png'
        }),
        label='Attachment 3'
    )
    
    attachment_name_3 = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 rounded-lg'
            ),
            'placeholder': 'Document name (optional)'
        }),
        label='Document Name 3'
    )
    
    attachment_file_4 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': (
                'block w-full text-sm text-gray-900 border '
                'border-gray-300 rounded-lg cursor-pointer bg-gray-50'
            ),
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png'
        }),
        label='Attachment 4'
    )
    
    attachment_name_4 = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 rounded-lg'
            ),
            'placeholder': 'Document name (optional)'
        }),
        label='Document Name 4'
    )
    
    attachment_file_5 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': (
                'block w-full text-sm text-gray-900 border '
                'border-gray-300 rounded-lg cursor-pointer bg-gray-50'
            ),
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png'
        }),
        label='Attachment 5'
    )
    
    attachment_name_5 = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 rounded-lg'
            ),
            'placeholder': 'Document name (optional)'
        }),
        label='Document Name 5'
    )
    
    class Meta:
        model = StaffPayroll
        fields = [
            'staff',
            'month',
            'year',
            'base_salary',
            'allowances',
            'bonuses',
            'tax_deduction',
            'other_deductions',
            'payment_method',
            'bank_name',
            'account_number',
            'notes',
        ]
        widgets = {
            'staff': forms.Select(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500 bg-white'
                ),
            }),
            'month': forms.Select(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500 bg-white'
                ),
            }),
            'year': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '2025',
                'min': '2020',
                'max': '2030',
            }),
            'base_salary': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'allowances': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'bonuses': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'tax_deduction': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'other_deductions': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'payment_method': forms.Select(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500 bg-white'
                ),
            }),
            'bank_name': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': 'Bank name',
            }),
            'account_number': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': 'Account number',
            }),
            'notes': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'rows': 3,
                'placeholder': 'Additional notes...',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Customize the staff field to show name and role
        # Get the queryset with related profile data
        self.fields['staff'].queryset = (
            self.fields['staff'].queryset
            .select_related('profile')
            .order_by('first_name', 'last_name', 'username')
        )
        
        # Override the label_from_instance to show custom format
        self.fields['staff'].label_from_instance = (
            lambda obj: f"{obj.get_full_name() or obj.username} "
                       f"- {obj.profile.get_role_display()}"
            if hasattr(obj, 'profile') 
            else obj.username
        )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate salary amounts
        base_salary = cleaned_data.get('base_salary', Decimal('0'))
        allowances = cleaned_data.get('allowances', Decimal('0'))
        bonuses = cleaned_data.get('bonuses', Decimal('0'))
        tax = cleaned_data.get('tax_deduction', Decimal('0'))
        other_ded = cleaned_data.get('other_deductions', Decimal('0'))
        
        gross = base_salary + allowances + bonuses
        net = gross - tax - other_ded
        
        if net < 0:
            raise ValidationError(
                'Total deductions cannot exceed gross salary'
            )
        
        return cleaned_data


class PayrollFilterForm(forms.Form):
    """Filter form for payroll list"""
    
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('on_hold', 'On Hold'),
    ]
    
    MONTH_CHOICES = [('', 'All Months')] + [
        (str(i), f'{i:02d}') for i in range(1, 13)
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 bg-white'
            )
        })
    )
    
    year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Year'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2.5 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Search by staff name or reference...'
        })
    )


class PayrollStatusForm(forms.ModelForm):
    """Form for updating payroll status"""
    
    class Meta:
        model = StaffPayroll
        fields = ['payment_status', 'payment_date']
        widgets = {
            'payment_status': forms.Select(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500 bg-white'
                )
            }),
            'payment_date': forms.DateInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'type': 'date'
            }),
        }