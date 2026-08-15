from django import forms
from .models import (
    ContactMessage, CourseApplication,
    ApplicationDocument, Program
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
    
    def clean_password1(self):
        password = self.cleaned_data.get('password1', '')
        import re
        errors = []
        if len(password) < 8:
            errors.append('At least 8 characters.')
        if not re.search(r'[A-Z]', password):
            errors.append('At least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            errors.append('At least one lowercase letter.')
        if not re.search(r'\d', password):
            errors.append('At least one number.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append('At least one special character (!@#$% etc).')
        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)
        return password

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('Passwords do not match.')
        return password2
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


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


# COURSE APPLICATION FORM  — simple one-page inquiry form
# ─────────────────────────────────────────────────────────────────────────────
class CourseApplicationForm(forms.ModelForm):

    YES_NO_CHOICES = [('yes', 'Yes'), ('no', 'No')]

    age = forms.IntegerField(
        required=True, min_value=10, max_value=100,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'placeholder': 'Your age'}),
    )

    has_internet_access = forms.TypedChoiceField(
        choices=YES_NO_CHOICES,
        coerce=lambda v: v == 'yes',
        required=True,
        widget=forms.RadioSelect,
        label='Do you have access to the internet?',
    )
    has_laptop = forms.TypedChoiceField(
        choices=YES_NO_CHOICES,
        coerce=lambda v: v == 'yes',
        required=True,
        widget=forms.RadioSelect,
        label='Do you have a laptop?',
    )
    laptop_configuration = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'e.g. 8GB RAM, Intel i5-i7-i9, SSD'}),
        label='Your laptop configuration',
    )

    class Meta:
        model = CourseApplication
        fields = [
            'program',
            'first_name', 'last_name', 'email', 'phone', 'age',
            'country', 'state', 'address_line1',
            'highest_qualification',
            'has_internet_access', 'has_laptop', 'laptop_configuration',
        ]

        widgets = {
            'program': DisabledEmptySelect(attrs={'class': _SELECT}),

            'first_name': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Enter your first name'}),
            'last_name':  forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Enter your last name'}),
            'email':      forms.EmailInput(attrs={'class': _INPUT, 'placeholder': 'your.email@example.com', 'readonly': 'readonly'}),
            'phone':      forms.TextInput(attrs={'class': _INPUT, 'placeholder': '+234 XXX XXX XXXX'}),

            'country':        forms.TextInput(attrs={'class': f'{_SELECT} select2-country'}),
            'state':          forms.TextInput(attrs={'class': f'{_SELECT} select2-state'}),
            'address_line1':  forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Street address'}),

            'highest_qualification': forms.TextInput(attrs={'class': _INPUT, 'placeholder': "e.g., High School Diploma, Bachelor's Degree"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program'].queryset = (
            Program.objects.filter(is_active=True)
            .select_related('department__faculty')
            .order_by('department__faculty__name', 'name')
        )

    # ── Validation helpers ────────────────────────────────────────────────────
    def clean_email(self):
        return self.cleaned_data.get('email', '').lower().strip()

    def clean_phone(self):
        return self.cleaned_data.get('phone', '').strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('has_laptop') and not cleaned.get('laptop_configuration', '').strip():
            self.add_error('laptop_configuration', 'Please specify your laptop configuration.')
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
        # Deliberately does NOT check whether the email exists. It used to,
        # raising a ValidationError (and so failing form.is_valid()) only
        # for unregistered emails — which let anyone enumerate real accounts
        # simply by watching whether the "check your email" success screen
        # appeared or a field error did. The view (forgot_password) already
        # does the existence check itself and always renders the same
        # success screen either way; this form must stay silent on it.
        return self.cleaned_data.get('email', '').strip().lower()


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

    def clean_password1(self):
        password = self.cleaned_data.get('password1', '')
        import re
        errors = []
        if len(password) < 8:
            errors.append('At least 8 characters.')
        if not re.search(r'[A-Z]', password):
            errors.append('At least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            errors.append('At least one lowercase letter.')
        if not re.search(r'\d', password):
            errors.append('At least one number.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append('At least one special character (!@#$% etc).')
        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError({'password2': 'Passwords do not match.'})
        return cleaned