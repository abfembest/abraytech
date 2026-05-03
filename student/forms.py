from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from eduweb.models import (
    AssignmentSubmission,
    UserProfile,
    Message,
    Discussion,
    DiscussionReply,
    StudyGroup,
    LMSCourse,
    Enrollment
)
from django.core.validators import FileExtensionValidator



# ==================== ASSIGNMENT FORMS ====================
class AssignmentSubmissionForm(forms.ModelForm):
    """Form for submitting assignments with validation"""
    
    class Meta:
        model = AssignmentSubmission
        fields = ['submission_text', 'attachment']
        widgets = {
            'submission_text': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 8,
                'placeholder': 'Enter your submission text here...',
                'required': True,
            }),
            'attachment': forms.FileInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'accept': '.pdf,.doc,.docx,.txt,.zip'
            }),
        }
    
    def clean_submission_text(self):
        """Validate submission text"""
        text = self.cleaned_data.get('submission_text', '')
        
        if not text or text.strip() == '':
            raise ValidationError(
                'Submission text is required and cannot be empty.'
            )
        
        if len(text.strip()) < 10:
            raise ValidationError(
                'Submission text must be at least 10 characters long.'
            )
        
        return text.strip()
    
    def clean_attachment(self):
        """Validate file attachment"""
        attachment = self.cleaned_data.get('attachment')
        
        if attachment:
            # Check file size (10MB max)
            max_size = 10 * 1024 * 1024
            if attachment.size > max_size:
                raise ValidationError(
                    'File size cannot exceed 10MB.'
                )
            
            # Check file extension
            allowed_extensions = [
                'pdf', 'doc', 'docx', 'txt', 'zip'
            ]
            ext = attachment.name.split('.')[-1].lower()
            
            if ext not in allowed_extensions:
                raise ValidationError(
                    f'File type not allowed. '
                    f'Accepted: {", ".join(allowed_extensions)}'
                )
        
        return attachment


