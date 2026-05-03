from django import forms
from django.core.validators import FileExtensionValidator
from eduweb.models import (
    LMSCourse, Lesson, LessonSection, Quiz, QuizQuestion,
    QuizAnswer, Assignment, Announcement
)
from django.contrib.auth.models import User
from eduweb.models import UserProfile, Exam


class CourseForm(forms.ModelForm):
    """Form for creating and editing courses with Tailwind styling"""

    class Meta:
        model = LMSCourse
        fields = [
            'title', 'code', 'short_description',
            'description', 'difficulty_level',
            'thumbnail', 'promo_video_url',
            'academic_course',
            # 'has_certificate', 'certificate_template',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Enter course title'
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'e.g., CS101 (auto-generated if blank)'
            }),
            # 'category': forms.Select(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            # }),
            'short_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 3,
                'placeholder': 'Brief description (max 500 characters)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 6,
                'placeholder': 'Detailed course description'
            }),
            'difficulty_level': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
            # 'duration_hours': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'step': '0.5',
            #     'placeholder': 'e.g., 10'
            # }),
            # 'language': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'value': 'English'
            # }),
            'promo_video_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'https://youtube.com/watch?v=...'
            }),
            # 'max_students': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'placeholder': 'Leave blank for unlimited'
            # }),
            # 'enrollment_start_date': forms.DateInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'type': 'date'
            # }),
            # 'enrollment_end_date': forms.DateInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'type': 'date'
            # }),
            'academic_course': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'id': 'id_academic_course',
            }),
            'thumbnail': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100'
            }),
            # 'has_certificate': forms.CheckboxInput(attrs={
            #     'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            # }),
            # 'certificate_fee': forms.NumberInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'step': '0.01',
            #     'placeholder': '0.00 — leave as 0 for free certificate'
            # }),
            # 'certificate_template': forms.TextInput(attrs={
            #     'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            #     'placeholder': 'e.g., default, gold, premium'
            # }),
            # 'is_published': forms.CheckboxInput(attrs={
            #     'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            # }),
            # 'is_featured': forms.CheckboxInput(attrs={
            #     'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            # }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # code is optional — auto-generated in save() if left blank
        self.fields['code'].required = False
        # Give the academic_course dropdown a clear "standalone" empty option
        self.fields['academic_course'].empty_label = '— Choose Course —'
        # category is conditionally optional — JS hides it when academic_course is chosen;
        # the form-level required=False prevents server-side validation from blocking the save.
        # category field removed — LMSCourse uses academic_course instead
        # # certificate_fee has a model default of 0.00 — never block submission on it
        # self.fields['certificate_fee'].required = False

    def clean(self):
        cleaned = super().clean()
        academic_course = cleaned.get('academic_course')
        # category field removed — no validation needed

        # # certificate_fee: make it optional / zero-out when academic course is linked
        # # (academic programmes handle certification fees themselves)
        # if academic_course:
        #     from decimal import Decimal
        #     cleaned['certificate_fee'] = Decimal('0.00')
        #     self.fields['certificate_fee'].required = False

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Auto-generate a unique course code if the instructor left it blank
        if not instance.code:
            import uuid as _uuid
            base = _uuid.uuid4().hex[:8].upper()
            candidate = f'LMS-{base}'
            while LMSCourse.objects.filter(code=candidate).exclude(pk=instance.pk).exists():
                candidate = f'LMS-{_uuid.uuid4().hex[:8].upper()}'
            instance.code = candidate
        if commit:
            instance.save()
        return instance


class CourseObjectivesForm(forms.ModelForm):
    """Form for managing course learning objectives"""
    objectives = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            'rows': 6,
            'placeholder': 'Enter one objective per line'
        }),
        help_text='Enter each learning objective on a new line'
    )
    prerequisites = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
            'rows': 4,
            'placeholder': 'Enter one prerequisite per line'
        }),
        help_text='Enter each prerequisite on a new line'
    )
    
    class Meta:
        model = LMSCourse
        fields = []


