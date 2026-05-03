from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from eduweb.models import (
    Faculty,
    Department,
    Program,
    Course,
    BlogPost,
    BlogCategory,
    BroadcastMessage,
    LMSCourse,
    CourseApplication,
    Enrollment,
    UserProfile,
    SystemConfiguration,
    CourseCategory,
    StaffPayroll,
    Review,
    Certificate,
    Badge,
    StudentBadge,
    PaymentGateway,
    Transaction,
    Invoice,
    AllRequiredPayments,
    Announcement,
    SiteConfig, SiteHistoryMilestone, Testimonial, InstitutionMember, LibraryItem
)
import json


# ==============================================================================
# CUSTOM DATALIST WIDGETS
# ==============================================================================

class DatalistWidget(forms.TextInput):
    """Custom widget that renders a datalist for model selections"""
    def __init__(self, datalist_id=None, attrs=None):
        super().__init__(attrs)
        self.datalist_id = datalist_id or 'datalist-' + str(id(self))
    
    def render(self, name, value, attrs=None, renderer=None):
        # Get the html_id
        if attrs is None:
            attrs = {}
        attrs['list'] = self.datalist_id
        attrs['class'] = 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
        
        html = super().render(name, value, attrs, renderer)
        return html


class ModelDatalistWidget(forms.Widget):
    """Widget that renders input with datalist for model foreign keys"""
    def __init__(self, queryset, label_func=None, attrs=None):
        super().__init__(attrs)
        self.queryset = queryset
        self.label_func = label_func or (lambda obj: str(obj))
        self.datalist_id = 'datalist-' + str(id(self))
    
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        attrs['class'] = 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
        
        # Get the selected label
        selected_label = ''
        if value:
            try:
                obj = self.queryset.get(pk=value)
                selected_label = self.label_func(obj)
            except:
                selected_label = str(value)
        
        # Build the HTML
        html = f'<input type="text" name="{name}" value="{selected_label}" list="{self.datalist_id}" '
        for key, attr_value in attrs.items():
            html += f'{key}="{attr_value}" '
        html += '/>\n'
        
        # Add datalist
        html += f'<datalist id="{self.datalist_id}">\n'
        for obj in self.queryset:
            html += f'  <option value="{obj.pk}">{self.label_func(obj)}</option>\n'
        html += '</datalist>\n'
        
        return html


# ==============================================================================
# FACULTY FORM
# ==============================================================================

