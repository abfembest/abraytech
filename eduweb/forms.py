from django import forms
from .models import (
    ContactMessage, CourseApplication,
    ListOfCountry, ApplicationDocument
)
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import os


# ─────────────────────────────────────────────────────────────────────────────
# SHARED FIELD CSS
# ─────────────────────────────────────────────────────────────────────────────
_INPUT  = 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-purple-600 focus:ring-2 focus:ring-purple-200 transition-all bg-white text-gray-800'
_SELECT = 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-purple-600 focus:ring-2 focus:ring-purple-200 transition-all bg-white text-gray-800'
_AREA   = 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-purple-600 focus:ring-2 focus:ring-purple-200 transition-all bg-white text-gray-800 resize-y'
_CHECK  = 'h-5 w-5 text-purple-700 rounded focus:ring-purple-500 cursor-pointer'


# ─────────────────────────────────────────────────────────────────────────────
# AUTH FORMS
# ─────────────────────────────────────────────────────────────────────────────
class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': _INPUT, 'placeholder': 'your.email@example.com', 'autocomplete': 'email'})
    )
    first_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'John', 'autocomplete': 'given-name'})
    )
    last_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Smith', 'autocomplete': 'family-name'})
    )
    captcha = forms.IntegerField(
        required=True,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'placeholder': 'Enter the result', 'autocomplete': 'off'})
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Choose a username', 'autocomplete': 'username'}),
        }

    def __init__(self, *args, **kwargs):
        self.captcha_answer = kwargs.pop('captcha_answer', None)
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': _INPUT, 'placeholder': 'Create a strong password', 'autocomplete': 'new-password'})
        self.fields['password2'].widget.attrs.update({'class': _INPUT, 'placeholder': 'Confirm your password', 'autocomplete': 'new-password'})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email address is already registered.')
        return email

    def clean_captcha(self):
        captcha = self.cleaned_data.get('captcha')
        if self.captcha_answer is None:
            raise ValidationError('Captcha session expired. Please refresh the page.')
        try:
            if int(captcha) != int(self.captcha_answer):
                raise ValidationError('Incorrect answer. Please try again.')
        except (ValueError, TypeError):
            raise ValidationError('Invalid captcha answer format.')
        return captcha


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Enter your username or email', 'autocomplete': 'username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': _INPUT, 'placeholder': 'Enter your password', 'autocomplete': 'current-password'})
    )
    captcha = forms.IntegerField(
        required=True,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'placeholder': 'Enter the result', 'autocomplete': 'off'})
    )

    def __init__(self, *args, **kwargs):
        self.captcha_answer = kwargs.pop('captcha_answer', None)
        super().__init__(*args, **kwargs)

    def clean_captcha(self):
        captcha = self.cleaned_data.get('captcha')
        if self.captcha_answer is None:
            raise ValidationError('Captcha session expired. Please refresh the page.')
        try:
            if int(captcha) != int(self.captcha_answer):
                raise ValidationError('Incorrect answer. Please try again.')
        except (ValueError, TypeError):
            raise ValidationError('Invalid captcha answer format.')
        return captcha


# ─────────────────────────────────────────────────────────────────────────────
# CONTACT FORM
# ─────────────────────────────────────────────────────────────────────────────
class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name':    forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'John Smith'}),
            'email':   forms.EmailInput(attrs={'class': _INPUT, 'placeholder': 'john@example.com'}),
            'subject': forms.Select(attrs={'class': _SELECT}),
            'message': forms.Textarea(attrs={'class': _AREA, 'placeholder': "I'm interested in learning more about...", 'rows': 4}),
        }


# ─────────────────────────────────────────────────────────────────────────────
class DisabledEmptySelect(forms.Select):
    """Renders the blank option as selected+disabled so it acts as a true placeholder."""
    def __init__(self, *args, empty_label="-- Select --", **kwargs):
        super().__init__(*args, **kwargs)
        self._empty_label = empty_label

    def create_option(self, name, value, label, selected, index, attrs=None, **kwargs):
        option = super().create_option(name, value, label, selected, index, attrs=attrs, **kwargs)
        if value == '' or value is None or str(value) == '':
            option['attrs']['disabled'] = True
            option['selected'] = True
        return option


