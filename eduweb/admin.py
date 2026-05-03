from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    Announcement, Assignment, AssignmentSubmission, AuditLog,
    Badge, StudentBadge, BlogCategory, BlogPost,
    Certificate, ContactMessage,
    Course, CourseIntake, CourseApplication, ApplicationDocument, ApplicationPayment,
    CourseCategory, Discussion, DiscussionReply,
    Department, Program, AllRequiredPayments,
    AcademicSession,
    Enrollment, Faculty, InstitutionMember, Invoice, Lesson, LessonSection, LessonProgress,
    LMSCourse, Message, Notification,
    PaymentGateway, Transaction, Quiz, QuizQuestion, QuizAnswer, QuizAttempt, QuizResponse,
    Review, SiteConfig, SiteHistoryMilestone, SubscriptionPlan, Subscription, SupportTicket, TicketReply,
    StaffPayroll, StudyGroup, StudyGroupMember, StudyGroupMessage,
    SystemConfiguration, UserProfile, Vendor, BroadcastMessage, ListOfCountry, Testimonial, FeePayment, Exam, ExamQuestion, ExamStatusLog, StudentExamResponse
)


# ==================== SITE CONFIGURATION ====================

class EmbedCodeWidget(forms.Textarea):
    """Safe widget for raw HTML/iframe fields."""
    def __init__(self, safe_help_text='', *args, **kwargs):
        kwargs.setdefault('attrs', {})
        kwargs['attrs'].update({
            'rows': 6,
            'style': 'font-family: monospace; font-size: 12px; width: 100%;',
        })
        self.safe_help_text = safe_help_text
        super().__init__(*args, **kwargs)

    def format_value(self, value):
        return value or ''


class SiteConfigForm(forms.ModelForm):
    promo_video_url = forms.CharField(
        required=False,
        label='Promo video embed code',
        help_text='Paste the full iframe embed code from YouTube or Vimeo.',
        widget=EmbedCodeWidget(),
    )
    campus_map_embed_url = forms.CharField(
        required=False,
        label='Campus map embed code',
        help_text='Paste the full iframe embed code from Google Maps.',
        widget=EmbedCodeWidget(),
    )
    virtual_tour_url = forms.CharField(
        required=False,
        label='Virtual tour embed code',
        help_text='Paste the full iframe embed code for the virtual campus tour.',
        widget=EmbedCodeWidget(),
    )

    class Meta:
        model  = SiteConfig
        fields = '__all__'

class SiteHistoryMilestoneInline(admin.TabularInline):
    model = SiteHistoryMilestone
    extra = 1
    fields = ('year', 'title', 'description', 'display_order', 'is_active')
    ordering = ('display_order', 'year')

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    form = SiteConfigForm
    inlines = [SiteHistoryMilestoneInline]
    list_display = ('school_name', 'school_short_name', 'email', 'phone_primary')

    fieldsets = (
        ('🏫 Identity', {
            'fields': (
                'school_name', 'school_short_name', 'tagline',
                'logo', 'logo_dark', 'favicon', 'og_image',
                'theme_color',
            )
        }),
        ('📞 Contact — Footer Bar', {
            'description': 'These appear in the footer and base nav bar.',
            'fields': (
                'email', 'phone_primary', 'phone_secondary',
                'phone_ng_primary', 'phone_ng_secondary', 'whatsapp',
            )
        }),
        ('📧 Contact Page — Emails', {
            'description': 'Labelled department emails shown on the Contact page.',
            'fields': (
                'email_admissions', 'email_info', 'email_international',
            )
        }),
        ('📱 Contact Page — Phone Lines', {
            'description': 'Labelled phone lines shown on the Contact page.',
            'fields': (
                'phone_admissions', 'phone_general', 'phone_international',
            )
        }),
        ('🕐 Office Hours', {
            'description': 'Shown on the Contact page office hours card.',
            'fields': (
                'office_hours_weekday', 'office_hours_saturday', 'office_hours_sunday',
            )
        }),
        ('📍 Addresses', {
            'fields': ('address_usa', 'address_nigeria'),
        }),
        ('📱 Social Media', {
            'fields': ('facebook', 'instagram', 'youtube', 'twitter', 'tiktok', 'linkedin'),
        }),
        ('🎬 Embed Codes', {
            'description': (
                'Paste raw iframe embed codes here. '
                'They are stored as plain text and will NOT render inside this form.'
            ),
            'fields': (
                'promo_video_url',
                'campus_map_embed_url', 'campus_map_address',
                'virtual_tour_url',
            ),
        }),
        ('🖼 Hero Slides', {
            'description': (
                'Upload up to 3 hero background slides. '
                'Each slide can be an image OR a video — if both are set, video takes priority. '
                'Leave all blank to use the default static images.'
            ),
            'fields': (
                'hero_slide_1_image', 'hero_slide_1_video',
                'hero_slide_1_alt', 'hero_slide_1_duration',
                'hero_slide_2_image', 'hero_slide_2_video',
                'hero_slide_2_alt', 'hero_slide_2_duration',
                'hero_slide_3_image', 'hero_slide_3_video',
                'hero_slide_3_alt', 'hero_slide_3_duration',
            ),
            'classes': ('collapse',),
        }),
        ('About Page', {
            'fields': ('about_mission', 'about_vision', 'about_values'),
        }),
        ('🦶 Footer & Copyright', {
            'fields': ('footer_tagline', 'copyright_year'),
        }),
        ('🔍 SEO', {
            'fields': ('meta_description', 'meta_keywords'),
        }),
    )

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        app = SiteConfig._meta.app_label
        obj = SiteConfig.objects.first()
        if obj:
            return HttpResponseRedirect(
                reverse(f'admin:{app}_siteconfig_change', args=[obj.pk])
            )
        return HttpResponseRedirect(
            reverse(f'admin:{app}_siteconfig_add')
        )

# ==================== TESTIMONIALS ====================
@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display  = ('author_name', 'author_role', 'is_active', 'order')
    list_filter   = ('is_active',)
    search_fields = ('author_name', 'author_role', 'quote')
    list_editable = ('is_active', 'order')

    fieldsets = (
        ('Testimonial', {
            'fields': ('quote', 'author_name', 'author_role', 'avatar')
        }),
        ('Display', {
            'fields': ('is_active', 'order')
        }),
    )



@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_reference",
        "user",
        "fee",
        "amount",
        "currency",
        "status",
        "created_at",
        "paid_at",
    )

    list_filter = (
        "status",
        "currency",
        "created_at",
        "paid_at",
    )

    search_fields = (
        "payment_reference",
        "user__username",
        "user__email",
        "fee__purpose",
        "gateway_payment_id",
    )

    readonly_fields = (
        "payment_reference",
        "gateway_payment_id",
        "created_at",
        "updated_at",
        "paid_at",
    )

    ordering = ("-created_at",)

    list_select_related = ("user", "fee")

    date_hierarchy = "created_at"

    fieldsets = (
        ("Payment Info", {
            "fields": (
                "payment_reference",
                "status",
                "amount",
                "currency",
                "payment_method",
            )
        }),
        ("User & Fee", {
            "fields": (
                "user",
                "fee",
            )
        }),
        ("Gateway Details", {
            "fields": (
                "gateway_payment_id",
                "card_last4",
                "card_brand",
                "payment_metadata",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "paid_at",
                "updated_at",
            )
        }),
        ("Failure Info", {
            "fields": ("failure_reason",),
            "classes": ("collapse",),
        }),
    )