# ==================== PROFILE FORMS ====================
class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile"""
    
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            ),
            'placeholder': 'First Name'
        })
    )
    
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            ),
            'placeholder': 'Last Name'
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            ),
            'placeholder': 'Email Address'
        })
    )
    
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'phone', 'city', 'country',
            'avatar', 'website', 'linkedin', 'twitter'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 4,
                'placeholder': 'Tell us about yourself...'
            }),
            'phone': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'Phone Number'
            }),
            'city': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'City'
            }),
            'country': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'Country'
            }),
            'avatar': forms.FileInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'accept': 'image/*'
            }),
            'website': forms.URLInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'https://yourwebsite.com'
            }),
            'linkedin': forms.URLInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'https://linkedin.com/in/yourprofile'
            }),
            'twitter': forms.URLInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'https://twitter.com/yourusername'
            }),
        }
    
    def clean_avatar(self):
        """Validate avatar upload"""
        avatar = self.cleaned_data.get('avatar')
        
        if avatar:
            # Check file size (2MB max)
            max_size = 2 * 1024 * 1024
            if avatar.size > max_size:
                raise ValidationError(
                    'Avatar file size cannot exceed 2MB.'
                )
            
            # Check file type
            allowed_types = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp'
            ]
            if hasattr(avatar, 'content_type'):
                if avatar.content_type not in allowed_types:
                    raise ValidationError(
                        'Only JPG, PNG, GIF, and WebP images are allowed.'
                    )
        
        return avatar


# ==================== MESSAGE FORMS ====================
class MessageComposeForm(forms.ModelForm):
    """Form for composing messages"""
    
    recipient = forms.ModelChoiceField(
        queryset=User.objects.filter(
            profile__role__in=['instructor', 'admin']
        ).select_related('profile').order_by('profile__role', 'first_name'),
        widget=forms.HiddenInput(),
    )
    
    class Meta:
        model = Message
        fields = ['recipient', 'subject', 'body']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'Message Subject'
            }),
            'body': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 6,
                'placeholder': 'Type your message here...'
            }),
        }
    
    def clean_subject(self):
        """Validate subject"""
        subject = self.cleaned_data.get('subject', '')
        
        if not subject or subject.strip() == '':
            raise ValidationError('Subject is required.')
        
        if len(subject.strip()) < 3:
            raise ValidationError(
                'Subject must be at least 3 characters long.'
            )
        
        return subject.strip()
    
    def clean_body(self):
        """Validate message body"""
        body = self.cleaned_data.get('body', '')
        
        if not body or body.strip() == '':
            raise ValidationError('Message body is required.')
        
        if len(body.strip()) < 10:
            raise ValidationError(
                'Message must be at least 10 characters long.'
            )
        
        return body.strip()


# ==================== SETTINGS FORMS ====================
class SettingsForm(forms.ModelForm):
    """Form for account settings"""
    
    class Meta:
        model = UserProfile
        fields = ['email_notifications', 'marketing_emails']
        widgets = {
            'email_notifications': forms.CheckboxInput(attrs={
                'class': (
                    'w-4 h-4 text-primary-600 '
                    'focus:ring-2 focus:ring-primary-500'
                )
            }),
            'marketing_emails': forms.CheckboxInput(attrs={
                'class': (
                    'w-4 h-4 text-primary-600 '
                    'focus:ring-2 focus:ring-primary-500'
                )
            }),
        }


# ==================== DISCUSSION FORMS ====================
class ThreadCreateForm(forms.ModelForm):
    """Form for creating discussion threads"""
    
    course = forms.ModelChoiceField(
        queryset=LMSCourse.objects.none(),
        required=False,
        empty_label="General Discussion (No specific course)",
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            )
        }),
        help_text='Select a course if this discussion is course-specific'
    )
    
    class Meta:
        model = Discussion
        fields = ['title', 'content', 'course']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'Enter a clear, descriptive title',
                'maxlength': 200
            }),
            'content': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 8,
                'placeholder': (
                    'Provide detailed information about your discussion topic. '
                    'Include context, questions, or points you want to discuss.'
                )
            }),
        }
        labels = {
            'title': 'Discussion Title',
            'content': 'Description',
            'course': 'Related Course (Optional)'
        }
    
    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set queryset to user's enrolled courses if user provided
        if user:
            enrolled_course_ids = Enrollment.objects.filter(
                student=user,
                status='active'
            ).values_list('course_id', flat=True)
            
            self.fields['course'].queryset = LMSCourse.objects.filter(
                id__in=enrolled_course_ids,
                is_published=True
            )
    
    def clean_title(self):
        """Validate title"""
        title = self.cleaned_data.get('title', '')
        
        if not title or title.strip() == '':
            raise ValidationError('Title is required.')
        
        if len(title.strip()) < 5:
            raise ValidationError(
                'Title must be at least 5 characters long.'
            )
        
        return title.strip()
    
    def clean_content(self):
        """Validate content"""
        content = self.cleaned_data.get('content', '')
        
        if not content or content.strip() == '':
            raise ValidationError('Description is required.')
        
        if len(content.strip()) < 20:
            raise ValidationError(
                'Description must be at least 20 characters long.'
            )
        
        return content.strip()


class ReplyCreateForm(forms.ModelForm):
    """Form for creating discussion replies"""
    
    class Meta:
        model = DiscussionReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 5,
                'placeholder': 'Write your reply here...'
            }),
        }
        labels = {
            'content': 'Your Reply'
        }
    
    def clean_content(self):
        """Validate reply content"""
        content = self.cleaned_data.get('content', '')
        
        if not content or content.strip() == '':
            raise ValidationError('Reply content is required.')
        
        if len(content.strip()) < 10:
            raise ValidationError(
                'Reply must be at least 10 characters long.'
            )
        
        return content.strip()


# ==================== STUDY GROUP FORMS ====================
class StudyGroupMessageForm(forms.Form):
    """Form for posting messages in study groups"""
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            ),
            'rows': 4,
            'placeholder': 'Share something with your study group...'
        }),
        label='Message',
        min_length=5,
        max_length=1000,
        help_text='Share updates, questions, or resources with group members'
    )
    
    def clean_message(self):
        """Validate message"""
        message = self.cleaned_data.get('message', '')
        
        if not message or message.strip() == '':
            raise ValidationError('Message cannot be empty.')
        
        if len(message.strip()) < 5:
            raise ValidationError(
                'Message must be at least 5 characters long.'
            )
        
        return message.strip()


class StudyGroupCreateForm(forms.ModelForm):
    """Form for creating study groups"""
    
    course = forms.ModelChoiceField(
        queryset=LMSCourse.objects.none(),
        required=False,
        empty_label="General Study Group (No specific course)",
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-3 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-transparent'
            )
        }),
        help_text='Select a course if this group is course-specific'
    )
    
    class Meta:
        model = StudyGroup
        fields = [
            'name', 'description', 'course',
            'max_members', 'is_public'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'placeholder': 'Enter group name',
                'maxlength': 200
            }),
            'description': forms.Textarea(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'rows': 4,
                'placeholder': (
                    'Describe the purpose of this study group, '
                    'topics to be covered, and what members can expect'
                )
            }),
            'max_members': forms.NumberInput(attrs={
                'class': (
                    'w-full px-4 py-3 border border-gray-300 '
                    'rounded-lg focus:ring-2 focus:ring-primary-500 '
                    'focus:border-transparent'
                ),
                'min': 2,
                'max': 50,
                'value': 10
            }),
            'is_public': forms.CheckboxInput(attrs={
                'class': (
                    'w-4 h-4 text-primary-600 '
                    'focus:ring-2 focus:ring-primary-500'
                )
            }),
        }
        labels = {
            'name': 'Group Name',
            'description': 'Description',
            'course': 'Related Course (Optional)',
            'max_members': 'Maximum Members',
            'is_public': 'Make this group publicly visible'
        }
        help_texts = {
            'max_members': 'Maximum number of members allowed (2-50)',
            'is_public': (
                'Public groups are visible to all students. '
                'Private groups are invitation-only.'
            )
        }
    
    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set queryset to user's enrolled courses if user provided
        if user:
            enrolled_course_ids = Enrollment.objects.filter(
                student=user,
                status='active'
            ).values_list('course_id', flat=True)
            
            self.fields['course'].queryset = LMSCourse.objects.filter(
                id__in=enrolled_course_ids,
                is_published=True
            )
    
    def clean_name(self):
        """Validate group name"""
        name = self.cleaned_data.get('name', '')
        
        if not name or name.strip() == '':
            raise ValidationError('Group name is required.')
        
        if len(name.strip()) < 3:
            raise ValidationError(
                'Group name must be at least 3 characters long.'
            )
        
        return name.strip()
    
    def clean_max_members(self):
        """Validate max members"""
        max_members = self.cleaned_data.get('max_members')
        
        if max_members < 2:
            raise ValidationError(
                'Group must allow at least 2 members.'
            )
        
        if max_members > 50:
            raise ValidationError(
                'Group cannot have more than 50 members.'
            )
        
        return max_members
    
class StudentSupportTicketForm(forms.Form):
    """Form for students to submit support tickets"""
    
    CATEGORY_CHOICES = [
        ('technical', 'Technical Issue'),
        ('course', 'Course Content'),
        ('enrollment', 'Enrollment Issue'),
        ('payment', 'Payment & Billing'),
        ('account', 'Account Settings'),
        ('assignment', 'Assignment Help'),
        ('quiz', 'Quiz/Assessment'),
        ('certificate', 'Certificate Issue'),
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
            'class': (
                'w-full px-4 py-2 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            )
        }),
        label='Issue Category'
    )
    
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        widget=forms.Select(attrs={
            'class': (
                'w-full px-4 py-2 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            )
        }),
        label='Priority Level'
    )
    
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': (
                'w-full px-4 py-2 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'placeholder': 'Brief description of your issue'
        }),
        label='Subject'
    )
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': (
                'w-full px-4 py-2 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500'
            ),
            'rows': 6,
            'placeholder': 'Please provide detailed information...'
        }),
        label='Message'
    )
    
    attachment = forms.FileField(
        required=False,
        validators=[
            FileExtensionValidator(
                ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']
            )
        ],
        widget=forms.FileInput(attrs={
            'class': (
                'w-full px-4 py-2 border border-gray-300 '
                'rounded-lg focus:ring-2 focus:ring-primary-500 '
                'focus:border-primary-500 file:mr-4 file:py-2 '
                'file:px-4 file:rounded-lg file:border-0 '
                'file:text-sm file:font-semibold '
                'file:bg-primary-50 file:text-primary-700 '
                'hover:file:bg-primary-100'
            ),
        }),
        label='Attachment (Optional)',
        help_text='Upload screenshot or document (Max 5MB)'
    )