# ==================== SECTION FORMS ====================
class SectionForm(forms.ModelForm):
    """Form for creating course sections"""
    
    class Meta:
        model = LessonSection
        fields = ['title', 'description', 'display_order']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Section Title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 3,
                'placeholder': 'Section description (optional)'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
        }


# ==================== LESSON FORMS ====================
class LessonForm(forms.ModelForm):
    """Form for creating and editing lessons"""
    
    class Meta:
        model = Lesson
        fields = [
            'section', 'title', 'lesson_type', 'description',
            'content', 'video_url', 'video_file', 'video_duration_minutes',
            'file', 'is_preview', 'display_order'
        ]
        widgets = {
            'section': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Lesson Title'
            }),
            'lesson_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 3,
                'placeholder': 'Lesson description'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 8,
                'placeholder': 'Lesson content (for text lessons)'
            }),
            'video_url': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'YouTube, Vimeo, or storage URL'
            }),
            'video_file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
                'accept': 'video/mp4,video/webm,video/ogg,video/x-msvideo,video/quicktime'
            }),
            'video_duration_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
            'file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100'
            }),
            'is_preview': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
        if course:
            self.fields['section'].queryset = LessonSection.objects.filter(
                course=course
            )
        # Section is required — a lesson must belong to a section to appear correctly
        self.fields['section'].required = True
        self.fields['section'].empty_label = '— Select a section —'


# ==================== QUIZ FORMS ====================
class QuizForm(forms.ModelForm):
    """Form for creating and editing quizzes"""

    class Meta:
        model = Quiz
        fields = [
            'title', 'description', 'instructions',
            'time_limit_minutes', 'passing_score', 'max_attempts',
            'shuffle_questions', 'show_correct_answers', 'display_order'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Quiz Title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 3,
                'placeholder': 'Quiz description'
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 4,
                'placeholder': 'Instructions for students'
            }),
            'time_limit_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Leave blank for no limit'
            }),
            'passing_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 70,
                'step': '0.01'
            }),
            'max_attempts': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 3
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
            'shuffle_questions': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'show_correct_answers': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_order'].required = False
        self.fields['display_order'].initial = 0

    def clean_display_order(self):
        val = self.cleaned_data.get('display_order')
        return val if val is not None else 0


class QuizQuestionForm(forms.ModelForm):
    """Form for creating quiz questions"""
    
    class Meta:
        model = QuizQuestion
        fields = [
            'question_type', 'question_text', 'explanation',
            'points', 'display_order'
        ]
        widgets = {
            'question_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
            'question_text': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 3,
                'placeholder': 'Enter your question'
            }),
            'explanation': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 2,
                'placeholder': 'Explanation (shown after answer)'
            }),
            'points': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 1,
                'step': '0.01'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
        }


class QuizAnswerForm(forms.ModelForm):
    """Form for creating quiz answer choices"""
    
    class Meta:
        model = QuizAnswer
        fields = ['answer_text', 'is_correct', 'display_order']
        widgets = {
            'answer_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Answer choice'
            }),
            'is_correct': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
        }


# ==================== ASSIGNMENT FORMS ====================
class AssignmentForm(forms.ModelForm):
    """Form for creating and editing assignments"""

    class Meta:
        model = Assignment
        fields = [
            'title', 'description', 'instructions',
            'max_score', 'passing_score', 'attachment',
            'due_date', 'allow_late_submission',
            'late_penalty_percent', 'display_order'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Assignment Title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 4,
                'placeholder': 'Assignment description'
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 6,
                'placeholder': 'Detailed instructions for students'
            }),
            'max_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 100,
                'step': '0.01'
            }),
            'passing_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 50,
                'step': '0.01'
            }),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'type': 'datetime-local'
            }),
            'late_penalty_percent': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'value': 0
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100'
            }),
            'allow_late_submission': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_order'].required = False
        self.fields['display_order'].initial = 0

    def clean_display_order(self):
        val = self.cleaned_data.get('display_order')
        return val if val is not None else 0


# ==================== ANNOUNCEMENT FORMS ====================
class AnnouncementForm(forms.ModelForm):
    """Form for creating course announcements"""
    
    class Meta:
        model = Announcement
        fields = [
            'title', 'content', 'priority',
            'publish_date', 'expiry_date'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Announcement Title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 6,
                'placeholder': 'Announcement content'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
            'publish_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'type': 'datetime-local'
            }),
            'expiry_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'type': 'datetime-local'
            }),
        }