class FacultyForm(forms.ModelForm):
    special_features_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
            'rows': 6,
            'placeholder': 'Enter one feature per line in format:\nicon|title|description\n\nExample:\nrocket|Business Incubator|Launch your startup with mentorship'
        }),
        label='Special Features',
        help_text='Format: icon|title|description (one per line)'
    )

    class Meta:
        model = Faculty
        fields = [
            'name', 'code', 'icon', 'color_primary', 'color_secondary',
            'tagline', 'description', 'mission', 'vision',
            'student_count', 'placement_rate', 'partner_count', 'international_faculty',
            'accreditation', 'hero_image', 'about_image',
            'meta_description', 'meta_keywords',
            'is_active', 'display_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Faculty of Business'
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., BUS'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., briefcase (Lucide icon name)'
            }),
            'color_primary': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }, choices=[
                ('orange', 'Orange'), ('blue', 'Blue'), ('teal', 'Teal'),
                ('green', 'Green'), ('purple', 'Purple'), ('red', 'Red'),
                ('pink', 'Pink'), ('indigo', 'Indigo'), ('cyan', 'Cyan')
            ]),
            'color_secondary': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }, choices=[
                ('amber', 'Amber'), ('cyan', 'Cyan'), ('emerald', 'Emerald'),
                ('lime', 'Lime'), ('violet', 'Violet'), ('rose', 'Rose'),
                ('fuchsia', 'Fuchsia'), ('sky', 'Sky'), ('yellow', 'Yellow')
            ]),
            'tagline': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Lead. Innovate. Transform.'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 4,
                'placeholder': 'Main description of the faculty...'
            }),
            'mission': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 3,
                'placeholder': 'Faculty mission statement...'
            }),
            'vision': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 3,
                'placeholder': 'Faculty vision statement...'
            }),
            'student_count': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 4000'
            }),
            'placement_rate': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 95 (percentage)', 'min': 0, 'max': 100
            }),
            'partner_count': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 500'
            }),
            'international_faculty': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 85 (percentage)', 'min': 0, 'max': 100
            }),
            'accreditation': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 3,
                'placeholder': 'e.g., AACSB Accreditation - Top 5% worldwide'
            }),
            'hero_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'accept': 'image/*'
            }),
            'about_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'accept': 'image/*'
            }),
            'meta_description': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'SEO description (160 characters max)', 'maxlength': 160
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'keyword1, keyword2, keyword3'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 1 (lower numbers appear first)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.special_features:
            lines = []
            if isinstance(self.instance.special_features, list):
                for feature in self.instance.special_features:
                    if isinstance(feature, dict):
                        icon = feature.get('icon', '')
                        title = feature.get('title', '')
                        description = feature.get('description', '')
                        lines.append(f"{icon}|{title}|{description}")
                self.fields['special_features_text'].initial = '\n'.join(lines)

    def clean_special_features_text(self):
        text = self.cleaned_data.get('special_features_text', '').strip()
        if not text:
            return []
        features = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split('|')
            if len(parts) == 3:
                features.append({
                    'icon': parts[0].strip(),
                    'title': parts[1].strip(),
                    'description': parts[2].strip()
                })
        return features

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.special_features = self.cleaned_data.get('special_features_text', [])
        if commit:
            instance.save()
        return instance


# ==============================================================================
# COURSE FORM  — updated to match refactored Course model
# Course is now a subject/unit under a Program.
# Program-level fields (fees, degree_level, duration, etc.) are no longer here.
# ==============================================================================

class CourseForm(forms.ModelForm):
    """
    Form for creating / editing a Course (academic subject unit).
    Aligns with the refactored Course model:
      - Belongs to a Program (not directly to Faculty/Department)
      - Has course_type, credit_units, year_of_study, semester
      - Has academic_session and lecturer
      - learning_outcomes stored as JSON (textarea helper provided)
    """

    # ── JSON textarea helpers ──────────────────────────────────────────────────
    learning_outcomes_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
            'rows': 4,
            'placeholder': (
                'Enter one outcome per line:\n'
                'Understand core programming concepts\n'
                'Apply data structures in real problems\n'
                'Build and deploy web applications'
            )
        }),
        label='Learning Outcomes',
        help_text='One outcome per line — stored as a list'
    )

    class Meta:
        model = Course
        fields = [
            'program', 'name', 'code', 'course_type', 'credit_units',
            'year_of_study', 'semester',
            'description', 'learning_outcomes', 'is_active',
            # 'icon', 'color_primary', 'color_secondary', 'display_order',
        ]
        widgets = {
            # ── Hierarchy ──────────────────────────────────────────────────
            'program': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white',
            }),

            # ── Identity ──────────────────────────────────────────────────
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Introduction to Programming'
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., CS101'
            }),

            # ── Academic Structure ─────────────────────────────────────────
            'course_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }),
            'credit_units': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 3',
                'min': 1,
                'max': 12
            }),
            'year_of_study': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 1',
                'min': 1,
                'max': 7
            }),
            'semester': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }),

            # ── Session & Instructor ───────────────────────────────────────
            # 'academic_session': forms.Select(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            # }),
            # 'lecturer': forms.Select(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            # }),

            # ── Content ────────────────────────────────────────────────────
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 4,
                'placeholder': 'What does this course cover?'
            }),

            # ── Display ────────────────────────────────────────────────────
            # 'icon': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
            #     'placeholder': 'e.g., book-open (Lucide icon name)'
            # }),
            # 'color_primary': forms.Select(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            # }, choices=[
            #     ('blue', 'Blue'), ('teal', 'Teal'), ('green', 'Green'),
            #     ('orange', 'Orange'), ('purple', 'Purple'), ('red', 'Red'),
            #     ('pink', 'Pink'), ('indigo', 'Indigo'), ('cyan', 'Cyan')
            # ]),
            # 'color_secondary': forms.Select(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            # }, choices=[
            #     ('cyan', 'Cyan'), ('emerald', 'Emerald'), ('lime', 'Lime'),
            #     ('amber', 'Amber'), ('violet', 'Violet'), ('rose', 'Rose'),
            #     ('fuchsia', 'Fuchsia'), ('sky', 'Sky'), ('yellow', 'Yellow')
            # ]),

            # ── Status ─────────────────────────────────────────────────────
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            # 'display_order': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
            #     'placeholder': 'e.g., 1 (lower numbers appear first)'
            # }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program'].empty_label = '— Select Program —'

        # Pre-populate learning_outcomes_text when editing
        if self.instance.pk:
            outcomes = self.instance.learning_outcomes
            if outcomes and isinstance(outcomes, list):
                self.fields['learning_outcomes_text'].initial = '\n'.join(outcomes)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert textarea to JSON list
        raw = self.cleaned_data.get('learning_outcomes_text', '')
        instance.learning_outcomes = [
            line.strip() for line in raw.split('\n') if line.strip()
        ]
        if commit:
            instance.save()
        return instance


# ==============================================================================
# BLOG FORMS
# ==============================================================================

class BlogCategoryForm(forms.ModelForm):
    class Meta:
        model = BlogCategory
        fields = ['name', 'description', 'icon', 'color', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Student Life'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 3,
                'placeholder': 'Brief description of this category...'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., users (Lucide icon name)'
            }),
            'color': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }, choices=[
                ('blue', 'Blue'), ('green', 'Green'), ('purple', 'Purple'),
                ('orange', 'Orange'), ('red', 'Red'), ('teal', 'Teal'),
                ('pink', 'Pink'), ('indigo', 'Indigo'), ('rose', 'Rose')
            ]),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 1 (lower numbers appear first)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }


class BlogPostForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
            'placeholder': 'research, innovation, technology (comma-separated)'
        }),
        label='Tags',
        help_text='Enter tags separated by commas'
    )

    class Meta:
        model = BlogPost
        fields = [
            'title', 'subtitle', 'excerpt', 'content', 'category',
            'author_name', 'author_title', 'featured_image', 'featured_image_alt',
            'read_time', 'status', 'is_featured', 'publish_date',
            'meta_description', 'meta_keywords'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., MIU Researchers Develop Breakthrough AI Technology'
            }),
            'subtitle': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'Optional subtitle for additional context'
            }),
            'excerpt': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 3,
                'placeholder': 'Write a compelling summary (max 500 characters)...',
                'maxlength': 500
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'rows': 15,
                'placeholder': 'Write your full blog post content here. You can use HTML for formatting...'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }),
            'author_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Dr. Sarah Johnson'
            }),
            'author_title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., Communications Director'
            }),
            'featured_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'accept': 'image/*'
            }),
            'featured_image_alt': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'Describe the image for accessibility'
            }),
            'read_time': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'e.g., 5 (minutes)', 'min': 1
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all bg-white'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'publish_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all'
            }),
            'meta_description': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'SEO meta description (max 160 characters)', 'maxlength': 160
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all',
                'placeholder': 'keyword1, keyword2, keyword3'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.tags:
            if isinstance(self.instance.tags, list):
                self.fields['tags_text'].initial = ', '.join(self.instance.tags)

    def clean_tags_text(self):
        text = self.cleaned_data.get('tags_text', '').strip()
        if not text:
            return []
        return [tag.strip().lower() for tag in text.split(',') if tag.strip()]

    def clean_excerpt(self):
        excerpt = self.cleaned_data.get('excerpt', '')
        if len(excerpt) > 500:
            raise forms.ValidationError('Excerpt must be 500 characters or less.')
        return excerpt

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.tags = self.cleaned_data.get('tags_text', [])
        if commit:
            instance.save()
        return instance


# ==============================================================================
# USER FORMS
# ==============================================================================

class UserSearchForm(forms.Form):
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Search by name, username, or email...',
            'id': 'searchInput'
        })
    )
    role = forms.ChoiceField(
        required=False,
        choices=[('', 'All Roles')] + UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white',
            'id': 'roleFilter'
        })
    )
    is_active = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status'), ('true', 'Active'), ('false', 'Inactive')],
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white',
            'id': 'statusFilter'
        })
    )


class UserCreateForm(forms.ModelForm):
    """
    Admin-facing user creation form.
    Password is NOT included — the view generates it automatically and
    emails the credentials to the new user.
    Role is captured here and applied to UserProfile after save().
    is_staff is intentionally excluded: it is set by the view based on role.
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
            'placeholder': 'user@example.com',
        })
    )
    first_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
            'placeholder': 'John',
        })
    )
    last_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
            'placeholder': 'Doe',
        })
    )
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white text-md',
        })
    )
    is_active = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500',
        }),
        help_text='User can log in immediately after creation.'
    )
 
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
                'placeholder': 'johndoe',
            }),
        }
 
    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email is already registered.')
        return email
 
    def save(self, commit=True, raw_password=None):
        """
        Save the User instance.
        raw_password must be provided by the view (already generated).
        """
        user = super().save(commit=False)
        if raw_password:
            user.set_password(raw_password)
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """
    Edit basic User fields. is_staff is NOT included — the view derives
    it from UserProfile.role to enforce the admin-only staff rule.
    """
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-200 bg-gray-50 rounded-lg text-md text-gray-500 cursor-not-allowed',
                'readonly': True,
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
                'placeholder': 'Last name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-md',
                'placeholder': 'user@example.com',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500',
            }),
        }
 
    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('This email is already in use.')
        return email


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('role', 'bio', 'avatar', 'phone', 'date_of_birth',
                  'address', 'city', 'country', 'website', 'linkedin',
                  'twitter', 'email_notifications', 'marketing_emails')
        widgets = {
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 4, 'placeholder': 'Tell us about yourself...'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'accept': 'image/*'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': '+1234567890'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'type': 'date'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 2, 'placeholder': 'Street address'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'City'
            }),
            'country': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Country'
            }),
            'website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://yourwebsite.com'
            }),
            'linkedin': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://linkedin.com/in/username'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://twitter.com/username'
            }),
            'email_notifications': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
            }),
            'marketing_emails': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
            })
        }


class QuickRoleChangeForm(forms.Form):
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white'
        })
    )


# ==============================================================================
# SYSTEM CONFIGURATION FORMS
# ==============================================================================

class SystemConfigurationForm(forms.ModelForm):
    class Meta:
        model = SystemConfiguration
        fields = ('key', 'value', 'setting_type', 'description', 'is_public')
        widgets = {
            'key': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'e.g., site_name'
            }),
            'value': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 4, 'placeholder': 'Configuration value'
            }),
            'setting_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 2, 'placeholder': 'Describe what this setting controls'
            }),
            'is_public': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
            })
        }

# ── shared Tailwind input attr dicts (matches the rest of this forms.py) ──────
_SC_I = {'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm'}
_SC_T = {'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none'}
_SC_C = {'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm font-mono resize-none'}


class SiteConfigGeneralForm(forms.ModelForm):
    """
    Covers everything base.html reads:
    identity, logos, SEO, footer tagline, copyright,
    social links, contact (phone/email/address).
    """
    class Meta:
        model = SiteConfig
        fields = [
            # Identity
            'school_name', 'school_short_name', 'tagline', 'theme_color',
            # Logos & images
            'logo', 'logo_dark', 'favicon', 'og_image',
            # SEO
            'meta_description', 'meta_keywords',
            # Footer
            'footer_tagline', 'copyright_year',
            # Contact — footer bar
            'email', 'phone_primary', 'phone_secondary',
            'phone_ng_primary', 'phone_ng_secondary', 'whatsapp',
            # Contact page emails
            'email_admissions', 'email_info', 'email_international',
            # Contact page phones
            'phone_admissions', 'phone_general', 'phone_international',
            # Addresses
            'address_usa', 'address_nigeria',
            # Office hours
            'office_hours_weekday', 'office_hours_saturday', 'office_hours_sunday',
            # Social
            'facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'tiktok',
        ]
        widgets = {
            # Identity
            'school_name':           forms.TextInput(attrs=_SC_I),
            'school_short_name':     forms.TextInput(attrs=_SC_I),
            'tagline':               forms.TextInput(attrs=_SC_I),
            'theme_color':           forms.TextInput(attrs={
                'type': 'color',
                'class': 'h-10 w-16 p-1 border border-gray-300 rounded-lg cursor-pointer',
            }),
            # SEO
            'meta_description':      forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            'meta_keywords':         forms.Textarea(attrs={**_SC_T, 'rows': 2}),
            # Footer
            'footer_tagline':        forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            'copyright_year':        forms.TextInput(attrs=_SC_I),
            # Contact — footer bar
            'email':                 forms.EmailInput(attrs=_SC_I),
            'phone_primary':         forms.TextInput(attrs=_SC_I),
            'phone_secondary':       forms.TextInput(attrs=_SC_I),
            'phone_ng_primary':      forms.TextInput(attrs=_SC_I),
            'phone_ng_secondary':    forms.TextInput(attrs=_SC_I),
            'whatsapp':              forms.TextInput(attrs=_SC_I),
            # Contact page emails
            'email_admissions':      forms.EmailInput(attrs=_SC_I),
            'email_info':            forms.EmailInput(attrs=_SC_I),
            'email_international':   forms.EmailInput(attrs=_SC_I),
            # Contact page phones
            'phone_admissions':      forms.TextInput(attrs=_SC_I),
            'phone_general':         forms.TextInput(attrs=_SC_I),
            'phone_international':   forms.TextInput(attrs=_SC_I),
            # Addresses
            'address_usa':           forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            'address_nigeria':       forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            # Office hours
            'office_hours_weekday':  forms.TextInput(attrs=_SC_I),
            'office_hours_saturday': forms.TextInput(attrs=_SC_I),
            'office_hours_sunday':   forms.TextInput(attrs=_SC_I),
            # Social
            'facebook':              forms.URLInput(attrs=_SC_I),
            'twitter':               forms.URLInput(attrs=_SC_I),
            'instagram':             forms.URLInput(attrs=_SC_I),
            'linkedin':              forms.URLInput(attrs=_SC_I),
            'youtube':               forms.URLInput(attrs=_SC_I),
            'tiktok':                forms.URLInput(attrs=_SC_I),
        }


class SiteConfigIndexForm(forms.ModelForm):
    """
    Covers everything index.html reads beyond the general fields:
    hero slides (3×image+video+alt+duration), promo video embed,
    campus map embed + address.
    """
    class Meta:
        model = SiteConfig
        fields = [
            # Hero slide 1
            'hero_slide_1_image', 'hero_slide_1_video',
            'hero_slide_1_alt', 'hero_slide_1_duration',
            # Hero slide 2
            'hero_slide_2_image', 'hero_slide_2_video',
            'hero_slide_2_alt', 'hero_slide_2_duration',
            # Hero slide 3
            'hero_slide_3_image', 'hero_slide_3_video',
            'hero_slide_3_alt', 'hero_slide_3_duration',
            # Embeds
            'promo_video_url',
            'campus_map_embed_url', 'campus_map_address',
        ]
        widgets = {
            'hero_slide_1_alt':      forms.TextInput(attrs=_SC_I),
            'hero_slide_1_duration': forms.NumberInput(attrs=_SC_I),
            'hero_slide_2_alt':      forms.TextInput(attrs=_SC_I),
            'hero_slide_2_duration': forms.NumberInput(attrs=_SC_I),
            'hero_slide_3_alt':      forms.TextInput(attrs=_SC_I),
            'hero_slide_3_duration': forms.NumberInput(attrs=_SC_I),
            'promo_video_url':       forms.Textarea(attrs={
                **_SC_C, 'rows': 4,
                'placeholder': 'Paste full <iframe> embed code from YouTube/Vimeo',
            }),
            'campus_map_embed_url':  forms.Textarea(attrs={
                **_SC_C, 'rows': 4,
                'placeholder': 'Paste full <iframe> embed code from Google Maps',
            }),
            'campus_map_address':    forms.TextInput(attrs=_SC_I),
        }


class SiteConfigAboutForm(forms.ModelForm):
    """
    Covers everything about.html reads beyond the general fields:
    mission, vision, values (JSON list), virtual tour embed.
    """
    about_values = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            **_SC_T, 'rows': 6,
            'placeholder': 'One value per line e.g.\nExcellence in Education\nDiversity & Inclusion',
        }),
        help_text='Enter each core value on its own line. Saved as a JSON list automatically.',
    )

    class Meta:
        model = SiteConfig
        fields = [
            'about_mission', 'about_vision', 'about_values',
            'virtual_tour_url',
        ]
        widgets = {
            'about_mission':    forms.Textarea(attrs={**_SC_T, 'rows': 5}),
            'about_vision':     forms.Textarea(attrs={**_SC_T, 'rows': 5}),
            'virtual_tour_url': forms.Textarea(attrs={
                **_SC_C, 'rows': 4,
                'placeholder': 'Paste full <iframe> embed code for the virtual campus tour',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.about_values:
            vals = self.instance.about_values
            if isinstance(vals, list):
                self.fields['about_values'].initial = '\n'.join(vals)

    def clean_about_values(self):
        raw = self.cleaned_data.get('about_values', '')
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return lines

class SiteHistoryMilestoneForm(forms.ModelForm):
    class Meta:
        model = SiteHistoryMilestone
        fields = ['year', 'title', 'description', 'display_order', 'is_active']
        widgets = {
            'year':          forms.NumberInput(attrs={**_SC_I, 'placeholder': 'e.g. 1995'}),
            'title':         forms.TextInput(attrs={**_SC_I, 'placeholder': "e.g. 'Founding'"}),
            'description':   forms.Textarea(attrs={**_SC_T, 'rows': 3}),
            'display_order': forms.NumberInput(attrs=_SC_I),
        }


class TestimonialForm(forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ['author_name', 'author_role', 'quote', 'avatar', 'order', 'is_active']
        widgets = {
            'author_name': forms.TextInput(attrs=_SC_I),
            'author_role': forms.TextInput(attrs={**_SC_I, 'placeholder': "e.g. 'MBA Graduate, 2023'"}),
            'quote':       forms.Textarea(attrs={**_SC_T, 'rows': 4}),
            'order':       forms.NumberInput(attrs=_SC_I),
        }


class InstitutionMemberForm(forms.ModelForm):
    class Meta:
        model = InstitutionMember
        fields = ['member_type', 'name', 'role', 'photo', 'bio', 'display_order', 'is_active']
        widgets = {
            'member_type':   forms.Select(attrs={'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm bg-white'}),
            'name':          forms.TextInput(attrs=_SC_I),
            'role':          forms.TextInput(attrs={**_SC_I, 'placeholder': "e.g. 'Vice Chancellor'"}),
            'bio':           forms.Textarea(attrs={**_SC_T, 'rows': 4}),
            'display_order': forms.NumberInput(attrs=_SC_I),
        }

class BrandingConfigForm(forms.Form):
    site_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Your University Name'
        })
    )
    site_tagline = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Your inspiring tagline'
        })
    )
    logo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'accept': 'image/*'
        })
    )
    favicon = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'accept': 'image/*'
        })
    )
    primary_color = forms.CharField(
        max_length=7,
        widget=forms.TextInput(attrs={
            'type': 'color',
            'class': 'h-12 w-24 rounded-lg border border-gray-300'
        })
    )


class EmailConfigForm(forms.Form):
    smtp_host = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'smtp.example.com'
        })
    )
    smtp_port = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': '587'
        })
    )
    smtp_username = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'your-email@example.com'
        })
    )
    smtp_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': '••••••••'
        })
    )
    from_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'noreply@example.com'
        })
    )
    from_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'University Name'
        })
    )


class NotificationConfigForm(forms.Form):
    enable_email_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
        })
    )
    enable_sms_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
        })
    )
    enable_push_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
        })
    )
    notification_from_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'notifications@example.com'
        })
    )


# ==============================================================================
# COURSE CATEGORY FORM
# ==============================================================================

class CourseCategoryForm(forms.ModelForm):
    class Meta:
        model = CourseCategory
        fields = ('name', 'description', 'icon', 'color', 'is_active', 'display_order')
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'e.g., Programming'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 3, 'placeholder': 'Brief description of this category'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'code (Font Awesome icon name without fa-)'
            }),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'h-12 w-24 rounded-lg border border-gray-300'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 border-gray-300 rounded focus:ring-2 focus:ring-primary-500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': '0'
            })
        }


# ==============================================================================
# AUDIT LOG FILTER FORM
# ==============================================================================

class AuditLogFilterForm(forms.Form):
    ACTION_CHOICES = [
        ('', 'All Actions'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('password_reset', 'Password Reset'),
        ('permission_change', 'Permission Change'),
    ]

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        empty_label='All Users',
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white'
        })
    )
    action = forms.ChoiceField(
        choices=ACTION_CHOICES, required=False,
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white'
        })
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
        })
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Search description...'
        })
    )


# ==============================================================================
# BROADCAST FORM
# NOTE: The Course filter here refers to academic Course (admission),
#       not the old Course which had program-level fields.
# ==============================================================================

class BroadcastMessageForm(forms.ModelForm):

    faculties = forms.ModelMultipleChoiceField(
        queryset=Faculty.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Faculties"
    )

    # Filters by Program now (since Course is a unit — Program is the admission-level entity)
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Programs (Admission)"
    )

    # Keep academic Course filter — now scoped to subject units
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Courses (Academic Units)"
    )

    lms_courses = forms.ModelMultipleChoiceField(
        queryset=LMSCourse.objects.filter(is_published=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select LMS Courses"
    )

    roles = forms.MultipleChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select User Roles"
    )

    application_statuses = forms.MultipleChoiceField(
        choices=CourseApplication.STATUS_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Application Statuses"
    )

    enrollment_statuses = forms.MultipleChoiceField(
        choices=Enrollment.STATUS_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Select Enrollment Statuses"
    )

    class Meta:
        model = BroadcastMessage
        fields = ['subject', 'message', 'filter_type']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'placeholder': 'Email Subject'
            }),
            'message': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border rounded-lg',
                'rows': 8,
                'placeholder': 'Email Message Content'
            }),
            'filter_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'id': 'id_filter_type'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        filter_type = cleaned_data.get('filter_type')

        validation_map = {
            'faculty':            ('faculties',            'Please select at least one faculty.'),
            'program':            ('programs',             'Please select at least one program.'),
            'course':             ('courses',              'Please select at least one course.'),
            'lms_course':         ('lms_courses',          'Please select at least one LMS course.'),
            'role':               ('roles',                'Please select at least one role.'),
            'application_status': ('application_statuses', 'Please select at least one application status.'),
            'enrollment_status':  ('enrollment_statuses',  'Please select at least one enrollment status.'),
        }

        if filter_type in validation_map:
            field, message = validation_map[filter_type]
            if not cleaned_data.get(field):
                raise forms.ValidationError(message)

        return cleaned_data

from django import forms
from eduweb.models import (
    Department, Program, AcademicSession, CourseIntake,
    Announcement, LMSCourse, CourseCategory
)


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['faculty', 'name', 'code', 'description', 'display_order', 'is_active']

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        return code


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = [
            'department', 'name', 'code', 'degree_level',
            'duration_years', 'credits_required', 'max_students',
            'tagline', 'overview', 'description',
            'application_fee', 'tuition_fee', 'avg_starting_salary',
            'job_placement_rate',
            'is_active', 'is_featured', 'display_order',
            'hero_image', 'meta_description', 'meta_keywords',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'placeholder': 'e.g., BSc Electrical Engineering'
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm uppercase',
                'placeholder': 'e.g., BSC-EEE'
            }),
            'degree_level': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm'
            }),
            'duration_years': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'step': '0.5',
                'min': '0.5',
                'placeholder': '4.0'
            }),
            'credits_required': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'min': '0'
            }),
            'max_students': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'min': '1',
                'placeholder': 'Unlimited'
            }),
            'tagline': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'placeholder': 'Short marketing tagline…'
            }),
            'overview': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none',
                'rows': '3'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none',
                'rows': '5'
            }),
            'application_fee': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'step': '0.01',
                'min': '0'
            }),
            'tuition_fee': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'step': '0.01',
                'min': '0'
            }),
            'avg_starting_salary': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'placeholder': 'e.g., $45,000 - $60,000'
            }),
            'job_placement_rate': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'min': '0',
                'max': '100'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded text-primary-600 border-gray-300 focus:ring-primary-500'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded text-primary-600 border-gray-300 focus:ring-primary-500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-20 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'min': '0'
            }),
            'hero_image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'accept': 'image/*'
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm resize-none',
                'rows': '2',
                'maxlength': '160',
                'placeholder': 'Brief description for search engines'
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm',
                'placeholder': 'e.g., engineering, computer science, degree'
            }),
        }

    def clean_code(self):
        return self.cleaned_data.get('code', '').strip().upper()


class AcademicSessionForm(forms.ModelForm):
    class Meta:
        model = AcademicSession
        fields = [
            'name', 'status', 'is_current',
            'term_dates'
            # 'registration_start', 'registration_end',
        ]
        # widgets = {
        #     'registration_start': forms.DateInput(attrs={'type': 'date'}),
        #     'registration_end': forms.DateInput(attrs={'type': 'date'}),
        # }

    # def clean(self):
    #     cleaned = super().clean()
    #     reg_start = cleaned.get('registration_start')
    #     reg_end = cleaned.get('registration_end')
    #     if reg_start and reg_end and reg_start >= reg_end:
    #         raise forms.ValidationError('Registration start must be before end date.')
    #     return cleaned


class CourseIntakeForm(forms.ModelForm):
    class Meta:
        model = CourseIntake
        fields = ['program', 'intake_period', 'year', 'start_date', 'application_deadline', 'available_slots', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'application_deadline': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        deadline = cleaned.get('application_deadline')
        if start and deadline and deadline >= start:
            raise forms.ValidationError('Application deadline must be before the start date.')
        return cleaned


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            'title', 'content',
            'announcement_type', 'priority',
            'course', 'category',
            'is_active', 'publish_date', 'expiry_date',
        ]
        widgets = {
            'publish_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expiry_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'content': forms.Textarea(attrs={'rows': 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active courses & categories
        self.fields['course'].queryset = LMSCourse.objects.filter(is_published=True).order_by('title')
        self.fields['category'].queryset = CourseCategory.objects.filter(is_active=True).order_by('name')
        self.fields['course'].required = False
        self.fields['category'].required = False


class LMSCourseForm(forms.ModelForm):
    """Form for creating/editing LMS courses"""
    
    # JSON textarea helpers
    learning_objectives_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            'rows': 4,
            'placeholder': 'One objective per line:\nUnderstand core concepts\nApply practical skills\nEvaluate real-world scenarios'
        }),
        label='Learning Objectives',
        help_text='One objective per line'
    )
    
    prerequisites_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            'rows': 3,
            'placeholder': 'One prerequisite per line:\nBasic programming knowledge\nHTML/CSS fundamentals'
        }),
        label='Prerequisites',
        help_text='One prerequisite per line'
    )
    
    class Meta:
        model = LMSCourse
        fields = [
            'title', 'code', 'short_description', 'description',
            'difficulty_level',
            'academic_course', 'session', 'term',
            'instructor',
            'thumbnail', 'promo_video_url',
            'is_published', 'is_featured',
            'meta_description', 'meta_keywords',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Course title'
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'UNIQ course code'
            }),
            # 'category': forms.Select(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            # }),
            'short_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'rows': 2,
                'placeholder': 'Brief course summary (max 500 chars)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'rows': 5,
                'placeholder': 'Detailed course description'
            }),
            'difficulty_level': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            # 'duration_hours': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': 'Estimated hours',
            #     'step': '0.5',
            #     'min': '0'
            # }),
            # 'language': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': 'English'
            # }),
            'instructor': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            # 'instructor_name': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': 'Instructor name (if not selected above)'
            # }),
            # 'instructor_bio': forms.Textarea(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'rows': 3,
            #     'placeholder': 'Brief biography'
            # }),
            'thumbnail': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            }),
            'promo_video_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'YouTube or Vimeo URL'
            }),
            # 'max_students': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': 'Leave empty for unlimited'
            # }),
            # 'enrollment_start_date': forms.DateInput(attrs={
            #     'type': 'date',
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            # }),
            # 'enrollment_end_date': forms.DateInput(attrs={
            #     'type': 'date',
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            # }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded focus:ring-2 focus:ring-primary-500'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded focus:ring-2 focus:ring-primary-500'
            }),
            # 'has_certificate': forms.CheckboxInput(attrs={
            #     'class': 'w-5 h-5 text-primary-600 rounded focus:ring-2 focus:ring-primary-500'
            # }),
            # 'certificate_template': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': 'Certificate template filename'
            # }),
            'academic_course': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'session': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'term': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            # 'certificate_fee': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
            #     'placeholder': '0.00',
            #     'step': '0.01',
            #     'min': '0'
            # }),
            'meta_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'rows': 2,
                'placeholder': 'SEO meta description (160 chars)'
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Comma-separated keywords'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['category'].empty_label = '— Select Category —'
        self.fields['instructor'].empty_label = '— Select Instructor —'
        self.fields['instructor'].queryset = User.objects.filter(
            profile__role='instructor',
            is_active=True,
        ).order_by('last_name', 'first_name')
        self.fields['instructor'].required = False
        # Display full name in the dropdown instead of username
        self.fields['instructor'].label_from_instance = lambda u: (
            u.get_full_name().strip() or u.username
        )
        self.fields['academic_course'].empty_label = '— Select Academic Course —'
        # NOTE: academic_course is REQUIRED — all LMS courses must be tied to
        # the academic catalogue per MIU policy (no standalone LMS courses).
        self.fields['academic_course'].required = True
        from eduweb.models import Course as AcademicCourse
        self.fields['academic_course'].queryset = (
            AcademicCourse.objects
            .select_related('program__department__faculty')
            .only(
                'id', 'code', 'name', 'year_of_study', 'semester',
                'program__id', 'program__name',
                'program__department__id', 'program__department__name',
                'program__department__faculty__id', 'program__department__faculty__name',
            )
            .order_by('program__department__faculty__name', 'program__department__name', 'program__name', 'year_of_study', 'semester', 'code')
        )
        self.fields['academic_course'].label_from_instance = lambda c: (
            f"{c.code} — {c.name}"
        )        
        # Pre-populate JSON fields when editing
        if self.instance.pk:
            objectives = self.instance.learning_objectives
            if objectives and isinstance(objectives, list):
                self.fields['learning_objectives_text'].initial = '\n'.join(objectives)
            
            prerequisites = self.instance.prerequisites
            if prerequisites and isinstance(prerequisites, list):
                self.fields['prerequisites_text'].initial = '\n'.join(prerequisites)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Convert learning objectives textarea to JSON list
        objectives_raw = self.cleaned_data.get('learning_objectives_text', '')
        instance.learning_objectives = [
            line.strip() for line in objectives_raw.split('\n') if line.strip()
        ]
        
        # Convert prerequisites textarea to JSON list
        prerequisites_raw = self.cleaned_data.get('prerequisites_text', '')
        instance.prerequisites = [
            line.strip() for line in prerequisites_raw.split('\n') if line.strip()
        ]
        
        if commit:
            instance.save()
        return instance


# ==============================================================================
# ENROLLMENT FORM
# ==============================================================================

class EnrollmentForm(forms.ModelForm):
    """Form for managing student course enrollments"""
    
    class Meta:
        model = Enrollment
        fields = [
            'student', 'course', 'status',
            'progress_percentage', 'current_grade',
            'completed_at'
        ]
        widgets = {
            'student': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'course': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'list': 'course-list',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'progress_percentage': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'current_grade': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'completed_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].empty_label = '— Select Student —'
        self.fields['course'].empty_label = '— Select Course —'
        self.fields['current_grade'].required = False
        self.fields['completed_at'].required = False


# ==============================================================================
# STAFF PAYROLL FORM
# ==============================================================================

class StaffPayrollForm(forms.ModelForm):
    """Form for managing staff payroll"""
    
    class Meta:
        model = StaffPayroll
        fields = [
            'staff', 'month', 'year', 'base_salary', 'allowances',
            'bonuses', 'tax_deduction', 'other_deductions',
            'payment_method', 'payment_date', 'bank_name', 'account_number',
            'currency'
        ]
        widgets = {
            'staff': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'month': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'year': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'min': '2020'
            }),
            'base_salary': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'allowances': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'bonuses': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'tax_deduction': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'other_deductions': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'payment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Bank name'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Account number'
            }),
            'currency': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 uppercase',
                'placeholder': 'e.g. USD, GBP, EUR',
                'maxlength': '3',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['staff'].empty_label = '— Select Staff —'
        self.fields['payment_date'].required = False
        self.fields['bank_name'].required = False
        self.fields['account_number'].required = False

# ==============================================================================
# CERTIFICATE FORM
# ==============================================================================

class CertificateForm(forms.ModelForm):
    """Certificate issue / edit form"""

    class Meta:
        model  = Certificate
        fields = [
            'student', 'course', 'completion_date',
            'grade', 'certificate_file', 'is_verified',
        ]
        widgets = {
            # student & course are rendered as datalists in the template;
            # these hidden-compatible widgets just need to accept a PK.
            'student': forms.HiddenInput(),
            'course':  forms.HiddenInput(),
            'completion_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'type': 'date',
                    'class': (
                        'w-full px-4 py-3 border border-gray-300 rounded-lg'
                        ' focus:ring-2 focus:ring-primary-500 focus:outline-none'
                    ),
                }
            ),
            'grade': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 rounded-lg'
                    ' focus:ring-2 focus:ring-primary-500 focus:outline-none'
                ),
                'placeholder': 'e.g. A, B+, 85',
                'maxlength': '5',
            }),
            'certificate_file': forms.FileInput(attrs={
                'class': (
                    'block w-full text-sm text-gray-500'
                    ' file:mr-4 file:py-2 file:px-4'
                    ' file:rounded-lg file:border-0'
                    ' file:text-sm file:font-semibold'
                    ' file:bg-primary-50 file:text-primary-700'
                    ' hover:file:bg-primary-100'
                ),
            }),
            'is_verified': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded cursor-pointer',
            }),
        }


# ==============================================================================
# BADGE FORM
# ==============================================================================

class BadgeForm(forms.ModelForm):
    """Form for managing achievement badges"""
    
    class Meta:
        model = Badge
        fields = [
            'name', 'description', 'icon', 'color',
            'criteria', 'points', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'e.g., Coding Master'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'rows': 3,
                'placeholder': 'What does this badge represent?'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Icon name (e.g., award, star, trophy)'
            }),
            'color': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Color (e.g., gold, silver, bronze)',
                'type': 'color'
            }),
            'criteria': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'rows': 2,
                'placeholder': 'Requirements to earn this badge'
            }),
            'points': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'min': '0'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded'
            }),
        }


# ==============================================================================
# REVIEW FORM  —  replace the existing ReviewForm class in forms.py
# ==============================================================================

class ReviewForm(forms.ModelForm):
    """Form for managing course reviews. Course and Student use datalist in the
    template; these hidden fields carry the resolved PKs to the view."""

    class Meta:
        model = Review
        fields = [
            'course', 'student', 'rating', 'review_text', 'is_approved'
        ]
        widgets = {
            # course & student PKs are injected by JavaScript from datalist inputs
            'course': forms.HiddenInput(),
            'student': forms.HiddenInput(),
            'rating': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:outline-none',
                'min': '1',
                'max': '5',
                'step': '1',
            }),
            'review_text': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:outline-none',
                'rows': 4,
                'placeholder': 'Write your detailed review...',
            }),
            'is_approved': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['review_text'].required = False
        # Only students (UserProfile.role == 'student') are valid reviewers
        self.fields['student'].queryset = User.objects.filter(
            profile__role='student'
        ).order_by('last_name', 'first_name', 'username')


# ==============================================================================
# STUDENT BADGE ASSIGNMENT FORM  —  replace the existing StudentBadgeForm class
# ==============================================================================

class StudentBadgeForm(forms.ModelForm):
    """Form for assigning badges to students. Student and Badge use datalist in
    the template; hidden fields carry the resolved PKs."""

    class Meta:
        model = StudentBadge
        fields = ['student', 'badge', 'reason']
        widgets = {
            # student & badge PKs are injected by JavaScript from datalist inputs
            'student': forms.HiddenInput(),
            'badge': forms.HiddenInput(),
            'reason': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:outline-none',
                'rows': 2,
                'placeholder': 'Why is this badge being awarded?',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reason'].required = False
        # Restrict student choices to users whose profile role is 'student'
        self.fields['student'].queryset = User.objects.filter(
            profile__role='student'
        ).order_by('last_name', 'first_name', 'username')
        self.fields['badge'].queryset = Badge.objects.filter(
            is_active=True
        ).order_by('name')


# ==============================================================================
# PAYMENT GATEWAY FORM
# ==============================================================================

class PaymentGatewayForm(forms.ModelForm):
    """Form for managing payment gateways"""
    
    class Meta:
        model = PaymentGateway
        fields = [
            'name', 'gateway_type', 'api_key', 'api_secret',
            'webhook_secret', 'is_active', 'is_test_mode'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'e.g., Stripe Live'
            }),
            'gateway_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'api_key': forms.PasswordInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'API Key (password field)'
            }),
            'api_secret': forms.PasswordInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'API Secret (password field)'
            }),
            'webhook_secret': forms.PasswordInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'Webhook Secret (password field)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded'
            }),
            'is_test_mode': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['api_key'].required = False
        self.fields['api_secret'].required = False
        self.fields['webhook_secret'].required = False


# ==============================================================================
# TRANSACTION FORM (for admin manual entry/edit)
# ==============================================================================

class TransactionForm(forms.ModelForm):
    """Form for managing transactions"""
    
    class Meta:
        model = Transaction
        fields = [
            'user', 'transaction_type', 'gateway', 'amount',
            'currency', 'status', 'course', 'completed_at'
        ]
        widgets = {
            'user': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'transaction_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'gateway': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'currency': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'USD'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'course': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'list': 'course-list',
            }),
            'completed_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].empty_label = '— Select User —'
        self.fields['transaction_type'].empty_label = '— Select Type —'
        self.fields['gateway'].empty_label = '— Select Gateway —'
        self.fields['status'].empty_label = '— Select Status —'
        self.fields['course'].empty_label = '— Select Course (Optional) —'
        self.fields['completed_at'].required = False
        self.fields['course'].required = False
        self.fields['gateway'].required = False


# ==============================================================================
# ALL REQUIRED PAYMENTS FORM
# ==============================================================================

class AllRequiredPaymentsForm(forms.ModelForm):
    """Form for managing required payments"""
    
    class Meta:
        model = AllRequiredPayments
        fields = [
            'program', 'course', 'academic_session', 'semester',
            'purpose', 'who_to_pay', 'amount', 'currency', 'due_date', 'is_active'
        ]
        widgets = {
            'program': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'course': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'list': 'course-list',
            }),
            'academic_session': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'semester': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'purpose': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'placeholder': 'e.g., Tuition, Library Fees, Registration'
            }),
            'who_to_pay': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 bg-white'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'currency': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 uppercase',
                'placeholder': 'e.g. USD, GBP, EUR',
                'maxlength': '3',
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary-600 rounded'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program'].empty_label = '— Select Program —'
        self.fields['course'].empty_label = '— Select Course (Optional) —'
        self.fields['academic_session'].empty_label = '— Select Session (Optional) —'
        self.fields['course'].required = False
        self.fields['academic_session'].required = False

class LibraryItemForm(forms.ModelForm):
    """
    Create / edit form for LibraryItem.
 
    Exact editable fields from the model:
      category, subcategory, title,
      author, publisher, year, edition, isbn, language,
      description, tags,
      cover_image, file,
      external_url, external_url_label,
      allow_download, allow_read_online,
      access, featured, is_active, order
 
    Auto-filled / editable=False excluded:
      id, file_size_mb, file_type,
      view_count, download_count,
      created_by, created_at, updated_at
    """
 
    class Meta:
        from eduweb.models import LibraryItem as _LI
        model  = _LI
        fields = [
            'category', 'subcategory',
            'title',
            'author', 'publisher', 'year', 'edition', 'isbn', 'language',
            'description', 'tags',
            'cover_image', 'file',
            'external_url', 'external_url_label',
            'allow_download', 'allow_read_online',
            'access', 'featured', 'is_active', 'order',
        ]
        widgets = {
            # ── taxonomy ──────────────────────────────────────────────────
            'category': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. Books',
                'list': 'category_datalist',
            }),
            'subcategory': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. Systematic Theology, Church History, Commentaries …',
            }),
            # ── identity ──────────────────────────────────────────────────
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. Systematic Theology',
            }),
            
            # ── bibliographic ─────────────────────────────────────────────
            'author': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. Wayne Grudem',
            }),
            'publisher': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. Zondervan',
            }),
            'year': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. 2009',
                'min': 1000, 'max': 2100,
            }),
            'edition': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. 3rd Edition, Vol. 2',
            }),
            'isbn': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm font-mono transition-colors',
                'placeholder': 'e.g. 978-0-310-28441-6',
            }),
            'language': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. English',
                'list': 'language_datalist',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors resize-none',
                'rows': 4,
                'placeholder': 'Abstract, synopsis, or table of contents …',
            }),
            'tags': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'theology, salvation, grace  (comma-separated)',
            }),
            # ── external link ─────────────────────────────────────────────
            'external_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'https://drive.google.com/… or https://gutenberg.org/…',
            }),
            'external_url_label': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'Read / Download',
            }),
            # ── access & ordering ─────────────────────────────────────────
            'access': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'placeholder': 'e.g. public',
                'list': 'access_datalist',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-blue-500 focus:border-blue-500 '
                         'text-sm transition-colors',
                'min': 0,
            }),
            # ── file / image — styled via template drop-zones ─────────────
            'cover_image': forms.ClearableFileInput(attrs={
                'class': 'sr-only',
                'accept': 'image/*',
                'id': 'id_cover_image',
            }),
            'file': forms.ClearableFileInput(attrs={
                'class': 'sr-only',
                'accept': '.pdf,.doc,.docx,.epub,.txt,.pptx,.xlsx',
                'id': 'id_file',
            }),
            # ── booleans — styled as toggles by JS in the template ────────
            'allow_download':    forms.CheckboxInput(),
            'allow_read_online': forms.CheckboxInput(),
            'featured':          forms.CheckboxInput(),
            'is_active':         forms.CheckboxInput(),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
 
        optional_fields = [
            'author', 'publisher', 'year', 'edition', 'isbn',
            'description', 'tags', 'cover_image', 'file',
            'external_url', 'external_url_label', 'order',
        ]
        for f in optional_fields:
            if f in self.fields:
                self.fields[f].required = False
 
        self.fields['tags'].help_text = (
            'Comma-separated keywords. Improves front-end search results.'
        )
        self.fields['file'].help_text = (
            'Accepted formats: PDF, DOCX, EPUB, TXT, PPTX, XLSX.'
        )
        self.fields['cover_image'].help_text = (
            'Recommended: 400 × 560 px, JPG or PNG.'
        )
        self.fields['external_url'].help_text = (
            'Paste a public link if the document is hosted externally '
            '(Google Drive, archive.org, Project Gutenberg, etc.).'
        )
        self.fields['external_url_label'].help_text = (
            'Button label shown on the front-end, default: "Read / Download".'
        )


# ==================== ADMIN MESSAGING FORMS ====================
class AdminMessageComposeForm(forms.ModelForm):
    """
    Form for admins/staff to compose a message to any user.
    Unlike the student version, recipient is a visible dropdown
    covering all active users.
    """
    from eduweb.models import Message as _Msg

    recipient = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True)
            .select_related('profile')
            .order_by('profile__role', 'first_name', 'last_name'),
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 rounded-lg '
                'focus:ring-2 focus:ring-primary-blue-500 focus:border-transparent '
                'text-sm'
            )
        }),
        label='Recipient',
    )

    class Meta:
        from eduweb.models import Message
        model = Message
        fields = ['recipient', 'subject', 'body']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-blue-500 focus:border-transparent text-sm'
                ),
                'placeholder': 'Message subject…',
            }),
            'body': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-blue-500 focus:border-transparent text-sm'
                ),
                'rows': 7,
                'placeholder': 'Type your message here…',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show username + role in the dropdown label
        self.fields['recipient'].label_from_instance = lambda u: (
            f"{u.get_full_name() or u.username} "
            f"[{u.profile.get_role_display() if hasattr(u, 'profile') else 'User'}]"
        )

    def clean_subject(self):
        s = self.cleaned_data.get('subject', '').strip()
        if len(s) < 3:
            raise forms.ValidationError('Subject must be at least 3 characters.')
        return s

    def clean_body(self):
        b = self.cleaned_data.get('body', '').strip()
        if len(b) < 10:
            raise forms.ValidationError('Message must be at least 10 characters.')
        return b