from django import forms

from .models import Lead, LeadActivity, LeadMessage

# Matches apps/management/forms.py's _SC_I / _SC_T constants — marketing
# templates extend management/base.html, so form fields use the same
# input/textarea styling as the rest of that portal.
_SC_I = {'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm'}
_SC_T = {'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none'}


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ['name', 'organization', 'email', 'phone', 'source', 'status', 'notes']
        widgets = {
            'name':         forms.TextInput(attrs=_SC_I),
            'organization': forms.TextInput(attrs=_SC_I),
            'email':        forms.EmailInput(attrs=_SC_I),
            'phone':        forms.TextInput(attrs=_SC_I),
            'source':       forms.Select(attrs=_SC_I),
            'status':       forms.Select(attrs=_SC_I),
            'notes':        forms.Textarea(attrs={**_SC_T, 'rows': 4}),
        }


class LeadActivityForm(forms.ModelForm):
    class Meta:
        model = LeadActivity
        fields = ['note', 'status_at_time']
        widgets = {
            'note':          forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            'status_at_time': forms.Select(attrs=_SC_I),
        }


class LeadMessageForm(forms.ModelForm):
    class Meta:
        model = LeadMessage
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={**_SC_T, 'rows': 2, 'placeholder': 'Write a message…'}),
        }