# ==================== PROFILE FORM ====================
class InstructorProfileForm(forms.ModelForm):
    """Form for instructor profile management"""
    
    # User fields
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'First Name'
        })
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Last Name'
        })
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'email@example.com'
        })
    )
    
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'avatar', 'phone', 'city', 'country',
            'website', 'linkedin', 'twitter'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'rows': 4,
                'placeholder': 'Tell us about yourself, your teaching experience, and expertise...'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': '+234 XXX XXX XXXX'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Lagos'
            }),
            'country': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Nigeria'
            }),
            'website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://yourwebsite.com'
            }),
            'linkedin': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://linkedin.com/in/yourprofile'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'https://twitter.com/yourusername'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
                'accept': 'image/*'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        user = self.instance.user
        
        if User.objects.exclude(pk=user.pk).filter(email=email).exists():
            raise forms.ValidationError('Email already in use.')
        return email


# ==================== SETTINGS FORM ====================
class InstructorSettingsForm(forms.ModelForm):
    """Form for instructor account settings"""
    
    class Meta:
        model = UserProfile
        fields = [
            'email_notifications',
            'marketing_emails',
        ]
        widgets = {
            'email_notifications': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'marketing_emails': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }


class PasswordChangeForm(forms.Form):
    """Form for changing password"""
    
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': '••••••••'
        }),
        label='Current Password'
    )
    
    new_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': '••••••••'
        }),
        label='New Password',
        help_text='Must be at least 8 characters long'
    )
    
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': '••••••••'
        }),
        label='Confirm New Password'
    )
    
    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
    
    def clean_current_password(self):
        password = self.cleaned_data.get('current_password')
        if not self.user.check_password(password):
            raise forms.ValidationError('Current password is incorrect.')
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError({
                    'confirm_password': 'Passwords do not match.'
                })
        return cleaned_data


# ==================== HELP & SUPPORT FORM ====================
class SupportTicketForm(forms.Form):
    """Form for submitting support tickets"""
    
    CATEGORY_CHOICES = [
        ('technical', 'Technical Issue'),
        ('course', 'Course Management'),
        ('billing', 'Billing & Payments'),
        ('account', 'Account Settings'),
        ('student', 'Student Management'),
        ('content', 'Content Upload'),
        ('other', 'Other'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low - General Question'),
        ('medium', 'Medium - Need Help'),
        ('high', 'High - Urgent Issue'),
    ]
    
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
        }),
        label='Issue Category'
    )
    
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
        }),
        label='Priority Level'
    )
    
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'placeholder': 'Brief description of your issue'
        }),
        label='Subject'
    )
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            'rows': 6,
            'placeholder': 'Please provide detailed information about your issue...'
        }),
        label='Message'
    )
    
    attachment = forms.FileField(
        required=False,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'])
        ],
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
        }),
        label='Attachment (Optional)',
        help_text='Upload screenshot or document (Max 5MB)'
    )

from django import forms
from django.contrib.auth.models import User
from eduweb.models import Message, DiscussionReply


# ==================== MESSAGE FORM ====================
class MessageForm(forms.ModelForm):
    """Form for composing a new message to a student or colleague."""

    class Meta:
        model  = Message
        fields = ['recipient', 'subject', 'body']
        widgets = {
            'recipient': forms.Select(attrs={
                'class': (
                    'w-full px-4 py-2 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 '
                    'transition-colors'
                ),
            }),
            'subject': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-2 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 '
                    'transition-colors'
                ),
                'placeholder': 'Message subject',
            }),
            'body': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-2 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 '
                    'transition-colors resize-none'
                ),
                'rows': 8,
                'placeholder': 'Write your message...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow messaging students enrolled in at least one of the
        # instructor's courses, or any active user. Adjust the queryset
        # as needed for your use case.
        self.fields['recipient'].queryset = User.objects.filter(
            is_active=True
        ).exclude(
            id=self.instance.sender_id if self.instance.pk else None
        ).order_by('first_name', 'last_name')
        self.fields['recipient'].label_from_instance = (
            lambda u: f"{u.get_full_name()} ({u.email})" if u.get_full_name() else u.email
        )