# ==================== ANNOUNCEMENTS ====================
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'announcement_type', 'priority', 'is_active', 'publish_date', 'created_by')
    list_filter = ('announcement_type', 'priority', 'is_active', 'publish_date')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'publish_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'content', 'announcement_type', 'priority')
        }),
        ('Targeting', {
            'fields': ('course', 'category')
        }),
        ('Publishing', {
            'fields': ('is_active', 'publish_date', 'expiry_date', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== ASSIGNMENTS ====================
@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'due_date', 'max_score', 'passing_score', 'is_active', 'display_order')
    list_filter = ('lesson__course', 'is_active', 'due_date')
    search_fields = ('title', 'description', 'lesson__title')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active', 'display_order')
    date_hierarchy = 'due_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('lesson', 'title', 'slug', 'description', 'instructions')
        }),
        ('Grading', {
            'fields': ('max_score', 'passing_score')
        }),
        ('Deadlines', {
            'fields': ('due_date', 'allow_late_submission', 'late_penalty_percent')
        }),
        ('Attachment', {
            'fields': ('attachment',)
        }),
        ('Settings', {
            'fields': ('is_active', 'display_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'assignment', 'status', 'score', 'is_late', 'submitted_at', 'graded_by')
    list_filter = ('status', 'is_late', 'submitted_at')
    search_fields = ('student__username', 'assignment__title')
    readonly_fields = ('submitted_at', 'graded_at', 'created_at', 'updated_at')

    fieldsets = (
        ('Submission', {
            'fields': ('assignment', 'student', 'submission_text', 'attachment')
        }),
        ('Grading', {
            'fields': ('score', 'feedback', 'graded_by', 'graded_at')
        }),
        ('Status', {
            'fields': ('status', 'is_late')
        }),
        ('Timestamps', {
            'fields': ('submitted_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== AUDIT LOGS ====================
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'object_id', 'ip_address', 'timestamp')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__username', 'model_name', 'description')
    readonly_fields = (
        'user', 'action', 'model_name', 'object_id',
        'description', 'ip_address', 'user_agent', 'extra_data', 'timestamp'
    )
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Event', {
            'fields': ('user', 'action', 'model_name', 'object_id', 'description')
        }),
        ('Request Info', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Extra Data', {
            'fields': ('extra_data',),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('timestamp',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ==================== BADGES ====================
@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'color', 'points', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'icon', 'color')
        }),
        ('Criteria', {
            'fields': ('criteria', 'points')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudentBadge)
class StudentBadgeAdmin(admin.ModelAdmin):
    list_display = ('student', 'badge', 'awarded_by', 'awarded_at')
    list_filter = ('badge', 'awarded_at')
    search_fields = ('student__username', 'badge__name')
    readonly_fields = ('awarded_at',)

    fieldsets = (
        ('Badge Award', {
            'fields': ('student', 'badge', 'awarded_by', 'reason')
        }),
        ('Timestamp', {
            'fields': ('awarded_at',)
        }),
    )


# ==================== BLOG ====================
@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'get_post_count', 'icon', 'color', 'display_order', 'is_active')
    list_filter = ('is_active', 'color')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('display_order', 'is_active')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description')
        }),
        ('Display Settings', {
            'fields': ('icon', 'color', 'display_order', 'is_active')
        }),
    )

    def get_post_count(self, obj):
        return obj.get_post_count()
    get_post_count.short_description = 'Published Posts'


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'author_name', 'category', 'status',
        'is_featured', 'views_count', 'publish_date', 'created_at'
    )
    list_filter = (
        'status', 'is_featured', 'category',
        'publish_date', 'created_at'
    )
    search_fields = ('title', 'subtitle', 'content', 'author_name')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('status', 'is_featured')
    readonly_fields = ('created_at', 'updated_at', 'views_count')
    date_hierarchy = 'publish_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'subtitle', 'category')
        }),
        ('Content', {
            'fields': ('excerpt', 'content')
        }),
        ('Author Information', {
            'fields': ('author', 'author_name', 'author_title', 'author_photo', 'author_bio')
        }),
        ('Media', {
            'fields': ('featured_image', 'featured_image_alt'),
            'classes': ('collapse',)
        }),
        ('Categorization', {
            'fields': ('tags',),
            'classes': ('collapse',)
        }),
        ('Publishing', {
            'fields': ('status', 'is_featured', 'publish_date')
        }),
        ('Metadata', {
            'fields': ('read_time', 'views_count'),
            'classes': ('collapse',)
        }),
        ('SEO', {
            'fields': ('meta_description', 'meta_keywords'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['publish_posts', 'unpublish_posts', 'feature_posts']

    def publish_posts(self, request, queryset):
        updated = queryset.update(status='published', publish_date=timezone.now())
        self.message_user(request, f'{updated} post(s) published.')
    publish_posts.short_description = "Publish selected posts"

    def unpublish_posts(self, request, queryset):
        updated = queryset.update(status='draft')
        self.message_user(request, f'{updated} post(s) unpublished.')
    unpublish_posts.short_description = "Unpublish selected posts"

    def feature_posts(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} post(s) featured.')
    feature_posts.short_description = "Feature selected posts"


# ==================== CERTIFICATES ====================
@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_id', 'student', 'course', 'program', 'certificate_type', 'payment_status', 'issued_date', 'completion_date', 'grade', 'is_verified')
    list_filter = ('certificate_type', 'payment_status', 'is_verified', 'issued_date')
    search_fields = ('certificate_id', 'student__username', 'course__title', 'program__name')
    search_fields = ('certificate_id', 'student__username', 'course__title')
    readonly_fields = ('certificate_id', 'verification_code', 'issued_date', 'created_at')

    fieldsets = (
        ('Certificate Information', {
            'fields': ('student', 'course', 'program', 'certificate_type', 'certificate_id', 'verification_code')
        }),
        ('Details', {
            'fields': ('issued_date', 'completion_date', 'grade', 'is_verified')
        }),
        ('Payment Gate', {
            'fields': ('payment_status', 'payment_reference'),
        }),
        ('File', {
            'fields': ('certificate_file',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

from .models import CourseGrade

@admin.register(CourseGrade)
class CourseGradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'session', 'grade', 'score', 'credit_units', 'is_passed', 'recorded_at')
    list_filter = ('session', 'grade', 'is_passed', 'course__program__department__faculty')
    search_fields = ('student__username', 'course__code', 'course__name')
    readonly_fields = ('recorded_at', 'updated_at')

    fieldsets = (
        ('Grade Record', {
            'fields': ('student', 'course', 'lms_course', 'session', 'term', 'application')
        }),
        ('Grading', {
            'fields': ('score', 'grade', 'credit_units', 'is_passed', 'result_status')
        }),
        ('Recorded By', {
            'fields': ('recorded_by', 'recorded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


from .models import InstitutionPartner

@admin.register(InstitutionPartner)
class InstitutionPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'location', 'display_order', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'location')
    list_editable = ('display_order', 'is_active')

    fieldsets = (
        ('Partner Information', {
            'fields': ('name', 'category', 'location', 'logo')
        }),
        ('Display', {
            'fields': ('display_order', 'is_active')
        }),
    )


# ==================== CONTACT ====================
@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at', 'is_read', 'responded', 'responded_by')
    list_filter = ('subject', 'is_read', 'responded', 'created_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('created_at', 'responded_at')
    list_editable = ('is_read', 'responded')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Contact Information', {
            'fields': ('user', 'name', 'email', 'subject')
        }),
        ('Message', {
            'fields': ('message',)
        }),
        ('Status', {
            'fields': ('is_read', 'responded', 'responded_by', 'responded_at', 'created_at')
        }),
    )


# ==================== ACADEMIC STRUCTURE ====================
@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'student_count', 'is_active', 'display_order', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'code', 'is_active', 'display_order')
        }),
        ('Display Settings', {
            'fields': ('icon', 'color_primary', 'color_secondary', 'tagline')
        }),
        ('Content', {
            'fields': ('description', 'mission', 'vision')
        }),
        ('Dean Information', {
            'fields': ('dean_name', 'dean_role', 'dean_faculty_label', 'dean_photo'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('hero_image', 'about_image'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('student_count', 'placement_rate', 'partner_count', 'international_faculty')
        }),
        ('Additional Information', {
            'fields': ('accreditation', 'special_features'),
            'classes': ('collapse',)
        }),
        ('SEO', {
            'fields': ('meta_description', 'meta_keywords'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InstitutionMember)
class InstitutionMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'member_type', 'display_order', 'is_active')
    list_filter = ('member_type', 'is_active')
    search_fields = ('name', 'role', 'bio')
    list_editable = ('display_order', 'is_active')

    fieldsets = (
        ('Member Information', {
            'fields': ('member_type', 'name', 'role', 'photo', 'bio')
        }),
        ('Display', {
            'fields': ('display_order', 'is_active')
        }),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'faculty', 'is_active', 'display_order', 'created_at')
    list_filter = ('faculty', 'is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'code', 'faculty', 'is_active', 'display_order')
        }),
        ('Content', {
            'fields': ('description',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'code', 'department', 'degree_level', 'duration_years',
        'application_fee', 'tuition_fee', 'is_active', 'is_featured', 'display_order'
    )
    list_filter = ('department__faculty', 'department', 'degree_level', 'is_active', 'is_featured')
    search_fields = ('name', 'code', 'description', 'tagline')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'is_featured', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'code', 'department', 'degree_level', 'is_active', 'is_featured', 'display_order')
        }),
        ('Program Details', {
            'fields': ('duration_years', 'credits_required', 'max_students', 'available_study_modes')
        }),
        ('Marketing Content', {
            'fields': ('tagline', 'overview', 'description')
        }),
        ('Financial Information', {
            'fields': ('application_fee', 'tuition_fee')
        }),
        ('Curriculum', {
            'fields': ('entry_requirements', 'core_courses', 'specialization_tracks'),
            'classes': ('collapse',)
        }),
        ('Outcomes & Career', {
            'fields': ('learning_outcomes', 'career_paths', 'avg_starting_salary', 'job_placement_rate'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('hero_image',),
            'classes': ('collapse',)
        }),
        ('SEO', {
            'fields': ('meta_description', 'meta_keywords'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'status', 'is_current',
        # 'registration_start', 'registration_end',
    )
    list_filter = ('status', 'is_current')
    search_fields = ('name',)
    list_editable = ('status', 'is_current')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'status', 'is_current')
        }),
        ('Term Dates', {
            'fields': ('term_dates',),
            'description': 'JSON list of term windows: [{"term": "first", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, ...]'
        }),
        # ('Registration Window', {
        #     'fields': ('registration_start', 'registration_end'),
        #     'classes': ('collapse',)
        # }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'code', 'program', 'course_type',
        'credit_units', 'year_of_study', 'semester',
        'is_active',
    )
    list_filter = (
        'program__department__faculty',
        'program__department',
        'program',
        'course_type',
        'semester',
        'year_of_study',
        'is_active',
    )
    search_fields = ('name', 'code', 'description')
    prepopulated_fields = {'slug': ('code', 'name')}
    list_editable = ('is_active',)
                    #  'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Hierarchy', {
            'fields': ('program',)
        }),
        ('Identity', {
            'fields': ('name', 'slug', 'code', 'is_active')
                    #    'display_order')
        }),
        ('Academic Structure', {
            'fields': ('course_type', 'credit_units', 'year_of_study', 'semester')
        }),
        ('Content', {
            'fields': ('description', 'learning_outcomes')
        }),
        # ('Display', {
        #     'fields': ('icon', 'color_primary', 'color_secondary'),
        #     'classes': ('collapse',)
        # }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AllRequiredPayments)
class AllRequiredPaymentsAdmin(admin.ModelAdmin):
    list_display = (
        'purpose', 'program', 'level', 'course',
        'amount', 'currency', 'who_to_pay', 'semester', 'academic_session', 'is_active', 'due_date'
    )
    list_filter = (
        'program__department__faculty',
        'program__department',
        'program',
        'level',
        'who_to_pay',
        'semester',
        'academic_session',
        'is_active',
    )
    search_fields = ('purpose', 'program__name', 'program__department__name')
    list_editable = ('is_active',)
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Scope', {
            'fields': ('program', 'level', 'course'),
            'description': 'Set "Level" to restrict this fee to a specific student level. Leave blank to apply to ALL levels in the program.'
        }),
        ('Payment Details', {
            'fields': ('purpose', 'amount', 'currency', 'who_to_pay', 'semester', 'academic_session', 'due_date')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# ==================== COURSE APPLICATIONS ====================
@admin.register(CourseIntake)
class CourseIntakeAdmin(admin.ModelAdmin):
    list_display = (
        'program', 'intake_period', 'year', 'start_date',
        'application_deadline', 'available_slots', 'is_active'
    )
    list_filter = ('intake_period', 'year', 'is_active', 'program__department__faculty')
    search_fields = ('program__name', 'program__code')
    list_editable = ('is_active',)
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Course & Period', {
            'fields': ('program', 'intake_period', 'year')
        }),
        ('Dates', {
            'fields': ('start_date', 'application_deadline')
        }),
        ('Capacity', {
            'fields': ('available_slots', 'is_active')
        }),
    )


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    readonly_fields = ('file', 'file_type', 'original_filename', 'file_size', 'uploaded_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ApplicationPaymentInline(admin.StackedInline):
    model = ApplicationPayment
    extra = 0
    readonly_fields = (
        'payment_reference', 'amount', 'currency', 'status',
        'payment_method', 'gateway_payment_id', 'card_last4',
        'card_brand', 'payment_metadata', 'failure_reason',
        'created_at', 'paid_at', 'updated_at'
    )
    can_delete = False

    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_reference', 'amount', 'currency', 'status', 'payment_method')
        }),
        ('Gateway Details', {
            'fields': ('gateway_payment_id', 'card_last4', 'card_brand'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('payment_metadata', 'failure_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'paid_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CourseApplication)
class CourseApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'application_id',
        'get_full_name',
        'email',
        'program',
        'academic_session',
        'study_mode',
        'status',
        'admission_accepted',
        'admission_number',
        'department_approved',
        'submitted_at',
        'created_at',
        'payment_status',
        'in_processing'
    )
    list_filter = (
        'status',
        'admission_accepted',
        'department_approved',
        'program__department__faculty',
        'program',
        'academic_session',
        'study_mode',
        'created_at',
        'payment_status'
    )
    search_fields = (
        'application_id',
        'admission_number',
        'first_name',
        'last_name',
        'email',
        'phone'
    )
    readonly_fields = (
        'application_id',
        'admission_number',
        'submitted_at',
        'reviewed_at',
        'admission_accepted_at',
        'department_approved_at',
        'created_at',
        'updated_at'
    )
    date_hierarchy = 'created_at'
    inlines = [ApplicationDocumentInline, ApplicationPaymentInline]

    fieldsets = (
        ('Application Info', {
            'fields': ('application_id', 'user', 'status', 'reviewer', 'review_notes', 'in_processing')
        }),
        ('Admission Acceptance Tracking', {
            'fields': (
                'admission_accepted',
                'admission_accepted_at',
                'admission_number',
                'department_approved',
                'department_approved_at',
                'department_approved_by'
            ),
            'classes': ('collapse',),
            'description': 'Track student admission acceptance and department approval'
        }),
        ('Course Selection', {
            'fields': ('program', 'academic_session', 'study_mode')
        }),
        ('Personal Information', {
            'fields': (
                'first_name', 'last_name', 'email', 'phone',
                'date_of_birth', 'gender', 'nationality'
            )
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2', 'city',
                'state', 'postal_code', 'country'
            ),
            'classes': ('collapse',)
        }),
        ('Academic Background', {
            'fields': (
                'highest_qualification', 'institution_name',
                'graduation_year', 'gpa_or_grade',
                'language_skill', 'language_score',
            )
        }),
        ('Additional Information', {
            'fields': (
                'work_experience_years', 'personal_statement',
                'how_did_you_hear', 'how_did_you_hear_other',
                'scholarship',
            ),
            'classes': ('collapse',)
        }),
        ('Privacy & Consent', {
            'fields': ('accept_privacy_policy', 'accept_terms_conditions', 'marketing_consent'),
            'classes': ('collapse',)
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name', 'emergency_contact_phone',
                'emergency_contact_relationship',
                'emergency_contact_email', 'emergency_contact_address',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'submitted_at',
                'reviewed_at',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    get_full_name.short_description = 'Full Name'
    get_full_name.admin_order_field = 'first_name'


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'application',
        'file_type',
        'original_filename',
        'file_size',
        'uploaded_at'
    )
    list_filter = ('file_type', 'uploaded_at')
    search_fields = (
        'application__application_id',
        'application__first_name',
        'application__last_name',
        'original_filename'
    )
    readonly_fields = (
        'application',
        'file',
        'file_type',
        'original_filename',
        'file_size',
        'uploaded_at'
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApplicationPayment)
class ApplicationPaymentAdmin(admin.ModelAdmin):
    list_display = (
        'payment_reference', 'application', 'amount', 'currency',
        'status', 'payment_method', 'paid_at', 'created_at'
    )
    list_filter = ('status', 'payment_method', 'currency', 'created_at', 'paid_at')
    search_fields = (
        'payment_reference', 'gateway_payment_id',
        'application__application_id', 'application__email'
    )
    readonly_fields = (
        'payment_reference', 'application', 'amount', 'currency',
        'gateway_payment_id', 'card_last4', 'card_brand',
        'payment_metadata', 'failure_reason',
        'created_at', 'paid_at', 'updated_at'
    )
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_reference', 'application', 'amount', 'currency', 'status', 'payment_method')
        }),
        ('Gateway Details', {
            'fields': ('gateway_payment_id', 'card_last4', 'card_brand'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('payment_metadata', 'failure_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'paid_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    actions = ['mark_as_success', 'mark_as_failed']

    def mark_as_success(self, request, queryset):
        updated = queryset.filter(status='processing').update(
            status='success',
            paid_at=timezone.now()
        )
        self.message_user(request, f'{updated} payment(s) marked as successful.')
    mark_as_success.short_description = "Mark selected as Successful"

    def mark_as_failed(self, request, queryset):
        updated = queryset.filter(status='processing').update(status='failed')
        self.message_user(request, f'{updated} payment(s) marked as failed.')
    mark_as_failed.short_description = "Mark selected as Failed"


# ==================== COURSE CATEGORIES ====================
@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'icon', 'color', 'display_order', 'is_active')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('display_order', 'is_active')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'parent')
        }),
        ('Display Settings', {
            'fields': ('icon', 'color', 'display_order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== DISCUSSIONS ====================
@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'author', 'is_pinned', 'is_locked', 'views_count', 'created_at')
    list_filter = ('is_pinned', 'is_locked', 'course', 'created_at')
    search_fields = ('title', 'content', 'author__username')
    readonly_fields = ('views_count', 'created_at', 'updated_at')
    list_editable = ('is_pinned', 'is_locked')

    fieldsets = (
        ('Discussion Information', {
            'fields': ('course', 'title', 'slug', 'content', 'author')
        }),
        ('Settings', {
            'fields': ('is_pinned', 'is_locked', 'views_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DiscussionReply)
class DiscussionReplyAdmin(admin.ModelAdmin):
    list_display = ('discussion', 'author', 'is_solution', 'created_at')
    list_filter = ('is_solution', 'created_at')
    search_fields = ('discussion__title', 'author__username', 'content')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Reply Information', {
            'fields': ('discussion', 'author', 'content', 'parent', 'is_solution')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== ENROLLMENTS ====================
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'status', 'progress_percentage', 'completed_lessons', 'enrolled_at', 'completed_at')
    list_filter = ('status', 'course', 'enrolled_at', 'completed_at')
    search_fields = ('student__username', 'course__title')
    readonly_fields = ('enrolled_at', 'completed_at', 'last_accessed')

    fieldsets = (
        ('Enrollment Information', {
            'fields': ('student', 'course', 'enrolled_by', 'status')
        }),
        ('Progress', {
            'fields': ('progress_percentage', 'completed_lessons', 'current_grade')
        }),
        ('Timestamps', {
            'fields': ('enrolled_at', 'completed_at', 'last_accessed'),
            'classes': ('collapse',)
        }),
    )


# ==================== HELPDESK / SUPPORT ====================
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'user', 'category', 'subject', 'priority', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'category', 'created_at')
    search_fields = ('ticket_id', 'user__username', 'subject', 'description')
    readonly_fields = ('ticket_id', 'created_at', 'updated_at', 'resolved_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Ticket Information', {
            'fields': ('ticket_id', 'user', 'category', 'subject', 'description')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'assigned_to')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TicketReply)
class TicketReplyAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'author', 'is_internal_note', 'created_at')
    list_filter = ('is_internal_note', 'created_at')
    search_fields = ('ticket__ticket_id', 'author__username', 'message')
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Reply Information', {
            'fields': ('ticket', 'author', 'message', 'is_internal_note')
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )


# ==================== INVOICES ====================
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'student', 'course', 'total_amount', 'status', 'issue_date', 'due_date', 'paid_date')
    list_filter = ('status', 'issue_date', 'due_date', 'currency')
    search_fields = ('invoice_number', 'student__username', 'course__title')
    readonly_fields = ('invoice_number', 'issue_date', 'created_at', 'updated_at', 'tax_amount', 'total_amount')

    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'student', 'course', 'status')
        }),
        ('Financial Details', {
            'fields': ('subtotal', 'tax_rate', 'tax_amount', 'discount_amount', 'total_amount', 'currency')
        }),
        ('Dates', {
            'fields': ('issue_date', 'due_date', 'paid_date')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== LESSON PROGRESS ====================
@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'lesson', 'is_completed', 'completion_percentage', 'time_spent_minutes', 'last_accessed')
    list_filter = ('is_completed', 'lesson__course', 'last_accessed')
    search_fields = ('enrollment__student__username', 'lesson__title')
    readonly_fields = ('started_at', 'completed_at', 'last_accessed')

    fieldsets = (
        ('Progress Information', {
            'fields': ('enrollment', 'lesson', 'is_completed', 'completion_percentage', 'time_spent_minutes')
        }),
        ('Video Progress', {
            'fields': ('video_progress_seconds',)
        }),
        ('Timestamps', {
            'fields': ('started_at', 'completed_at', 'last_accessed'),
            'classes': ('collapse',)
        }),
    )


# ==================== LMS COURSES ====================
@admin.register(LMSCourse)
class LMSCourseAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'code', 'difficulty_level',
        'is_published', 'is_featured', 'total_enrollments', 'average_rating'
    )
    list_filter = (
        'difficulty_level', 'is_published',
        'is_featured', 'created_at'
    )
    search_fields = ('title', 'code', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_published', 'is_featured')
    readonly_fields = (
        'total_enrollments', 'average_rating', 'total_reviews',
        'created_at', 'updated_at', 'published_at'
    )

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'code', 'academic_course')
        }),
        ('Academic Delivery', {
            'fields': ('session', 'term', 'lecturer'),
            'classes': ('collapse',)
        }),
        ('Content', {
            'fields': ('description', 'learning_objectives', 'prerequisites')
        }),
        ('Course Details', {
            'fields': ('difficulty_level',),
            'description': 'Difficulty Level is now a student level (100–800), e.g. 100 = first year, 400 = final year undergraduate.'
        }),
        ('Instructor', {
            'fields': ('instructor',)
        }),
        ('Media', {
            'fields': ('thumbnail', 'promo_video_url'),
            'classes': ('collapse',)
        }),
        # ('Enrollment', {
        #     'fields': ('max_students', 'enrollment_start_date', 'enrollment_end_date')
        # }),
        ('Status', {
            'fields': ('is_published', 'is_featured')
        }),
        # ('Certificate', {
        #     'fields': ('has_certificate', 'certificate_template', 'certificate_fee')
        # }),
        ('SEO', {
            'fields': ('meta_description', 'meta_keywords'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_enrollments', 'average_rating', 'total_reviews'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'section', 'lesson_type', 'is_preview', 'is_active', 'display_order')
    list_filter = ('lesson_type', 'is_preview', 'is_active', 'course')
    search_fields = ('title', 'description', 'course__title')
    list_editable = ('is_active', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('course', 'section', 'title', 'slug', 'lesson_type')
        }),
        ('Content', {
            'fields': ('description', 'content')
        }),
        ('Video Content', {
            'fields': ('video_url', 'video_file', 'video_duration_minutes')
        }),
        ('File Content', {
            'fields': ('file',)
        }),
        ('Settings', {
            'fields': ('is_preview', 'is_active', 'display_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LessonSection)
class LessonSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'display_order', 'is_active')
    list_filter = ('is_active', 'course')
    search_fields = ('title', 'description', 'course__title')
    list_editable = ('display_order', 'is_active')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Section Information', {
            'fields': ('course', 'title', 'slug', 'description')
        }),
        ('Settings', {
            'fields': ('display_order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== MESSAGES ====================
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'subject', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('sender__username', 'recipient__username', 'subject', 'body')
    readonly_fields = ('created_at', 'read_at')

    fieldsets = (
        ('Message Information', {
            'fields': ('sender', 'recipient', 'subject', 'body', 'parent')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )


# ==================== NOTIFICATIONS ====================
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at', 'read_at')

    fieldsets = (
        ('Notification Information', {
            'fields': ('user', 'notification_type', 'title', 'message', 'link')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )


# ==================== PAYMENT GATEWAY ====================
@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'gateway_type', 'is_active', 'is_test_mode', 'created_at')
    list_filter = ('gateway_type', 'is_active', 'is_test_mode')
    search_fields = ('name', 'gateway_type')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'gateway_type')
        }),
        ('Credentials', {
            'fields': ('api_key', 'api_secret', 'webhook_secret')
        }),
        ('Settings', {
            'fields': ('is_active', 'is_test_mode')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'transaction_type', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'currency', 'created_at')
    search_fields = ('transaction_id', 'user__username', 'gateway_transaction_id')
    readonly_fields = ('transaction_id', 'created_at', 'completed_at')

    fieldsets = (
        ('Transaction Information', {
            'fields': ('transaction_id', 'user', 'transaction_type', 'status')
        }),
        ('Financial Details', {
            'fields': ('amount', 'currency')
        }),
        ('Gateway Details', {
            'fields': ('gateway', 'gateway_transaction_id')
        }),
        ('Related Objects', {
            'fields': ('course',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== QUIZZES ====================
@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'passing_score', 'max_attempts', 'time_limit_minutes', 'is_active', 'display_order')
    list_filter = ('lesson__course', 'is_active')
    search_fields = ('title', 'description', 'lesson__title')
    list_editable = ('is_active', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('lesson', 'title', 'slug', 'description', 'instructions')
        }),
        ('Settings', {
            'fields': (
                'time_limit_minutes', 'passing_score', 'max_attempts',
                'shuffle_questions', 'show_correct_answers'
            )
        }),
        ('Status', {
            'fields': ('is_active', 'display_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'question_type', 'get_question_preview', 'points', 'display_order', 'is_active')
    list_filter = ('question_type', 'is_active', 'quiz__lesson__course')
    search_fields = ('question_text', 'quiz__title')
    list_editable = ('display_order', 'is_active')

    fieldsets = (
        ('Question Information', {
            'fields': ('quiz', 'question_type', 'question_text', 'explanation', 'points')
        }),
        ('Settings', {
            'fields': ('display_order', 'is_active')
        }),
    )

    def get_question_preview(self, obj):
        return obj.question_text[:50] + "..." if len(obj.question_text) > 50 else obj.question_text
    get_question_preview.short_description = 'Question'


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ('question', 'get_answer_preview', 'is_correct', 'display_order')
    list_filter = ('is_correct', 'question__quiz__lesson__course')
    search_fields = ('answer_text', 'question__question_text')

    fieldsets = (
        ('Answer Information', {
            'fields': ('question', 'answer_text', 'is_correct', 'display_order')
        }),
    )

    def get_answer_preview(self, obj):
        return obj.answer_text[:50] + "..." if len(obj.answer_text) > 50 else obj.answer_text
    get_answer_preview.short_description = 'Answer'


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'quiz', 'score', 'max_score', 'percentage', 'passed', 'is_completed', 'started_at')
    list_filter = ('is_completed', 'passed', 'quiz__lesson__course')
    search_fields = ('student__username', 'quiz__title')
    readonly_fields = ('started_at', 'completed_at')

    fieldsets = (
        ('Attempt Information', {
            'fields': ('quiz', 'student')
        }),
        ('Scoring', {
            'fields': ('score', 'max_score', 'percentage', 'passed')
        }),
        ('Status', {
            'fields': ('is_completed', 'time_taken_minutes')
        }),
        ('Timestamps', {
            'fields': ('started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'is_correct', 'points_earned')
    list_filter = ('is_correct', 'attempt__quiz__lesson__course')
    search_fields = ('attempt__student__username', 'question__question_text')

    fieldsets = (
        ('Response Information', {
            'fields': ('attempt', 'question', 'selected_answer', 'text_response')
        }),
        ('Grading', {
            'fields': ('is_correct', 'points_earned')
        }),
    )


# ==================== REVIEWS ====================
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'rating', 'is_approved', 'created_at')
    list_filter = ('rating', 'is_approved', 'course', 'created_at')
    search_fields = ('course__title', 'student__username', 'review_text')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_approved',)

    fieldsets = (
        ('Review Information', {
            'fields': ('course', 'student', 'rating', 'review_text')
        }),
        ('Status', {
            'fields': ('is_approved',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== SUBSCRIPTION PLANS ====================
@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'billing_cycle', 'max_courses', 'is_active', 'is_popular', 'display_order')
    list_filter = ('billing_cycle', 'is_active', 'is_popular', 'currency')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'is_popular', 'display_order')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'features')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'billing_cycle')
        }),
        ('Access', {
            'fields': ('max_courses',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_popular', 'display_order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'start_date', 'end_date', 'auto_renew')
    list_filter = ('status', 'auto_renew', 'plan')
    search_fields = ('user__username', 'plan__name', 'gateway_subscription_id')
    readonly_fields = ('start_date', 'created_at', 'updated_at', 'cancelled_at')

    fieldsets = (
        ('Subscription Information', {
            'fields': ('user', 'plan', 'status')
        }),
        ('Billing', {
            'fields': ('start_date', 'end_date', 'auto_renew')
        }),
        ('Payment', {
            'fields': ('gateway_subscription_id',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'cancelled_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== SYSTEM CONFIGURATION ====================
@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    list_display = ('key', 'setting_type', 'is_public', 'updated_by', 'updated_at')
    list_filter = ('setting_type', 'is_public')
    search_fields = ('key', 'value', 'description')
    readonly_fields = ('updated_at',)

    fieldsets = (
        ('Configuration', {
            'fields': ('key', 'value', 'setting_type', 'description')
        }),
        ('Permissions', {
            'fields': ('is_public', 'updated_by')
        }),
        ('Timestamp', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )


# ==================== USER PROFILE ====================
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'faculty', 'department', 'program', 'year_of_study', 'progression_status', 'email_verified', 'is_logged_in')
    list_filter = ('role', 'faculty', 'department', 'email_verified', 'progression_status', 'is_logged_in')
    search_fields = ('user__username', 'user__email', 'phone')
    readonly_fields = ('verification_token', 'active_session_key', 'created_at', 'updated_at')

    fieldsets = (
        ('Identity', {
            'fields': ('user', 'role', 'faculty', 'department', 'program')
        }),
        ('Academic Progression', {
            'fields': ('year_of_study', 'progression_status', 'admission_session')
        }),
        ('Personal Info', {
            'fields': ('bio', 'avatar', 'phone', 'date_of_birth', 'address', 'city', 'country')
        }),
        ('Social', {
            'fields': ('website', 'linkedin', 'twitter'),
            'classes': ('collapse',)
        }),
        ('Preferences', {
            'fields': ('email_notifications', 'marketing_emails')
        }),
        ('Verification & Security', {
            'fields': ('email_verified', 'verification_token', 'is_logged_in', 'active_session_key'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== VENDOR ====================
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'country', 'is_active', 'created_at')
    list_filter = ('is_active', 'country', 'created_at')
    search_fields = ('name', 'email', 'stripe_account_id')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active',)
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'email', 'country')
        }),
        ('Integration', {
            'fields': ('stripe_account_id',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at')
        }),
    )


# ==================== BROADCAST CENTER ====================
@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = (
        'subject',
        'filter_type',
        'recipient_count',
        'status',
        'created_by',
        'created_at',
        'sent_at'
    )
    list_filter = (
        'status',
        'filter_type',
        'created_at',
        'sent_at'
    )
    search_fields = (
        'subject',
        'message',
        'created_by__username'
    )
    readonly_fields = (
        'slug',
        'recipient_count',
        'recipient_emails',
        'sent_at',
        'created_at',
        'updated_at',
        'error_message'
    )
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Message Content', {
            'fields': ('subject', 'slug', 'message')
        }),
        ('Recipients', {
            'fields': (
                'filter_type',
                'filter_values',
                'recipient_count',
                'recipient_emails'
            )
        }),
        ('Status', {
            'fields': ('status', 'sent_at', 'error_message')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.status == 'sent':
            readonly.extend(['subject', 'message', 'filter_type', 'filter_values'])
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == 'sent':
            return False
        return super().has_delete_permission(request, obj)


# ==================== STUDY GROUPS ====================
@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'created_by', 'max_members', 'is_active', 'is_public', 'created_at')
    list_filter = ('is_active', 'is_public', 'course', 'created_at')
    search_fields = ('name', 'description', 'created_by__username')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'is_public')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'course', 'created_by')
        }),
        ('Settings', {
            'fields': ('max_members', 'is_active', 'is_public')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudyGroupMember)
class StudyGroupMemberAdmin(admin.ModelAdmin):
    list_display = ('study_group', 'user', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active', 'joined_at')
    search_fields = ('study_group__name', 'user__username')
    list_editable = ('role', 'is_active')
    readonly_fields = ('joined_at', 'updated_at')

    fieldsets = (
        ('Membership', {
            'fields': ('study_group', 'user', 'role', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudyGroupMessage)
class StudyGroupMessageAdmin(admin.ModelAdmin):
    list_display = ('study_group', 'author', 'get_content_preview', 'created_at')
    list_filter = ('study_group', 'created_at')
    search_fields = ('study_group__name', 'author__username', 'content')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Message', {
            'fields': ('study_group', 'author', 'content')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_content_preview(self, obj):
        return obj.content[:60] + '...' if len(obj.content) > 60 else obj.content
    get_content_preview.short_description = 'Content'


# ==================== STAFF PAYROLL ====================
@admin.register(StaffPayroll)
class StaffPayrollAdmin(admin.ModelAdmin):
    list_display = (
        'payroll_reference', 'staff', 'month', 'year',
        'base_salary', 'allowances', 'bonuses', 'gross_salary',
        'tax_deduction', 'other_deductions', 'net_salary',
        'payment_status', 'payment_method', 'payment_date'
    )
    list_filter = ('payment_status', 'payment_method', 'month', 'year')
    search_fields = ('payroll_reference', 'staff__username', 'staff__first_name', 'staff__last_name')
    readonly_fields = (
        'payroll_reference', 'gross_salary', 'net_salary',
        'created_at', 'updated_at', 'approved_at'
    )
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Reference', {
            'fields': ('payroll_reference', 'staff', 'month', 'year')
        }),
        ('Salary', {
            'fields': ('base_salary', 'allowances', 'bonuses', 'gross_salary')
        }),
        ('Deductions', {
            'fields': ('tax_deduction', 'other_deductions', 'net_salary')
        }),
        ('Payment', {
            'fields': ('payment_status', 'payment_method', 'payment_date', 'bank_name', 'account_number', 'currency')
        }),
        ('Attachments', {
            'fields': (
                'attachment_1', 'attachment_1_name',
                'attachment_2', 'attachment_2_name',
                'attachment_3', 'attachment_3_name',
                'attachment_4', 'attachment_4_name',
                'attachment_5', 'attachment_5_name',
            ),
            'classes': ('collapse',)
        }),
        ('Administration', {
            'fields': ('notes', 'created_by', 'approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.payment_status == 'paid':
            return False
        return super().has_delete_permission(request, obj)


# ==================== LIST OF COUNTRIES ====================
@admin.register(ListOfCountry)
class ListOfCountryAdmin(admin.ModelAdmin):
    list_display = ('country', 'country_code', 'country_phonecode', 'nationality')
    search_fields = ('country', 'country_code', 'country_phonecode', 'nationality')
    list_filter = ()

    fieldsets = (
        ('Country Information', {
            'fields': ('country', 'country_code', 'country_phonecode', 'nationality')
        }),
    )

from .models import LibraryItem

@admin.register(LibraryItem)
class LibraryItemAdmin(admin.ModelAdmin):
    list_display  = ['title', 'author', 'category', 'subcategory', 'access', 'is_active', 'featured']
    list_filter   = ['category', 'access', 'is_active', 'featured', 'language']
    search_fields = ['title', 'author', 'subcategory', 'tags']
    readonly_fields = ['slug', 'view_count', 'download_count', 'file_size_mb', 'file_type', 'created_at', 'updated_at']

    fieldsets = (
        ('Taxonomy', {
            'fields': ('category', 'subcategory', 'slug')
        }),
        ('Bibliographic', {
            'fields': ('title', 'author', 'publisher', 'year', 'edition', 'isbn', 'language', 'description', 'tags')
        }),
        ('Media', {
            'fields': ('cover_image', 'file', 'file_size_mb', 'file_type'),
            'classes': ('collapse',)
        }),
        ('External Access', {
            'fields': ('external_url', 'external_url_label')
        }),
        ('Behaviour', {
            'fields': ('allow_download', 'allow_read_online', 'access', 'featured', 'is_active', 'order')
        }),
        ('Stats', {
            'fields': ('view_count', 'download_count'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# ==================== COURSE REGISTRATION ====================
from .models import CourseRegistration

@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display  = ('student', 'course', 'session', 'term', 'status', 'registered_at', 'dropped_at')
    list_filter   = ('status', 'session', 'term', 'course__program__department__faculty')
    search_fields = ('student__username', 'student__email', 'course__code', 'course__name')
    readonly_fields = ('registered_at', 'dropped_at')
    date_hierarchy  = 'registered_at'

    fieldsets = (
        ('Registration', {
            'fields': ('student', 'course', 'session', 'term', 'status')
        }),
        ('Timestamps', {
            'fields': ('registered_at', 'dropped_at'),
            'classes': ('collapse',)
        }),
    )


# ==================== SITE HISTORY MILESTONES (standalone) ====================
@admin.register(SiteHistoryMilestone)
class SiteHistoryMilestoneAdmin(admin.ModelAdmin):
    list_display  = ('year', 'title', 'site', 'display_order', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('title', 'description')
    list_editable = ('display_order', 'is_active')

    fieldsets = (
        ('Milestone', {
            'fields': ('site', 'year', 'title', 'description')
        }),
        ('Display', {
            'fields': ('display_order', 'is_active')
        }),
    )


# ==================== EXAMS ====================
class ExamQuestionInline(admin.TabularInline):
    model    = ExamQuestion
    extra    = 0
    max_num  = 20
    per_page = 20
    fields   = ('question_text', 'question_type', 'marks', 'is_active')
    readonly_fields  = ('created_at',)
    show_change_link = True

    #def get_queryset(self, request):
    #    qs = super().get_queryset(request).order_by('order')
     #   # Return only first 20 — but don't slice here (breaks Django formset filter).
      #  # Use the IDs instead so the queryset remains filterable.
       # ids = list(qs.values_list('pk', flat=True)[:20])
        #return qs.filter(pk__in=ids)


class ExamStatusLogInline(admin.TabularInline):
    model   = ExamStatusLog
    extra   = 0
    fields  = ('from_status', 'to_status', 'changed_by', 'note', 'created_at')
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'note', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display  = (
        'reference_code', 'title', 'exam_type', 'course',
        'start_datetime', 'end_datetime',
        'status', 'show_result_immediately', 'is_active',
        # REMOVED: 'mode'             — always online, no longer a field
        # REMOVED: 'academic_session' — derived from LMSCourse
        # REMOVED: 'department'       — derived from LMSCourse
        # REMOVED: 'exam_date'        — replaced by start_datetime
    )
    list_filter   = (
        'status', 'exam_type',
        'show_result_immediately', 'is_active',
        # REMOVED: 'mode'             — always online
        # REMOVED: 'academic_session' — not stored on Exam
        # REMOVED: 'department'       — not stored on Exam
        # REMOVED: 'exam_date'        — replaced by start_datetime
    )
    search_fields = ('reference_code', 'title', 'instructor__username')
    # REMOVED: 'venue' from search_fields — venue no longer stored
    readonly_fields = (
        'reference_code', 'slug', 'submission_count',
        'submitted_at', 'approved_at', 'rejected_at',
        'published_at', 'cancelled_at', 'created_at', 'updated_at',
        # Computed properties — shown read-only so admins can inspect them
        'duration_minutes_display',
        'instructions_open_at_display',
        'visible_from_display',
        'visible_until_display',
        'has_clash_display',
    )
    date_hierarchy = 'start_datetime'
    # REMOVED: date_hierarchy = 'exam_date' — replaced by start_datetime
    inlines        = [ExamQuestionInline, ExamStatusLogInline]
 
    fieldsets = (
        ('Identity', {
            'fields': (
                'reference_code', 'slug', 'title', 'description',
                'exam_type',
                # REMOVED: 'mode' — always online/CBT
                'is_active',
            )
        }),
        ('Relationships', {
            'fields': (
                'course',
                'instructor',
                # REMOVED: 'academic_session' — derived from LMSCourse
                # REMOVED: 'department'       — derived from LMSCourse
                # REMOVED: 'invigilators'     — online exam, no invigilators
            )
        }),
        ('Schedule', {
            # REMOVED: 'exam_date', 'start_time', 'end_time' (split fields)
            # REMOVED: 'instruction_window_minutes' (now a class constant = 10)
            'fields': (
                'start_datetime', 'end_datetime',
                'duration_minutes_display',
                'instructions_open_at_display',
            ),
        }),
        # REMOVED: Venue fieldset entirely — online exam, no physical location
        # ('Venue', {
        #     'fields': ('venue', 'hall_capacity', 'expected_candidates', 'eligible_levels'),
        #     'classes': ('collapse',)
        # }),
        ('Question Pool', {
            'fields': (
                'questions_per_student',
                # REMOVED: 'difficulty_mix' — not used in this system
                'shuffle_questions', 'shuffle_options',
                'total_marks', 'pass_mark',
                'show_result_immediately', 'show_answers_after',
            )
        }),
        ('Question Import', {
            'fields': ('question_import_file', 'import_status', 'import_error_log'),
            'classes': ('collapse',)
        }),
        # REMOVED: Files fieldset — timetable_file and seating_plan_file removed
        # ('Files', {
        #     'fields': ('timetable_file', 'seating_plan_file'),
        #     'classes': ('collapse',)
        # }),
        ('Approval Workflow', {
            'fields': (
                'status', 'submission_count',
                'submitted_by', 'submitted_at',
                'approved_by', 'approved_at',
                'rejected_by', 'rejected_at', 'rejection_reason',
                'published_by', 'published_at',
                'cancelled_by', 'cancelled_at', 'cancellation_reason',
            ),
            'classes': ('collapse',)
        }),
        ('Student Visibility  (computed — read only)', {
            # REMOVED: 'visible_from_override', 'visible_until_override' (fields removed)
            # These are now pure @properties on the model.
            'description': (
                'Visibility is automatically computed: students see the exam '
                f'{Exam.VISIBILITY_HOURS_BEFORE}h before start and '
                f'{Exam.VISIBILITY_HOURS_AFTER}h after end. '
                'No manual overrides are stored.'
            ),
            'fields': ('visible_from_display', 'visible_until_display'),
            'classes': ('collapse',)
        }),
        ('Clash Detection  (computed — read only)', {
            # REMOVED: 'clash_group', has_clash BooleanField (both removed from model)
            # has_clash is now a @property; clash_notes plain text field is kept.
            'fields': ('has_clash_display', 'clash_notes'),
            'classes': ('collapse',)
        }),
        ('Instructions & Notes', {
            'fields': (
                'instructions', 'special_instructions', 'internal_notes',
                # REMOVED: 'has_accommodations', 'accommodation_notes'
                # — physical-exam concepts, not applicable for online/CBT
            ),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
 
    # ── Readonly display helpers for computed @properties ──────────────────────
    # These let admins see the derived values without them being editable fields.
 
    @admin.display(description='Duration (mins)')
    def duration_minutes_display(self, obj):
        return obj.duration_minutes
 
    @admin.display(description='Instructions open at')
    def instructions_open_at_display(self, obj):
        return obj.instructions_open_at
 
    @admin.display(description='Visible from')
    def visible_from_display(self, obj):
        return obj.visible_from
 
    @admin.display(description='Visible until')
    def visible_until_display(self, obj):
        return obj.visible_until
 
    @admin.display(description='Has clash?', boolean=True)
    def has_clash_display(self, obj):
        return obj.has_clash
 
    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in (Exam.PUBLISHED, Exam.APPROVED):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display  = (
        'exam', 'question_type', 'marks',
        'is_active', 'year_first_used', 'source_reference',
    )
    list_filter   = ('question_type', 'is_active', 'exam__exam_type')
    search_fields = ('question_text', 'source_reference', 'exam__reference_code')
    readonly_fields = ('slug', 'created_at', 'updated_at')
    list_editable   = ('is_active',)

    fieldsets = (
        ('Pool Membership', {
            'fields': ('slug', 'exam', 'is_active')
        }),
        ('Question Content', {
            'fields': ('question_text', 'question_type', 'marks', 'image', 'explanation')
        }),
        ('Answer Options', {
            'fields': ('options', 'accepted_answers'),
            'description': 'For MCQ/multi_select/true_false: fill options JSON. For short_answer: fill accepted_answers. Leave both empty for essay.',
            'classes': ('collapse',)
        }),
        ('Bank Metadata', {
            'fields': ('tags', 'source_reference', 'year_first_used'),
            'classes': ('collapse',)
        }),
        ('Import Traceability', {
            'fields': ('imported_from_file',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StudentExamResponse)
class StudentExamResponseAdmin(admin.ModelAdmin):
    list_display  = (
        'student', 'exam', 'status', 'total_score', 'score_percentage',
        'passed', 'auto_submitted', 'pending_manual_count',
        'tab_switch_count', 'submitted_at',
    )
    list_filter = (
        'status', 'passed', 'auto_submitted',
        'exam__exam_type',
    )
    search_fields = ('student__username', 'student__email', 'exam__reference_code', 'ip_address')
    readonly_fields = (
        'slug', 'assigned_question_ids', 'assigned_options_order',
        'answers', 'question_scores', 'total_score', 'score_percentage',
        'passed', 'graded_at', 'instructions_opened_at', 'exam_started_at',
        'last_autosave_at', 'submitted_at', 'time_spent_seconds',
        'tab_switch_count', 'ip_address', 'created_at', 'updated_at',
    )
    date_hierarchy  = 'submitted_at'

    fieldsets = (
        ('Identity', {
            'fields': ('slug', 'exam', 'student', 'status')
        }),
        ('Question Draw', {
            'fields': ('assigned_question_ids', 'assigned_options_order'),
            'classes': ('collapse',)
        }),
        ('Answers', {
            'fields': ('answers',),
            'classes': ('collapse',)
        }),
        ('Grading', {
            'fields': (
                'question_scores', 'total_score', 'score_percentage',
                'passed', 'pending_manual_count',
                'overall_feedback', 'graded_by', 'graded_at',
            )
        }),
        ('Timing', {
            'fields': (
                'instructions_opened_at', 'exam_started_at',
                'last_autosave_at', 'submitted_at',
                'auto_submitted', 'time_spent_seconds',
            ),
            'classes': ('collapse',)
        }),
        ('Security / Forensics', {
            'fields': ('ip_address', 'tab_switch_count', 'invigilator_notes'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False  # created server-side only

    def has_change_permission(self, request, obj=None):
        # Allow editing only grading/feedback fields; all response data is readonly above
        return True


@admin.register(ExamStatusLog)
class ExamStatusLogAdmin(admin.ModelAdmin):
    list_display  = ('exam', 'from_status', 'to_status', 'changed_by', 'note', 'created_at')
    list_filter   = ('from_status', 'to_status', 'created_at')
    search_fields = ('exam__reference_code', 'exam__title', 'changed_by__username', 'note')
    readonly_fields = ('slug', 'exam', 'from_status', 'to_status', 'changed_by', 'note', 'created_at')
    date_hierarchy  = 'created_at'

    fieldsets = (
        ('Transition', {
            'fields': ('slug', 'exam', 'from_status', 'to_status', 'changed_by', 'note')
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==================== ADMIN SITE BRANDING ====================
admin.site.site_header = "LMS Administration"
admin.site.site_title = "LMS Admin Portal"
admin.site.index_title = "Welcome to LMS Administration"