# COURSE APPLICATION FORM  — all model fields included
# ─────────────────────────────────────────────────────────────────────────────
class CourseApplicationForm(forms.ModelForm):

    HEAR_CHOICES = [
        ('', 'Select an option'),
        ('linkedin',       'LinkedIn'),
        ('facebook',       'Facebook'),
        ('tiktok',         'TikTok'),
        ('instagram',      'Instagram'),
        ('youtube',        'YouTube'),
        ('twitter',        'Twitter'),
        ('email_campaign', 'Email Campaign'),
        ('miu_website',    'MIU Website'),
        ('search_engine',  'Search Engine (Google, Bing, Yahoo)'),
        ('referral',       'Referral (friend, family)'),
        ('other',          'Other'),
    ]

    # ── Override fields that need dynamic choices or special widgets ──────────

    # Country — populated dynamically from ListOfCountry in __init__
    country = forms.ChoiceField(
        choices=[('', 'Select Country')],
        required=True,
        widget=DisabledEmptySelect(attrs={'class': f'{_SELECT} select2-country'}),
    )

    nationality = forms.ChoiceField(
        choices=[('', 'Select Nationality')],
        required=True,
        widget=DisabledEmptySelect(attrs={'class': f'{_SELECT} select2-nationality'}),
    )

    how_did_you_hear = forms.ChoiceField(
        choices=HEAR_CHOICES,
        required=True,
        widget=DisabledEmptySelect(attrs={'class': _SELECT}),
    )

    # Additional model fields exposed as explicit form fields
    how_did_you_hear_other = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Please specify...'}),
    )
    emergency_contact_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': _INPUT, 'placeholder': 'emergency@example.com'}),
    )
    emergency_contact_address = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Emergency contact full address'}),
    )

    class Meta:
        model = CourseApplication
        fields = [
            # ── Course, Session & Level
            'program', 'study_mode',
            # ── Personal
            'first_name', 'last_name', 'email', 'phone',
            'date_of_birth', 'gender', 'nationality',
            # ── Address
            'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country',
            # ── Academic Background
            'highest_qualification', 'institution_name',
            'graduation_year', 'gpa_or_grade',
            'language_skill', 'language_score',
            # ── Additional
            'work_experience_years', 'personal_statement',
            'how_did_you_hear', 'how_did_you_hear_other',
            # ── Emergency Contact
            'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship',
            'emergency_contact_email', 'emergency_contact_address',
            # ── Consent & Options
            'accept_terms_conditions', 'accept_privacy_policy',
            'marketing_consent', 'scholarship',
        ]

        widgets = {
            # Course, Session & Level
            'program':    DisabledEmptySelect(attrs={'class': _SELECT}),
            'study_mode': DisabledEmptySelect(attrs={'class': _SELECT}),

            # Personal Information
            'first_name':    forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Enter your first name'}),
            'last_name':     forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Enter your last name'}),
            'email':         forms.EmailInput(attrs={'class': _INPUT, 'placeholder': 'your.email@example.com', 'readonly': 'readonly'}),
            'phone':         forms.TextInput(attrs={'class': _INPUT, 'placeholder': '+234 XXX XXX XXXX'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': _INPUT}),
            'gender':        DisabledEmptySelect(attrs={'class': _SELECT}),

            # Address
            'address_line1': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Apartment, suite, etc. (optional)'}),
            'city':          forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'City'}),
            'state':         forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'State / Province'}),
            'postal_code':   forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Postal / ZIP code'}),

            # Academic Background
            'highest_qualification': forms.TextInput(attrs={'class': _INPUT, 'placeholder': "e.g., High School Diploma, Bachelor's Degree"}),
            'institution_name':      forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Name of institution attended'}),
            'graduation_year':       forms.NumberInput(attrs={'class': _INPUT, 'placeholder': 'e.g., 2020', 'min': 1950, 'max': 2030}),
            'gpa_or_grade':          forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'e.g., 3.5/4.0 or First Class'}),
            'language_skill':        DisabledEmptySelect(attrs={'class': _SELECT}),
            'language_score':        forms.NumberInput(attrs={'class': _INPUT, 'placeholder': 'e.g., 7.5 (IELTS) or 95 (TOEFL)', 'min': 0, 'step': '0.01'}),

            # Additional Information
            'work_experience_years': forms.NumberInput(attrs={'class': _INPUT, 'placeholder': '0', 'min': 0}),
            'personal_statement':    forms.Textarea(attrs={'class': _AREA, 'rows': 6, 'placeholder': 'Tell us about yourself and your goals...'}),

            # Emergency Contact
            'emergency_contact_name':         forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Full name'}),
            'emergency_contact_phone':        forms.TextInput(attrs={'class': _INPUT, 'placeholder': '+234 XXX XXX XXXX'}),
            'emergency_contact_relationship': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'e.g., Parent, Spouse, Sibling'}),

            # Consent & Options
            'accept_terms_conditions': forms.CheckboxInput(attrs={'class': _CHECK}),
            'accept_privacy_policy':   forms.CheckboxInput(attrs={'class': _CHECK}),
            'marketing_consent':       forms.CheckboxInput(attrs={'class': _CHECK}),
            'scholarship':             forms.CheckboxInput(attrs={'class': 'h-5 w-5 text-purple-700 rounded focus:ring-purple-500 cursor-pointer'}),
        }

    # ── __init__: populate dynamic choices ───────────────────────────────────
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Country choices from database
        countries = ListOfCountry.objects.order_by('country')
        self.fields['country'].choices = [('', 'Select Country')] + [
            (c.country_code, c.country) for c in countries
        ]

        # Nationality choices from database (use nationality field, fall back to country name)
        self.fields['nationality'].choices = [('', 'Select Nationality')] + [
            (c.nationality or c.country, c.nationality or c.country)
            for c in countries if (c.nationality or c.country)
        ]

        # personal_statement is optional at form level (model allows blank)
        self.fields['personal_statement'].required = False

        # language_score is optional if language_skill == 'none'
        self.fields['language_score'].required = False

    # ── Validation helpers ────────────────────────────────────────────────────
    def clean_email(self):
        return self.cleaned_data.get('email', '').lower().strip()

    def clean_phone(self):
        return self.cleaned_data.get('phone', '').strip()

    def clean_graduation_year(self):
        from datetime import datetime
        year = self.cleaned_data.get('graduation_year')
        try:
            year_int = int(year)
        except (ValueError, TypeError):
            raise forms.ValidationError('Please enter a valid graduation year.')
        if year_int < 1950:
            raise forms.ValidationError('Please enter a valid graduation year (1950 or later).')
        if year_int > datetime.now().year + 5:
            raise forms.ValidationError('Graduation year cannot be more than 5 years in the future.')
        return str(year_int)  # model field is TextField

    def clean(self):
        cleaned = super().clean()
        # If language_skill is set and not 'none', score is required
        skill = cleaned.get('language_skill')
        score = cleaned.get('language_score')
        if skill and skill != 'none' and not score:
            self.add_error('language_score', 'Please enter your test score.')
        # If how_did_you_hear == 'other', the other field is required
        hear = cleaned.get('how_did_you_hear')
        other = cleaned.get('how_did_you_hear_other', '').strip()
        if hear == 'other' and not other:
            self.add_error('how_did_you_hear_other', 'Please specify how you heard about us.')
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION DOCUMENT UPLOAD FORM
# ─────────────────────────────────────────────────────────────────────────────
class ApplicationDocumentUploadForm(forms.ModelForm):
    auto_submit = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'w-5 h-5 text-green-600 rounded focus:ring-2 focus:ring-green-500'}),
        label='Submit application after upload',
    )

    class Meta:
        model = ApplicationDocument
        fields = ['file', 'file_type']
        widgets = {
            'file_type': forms.Select(attrs={'class': _SELECT}),
            'file': forms.FileInput(attrs={'class': _INPUT, 'accept': '.pdf,.jpg,.jpeg,.png'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must be less than 5 MB.')
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in allowed_extensions:
                raise forms.ValidationError('Only PDF, JPG, and PNG files are allowed.')
        return file

# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD RESET FORMS
# ─────────────────────────────────────────────────────────────────────────────
class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': _INPUT,
            'placeholder': 'Enter your registered email',
            'autocomplete': 'email',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not User.objects.filter(email=email, is_active=True).exists():
            # Deliberate vague error — don't reveal if email exists
            raise ValidationError(
                'If this email is registered, you will receive a reset link shortly.'
            )
        return email


class SetNewPasswordForm(forms.Form):
    password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': _INPUT,
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        })
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': _INPUT,
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError({'password2': 'Passwords do not match.'})
        if p1 and len(p1) < 8:
            raise ValidationError({'password1': 'Password must be at least 8 characters.'})
        return cleaned