# ==================== DISCUSSION REPLY FORM ====================
class DiscussionReplyForm(forms.ModelForm):
    """Form for posting a reply to a discussion thread."""

    class Meta:
        model  = DiscussionReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 rounded-lg '
                    'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 '
                    'transition-colors text-sm resize-none'
                ),
                'rows': 4,
                'placeholder': (
                    'Share your thoughts, clarify a concept, '
                    'or guide the discussion…'
                ),
            }),
        }

class ExamForm(forms.ModelForm):
    """
    Exam creation / edit form for the instructor dashboard.
 
    Changes from original:
      - 'mode'                       REMOVED — always online/CBT
      - 'exam_date','start_time','end_time'
                                     REMOVED — replaced by start_datetime / end_datetime
      - 'instruction_window_minutes' REMOVED — fixed class constant (10 min)
      - 'venue'                      REMOVED — online exam, no physical location
      - 'difficulty_mix'             REMOVED — not used
      - 'visible_from_override',
        'visible_until_override'     REMOVED — visibility is fully computed
      - start_datetime / end_datetime ADDED   — combined date+time pickers
    """
 
    # ── manually declared so POST value is accepted and validated ────────────
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2 border border-gray-300 rounded-lg '
                'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            ),
            'placeholder': 'e.g. CSC301 End-of-Semester Exam 2025',
            'id': 'id_exam_title',
        }),
        help_text='Auto-filled from the course name — edit if needed.',
    )
 
    class Meta:
        model  = Exam
        fields = [
            # classification
            'exam_type',
            # REMOVED: 'mode' — always online/CBT
 
            # schedule — combined datetime fields replace the old date+time split
            'start_datetime',
            'end_datetime',
            # REMOVED: 'exam_date', 'start_time', 'end_time'
            # REMOVED: 'instruction_window_minutes' — fixed at 10, class constant
 
            # REMOVED: 'venue' — online exam
 
            # pool config
            'questions_per_student',
            # REMOVED: 'difficulty_mix'
            'total_marks', 'pass_mark',
            'shuffle_questions', 'shuffle_options',
            'show_result_immediately',
 
            # file import
            'question_import_file',
 
            # student-facing instructions only
            'instructions',
 
            # REMOVED: 'visible_from_override', 'visible_until_override'
            #          — visibility is purely computed from start/end + class constants
        ]
        widgets = {
            'exam_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors'
            }),
 
            # REMOVED: 'mode' widget
 
            # Combined datetime pickers — replaces the old separate date + time inputs
            'start_datetime': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                             'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                    'type': 'datetime-local',
                }
            ),
            'end_datetime': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                             'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                    'type': 'datetime-local',
                }
            ),
 
            # REMOVED: 'exam_date', 'start_time', 'end_time' widgets
            # REMOVED: 'instruction_window_minutes' widget
            # REMOVED: 'venue' widget
 
            'questions_per_student': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'placeholder': 'Leave blank for all questions'
            }),
            'total_marks': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'step': '0.01'
            }),
            'pass_mark': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'step': '0.01'
            }),
            'shuffle_questions': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'shuffle_options': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'show_result_immediately': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
            'question_import_file': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 '
                         'file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 '
                         'hover:file:bg-primary-100',
                'accept': '.docx,.xlsx'
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors',
                'rows': 4,
                'placeholder': 'Shown to students on the instruction page'
            }),
 
            # REMOVED: 'visible_from' / 'visible_until' widgets
            #          — these are now read-only @properties, not form fields
        }
 
    # REMOVED: clean_instruction_window_minutes — field no longer exists on model
 
    def clean(self):
        cleaned = super().clean()
        start   = cleaned.get('start_datetime')
        end     = cleaned.get('end_datetime')
        if start and end and end <= start:
            self.add_error('end_datetime', 'End date/time must be after start date/time.')
        return cleaned
 
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.title = self.cleaned_data.get('title', '')
        if commit:
            instance.save()
        return instance