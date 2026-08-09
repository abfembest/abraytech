import os

from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from apps.eduweb.models import InstitutionalSubscription, StaffPayroll
from decimal import Decimal

# Matches the widget's accept= hint — that hint is client-side only and
# trivially bypassed, so it must be enforced again server-side.
ALLOWED_ATTACHMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png'}
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

# Payment/refund/invoice filtering lives in payment.forms (PaymentFilterForm,
# RefundForm, InvoiceGenerateForm) — those views own the payment_management,
# refund_payment and invoice_generation pages, so their forms belong there.
# Duplicating them here was dead code; nothing in this app ever imported them.


# ==================== SUBSCRIPTION FORMS ====================

class InstitutionalSubscriptionForm(forms.ModelForm):
    """Add form for the institution's own paid subscriptions (superuser-only)."""

    class Meta:
        model = InstitutionalSubscription
        fields = ['purpose', 'amount', 'start_date', 'expiry_date']
        widgets = {
            'purpose': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'placeholder': 'e.g. Zoom Pro, Canva, AWS hosting'
            }),
            'amount': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'step': '0.01',
                'min': '0',
            }),
            'start_date': forms.DateInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'type': 'date',
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': (
                    'w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500'
                ),
                'type': 'date',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        expiry_date = cleaned_data.get('expiry_date')
        if start_date and expiry_date and expiry_date <= start_date:
            raise ValidationError('Expiry date must be after the start date.')
        return cleaned_data


# ==================== REPORT FORMS ====================

class DateRangeForm(forms.Form):
    """
    Date range filter backing the finance dashboard's auto-submitting
    range picker (templates/finance/dashboard.html). The field name and
    choices must match that <select name="range_type"> exactly.
    """

    RANGE_CHOICES = [
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('this_week', 'This Week'),
        ('last_week', 'Last Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_year', 'This Year'),
        ('custom', 'Custom Range'),
    ]

    range_type = forms.ChoiceField(
        choices=RANGE_CHOICES,
        required=False,
        initial='this_month',
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

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise ValidationError('Start date must be before end date.')
        return cleaned_data


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
                    'searchable-select w-full px-4 py-2.5 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-primary-500 bg-white'
                ),
            }),
            'month': forms.Select(attrs={
                'class': (
                    'searchable-select w-full px-4 py-2.5 border border-gray-300 '
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
                    'searchable-select w-full px-4 py-2.5 border border-gray-300 '
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

        # Validate each optional attachment: extension + size. The widget's
        # accept= hint is client-side only and trivially bypassed.
        for i in range(1, 6):
            uploaded = cleaned_data.get(f'attachment_file_{i}')
            if not uploaded:
                continue
            ext = os.path.splitext(uploaded.name)[1].lower()
            if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
                self.add_error(
                    f'attachment_file_{i}',
                    f'Unsupported file type "{ext}". Allowed: '
                    f'{", ".join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}.'
                )
            elif uploaded.size > MAX_ATTACHMENT_SIZE_BYTES:
                self.add_error(
                    f'attachment_file_{i}',
                    'File exceeds the 10MB size limit.'
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