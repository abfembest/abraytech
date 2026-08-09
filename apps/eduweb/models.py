from asyncio import Condition
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Max, F, FloatField, ExpressionWrapper
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from django.utils.functional import cached_property
from cryptography.fernet import Fernet, InvalidToken
from functools import lru_cache
import uuid
import os
import base64
import hashlib
from decimal import Decimal, ROUND_HALF_UP


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Fernet cipher keyed off SECRET_KEY. Cached — the key can't change within
    a running process, so re-deriving it on every call is wasted work."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """Encrypts a credential for storage. Key is derived from SECRET_KEY."""
    if not plain:
        return ''
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypts a value stored via encrypt_secret(). Returns '' if blank or
    undecryptable (e.g. SECRET_KEY rotated since it was encrypted)."""
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ''


DEGREE_LEVEL_CHOICES = [
    ('certificate', 'Certificate'),
    ('diploma', 'Diploma'),
    ('undergraduate', 'Undergraduate'),
    ('postgraduate', 'Postgraduate'),
    ('masters', 'Masters'),
    ('phd', 'PhD')
]

# Canonical academic level choices (year_of_study × 100).
# Level represents position within a program, not absolute academic rank.
# Works for all international systems: UG (100–400/500), Masters (100–200),
# PhD (100–400), Medicine/Law/Eng extended programs (up to 800).
# The Program.degree_level field identifies the qualification type.
STUDENT_LEVEL_CHOICES = [
    (100, 'Level 100'),
    (200, 'Level 200'),
    (300, 'Level 300'),
    (400, 'Level 400'),
    (500, 'Level 500'),
    (600, 'Level 600'),
    (700, 'Level 700'),
    (800, 'Level 800'),
]

import hashlib
import secrets
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.utils.text import slugify
from django.db import IntegrityError, models, transaction


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (upload_path, unique_slug, ImmutableMixin)
# ─────────────────────────────────────────────────────────────────────────────

def unique_slug(model_class, base_value, slug_field="slug", max_attempts=20):
    """Generate a unique slug. Retries with a random suffix on collision."""
    slug = slugify(base_value)[:200]
    for attempt in range(max_attempts):
        candidate = slug if attempt == 0 else f"{slug[:190]}-{secrets.token_hex(3)}"
        if not model_class._default_manager.filter(**{slug_field: candidate}).exists():
            return candidate
    raise RuntimeError(f"Could not generate a unique slug for {model_class.__name__} after {max_attempts} attempts.")


class upload_path:
    """
    Callable upload-to helper. Renames every uploaded file to a UUID so
    filenames can never be guessed and path traversal is impossible.
    """
    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        return f"{self.folder}/{uuid.uuid4()}.{ext}"

    def deconstruct(self):
        return (
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            [self.folder],
            {},
        )


class ImmutableMixin:
    """
    Prevents any update or delete on records that must be permanently immutable.
    Usage:  class MyLog(ImmutableMixin, models.Model): ...
    """
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                f"{self.__class__.__name__} records are immutable and cannot be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            f"{self.__class__.__name__} records are immutable and cannot be deleted."
        )

# ==================== HELPER FUNCTIONS ====================
def validate_file_size(file, max_size_mb=10):
    """Validate file size"""
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f'File size cannot exceed {max_size_mb}MB')


def get_video_upload_path(instance, filename):
    """Generate upload path for course videos"""
    course_slug = instance.lesson.course.slug if hasattr(instance, 'lesson') else 'misc'
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    return f'courses/{course_slug}/videos/{filename}'


def get_document_upload_path(instance, filename):
    """Generate upload path for course documents"""
    course_slug = instance.lesson.course.slug if hasattr(instance, 'lesson') else instance.course.slug
    ext = filename.split('.')[-1]
    safe_filename = f"{slugify(os.path.splitext(filename)[0])}.{ext}"
    return f'courses/{course_slug}/documents/{safe_filename}'


def get_assignment_upload_path(instance, filename):
    """Generate upload path for assignment submissions"""
    ext = filename.split('.')[-1]
    safe_filename = f"{instance.student.username}_{uuid.uuid4().hex[:8]}.{ext}"
    return f'courses/{instance.assignment.lesson.course.slug}/submissions/{safe_filename}'


def get_certificate_upload_path(instance, filename):
    """Generate upload path for certificates"""
    ext = filename.split('.')[-1]
    filename = f"{instance.student.username}_{uuid.uuid4().hex}.{ext}"
    return f'certificates/{filename}'


def blog_image_upload_path(instance, filename):
    """Generate upload path for blog images"""
    name, ext = os.path.splitext(filename)
    safe_filename = f"{slugify(name)}{ext}"
    return f'blog/{instance.slug}/{safe_filename}'


# Maps international/alias term keys → the canonical semester keys used on
# Course.semester. AcademicSession stores term_dates with keys from
# AcademicSession.TERM_CHOICES (first/second/third/fall/spring/summer/
# annual); Course.semester only uses first/second/annual. This is the only
# place that relationship is defined — previously duplicated as a local
# `term_normalisation_map` inside student/views.py; that copy now imports
# this one instead of hand-rolling its own, since Program.max_credits_for_term
# below needs the exact same mapping and a model can't import from a view
# module. Used only for the *fallback* tier of the credit-cap lookup — the
# most specific tier (ProgramSessionCreditCap) intentionally does NOT
# normalise, since it's keyed by whatever raw term a session actually uses
# (e.g. a real 'third' term gets its own cap there, not second's).
TERM_NORMALISATION_MAP = {
    # nigerian semester terms (already canonical — map to themselves)
    'first':  'first',
    'second': 'second',
    'third':  'second',   # third semester/harmattan treated as second semester
    'annual': 'annual',
    # international semester equivalents
    'fall':   'first',
    'spring': 'second',
    'summer': 'annual',
    'autumn': 'first',    # autumn = fall = first semester
}


class SiteConfig(models.Model):
    """
    Singleton model — drives the nav header, footer, and all embed codes
    (promo video, campus map, virtual tour) across all pages.

    In views:      site_config = SiteConfig.get()
    In templates:  {{ site_config.field_name }}
    """

    # =========================================================================
    # IDENTITY  —  nav logo, footer copyright, og/twitter meta tags
    # =========================================================================
    school_name = models.CharField(
        max_length=200,
        default='Melchisedec International University',
        help_text="Full legal name shown in nav, footer, og tags"
    )
    school_short_name = models.CharField(
        max_length=50, blank=True, default='MIU',
        help_text="Abbreviation used in footer copyright, og tags e.g. 'MIU'"
    )
    tagline = models.CharField(
        max_length=300, blank=True,
        help_text="Short tagline used in footer and og description fallback"
    )
    logo = models.ImageField(
        upload_to='site/logos/', blank=True, null=True,
        help_text="Nav bar and footer logo"
    )
    logo_dark = models.ImageField(
        upload_to='site/logos/', blank=True, null=True,
        help_text="Dark-background variant of the logo"
    )
    favicon = models.ImageField(
        upload_to='site/favicons/', blank=True, null=True,
        help_text="Browser tab favicon"
    )
    og_image = models.ImageField(
        upload_to='site/og/', blank=True, null=True,
        help_text="Default Open Graph / Twitter share image (1200×630 px recommended)"
    )
    theme_color = models.CharField(
        max_length=20, blank=True, default='#840384',
        help_text="Browser theme-color meta tag hex value e.g. '#840384'"
    )

    # =========================================================================
    # CONTACT  —  footer bottom bar (phone, email)
    # =========================================================================
    email = models.EmailField(
        blank=True,
        help_text="Primary contact email — footer bottom bar"
    )
    phone_primary = models.CharField(
        max_length=30, blank=True,
        help_text="Primary phone — footer bottom bar"
    )
    phone_secondary    = models.CharField(max_length=30, blank=True)
    phone_ng_primary   = models.CharField(max_length=30, blank=True,
                                          help_text="Primary Nigeria phone number")
    phone_ng_secondary = models.CharField(max_length=30, blank=True,
                                          help_text="Secondary Nigeria phone number")
    whatsapp = models.CharField(
        max_length=30, blank=True,
        help_text="WhatsApp number — digits only e.g. 15551234567"
    )

    # =========================================================================
    # CONTACT PAGE — department-specific emails
    # =========================================================================
    email_admissions = models.EmailField(
        blank=True,
        help_text="Admissions department email — contact page"
    )
    email_info = models.EmailField(
        blank=True,
        help_text="General info email — contact page"
    )
    email_international = models.EmailField(
        blank=True,
        help_text="International enquiries email — contact page"
    )

    # =========================================================================
    # CONTACT PAGE — labelled phone lines
    # =========================================================================
    phone_admissions = models.CharField(
        max_length=30, blank=True,
        help_text="Admissions phone line — contact page e.g. '+1 (555) 123-4567'"
    )
    phone_general = models.CharField(
        max_length=30, blank=True,
        help_text="General enquiries phone line — contact page"
    )
    phone_international = models.CharField(
        max_length=30, blank=True,
        help_text="International office phone line — contact page"
    )

    # =========================================================================
    # OFFICE HOURS  —  contact page office hours block
    # =========================================================================
    office_hours_weekday = models.CharField(
        max_length=100, blank=True,
        default='Monday - Friday: 8:00 AM - 6:00 PM',
        help_text="Weekday office hours e.g. 'Monday - Friday: 8:00 AM - 6:00 PM'"
    )
    office_hours_saturday = models.CharField(
        max_length=100, blank=True,
        default='Saturday: 9:00 AM - 1:00 PM',
        help_text="Saturday office hours e.g. 'Saturday: 9:00 AM - 1:00 PM'"
    )
    office_hours_sunday = models.CharField(
        max_length=100, blank=True,
        default='Sunday: Closed',
        help_text="Sunday office hours e.g. 'Sunday: Closed'"
    )

    # =========================================================================
    # ADDRESSES  —  footer address block
    # =========================================================================
    address_usa = models.TextField(
        blank=True,
        help_text="US campus address — footer"
    )
    address_nigeria = models.TextField(
        blank=True,
        help_text="Nigeria campus address — footer"
    )

    # =========================================================================
    # SOCIAL MEDIA  —  footer social icons + nav mega-menu Connect section
    # =========================================================================
    facebook  = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube   = models.URLField(blank=True)
    twitter   = models.URLField(blank=True)
    tiktok    = models.URLField(blank=True)
    linkedin  = models.URLField(blank=True)

    # =========================================================================
    # FOOTER COPY  —  footer tagline paragraph + copyright line
    # =========================================================================
    footer_tagline = models.TextField(
        blank=True,
        default='Empowering global education since 1995 with innovative learning experiences and world-class faculty.',
        help_text="Short paragraph shown under the logo in the footer"
    )
    copyright_year = models.CharField(
        max_length=10, blank=True, default='2025',
        help_text="Year in the footer copyright line e.g. '2025'"
    )

    # =========================================================================
    # SEO  —  base.html meta/og/twitter tags inherited by all pages
    # =========================================================================
    meta_description = models.TextField(
        blank=True,
        help_text="Default SEO meta description — also og:description and twitter:description"
    )
    meta_keywords = models.TextField(
        blank=True,
        help_text="Default SEO meta keywords (comma separated)"
    )

    # =========================================================================
    # EMBED CODES
    # These are kept here because they are shared across multiple pages:
    #   promo_video_url    → index.html about section + about.html Who We Are
    #   campus_map_embed_url → index.html campus map section
    #   virtual_tour_url   → about.html Campus & Facilities section
    # =========================================================================
    promo_video_url = models.TextField(
        blank=True,
        help_text="Full iframe embed code from YouTube/Vimeo for the promo video"
    )
    campus_map_embed_url = models.TextField(
        blank=True,
        help_text="Full iframe embed code from Google Maps for the campus map section"
    )
    campus_map_address = models.CharField(
        max_length=300, blank=True,
        help_text="Address shown on the map overlay card and used for the Get Directions link"
    )
    virtual_tour_url = models.TextField(
        blank=True,
        help_text="Full iframe embed code for the virtual campus tour on the about page"
    )

    # =========================================================================
    # HERO SLIDES  —  index.html rotating hero background (up to 3 slides)
    # Each slide is either an image OR a video — not both.
    # If image is set, it is used. If video_url is set instead, video plays.
    # duration = how many seconds the slide stays before advancing.
    # =========================================================================
    hero_slide_1_image    = models.ImageField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 1 background image"
    )
    hero_slide_1_video    = models.FileField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 1 background video (.mp4). Used instead of image if set."
    )
    hero_slide_1_alt      = models.CharField(
        max_length=200, blank=True,
        default='Students collaborating on campus',
        help_text="Accessibility label for slide 1"
    )
    hero_slide_1_duration = models.PositiveSmallIntegerField(
        default=6,
        help_text="Seconds slide 1 stays visible before advancing"
    )

    hero_slide_2_image    = models.ImageField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 2 background image"
    )
    hero_slide_2_video    = models.FileField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 2 background video (.mp4). Used instead of image if set."
    )
    hero_slide_2_alt      = models.CharField(
        max_length=200, blank=True,
        default='Graduates celebrating commencement',
        help_text="Accessibility label for slide 2"
    )
    hero_slide_2_duration = models.PositiveSmallIntegerField(
        default=6,
        help_text="Seconds slide 2 stays visible before advancing"
    )

    hero_slide_3_image    = models.ImageField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 3 background image"
    )
    hero_slide_3_video    = models.FileField(
        upload_to='site/hero/', blank=True, null=True,
        help_text="Slide 3 background video (.mp4). Used instead of image if set."
    )
    hero_slide_3_alt      = models.CharField(
        max_length=200, blank=True,
        default='Students using technology in class',
        help_text="Accessibility label for slide 3"
    )
    hero_slide_3_duration = models.PositiveSmallIntegerField(
        default=6,
        help_text="Seconds slide 3 stays visible before advancing"
    )

    # =========================================================================
    # ABOUT PAGE — Mission, Vision & Values
    # =========================================================================
    about_mission = models.TextField(
        blank=True,
        default='To provide accessible, innovative, and transformative education that empowers individuals from all backgrounds to achieve their full potential and make meaningful contributions to society.',
        help_text="Our Mission text — about page Mission card"
    )
    about_vision = models.TextField(
        blank=True,
        default='To be a globally recognized leader in higher education, known for innovation, inclusivity, and preparing future-ready graduates who drive positive change worldwide.',
        help_text="Our Vision text — about page Vision card"
    )
    about_values = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'List of core values shown in the Values card. '
            'Store as a JSON array of strings, e.g. '
            '["Excellence in Education", "Diversity & Inclusion", "Innovation & Creativity", "Global Citizenship"]'
        )
    )

    class Meta:
        verbose_name        = 'Site Configuration'
        verbose_name_plural = 'Site Configuration'

    def __str__(self):
        return self.school_name

    @classmethod
    def get(cls):
        """Fetch the single site config. Use this in all views."""
        return cls.objects.first()

class InstitutionPartner(models.Model):
    """
    Partners, affiliates, and accreditation bodies shown on the About page.
    Manageable from the Django admin without touching template code.
    """
    CATEGORY_CHOICES = [
        ('partner',      'Partner'),
        ('affiliation',  'Affiliation'),
        ('accreditation','Accreditation'),
    ]

    name          = models.CharField(max_length=300, help_text="Full institution name")
    category      = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='partner')
    location      = models.CharField(max_length=200, blank=True, help_text="e.g. 'New Jersey, USA'")
    logo          = models.ImageField(
                        upload_to='partners/logos/', blank=True, null=True,
                        help_text="Partner logo image (PNG/SVG recommended, transparent background)"
                    )
    is_active     = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Institution Partner / Affiliation'
        verbose_name_plural = 'Institution Partners & Affiliations'
        ordering            = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class SiteHistoryMilestone(models.Model):
    """
    One entry in the About page 'Our History' timeline.
    Add as many as needed; order by `year`.
    """
    site = models.ForeignKey(
        SiteConfig,
        on_delete=models.CASCADE,
        related_name='history_milestones',
    )
    year = models.PositiveSmallIntegerField(
        help_text="e.g. 1995"
    )
    title = models.CharField(
        max_length=150,
        help_text="e.g. 'Founding' — displayed as '1995 – Founding'"
    )
    description = models.TextField(
        help_text="One or two sentences describing what happened that year"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'History Milestone'
        verbose_name_plural = 'History Milestones'
        ordering = ['year']

    def __str__(self):
        return f"{self.year} – {self.title}"

# ==================== TESTIMONIALS ====================
class Testimonial(models.Model):
    quote       = models.TextField()
    author_name = models.CharField(max_length=100)
    author_role = models.CharField(max_length=150, help_text="e.g. 'MBA Graduate, 2023'")
    avatar      = models.ImageField(
        upload_to='testimonials/avatars/',
        blank=True,
        null=True,
        help_text="Author photo. If left blank, initials will be shown instead."
    )
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['author_name']
        verbose_name = 'Testimonial'
        verbose_name_plural = 'Testimonials'

    def __str__(self):
        return f"{self.author_name} – {self.author_role}"

# ==================== ANNOUNCEMENTS ====================
class Announcement(models.Model):
    """System-wide or course-specific announcements"""
    ANNOUNCEMENT_TYPE_CHOICES = [
        ('system', 'System-wide'),
        ('course', 'Course-specific'),
        ('category', 'Category-specific'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    announcement_type = models.CharField(max_length=20, choices=ANNOUNCEMENT_TYPE_CHOICES, default='system')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    
    # Targeting
    course = models.ForeignKey('LMSCourse', on_delete=models.CASCADE, null=True, blank=True, related_name='announcements')
    category = models.ForeignKey('CourseCategory', on_delete=models.CASCADE, null=True, blank=True, related_name='announcements')
    
    # Author
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='announcements_created')
    
    # Publishing
    is_active = models.BooleanField(default=True)
    publish_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', '-publish_date']
        verbose_name = 'Announcement'
        verbose_name_plural = 'Announcements'
        indexes = [
            models.Index(fields=['-publish_date', 'is_active']),
            models.Index(fields=['announcement_type']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            while Announcement.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if announcement has expired"""
        if self.expiry_date:
            return timezone.now() > self.expiry_date
        return False


# ==================== ASSIGNMENTS ====================
class Assignment(models.Model):
    """Assignments for lessons"""
    lesson = models.ForeignKey('Lesson', on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField()
    instructions = models.TextField(blank=True)
    
    # Grading
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, validators=[MinValueValidator(0)])
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=50.00, validators=[MinValueValidator(0)])
    
    # Attachments
    attachment = models.FileField(
        upload_to=get_document_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'txt', 'zip'])]
    )
    
    # Deadlines
    due_date = models.DateTimeField()
    allow_late_submission = models.BooleanField(default=False)
    late_penalty_percent = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Settings
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['lesson', 'display_order', 'due_date']
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'
        unique_together = [['lesson', 'slug']]
        indexes = [
            models.Index(fields=['lesson', 'is_active']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.lesson.course.title} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        """Check if assignment is overdue"""
        return timezone.now() > self.due_date


class AssignmentSubmission(models.Model):
    """Student assignment submissions"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned for Revision'),
    ]
    
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_submissions')
    
    # Submission
    submission_text = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to=get_assignment_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'txt', 'zip'])]
    )
    
    # Grading
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_assignments')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_late = models.BooleanField(default=False)
    
    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Assignment Submission'
        verbose_name_plural = 'Assignment Submissions'
        unique_together = [['assignment', 'student']]
        indexes = [
            models.Index(fields=['assignment', 'student']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"
    
    def save(self, *args, **kwargs):
        # Check if late submission
        if self.submitted_at and self.submitted_at > self.assignment.due_date:
            self.is_late = True
            
            # Apply late penalty only when late submission is allowed but penalized
            if self.score and self.assignment.allow_late_submission and self.assignment.late_penalty_percent > 0:
                penalty = (self.assignment.late_penalty_percent / 100) * float(self.score)
                self.score = max(Decimal('0.00'), self.score - Decimal(str(penalty)))
        
        # Set submitted_at when status changes to submitted
        if self.status == 'submitted' and not self.submitted_at:
            self.submitted_at = timezone.now()
        
        # Set graded_at when graded
        if self.status == 'graded' and not self.graded_at:
            self.graded_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def passed(self):
        """Check if student passed the assignment"""
        if self.score:
            return self.score >= self.assignment.passing_score
        return False


# ==================== AUDIT LOGS ====================
class AuditLog(models.Model):
    """System audit logs for security and tracking"""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('access', 'Access'),
        ('export', 'Export'),
        ('permission_change', 'Permission Change'),
        # ── User Activity (LMS behaviour tracking) ──
        ('course_access',     'Course Access'),
        ('assignment_submit', 'Assignment Submitted'),
        ('exam_start',        'Exam Started'),
        ('exam_finish',       'Exam Finished'),
        ('level_progression', 'Level Progression'),
        ('registration',      'Course Registration'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    extra_data = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['user', 'action', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.action} - {self.model_name} - {self.timestamp}"


# ==================== BADGES ====================
class Badge(models.Model):
    """Achievement badges for students"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=50, default='award')
    color = models.CharField(max_length=20, default='gold')
    
    # Criteria
    criteria = models.TextField(help_text="Criteria to earn this badge")
    points = models.IntegerField(default=10, help_text="Points awarded for earning this badge")
    
    # Settings
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Badge'
        verbose_name_plural = 'Badges'
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class StudentBadge(models.Model):
    """Badges earned by students"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='earned_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='awarded_to')
    awarded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='badges_awarded')
    reason = models.TextField(blank=True)
    awarded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-awarded_at']
        verbose_name = 'Student Badge'
        verbose_name_plural = 'Student Badges'
        unique_together = [['student', 'badge']]
    
    def __str__(self):
        return f"{self.student.username} - {self.badge.name}"


# ==================== BLOG SYSTEM ====================
class BlogCategory(models.Model):
    """Blog category model for organizing posts"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='folder')
    color = models.CharField(max_length=20, default='blue')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Blog Category'
        verbose_name_plural = 'Blog Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_post_count(self):
        return self.blog_posts.filter(status='published').count()


class BlogPost(models.Model):
    """Main blog post model"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    subtitle = models.CharField(max_length=200, blank=True)
    
    # Content
    excerpt = models.TextField(max_length=500)
    content = models.TextField()
    
    # Categorization
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, related_name='blog_posts')
    tags = models.JSONField(default=list, blank=True)
    
    # Author & Attribution
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='blog_posts')
    author_name = models.CharField(max_length=100)
    author_title = models.CharField(max_length=100, blank=True)
    author_photo = models.ImageField(upload_to='blog/authors/', blank=True, null=True)
    author_bio = models.TextField(blank=True)
    
    # Media
    featured_image = models.ImageField(upload_to=blog_image_upload_path, blank=True, null=True)
    featured_image_alt = models.CharField(max_length=200, blank=True)
    
    # Metadata
    read_time = models.IntegerField(default=5)
    views_count = models.IntegerField(default=0)
    
    # Publishing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    publish_date = models.DateTimeField(default=timezone.now)
    
    # SEO
    meta_description = models.CharField(max_length=160, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Blog Post'
        verbose_name_plural = 'Blog Posts'
        ordering = ['-publish_date', '-created_at']
        indexes = [
            models.Index(fields=['-publish_date', 'status']),
            models.Index(fields=['slug']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            while BlogPost.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        if not self.meta_description and self.excerpt:
            self.meta_description = self.excerpt[:160]
        
        if not self.author_name and self.author:
            self.author_name = self.author.get_full_name() or self.author.username
        
        super().save(*args, **kwargs)
    
    def increment_views(self):
        """Increment view count"""
        BlogPost.objects.filter(pk=self.pk).update(views_count=models.F('views_count') + 1)
        self.refresh_from_db(fields=['views_count'])
    
    def get_related_posts(self, limit=3):
        """Get related posts from same category"""
        return BlogPost.objects.filter(
            category=self.category,
            status='published'
        ).exclude(id=self.id)[:limit]


# ==================== CERTIFICATES ====================
class Certificate(models.Model):
    """Course completion certificates — covers both LMS courses and full academic programs"""

    CERTIFICATE_TYPE_CHOICES = [
        ('lms_course', 'LMS Course'),
        ('program',    'Academic Program'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('unpaid',  'Unpaid'),
        ('paid',    'Paid'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')

    # LMS course certificate — nullable so program certs don't need a course
    course = models.ForeignKey(
        'LMSCourse', on_delete=models.CASCADE,
        related_name='certificates', null=True, blank=True
    )

    # Academic program certificate
    program = models.ForeignKey(
        'Program', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='program_certificates'
    )

    certificate_type = models.CharField(
        max_length=20, choices=CERTIFICATE_TYPE_CHOICES, default='lms_course'
    )

    certificate_id = models.CharField(max_length=50, unique=True, editable=False)

    # Certificate Details
    issued_date = models.DateField(auto_now_add=True)
    completion_date = models.DateField()
    grade = models.CharField(max_length=5, blank=True)

    # File
    certificate_file = models.FileField(upload_to=get_certificate_upload_path, blank=True, null=True)

    # Verification
    verification_code = models.UUIDField(default=uuid.uuid4, editable=False)
    is_verified = models.BooleanField(default=True)

    # Payment gate — student must pay before certificate is released
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid',
        help_text="Certificate is only downloadable once payment_status is 'paid'"
    )
    payment_reference = models.CharField(
        max_length=100, blank=True,
        help_text="FeePayment.payment_reference that settled this certificate fee"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_date']
        verbose_name = 'Certificate'
        verbose_name_plural = 'Certificates'
        indexes = [
            models.Index(fields=['certificate_id']),
            models.Index(fields=['verification_code']),
            models.Index(fields=['student', 'certificate_type']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        if self.certificate_type == 'program' and self.program:
            return f"{self.student.get_full_name()} — {self.program.name}"
        return f"{self.student.get_full_name()} — {self.course.title if self.course else 'N/A'}"

    def is_paid(self):
        """Check if certificate fee has been settled."""
        return self.payment_status == 'paid'

    def has_paid_certificate_fee(self, user):
        """Return True if the student has a successful FeePayment for a certificate fee."""
        return FeePayment.objects.filter(
            user=user,
            status='success',
            fee__purpose__icontains='certificate',
        ).exists()

    def mark_paid(self, payment_reference=''):
        """Mark this certificate as paid and store the reference."""
        self.payment_status = 'paid'
        self.payment_reference = payment_reference
        self.save(update_fields=['payment_status', 'payment_reference'])

    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = f"CERT-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)


# ==================== CONTACT ====================
class ContactMessage(models.Model):
    SUBJECT_CHOICES = [
        ('admissions', 'Admissions Inquiry'),
        ('programs', 'Program Information'),
        ('campus', 'Campus Visit'),
        ('financial', 'Financial Aid'),
        ('support', 'Technical Support'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='contact_messages',
        help_text="User who submitted this message (if logged in)"
    )
    
    name = models.CharField(max_length=200)
    email = models.EmailField()
    subject = models.CharField(max_length=50, choices=SUBJECT_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)
    responded = models.BooleanField(default=False)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='contact_responses')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'
    
    def __str__(self):
        return f"{self.name} - {self.subject} ({self.created_at.strftime('%Y-%m-%d')})"


# ==================== COURSE APPLICATION SYSTEM ====================
class Faculty(models.Model):
    name = models.CharField(max_length=200, help_text="Faculty name (e.g., Faculty of Business)")
    slug = models.SlugField(max_length=200, unique=True, help_text="URL-friendly name")
    code = models.CharField(max_length=20, unique=True, help_text="Faculty code (e.g., BUS, ENG)")
    
    # Display Information
    icon = models.CharField(max_length=50, default='graduation-cap', help_text="Lucide icon name")
    color_primary = models.CharField(max_length=20, default='orange', help_text="Primary color")
    color_secondary = models.CharField(max_length=20, default='amber', help_text="Secondary color")
    
    # Content
    tagline = models.CharField(max_length=200, help_text="Short tagline for hero section")
    description = models.TextField(help_text="Main description of the faculty")
    mission = models.TextField(blank=True, help_text="Faculty mission statement")
    vision = models.TextField(blank=True, help_text="Faculty vision statement")

    # Dean Information
    dean_name = models.CharField(max_length=100, blank=True)
    dean_role = models.CharField(max_length=100, blank=True, default='Dean')
    dean_faculty_label = models.CharField(max_length=150, blank=True)
    dean_photo = models.ImageField(upload_to='faculties/deans/', blank=True, null=True)
    
    # Media
    hero_image = models.ImageField(upload_to='faculties/heroes/', blank=True, null=True)
    about_image = models.ImageField(upload_to='faculties/about/', blank=True, null=True)

    # Gallery (carousel on faculty_detail page) — optional, up to 3 images + 1 video
    gallery_image_1 = models.ImageField(upload_to='faculties/gallery/images/', blank=True, null=True, help_text="Gallery image 1 (max 3MB)")
    gallery_image_2 = models.ImageField(upload_to='faculties/gallery/images/', blank=True, null=True, help_text="Gallery image 2 (max 3MB)")
    gallery_image_3 = models.ImageField(upload_to='faculties/gallery/images/', blank=True, null=True, help_text="Gallery image 3 (max 3MB)")
    gallery_video = models.FileField(upload_to='faculties/gallery/videos/', blank=True, null=True, help_text="Gallery video (shown first in carousel if present)")

    # Statistics
    student_count = models.IntegerField(default=0, help_text="Number of students")
    placement_rate = models.IntegerField(default=0, help_text="Career placement rate (0-100)")
    partner_count = models.IntegerField(default=0, help_text="Number of corporate partners")
    international_faculty = models.IntegerField(default=0, help_text="International faculty percentage")
    
    # Accreditation & Features
    accreditation = models.TextField(blank=True, help_text="Accreditation details")
    special_features = models.JSONField(default=list, blank=True, help_text="List of special features")
    
    # SEO
    meta_description = models.CharField(max_length=160, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Faculty'
        verbose_name_plural = 'Faculties'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class InstitutionMember(models.Model):
    """Board members and institutional staff for About page"""
    MEMBER_TYPE_CHOICES = [
        ('admin_board',      'Administrative / Management Board'),
        ('academic_board',   'Academic Board'),
        ('advisorate_board', 'Advisorate Board'),
        ('staff',            'Staff'),
    ]
    member_type   = models.CharField(max_length=30, choices=MEMBER_TYPE_CHOICES, db_index=True)
    name          = models.CharField(max_length=150)
    role          = models.CharField(max_length=200)
    photo         = models.ImageField(upload_to='institution/members/', blank=True, null=True)
    bio           = models.TextField(blank=True)
    is_active     = models.BooleanField(default=True)
    is_who_we_are = models.BooleanField(
        default=False,
        verbose_name='Show in "Who We Are"',
        help_text='Featured on the About page "Who We Are" section. Only one member may be featured at a time.',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Institution Member'
        verbose_name_plural = 'Institution Members'

    def __str__(self):
        return f'{self.name} — {self.get_member_type_display()}'

    def save(self, *args, **kwargs):
        if self.is_who_we_are:
            InstitutionMember.objects.filter(is_who_we_are=True).exclude(pk=self.pk).update(is_who_we_are=False)
        super().save(*args, **kwargs)

#################### DEPARTMENTS #####################

class Department(models.Model):
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name="departments"
    )

    name = models.CharField(
        max_length=200,
        help_text="Department name (e.g., Electrical Engineering)"
    )
    slug = models.SlugField(max_length=200, unique=True)
    code = models.CharField(
        max_length=20,
        help_text="Department code (e.g., EEE)"
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("faculty", "code")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.faculty.code})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while Department.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)



    ############################# PROGRAMS ########

# ==============================================================================
# PROGRAM
# Represents the academic qualification / degree offering within a Department.
# e.g. "BSc Computer Science", "MBA", "Diploma in Nursing"
# ==============================================================================

class Program(models.Model):

    STUDY_MODE_CHOICES = [
        ('Full Time', 'Full Time'),
        ('Part Time', 'Part Time'),
        ('Online', 'Online'),
        ('Blended', 'Blended'),
    ]

    # ── Hierarchy ──────────────────────────────────────────────────────────────
    department = models.ForeignKey(
        "Department",
        on_delete=models.CASCADE,
        related_name="programs",
        help_text="Department this program belongs to"
    )

    # ── Identity ───────────────────────────────────────────────────────────────
    name = models.CharField(
        max_length=200,
        help_text="Program name (e.g., BSc Electrical Engineering)"
    )
    slug = models.SlugField(max_length=200, unique=True)
    code = models.CharField(
        max_length=30,
        help_text="Program code (e.g., BSC-EEE)"
    )

    # ── Academic Structure ─────────────────────────────────────────────────────
    degree_level = models.CharField(
        max_length=50,
        choices=DEGREE_LEVEL_CHOICES,
        help_text="The level of qualification awarded"
    )
    duration_years = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        help_text="Total duration of the program in years (e.g., 4.0)"
    )
    credits_required = models.IntegerField(
        default=120,
        help_text="Total credit units required to complete the program"
    )
    max_credits_per_semester = models.PositiveIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Default maximum credit units per term — used for any term not overridden in credit_caps_by_term below."
    )
    credit_caps_by_term = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Optional per-term overrides, e.g. {'first': 21, 'second': 18}. "
            "A term key not present here falls back to max_credits_per_semester. "
            "Use max_credits_for_term(term) rather than reading either field directly."
        ),
    )
    min_cgpa_to_progress = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Minimum cumulative GPA (5-point scale) required to advance to the next year of study"
    )
    available_study_modes = models.JSONField(
        default=list,
        blank=True,
        help_text="Study modes available: full_time, part_time, online, blended"
    )
    max_students = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum student capacity per intake (leave blank for unlimited)"
    )

    # ── Marketing / Display Content ────────────────────────────────────────────
    tagline = models.CharField(
        max_length=200,
        blank=True,
        help_text="Short marketing tagline shown on program cards and hero sections"
    )
    overview = models.TextField(
        blank=True,
        help_text="Short overview paragraph (used on listing pages)"
    )
    description = models.TextField(
        blank=True,
        help_text="Full program description (used on detail page)"
    )

    # ── Curriculum ─────────────────────────────────────────────────────────────
    entry_requirements = models.JSONField(
        default=list,
        blank=True,
        help_text="List of admission/entry requirements"
    )
    core_courses = models.JSONField(
        default=list,
        blank=True,
        help_text="List of compulsory course names/codes in this program"
    )
    specialization_tracks = models.JSONField(
        default=list,
        blank=True,
        help_text="List of available specialization tracks or majors"
    )

    # ── Outcomes & Career ──────────────────────────────────────────────────────
    learning_outcomes = models.JSONField(
        default=list,
        blank=True,
        help_text="What graduates will know and be able to do"
    )
    career_paths = models.JSONField(
        default=list,
        blank=True,
        help_text="Typical careers graduates pursue"
    )

    # ── Financial ──────────────────────────────────────────────────────────────
    # application_fee lives on CourseIntake now — it varies per intake period,
    # not per program.
    tuition_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Tuition fee per academic year"
    )

    # ── Media ──────────────────────────────────────────────────────────────────
    hero_image = models.ImageField(
        upload_to='programs/heroes/',
        blank=True,
        null=True,
        help_text="Hero/banner image for the program detail page"
    )

    # Gallery (carousel on program_detail page) — optional, up to 3 images + 1 video
    gallery_image_1 = models.ImageField(upload_to='programs/gallery/images/', blank=True, null=True, help_text="Gallery image 1 (max 3MB)")
    gallery_image_2 = models.ImageField(upload_to='programs/gallery/images/', blank=True, null=True, help_text="Gallery image 2 (max 3MB)")
    gallery_image_3 = models.ImageField(upload_to='programs/gallery/images/', blank=True, null=True, help_text="Gallery image 3 (max 3MB)")
    gallery_video = models.FileField(upload_to='programs/gallery/videos/', blank=True, null=True, help_text="Gallery video (shown first in carousel if present)")

    # ── SEO ────────────────────────────────────────────────────────────────────
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO meta description (max 160 characters)"
    )
    meta_keywords = models.CharField(
        max_length=255,
        blank=True,
        help_text="SEO meta keywords (comma separated)"
    )

    # ── Status & Display ───────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("department", "code")
        ordering = ["created_at"]  # as uploaded — oldest first
        verbose_name = "Program"
        verbose_name_plural = "Programs"
        indexes = [
            models.Index(fields=["department", "is_active"]),
            models.Index(fields=["degree_level"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while Program.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    # ── Convenience Properties ─────────────────────────────────────────────────
    @property
    def faculty(self):
        """Access faculty directly without storing a redundant FK."""
        return self.department.faculty

    def get_active_courses(self):
        """Return all active courses under this program."""
        return self.courses.filter(is_active=True).order_by('year_of_study', 'semester', 'display_order')

    def get_total_credit_units(self):
        """Sum of credit units across all active courses."""
        return self.courses.filter(is_active=True).aggregate(
            total=models.Sum('credit_units')
        )['total'] or 0

    def max_credits_for_term(self, term, session=None):
        """
        The credit-unit cap for one (term[, session]) pair — the single
        source of truth every registration-cap check should call instead of
        reading max_credits_per_semester/credit_caps_by_term/
        ProgramSessionCreditCap directly. Three-tier fallback, most specific
        first:

          1. ProgramSessionCreditCap for this exact (program, session, term)
             — pass `term` RAW here, exactly as the session itself names it
             (e.g. a session that defines a real 'third' term must be looked
             up as 'third', not pre-collapsed to 'second' — otherwise a cap
             set for that specific session/term could never be found).
          2. credit_caps_by_term[term] — a program-wide default for that
             *canonical* term name (first/second/annual), shared across
             every session that uses it. `term` is normalised via
             TERM_NORMALISATION_MAP for this tier only, since that dict was
             only ever keyed by the three canonical names.
          3. max_credits_per_semester — the final fallback.

        `session=None` skips tier 1 entirely (e.g. no specific session in
        context yet) and falls straight to tiers 2/3.
        """
        if session is not None and term:
            override = (
                self.session_credit_caps
                .filter(session=session, term=str(term).strip().lower())
                .values_list('max_credit_units', flat=True)
                .first()
            )
            if override is not None:
                return override

        if term and isinstance(self.credit_caps_by_term, dict):
            normalised = TERM_NORMALISATION_MAP.get(str(term).strip().lower(), str(term).strip().lower())
            fallback = self.credit_caps_by_term.get(normalised)
            if fallback is not None:
                return fallback

        return self.max_credits_per_semester

    def get_current_intake(self):
        """
        The CourseIntake a new application against this program should be
        attributed to — and therefore whose application_fee it should be
        charged. Prefers the active intake whose application window hasn't
        closed yet (earliest deadline first, so the intake that's actually
        closing soonest wins over one further out); falls back to the most
        recent intake overall so payment isn't left with nothing to charge
        just because staff forgot to keep deadlines current.
        """
        today = timezone.now().date()
        open_intake = (
            self.intakes
            .filter(is_active=True, application_deadline__gte=today)
            .order_by('application_deadline')
            .first()
        )
        if open_intake:
            return open_intake
        return self.intakes.filter(is_active=True).order_by('-year', 'intake_period').first()

# ==============================================================================
# ACADEMIC SESSION
# Represents a single academic year and its semester breakdown.
# e.g. "2024/2025" with First Semester: Sep–Jan, Second Semester: Feb–Jun
# ==============================================================================

class AcademicSession(models.Model):

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('active',   'Active'),
        ('closed',   'Closed'),
    ]

    # ── Identity ───────────────────────────────────────────────────────────
    name = models.CharField(
        max_length=20,
        unique=True,
        help_text="Academic year label (e.g., 2024/2025)"
    )

    TERM_CHOICES = [
        ('first',  'First Semester'),
        ('second', 'Second Semester'),
        ('third',  'Third Semester / Harmattan'),
        ('annual', 'Annual'),
        ('fall',   'Fall'),
        ('spring', 'Spring'),
        ('summer', 'Summer'),
    ]

    # ── Semester / Term Date Ranges ────────────────────────────────────────
    # Store as JSON list so the session can have 2, 3, or custom terms.
    # Format: [{"term": "first", "start": "2025-09-01", "end": "2026-01-31"}, ...]
    term_dates = models.JSONField(
        default=list,
        help_text=(
            'List of term windows. Each item: '
            '{"term": "first|second|third|fall|spring|summer", '
            '"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}'
        )
    )

    # ── Status ─────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='upcoming',
        help_text="Only one session should be 'active' at a time"
    )
    is_current = models.BooleanField(
        default=False,
        help_text="Mark this as the current running session"
    )

    REGISTRATION_OVERRIDE_CHOICES = [
        ('auto',   'Automatic (3-week window from term start)'),
        ('open',   'Force Open'),
        ('closed', 'Force Closed'),
    ]
    registration_override = models.CharField(
        max_length=10,
        choices=REGISTRATION_OVERRIDE_CHOICES,
        default='auto',
        help_text=(
            "Overrides the automatic 3-week registration window. Use 'Force Open' "
            "when a session is activated after its term's computed window has "
            "already elapsed (e.g. after end-of-session progression runs late)."
        )
    )

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-name']
        verbose_name = 'Academic Session'
        verbose_name_plural = 'Academic Sessions'
        indexes = [
            models.Index(fields=['is_current']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicSession.objects.exclude(pk=self.pk).update(is_current=False)
            if not self.status or self.status == 'upcoming':
                self.status = 'active'
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls):
        """Fetch the active session."""
        return cls.objects.filter(is_current=True).first()

    def get_current_term(self):
        """
        Return the term key whose date window contains today.
        Derived purely from term_dates — no override field needed.
        e.g. term_dates = [
            {"term": "first",  "start": "2025-09-01", "end": "2026-01-31"},
            {"term": "second", "start": "2026-02-01", "end": "2026-06-30"},
        ]
        """
        from datetime import date
        today = timezone.now().date()
        for entry in self.term_dates:
            try:
                start = date.fromisoformat(entry['start'])
                end   = date.fromisoformat(entry['end'])
                if start <= today <= end:
                    return entry['term']
            except (KeyError, ValueError):
                continue
        return None

    def get_registration_window(self, term=None):
        """
        Return (reg_open, reg_close) for the given term (defaults to
        get_current_term).  Registration opens on the first day of the
        term and closes 21 days later (3-week window).

        Returns (None, None) if the term is not found in term_dates.
        """
        from datetime import date, timedelta
        target = term or self.get_current_term()
        if not target:
            return (None, None)
        for entry in self.term_dates:
            if entry.get('term') == target:
                try:
                    reg_open  = date.fromisoformat(entry['start'])
                    reg_close = reg_open + timedelta(days=21)
                    return (reg_open, reg_close)
                except (KeyError, ValueError):
                    return (None, None)
        return (None, None)

    @property
    def is_registration_open(self):
        """
        True when today falls inside the 3-week registration window of
        whichever term is currently running, unless an admin has set an
        explicit `registration_override`.

        The computed window alone has a real operational gap: a session
        is often activated (`is_current=True`) some time after its
        term_dates were originally configured — e.g. right after an
        end-of-session progression run — by which point the computed
        3-week window may have already elapsed, permanently locking out
        registration for the whole term with no way to recover short of
        editing term_dates. `registration_override` gives admins (and
        `academic_session_set_current`, which auto-opens it when needed)
        an explicit escape hatch that takes precedence over the date math.
        """
        if self.registration_override == 'open':
            return True
        if self.registration_override == 'closed':
            return False

        reg_open, reg_close = self.get_registration_window()
        if reg_open is None:
            return False
        today = timezone.now().date()
        return reg_open <= today <= reg_close

    @property
    def available_study_modes_display(self):
        """
        Human-readable labels for available_study_modes.

        available_study_modes is a JSONField storing a list of raw choice
        keys (e.g. "full_time"), so Django's automatic get_FOO_display()
        doesn't apply here the way it would for a plain CharField(choices=...)
        — that only covers single-value fields. Templates were previously
        piping the raw key through the |title filter, which produced
        "Full_Time" instead of "Full Time" since |title doesn't treat
        underscores as word breaks. Use this property instead.
        """
        labels = dict(self.STUDY_MODE_CHOICES)
        return [labels.get(mode, mode.replace('_', ' ').title()) for mode in (self.available_study_modes or [])]

    def registration_window_for_term(self, term):
        """
        Convenience: human-readable window string for a specific term.
        Useful in admin list_display or template tags.
        e.g. "01 Sep 2025 – 22 Sep 2025"
        """
        reg_open, reg_close = self.get_registration_window(term=term)
        if reg_open and reg_close:
            return f"{reg_open.strftime('%d %b %Y')} – {reg_close.strftime('%d %b %Y')}"
        return "—"


class ProgramSessionCreditCap(models.Model):
    """
    The most specific tier of the credit-unit cap hierarchy — one row per
    (program, session, term), letting an admin set a genuinely different
    cap for the same program in different academic sessions (e.g. a
    curriculum that allows more CU per term starting a given year), and
    following whatever term structure that particular session actually
    has (two terms one year, three the next — the number of rows for a
    session is however many terms its own `term_dates` defines, not a
    fixed enum).

    Lookup order (see Program.max_credits_for_term):
      1. This model — most specific, per (program, session, term).
      2. Program.credit_caps_by_term[term] — a program-wide default for
         that term name, shared across every session that uses it.
      3. Program.max_credits_per_semester — the final fallback.
    """
    program = models.ForeignKey(
        'Program', on_delete=models.CASCADE, related_name='session_credit_caps',
    )
    session = models.ForeignKey(
        'AcademicSession', on_delete=models.CASCADE, related_name='program_credit_caps',
    )
    term = models.CharField(
        max_length=20,
        help_text="Term key matching one of this session's term_dates entries (e.g. 'first', 'second', 'third').",
    )
    max_credit_units = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(30)],
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        unique_together = [['program', 'session', 'term']]
        ordering = ['session__name', 'term']
        verbose_name = 'Program Session Credit Cap'
        verbose_name_plural = 'Program Session Credit Caps'

    def __str__(self):
        return f"{self.program.code} — {self.session} — {self.term}: {self.max_credit_units} CU"


class Course(models.Model):

    COURSE_TYPE_CHOICES = [
        ('core', 'Core'),
        ('elective', 'Elective'),
        ('general', 'General Studies'),
        ('prerequisite', 'Prerequisite'),
    ]

    SEMESTER_CHOICES = [
        ('first', 'First Semester'),
        ('second', 'Second Semester'),
        ('annual', 'Annual'),
    ]

    # ── Hierarchy ──────────────────────────────────────────────────────────────
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="courses",
        help_text="Program this course belongs to"
    )

    # ── Identity ───────────────────────────────────────────────────────────────
    name = models.CharField(max_length=200, help_text="Course name")
    slug = models.SlugField(max_length=200, unique=True)
    code = models.CharField(max_length=20, help_text="Course code (e.g., CS101)")

    # ── Academic Structure ─────────────────────────────────────────────────────
    course_type = models.CharField(
        max_length=20,
        choices=COURSE_TYPE_CHOICES,
        default='core',
        help_text="Whether this is a core requirement, elective, or general studies unit"
    )
    credit_units = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Credit units this course carries"
    )

    # ── Assessment weighting ───────────────────────────────────────────────────
    # Used to blend exam/quiz/assignment scores into one CourseGrade. Weights
    # of assessment types with no recorded data for a student are dropped and
    # the remaining weights re-normalized, so an exam-only course still grades
    # out of 100% from its exam component alone.
    exam_weight_pct = models.PositiveSmallIntegerField(
        default=70,
        validators=[MaxValueValidator(100)],
        help_text="Weight of the end-of-semester exam in the final course grade (%)"
    )
    quiz_weight_pct = models.PositiveSmallIntegerField(
        default=15,
        validators=[MaxValueValidator(100)],
        help_text="Weight of quiz scores in the final course grade (%)"
    )
    assignment_weight_pct = models.PositiveSmallIntegerField(
        default=15,
        validators=[MaxValueValidator(100)],
        help_text="Weight of assignment scores in the final course grade (%)"
    )

    year_of_study = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Which year of the program this course is taught in (e.g., 1, 2, 3)"
    )
    semester = models.CharField(
        max_length=20,
        choices=SEMESTER_CHOICES,
        default='first',
        help_text="Which semester this course runs in"
    )

    # ── Prerequisites ──────────────────────────────────────────────────────────
    prerequisites = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='prerequisite_for',
        help_text="Courses that must be passed before registering for this one"
    )

    # ── Content ────────────────────────────────────────────────────────────────
    description = models.TextField(
        blank=True,
        help_text="What this course covers"
    )
    learning_outcomes = models.JSONField(
        default=list,
        blank=True,
        help_text="Specific learning outcomes for this course unit"
    )

    # ── Display ────────────────────────────────────────────────────────────────
    # icon = models.CharField(
    #     max_length=50,
    #     default='book-open',
    #     help_text="Lucide icon name for display"
    # )
    # color_primary = models.CharField(max_length=20, default='blue')
    # color_secondary = models.CharField(max_length=20, default='cyan')

    # ── Status & Display ───────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    # display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['program', 'code']]
        ordering = ['year_of_study', 'semester', 'name']
        verbose_name = 'Course'
        verbose_name_plural = 'Courses'
        indexes = [
            models.Index(fields=['program', 'is_active']),
            models.Index(fields=['year_of_study', 'semester']),
            models.Index(fields=['course_type']),
            models.Index(fields=['course_type', 'year_of_study']),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")
            original_slug = self.slug
            counter = 1
            while Course.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    # ── Convenience Properties ─────────────────────────────────────────────────
    @property
    def level(self):
        """Nigerian level system: year 1 → 100, year 2 → 200 ... year 8 → 800."""
        return self.year_of_study * 100

    @property
    def department(self):
        return self.program.department

    @property
    def faculty(self):
        return self.program.department.faculty

class AllRequiredPayments(models.Model):
    WHO_TO_PAY_CHOICES = [
        ("student", "Student"),
        ("staff", "Staff"),
        ("applicant", "Applicant"),
        ("other", "Other"),
    ]
    
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="required_payments",
        help_text="Program this payment applies to"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="required_payments",
        help_text="Scope this payment to a specific course (optional)"
    )
    # Correct — proper FK reference
    academic_session = models.ForeignKey(
        'AcademicSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='required_payments'
    )
    semester = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('first', 'First Semester'), ('second', 'Second Semester'),
            ('third', 'Third Semester'), ('annual', 'Annual'),
            ('fall', 'Fall'), ('spring', 'Spring'), ('summer', 'Summer'),
        ],
        default='annual'
    )

    purpose = models.CharField(
        max_length=255,
        help_text="Purpose of the payment (e.g., School Fees, Library Fees)"
    )

    who_to_pay = models.CharField(
        max_length=20,
        choices=WHO_TO_PAY_CHOICES,
        default="student"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount to be paid"
    )
    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="ISO 4217 currency code e.g. USD, GBP, EUR"
    )

    level = models.IntegerField(
        choices=STUDENT_LEVEL_CHOICES,
        null=True,
        blank=True,
        help_text="Student level this fee applies to (100–800). Leave blank to apply to ALL levels."
    )

    due_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(
        default=True,
        help_text="Controls visibility of this payment"
    )

    class Meta:
        verbose_name = "Required Payment"
        verbose_name_plural = "All Required Payments"
        ordering = ["-created_at"]
        unique_together = [['program', 'academic_session', 'purpose', 'semester', 'level']]

    def __str__(self):
        session = self.academic_session.name if self.academic_session else 'No Session'
        program = self.program.code if self.program else 'All Programs'
        return f"{self.purpose} - {program} ({session})"

    @property
    def faculty(self):
        return self.program.department.faculty if self.program else None

    @property
    def department(self):
        return self.program.department if self.program else None


class CourseIntake(models.Model):
    """Course intake periods"""
    INTAKE_PERIOD_CHOICES = [
        ('january', 'January'),
        ('may', 'May'),
        ('september', 'September'),
    ]
    
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='intakes')
    intake_period = models.CharField(max_length=20, choices=INTAKE_PERIOD_CHOICES)
    year = models.IntegerField()
    application_start_date = models.DateField(
        null=True, blank=True,
        help_text="When applications open for this intake"
    )
    start_date = models.DateField(help_text="Program start date for this intake")
    application_deadline = models.DateField(help_text="Application closing date for this intake")
    application_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Fee to apply for this specific intake"
    )
    available_slots = models.IntegerField(default=50, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-year', 'intake_period']
        verbose_name = 'Course Intake'
        verbose_name_plural = 'Course Intakes'
        unique_together = [['program', 'intake_period', 'year']]
    
    @cached_property
    def accepted_count(self):
        """
        Number of approved applications for this intake. cached_property,
        not plain @property: remaining_slots and is_full each read this too,
        and intakes_list.html calls is_full twice per row — without caching
        that's 4 separate COUNT queries per intake (measured: 80 queries for
        a 20-row page). A filtered .count() also can't use the view's
        .prefetch_related('applications') — that only helps a plain
        .all() iteration, not an aggregate — so caching on the instance is
        the fix here, not prefetching harder. Safe within a request: nothing
        in this codebase creates an application against an intake and then
        re-checks these on that same already-loaded instance.
        """
        return self.applications.filter(status='approved').count()

    @property
    def remaining_slots(self):
        """available slots minus accepted applicants."""
        return max(0, self.available_slots - self.accepted_count)

    @property
    def is_full(self):
        """true when no slots remain."""
        return self.accepted_count >= self.available_slots

    def __str__(self):
        return f"{self.program.name} - {self.intake_period.title()} {self.year}"


class CourseApplication(models.Model):
    """Student application for courses"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_payment', 'Pending Payment'),
        ('payment_complete', 'Payment Complete'),
        ('under_review', 'Under Review'),
        ('documents_uploaded', 'Documents Uploaded'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    LANGUAGE_CHOICES = [
        ('toefl', 'TOEFL'),
        ('ielts', 'IELTS'),
        ('pte', 'PTE Academic'),
        ('duolingo', 'Duolingo English Test'),
        ('cambridge', 'Cambridge English'),
        ('none', 'None'),
    ]
    
    # Application ID
    application_id = models.CharField(max_length=20, unique=True, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications', null=True, blank=True)
    
    # Course & Session & Level
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='applications')
    academic_session = models.ForeignKey('AcademicSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    intake = models.ForeignKey(
        'CourseIntake', on_delete=models.SET_NULL, null=True, blank=True, related_name='applications',
        help_text="Which intake period this application is for, if known."
    )
    entry_level = models.IntegerField(
        null=True, blank=True,
        help_text="Entry level e.g. 100, 200, 300 etc."
    )
    study_mode = models.CharField(max_length=20, choices=Program.STUDY_MODE_CHOICES)
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    nationality = models.CharField(max_length=100)

    payment_status = models.CharField(max_length=20, default='pending')
    
    # Address
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    
    # Academic Background
    highest_qualification = models.CharField(max_length=100)
    institution_name = models.CharField(max_length=200)
    graduation_year = models.TextField()
    gpa_or_grade = models.CharField(max_length=20)
    language_skill = models.CharField(max_length=20, choices=LANGUAGE_CHOICES,blank=True, null=True)
    language_score = models.DecimalField(max_digits=5,decimal_places=2,blank=True,null=True,help_text="Enter test score (e.g. 7.5 for IELTS, 95 for TOEFL)")
    
    # Additional Information
    work_experience_years = models.IntegerField(default=0)
    personal_statement = models.TextField()
    how_did_you_hear = models.CharField(max_length=100, blank=True)
    scholarship = models.BooleanField(default=False)
    # Privacy & Consent
    accept_privacy_policy = models.BooleanField(default=False)
    accept_terms_conditions = models.BooleanField(default=False)
    marketing_consent = models.BooleanField(default=False)

    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=100)
    emergency_contact_phone = models.CharField(max_length=20)
    emergency_contact_relationship = models.CharField(max_length=50)
    
    # Application Status
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_applications')
    review_notes = models.TextField(blank=True)
    
    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    in_processing = models.BooleanField(default=False)
    how_did_you_hear_other = models.CharField(max_length=255, blank=True)
    emergency_contact_email = models.EmailField(blank=True, null=True)
    emergency_contact_address = models.CharField(max_length=255, blank=True)

    # Admission Acceptance Tracking
    admission_accepted = models.BooleanField(
        default=False,
        help_text="Student accepted the admission offer"
    )
    admission_accepted_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Date when student accepted admission"
    )
    admission_number = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="Unique admission number issued to student"
    )
    department_approved = models.BooleanField(
        default=False,
        help_text="Department head approved the admission"
    )
    department_approved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    department_approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='department_approved_applications'
    )

    # Graduation tracking
    is_graduated = models.BooleanField(
        default=False,
        help_text="Student has completed all program requirements and graduated"
    )
    graduated_at = models.DateField(
        null=True, blank=True,
        help_text="Date graduation was confirmed"
    )
    graduated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='graduations_confirmed'
    )

    # Transcript tracking
    transcript_requested = models.BooleanField(
        default=False,
        help_text="Student has formally requested their academic transcript"
    )
    transcript_issued = models.BooleanField(
        default=False,
        help_text="Transcript has been generated and made available to the student"
    )
    transcript_issued_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the transcript was issued"
    )
    transcript_issued_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transcripts_issued',
        help_text="Staff member who issued this transcript"
    )
    transcript_snapshot = models.JSONField(
        null=True, blank=True, encoder=DjangoJSONEncoder,
        help_text=(
            "Frozen copy of the student's grade record, captured the moment "
            "transcript_requested is set. Once requested, the transcript view "
            "renders this locked snapshot instead of live CourseGrade data, so "
            "results recorded afterwards can't silently change an already-"
            "requested transcript."
        )
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Course Application'
        verbose_name_plural = 'Course Applications'
        indexes = [
            models.Index(fields=['application_id']),
            models.Index(fields=['email']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['email', 'program'], name='unique_application_email_per_program'),
        ]
    
    def __str__(self):
        return f"{self.application_id} - {self.first_name} {self.last_name}"

    def resolve_intake(self):
        """
        Attribute this application to a CourseIntake, and return it. Set at
        the point `program` is assigned/changed (see eduweb.views.apply) so
        that everything downstream — the fee charged, the deadline shown —
        is pinned to one specific intake instead of drifting with whichever
        intake happens to look "current" whenever it's next read. Safe to
        call again later; it's a no-op once `intake` is already set.
        """
        if self.intake_id:
            return self.intake
        if not self.program_id:
            return None
        intake = self.program.get_current_intake()
        if intake:
            self.intake = intake
        return intake

    @property
    def application_fee(self):
        """
        The fee this application should be charged — from its resolved
        intake, not the program (fees vary per intake period). Falls back
        to 0 rather than raising if somehow no intake could be resolved,
        since callers computing a payment amount should treat that as "not
        chargeable yet" rather than crash.
        """
        intake = self.intake or self.resolve_intake()
        return intake.application_fee if intake else Decimal('0.00')

    @property
    def is_paid(self):
        """
        For free-flow applications, all statuses beyond draft are treated as paid.
        This property is kept for backward compatibility with templates.
        """
        # Free flow: draft and above are all "unlocked"
        #if self.status in ['draft', 'payment_complete', 'documents_uploaded', 'under_review', 'approved', 'rejected']:
         #   return True
        # Legacy fallback: check actual payment record if status is pending_payment
        try:
            return self.payment_status == 'success'
        except Exception:
            return False

    def can_upload_documents(self):
        """Check if application allows document uploads (payment-free flow)"""
        allowed_statuses = ['draft', 'payment_complete', 'documents_uploaded', 'under_review']
        return self.status in allowed_statuses

    def can_submit(self):
        """Check if application can be submitted"""
        allowed_statuses = ['draft', 'payment_complete', 'documents_uploaded']
        has_documents = self.documents.exists()
        return has_documents and self.status in allowed_statuses
    
    def mark_as_submitted(self):
        """Mark application as submitted"""
        if self.can_submit():
            self.status = 'under_review'
            self.submitted_at = timezone.now()
            self.save(update_fields=['status', 'submitted_at'])
            return True
        return False

    def accept_admission(self):
        """Student accepts admission offer"""
        if self.status == 'approved' and not self.admission_accepted:
            self.admission_accepted = True
            self.admission_accepted_at = timezone.now()
            self.save(
                update_fields=[
                    'admission_accepted', 
                    'admission_accepted_at'
                ]
            )
            return True
        return False

    def issue_admission_number(self):
        """Generate and assign admission number"""
        if not self.admission_number and self.admission_accepted:
            year = timezone.now().year
            # Generate unique admission number
            self.admission_number = (
                f"ADM-{year}-{uuid.uuid4().hex[:8].upper()}"
            )
            self.save(update_fields=['admission_number'])
            return True
        return False

    # ── Matric number format — CHANGE THE FORMAT HERE, NOWHERE ELSE ─────────
    # Computed on the fly from admission_number (never stored), so editing
    # these two constants + the matric_number property below instantly
    # changes what every student sees, with no migration/backfill needed.
    MATRIC_NUMBER_MAX_LENGTH = 15
    MATRIC_NUMBER_MIN_UNIQUE_CHARS = 4  # never shrink the unique tail below this

    @property
    def matric_number(self):
        """
        Student matriculation number: '{DEPT_CODE}-{YEAR}-{UNIQUE}', derived
        from admission_number (e.g. 'ADM-2026-10DEBA33') by swapping the
        'ADM' prefix for the student's department code, capped at
        MATRIC_NUMBER_MAX_LENGTH characters total.

        Reuses the year and unique hex tail already embedded in
        admission_number rather than generating new ones, so this always
        matches the admission record it's derived from and never needs its
        own DB column. Returns None until admission_number exists.

        An unusually long department code eats into the unique tail first
        down to MATRIC_NUMBER_MIN_UNIQUE_CHARS (keeping numbers readable),
        and only truncates the whole string as a last-resort safety net.
        """
        if not self.admission_number:
            return None

        department = self.program.department if self.program_id else None
        dept_code = ((department.code if department else '') or 'GEN').strip().upper()

        parts = self.admission_number.split('-')
        if len(parts) >= 3:
            year, unique = parts[1], parts[-1]
        else:
            # Unexpected admission_number shape — fall back gracefully
            # rather than raising.
            year, unique = str(timezone.now().year), self.admission_number[-8:]

        fixed_length = len(dept_code) + len(year) + 2  # +2 for the two hyphens
        unique_budget = max(
            self.MATRIC_NUMBER_MIN_UNIQUE_CHARS,
            self.MATRIC_NUMBER_MAX_LENGTH - fixed_length,
        )
        unique = unique[:unique_budget]

        matric = f"{dept_code}-{year}-{unique}"
        return matric[:self.MATRIC_NUMBER_MAX_LENGTH]

    def can_access_student_portal(self):
        """Check if student can access student dashboard"""
        return (
            self.status == 'approved' and
            self.admission_accepted and
            self.admission_number and
            self.department_approved and
            self.is_paid
        )

    def get_full_name(self):
        """Return applicant's full name"""
        return f"{self.first_name} {self.last_name}" 

    def has_completed_program(self):
        required_courses = Course.objects.filter(
            program=self.program,
            course_type='core',
            is_active=True,
        )
        if not required_courses.exists():
            return False

        # result_status='released' — an unpublished pass shouldn't be able to
        # auto-graduate a student (and issue a Certificate) before the
        # registrar has actually approved that result. See publish_results().
        passed_course_ids = CourseGrade.objects.filter(
            student=self.user,
            course__program=self.program,
            is_passed=True,
            result_status='released',
        ).values_list('course_id', flat=True)

        return all(c.id in passed_course_ids for c in required_courses)

    def award_program_certificate(self, confirmed_by=None):
        if not self.has_completed_program():
            return None

        existing = Certificate.objects.filter(
            student=self.user,
            program=self.program,
            certificate_type='program',
        ).first()
        if existing:
            return existing

        from django.utils import timezone as tz
        self.is_graduated = True
        self.graduated_at = tz.now().date()
        if confirmed_by:
            self.graduated_by = confirmed_by
        self.save(update_fields=['is_graduated', 'graduated_at', 'graduated_by'])

        return Certificate.objects.create(
            student=self.user,
            program=self.program,
            certificate_type='program',
            completion_date=self.graduated_at,
            payment_status='unpaid',
        )
    
    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = f"APP-{uuid.uuid4().hex[:12].upper()}"
        
        if self.status == 'under_review' and not self.reviewed_at:
            self.reviewed_at = timezone.now()
        
        super().save(*args, **kwargs)


class ApplicationDocument(models.Model):
    """Documents uploaded for course application"""
    FILE_TYPE_CHOICES = [
        ('transcript', 'Academic Transcript'),
        ('certificate', 'Certificate/Diploma'),
        ('id_document', 'ID Document'),
        ('passport', 'Passport'),
        ('cv', 'CV/Resume'),
        ('recommendation', 'Recommendation Letter'),
        ('other', 'Other'),
    ]
    
    application = models.ForeignKey(CourseApplication, on_delete=models.CASCADE, related_name='documents')
    file_type = models.CharField(max_length=30, choices=FILE_TYPE_CHOICES)
    file = models.FileField(upload_to='applications/documents/')
    original_filename = models.CharField(max_length=255)
    file_size = models.IntegerField(help_text="File size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Application Document'
        verbose_name_plural = 'Application Documents'
    
    def __str__(self):
        return f"{self.application.application_id} - {self.get_file_type_display()}"
    
    def get_file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class ApplicationPayment(models.Model):
    """Payment for course application"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    
    application = models.OneToOneField(CourseApplication, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES)
    payment_reference = models.CharField(max_length=100, unique=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_metadata = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Application Payment'
        verbose_name_plural = 'Application Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Payment for {self.application.application_id} - {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.payment_reference:
            self.payment_reference = f"PAY-{uuid.uuid4().hex[:12].upper()}"
        
        if not self.amount:
            self.amount = self.application.application_fee
        
        if self.status == 'success' and not self.paid_at:
            self.paid_at = timezone.now()
        
        super().save(*args, **kwargs)
        
        if self.status == 'success' and self.paid_at:
            if self.application.status in ['draft', 'pending_payment']:
                self.application.status = 'payment_complete'
                self.application.save(update_fields=['status'])


# ==================== COURSE CATEGORIES ====================
class CourseCategory(models.Model):
    """Categories for LMS courses"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='folder')
    color = models.CharField(max_length=20, default='blue')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Course Category'
        verbose_name_plural = 'Course Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ==================== DISCUSSIONS ====================
class Discussion(models.Model):
    """Course discussion forum topics"""
    course = models.ForeignKey('LMSCourse', on_delete=models.CASCADE, null=True, blank=True, related_name='discussions')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='discussions_started')
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    views_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_pinned', '-created_at']
        verbose_name = 'Discussion'
        verbose_name_plural = 'Discussions'
        unique_together = [['course', 'slug']]
        indexes = [
            models.Index(fields=['course', '-created_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class DiscussionReply(models.Model):
    """Replies to discussion topics"""
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='discussion_replies')
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='child_replies')
    is_solution = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = 'Discussion Reply'
        verbose_name_plural = 'Discussion Replies'
    
    def __str__(self):
        return f"Reply by {self.author.username} on {self.discussion.title}"


# ==================== ENROLLMENTS ====================
class Enrollment(models.Model):
    """Student enrollment in LMS courses"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
        ('suspended', 'Suspended'),
    ]
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey('LMSCourse', on_delete=models.CASCADE, related_name='enrollments')
    enrolled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='enrollments_created')
    
    # Progress
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, validators=[MinValueValidator(0), MaxValueValidator(100)])
    completed_lessons = models.IntegerField(default=0)
    
    # Grading
    current_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Timestamps
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-enrolled_at']
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
        unique_together = [['student', 'course']]
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['course', 'status']),
        ]
    
    def __str__(self):
        return f"{self.student.username} - {self.course.title}"
    
    def update_progress(self):
        """Calculate and update progress percentage"""
        total_lessons = self.course.lessons.filter(is_active=True).count()
        if total_lessons > 0:
            completed = LessonProgress.objects.filter(
                enrollment=self,
                is_completed=True
            ).count()
            self.completed_lessons = completed
            self.progress_percentage = (completed / total_lessons) * 100
            
            # Mark as completed if all lessons done
            if self.progress_percentage >= 100 and self.status == 'active':
                self.status = 'completed'
                self.completed_at = timezone.now()
            
            self.save(update_fields=['progress_percentage', 'completed_lessons', 'status', 'completed_at'])


# ==================== HELPDESK / SUPPORT TICKETS ====================
class SupportTicket(models.Model):
    """Support tickets for student/user assistance"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('waiting_response', 'Waiting for Response'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    CATEGORY_CHOICES = [
        ('technical', 'Technical Issue'),
        ('account', 'Account Access'),
        ('course', 'Course Content'),
        ('payment', 'Payment/Billing'),
        ('other', 'Other'),
    ]
    
    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Support Ticket'
        verbose_name_plural = 'Support Tickets'
        indexes = [
            models.Index(fields=['ticket_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.ticket_id} - {self.subject}"
    
    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = f"TKT-{uuid.uuid4().hex[:10].upper()}"
        
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        
        super().save(*args, **kwargs)


class TicketReply(models.Model):
    """Replies to support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ticket_replies')
    message = models.TextField()
    is_internal_note = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = 'Ticket Reply'
        verbose_name_plural = 'Ticket Replies'
    
    def __str__(self):
        return f"Reply by {self.author.username} on {self.ticket.ticket_id}"


# ==================== INVOICES ====================
class Invoice(models.Model):
    """Invoices for course payments"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    course = models.ForeignKey('LMSCourse', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    # Financial Details
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Dates
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issue_date']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"{self.invoice_number} - {self.student.username}"
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{uuid.uuid4().hex[:12].upper()}"
        
        # Calculate tax amount
        self.tax_amount = (self.subtotal * self.tax_rate) / 100
        
        # Calculate total
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        
        # Update paid date
        if self.status == 'paid' and not self.paid_date:
            self.paid_date = timezone.now().date()
        
        super().save(*args, **kwargs)


# ==================== LESSON PROGRESS ====================
class LessonProgress(models.Model):
    """Track student progress through lessons"""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey('Lesson', on_delete=models.CASCADE, related_name='student_progress')
    
    # Progress tracking
    is_completed = models.BooleanField(default=False)
    completion_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, validators=[MinValueValidator(0), MaxValueValidator(100)])
    time_spent_minutes = models.IntegerField(default=0)
    
    # Video progress (if applicable)
    video_progress_seconds = models.IntegerField(default=0)
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['lesson__display_order']
        verbose_name = 'Lesson Progress'
        verbose_name_plural = 'Lesson Progress'
        unique_together = [['enrollment', 'lesson']]
        indexes = [
            models.Index(fields=['enrollment', 'is_completed']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.student.username} - {self.lesson.title} - {self.completion_percentage}%"
    
    def save(self, *args, **kwargs):
        if not self.started_at:
            self.started_at = timezone.now()
        
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
            self.completion_percentage = 100.00
        
        super().save(*args, **kwargs)
        
        # Update enrollment progress
        if self.is_completed:
            self.enrollment.update_progress()


# ==================== LMS COURSES ====================
class LMSCourse(models.Model):
    """Learning Management System courses (actual learning content)"""
    
    # Basic Information
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    # category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='lms_courses')
    
    # Content
    short_description = models.TextField(max_length=500)
    description = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list)
    prerequisites = models.JSONField(default=list)

    academic_course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_courses',
        help_text="The academic course unit this LMS content delivers. Null = standalone LMS course."
    )
    session = models.ForeignKey(
        'AcademicSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_courses',
        help_text="Academic session this delivery runs in. Null = self-paced standalone."
    )
    term = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('first',  'First Semester'), ('second', 'Second Semester'),
            ('third',  'Third Semester'), ('annual', 'Annual'),
            ('fall',   'Fall'), ('spring', 'Spring'), ('summer', 'Summer'),
        ],
        help_text="Term within the session. Auto-derived from session.get_current_term() if blank."
    )
    lecturer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lms_courses_as_lecturer',
        help_text="Assigned academic lecturer for this delivery."
    )
    
    # Course Details
    difficulty_level = models.IntegerField(choices=STUDENT_LEVEL_CHOICES, default=100, verbose_name='Level')
    # duration_hours = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Estimated duration in hours")
    # language = models.CharField(max_length=50, default='English')
    
    # Instructor
    instructor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lms_courses_teaching')
    # instructor_name = models.CharField(max_length=100, blank=True)
    # instructor_bio = models.TextField(blank=True)
    
    # Media
    thumbnail = models.ImageField(upload_to='courses/thumbnails/', blank=True, null=True)
    promo_video_url = models.URLField(blank=True)
    
    # Enrollment
    # max_students = models.IntegerField(null=True, blank=True)
    # enrollment_start_date = models.DateField(null=True, blank=True)
    # enrollment_end_date = models.DateField(null=True, blank=True)
    
    # Status
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    
    # Certificate
    # has_certificate = models.BooleanField(default=False)
    # certificate_fee = models.DecimalField(
    #     max_digits=10,
    #     decimal_places=2,
    #     default=Decimal('0.00'),
    #     help_text="Fee charged to the student to receive their certificate"
    # )
    # certificate_template = models.CharField(max_length=100, blank=True)
    
    # SEO
    meta_description = models.CharField(max_length=160, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    
    # Statistics
    total_enrollments = models.IntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMS Course'
        verbose_name_plural = 'LMS Courses'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_published', '-created_at']),
            # models.Index(fields=['category']),
            models.Index(fields=['session', 'term']),
            models.Index(fields=['academic_course', 'session']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            while LMSCourse.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        # if not self.instructor_name and self.instructor:
        #     self.instructor_name = self.instructor.get_full_name() or self.instructor.username

        # Auto-sync term from linked academic course if not manually set
        if self.academic_course and not self.term:
            self.term = self.academic_course.semester
        
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def update_statistics(self):
        """Update course statistics"""
        self.total_enrollments = self.enrollments.count()
        
        # Calculate average rating
        ratings = self.reviews.aggregate(Avg('rating'))
        self.average_rating = ratings['rating__avg'] or 0.00
        self.total_reviews = self.reviews.count()
        
        self.save(update_fields=['total_enrollments', 'average_rating', 'total_reviews'])


class Lesson(models.Model):
    """Individual lessons within LMS courses"""
    LESSON_TYPE_CHOICES = [
        ('video', 'Video'),
        ('text', 'Text'),
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
        ('file', 'Downloadable File'),
    ]
    
    course = models.ForeignKey(LMSCourse, on_delete=models.CASCADE, related_name='lessons')
    section = models.ForeignKey('LessonSection', on_delete=models.SET_NULL, null=True, blank=True, related_name='lessons')
    
    # Basic Information
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPE_CHOICES, default='video')
    
    # Content
    description = models.TextField(blank=True)
    content = models.TextField(blank=True)
    
    # Video Content - URL or File Upload
    video_url = models.TextField(
        blank=True,
        null=True,
        help_text="Paste the full embed iframe code from YouTube, Vimeo, etc."
    )
    video_file = models.FileField(
        upload_to=get_video_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['mp4', 'webm', 'ogg', 'avi', 'mov'])
        ],
        help_text="Or upload video file (MP4, WebM, OGG, AVI, MOV)"
    )
    video_duration_minutes = models.IntegerField(default=0)
    
    # File Content
    file = models.FileField(upload_to=get_document_upload_path, blank=True, null=True)
    
    # Settings
    is_preview = models.BooleanField(default=False, help_text="Allow preview without enrollment")
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['course', 'section', 'display_order']
        verbose_name = 'Lesson'
        verbose_name_plural = 'Lessons'
        unique_together = [['course', 'slug']]
        indexes = [
            models.Index(fields=['course', 'is_active', 'display_order']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def clean(self):
        """Validate video fields"""
        from django.core.exceptions import ValidationError
        
        # For video lessons, ensure either URL or file is provided
        if self.lesson_type == 'video':
            if not self.video_url and not self.video_file:
                raise ValidationError(
                    "Video lessons require either video URL or video file"
                )
            if self.video_url and self.video_file:
                raise ValidationError(
                    "Provide either video URL or video file, not both"
                )

    def get_video_source(self):
        """Return video source (URL or file path)"""
        if self.video_file:
            return self.video_file.url
        return self.video_url or ''
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class LessonSection(models.Model):
    """Sections to organize lessons within a course"""
    course = models.ForeignKey(LMSCourse, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['course', 'display_order']
        verbose_name = 'Lesson Section'
        verbose_name_plural = 'Lesson Sections'
        unique_together = [['course', 'slug']]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


# ==================== MESSAGES ====================
class Message(models.Model):
    """Messages between users (student-instructor, student-admin, etc.)"""
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.sender.username} to {self.recipient.username}: {self.subject}"
    
    def mark_as_read(self):
        """Mark message as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


# ==================== NOTIFICATIONS ====================
class Notification(models.Model):
    """User notifications"""
    NOTIFICATION_TYPE_CHOICES = [
        ('enrollment', 'Enrollment'),
        ('assignment', 'Assignment'),
        ('quiz', 'Quiz'),
        ('grade', 'Grade'),
        ('announcement', 'Announcement'),
        ('message', 'Message'),
        ('certificate', 'Certificate'),
        ('payroll', 'Payroll'),
        ('account', 'Account'),
        ('system', 'System'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


# ==================== PAYMENT GATEWAY ====================
class PaymentGateway(models.Model):
    """Payment gateway configuration"""
    GATEWAY_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
    ]
    
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    gateway_type = models.CharField(max_length=50, choices=GATEWAY_CHOICES)
    api_key = models.CharField(max_length=255, blank=True)
    api_secret = models.CharField(max_length=255, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False)
    is_test_mode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """Financial transactions"""
    TRANSACTION_TYPE_CHOICES = [
        ('enrollment', 'Course Enrollment'),
        ('subscription', 'Subscription'),
        ('refund', 'Refund'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    transaction_id = models.CharField(max_length=100, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES)
    
    # Financial Details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Gateway Details
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.SET_NULL, null=True)
    gateway_transaction_id = models.CharField(max_length=255, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Related Objects
    course = models.ForeignKey(LMSCourse, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.transaction_id} - {self.user.username} - {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)


# ==================== QUIZZES ====================
class Quiz(models.Model):
    """Quizzes for lessons"""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    
    # Settings
    time_limit_minutes = models.IntegerField(null=True, blank=True, help_text="Leave blank for no time limit")
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70.00, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_attempts = models.IntegerField(default=3, help_text="Maximum number of attempts allowed")
    shuffle_questions = models.BooleanField(default=False)
    show_correct_answers = models.BooleanField(default=True, help_text="Show correct answers after submission")
    
    # Status
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['lesson', 'display_order']
        verbose_name = 'Quiz'
        verbose_name_plural = 'Quizzes'
        unique_together = [['lesson', 'slug']]
    
    def __str__(self):
        return f"{self.lesson.course.title} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class QuizQuestion(models.Model):
    """Questions for quizzes"""
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=30, choices=QUESTION_TYPE_CHOICES)
    question_text = models.TextField()
    explanation = models.TextField(blank=True, help_text="Explanation shown after answering")
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, validators=[MinValueValidator(0)])
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['quiz', 'display_order']
        verbose_name = 'Quiz Question'
        verbose_name_plural = 'Quiz Questions'
    
    def __str__(self):
        return f"{self.quiz.title} - Q{self.display_order}"


class QuizAnswer(models.Model):
    """Answer choices for multiple choice questions"""
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['question', 'display_order']
        verbose_name = 'Quiz Answer'
        verbose_name_plural = 'Quiz Answers'
    
    def __str__(self):
        return f"{self.question.question_text[:50]} - {self.answer_text[:50]}"


class QuizAttempt(models.Model):
    """Student quiz attempts"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    
    # Scoring
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Status
    is_completed = models.BooleanField(default=False)
    passed = models.BooleanField(default=False)
    pending_manual_grading = models.BooleanField(
        default=False,
        help_text="True while this attempt has short-answer/essay responses an instructor hasn't graded yet."
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken_minutes = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Quiz Attempt'
        verbose_name_plural = 'Quiz Attempts'
        indexes = [
            models.Index(fields=['quiz', 'student']),
        ]
    
    def __str__(self):
        return f"{self.student.username} - {self.quiz.title} - Attempt"
    
    def calculate_score(self):
        """Calculate the score for this attempt"""
        total_score = 0
        max_score = 0
        
        for response in self.responses.all():
            max_score += float(response.question.points)
            if response.is_correct:
                total_score += float(response.question.points)
        
        self.score = Decimal(str(total_score))
        self.max_score = Decimal(str(max_score))
        
        if max_score > 0:
            self.percentage = Decimal(str((total_score / max_score) * 100))
            self.passed = self.percentage >= self.quiz.passing_score
        
        self.save(update_fields=['score', 'max_score', 'percentage', 'passed'])


class QuizResponse(models.Model):
    """Student responses to quiz questions"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='responses')
    selected_answer = models.ForeignKey(QuizAnswer, on_delete=models.CASCADE, null=True, blank=True, related_name='selected_in_responses')
    text_response = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    points_earned = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    needs_grading = models.BooleanField(
        default=False,
        help_text="True for short-answer/essay responses awaiting an instructor's manual score."
    )
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='quiz_responses_graded')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Quiz Response'
        verbose_name_plural = 'Quiz Responses'
        unique_together = [['attempt', 'question']]
    
    def __str__(self):
        return f"{self.attempt.student.username} - {self.question.question_text[:50]}"


# ==================== REVIEWS ====================
class Review(models.Model):
    """Course reviews and ratings"""
    course = models.ForeignKey(LMSCourse, on_delete=models.CASCADE, related_name='reviews')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review_text = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Review'
        verbose_name_plural = 'Reviews'
        unique_together = [['course', 'student']]
        indexes = [
            models.Index(fields=['course', 'is_approved', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.student.username} - {self.course.title} - {self.rating}/5"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update course statistics
        self.course.update_statistics()


# ==================== SUBSCRIPTION PLANS ====================
class SubscriptionPlan(models.Model):
    """Subscription plans for premium access"""
    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField()
    features = models.JSONField(default=list)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES)
    
    # Access
    max_courses = models.IntegerField(null=True, blank=True, help_text="Leave blank for unlimited")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_order', 'price']
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'
    
    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}/{self.billing_cycle}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Subscription(models.Model):
    """User subscriptions"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Billing
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField()
    auto_renew = models.BooleanField(default=True)
    
    # Payment
    gateway_subscription_id = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['end_date']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name} - {self.status}"
    
    def is_active(self):
        """Check if subscription is currently active"""
        return self.status == 'active' and self.end_date >= timezone.now().date()


class InstitutionalSubscription(models.Model):
    """
    A third-party/organizational subscription the institution itself pays
    for (software licenses, hosting, tools, etc.) — unrelated to the
    student-facing SubscriptionPlan/Subscription pair above. Superuser-only.
    """
    purpose = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    expiry_date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Institutional Subscription'
        verbose_name_plural = 'Institutional Subscriptions'

    def __str__(self):
        return self.purpose

    @property
    def is_active(self):
        return self.expiry_date >= timezone.now().date()


# ==================== SYSTEM CONFIGURATION ====================
class SystemConfiguration(models.Model):
    """System-wide configuration settings"""
    SETTING_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('boolean', 'Boolean'),
        ('json', 'JSON'),
    ]
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    setting_type = models.CharField(max_length=20, choices=SETTING_TYPE_CHOICES, default='text')
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False, help_text="Can be accessed by non-admin users")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'System Configuration'
        verbose_name_plural = 'System Configurations'
        ordering = ['key']

    def __str__(self):
        return self.key

    @classmethod
    def get_value(cls, key: str, default: str = '') -> str:
        val = cls.objects.filter(key=key).values_list('value', flat=True).first()
        return val if val else default

    @classmethod
    def get_values(cls, keys) -> dict:
        """Batch lookup — one query for many keys, instead of one query per key.
        Returns a dict of only the keys that exist; missing keys are simply absent."""
        return dict(cls.objects.filter(key__in=keys).values_list('key', 'value'))

    @classmethod
    def get_secret(cls, key: str, default: str = '') -> str:
        return decrypt_secret(cls.get_value(key)) or default


# ==================== USER PROFILE ====================
class UserProfile(models.Model):
    """Extended user profile"""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Lecturers'),
        ('admin', 'Admin'),
        # ('content_manager', 'Content Manager'),
        ('support', 'Support'),
        # ('qa', 'QA Reviewer'),
        ('finance', 'Finance'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='student')
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name="faculty_students")
    department = models.ForeignKey("Department", on_delete=models.SET_NULL, null=True, blank=True, related_name='department_students')
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, related_name='program_students')

    # ── Academic Progression (StudentProgram concept — kept in UserProfile) ──────
    year_of_study = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Current year of study. Level = year × 100 (e.g. year 1 = 100L)."
    )
    PROGRESSION_STATUS_CHOICES = [
        ('active',     'Active'),
        ('probation',  'Probation'),
        ('repeated',   'Repeating Level'),
        ('graduated',  'Graduated'),
        ('withdrawn',  'Withdrawn'),
    ]
    progression_status = models.CharField(
        max_length=20, choices=PROGRESSION_STATUS_CHOICES, default='active'
    )
    admission_session = models.ForeignKey(
        'AcademicSession',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='admitted_students',
        help_text="Session in which the student was admitted."
    )
    
    # Personal Information
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)


    
    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Social
    website = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    
    # Preferences
    email_notifications = models.BooleanField(default=True)
    marketing_emails = models.BooleanField(default=False)
    
    # Verification
    email_verified = models.BooleanField(default=False)
    verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    verification_token_created = models.DateTimeField(default=timezone.now)

    # Password Reset
    password_reset_token = models.UUIDField(null=True, blank=True, editable=False)
    password_reset_token_created = models.DateTimeField(null=True, blank=True)

    # Force password change on first login (set for admin-created accounts)
    must_change_password = models.BooleanField(
        default=False,
        help_text="If True, user is redirected to change password immediately after login."
    )
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Single-device session tracking ────────────────────────────────────────────
    is_logged_in = models.BooleanField(
        default=False,
        help_text="True while a session is active for this user."
    )
    active_session_key = models.CharField(
        max_length=40,
        blank=True,
        default='',
        help_text="Django session key of the current active session."
    )

    # ── OTP / Two-Step Verification ───────────────────────────────────────────
    # otp_code is encrypted at rest using Django signing to prevent DB exposure.
    # Always use get_otp_code() / set_otp_code() — never access _otp_code directly.
    _otp_code = models.CharField(
        max_length=128,  # signed string is longer than raw 6 digits
        blank=True,
        default='',
        db_column='otp_code',
        help_text="Encrypted one-time password (6 digits)."
    )
    otp_created_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the OTP was last generated. Expires after 10 minutes."
    )
    otp_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Failed OTP attempts for current code. Locked after 5."
    )

    @property
    def otp_code(self):
        """Decrypt and return the OTP, or empty string if unset/invalid."""
        from django.core.signing import Signer, BadSignature
        if not self._otp_code:
            return ''
        try:
            return Signer().unsign(self._otp_code)
        except BadSignature:
            return ''

    @otp_code.setter
    def otp_code(self, raw_value):
        """Encrypt and store the OTP. Pass empty string to clear."""
        from django.core.signing import Signer
        if not raw_value:
            self._otp_code = ''
        else:
            self._otp_code = Signer().sign(raw_value)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def current_level(self):
        """100L, 200L … 800L — computed from year_of_study."""
        return self.year_of_study * 100

    def get_current_courses(self, session=None, term=None):
        """
        Returns Course queryset for this student's program + level + current term.
        Pass term explicitly or it is derived from session.get_current_term().
        """
        session = session or AcademicSession.get_current()
        if not session or not self.program:
            return Course.objects.none()
        current_term = term or session.get_current_term()
        qs = Course.objects.filter(
            program=self.program,
            year_of_study=self.year_of_study,
            is_active=True,
        )
        if current_term and current_term not in ('annual',):
            qs = qs.filter(
                models.Q(semester=current_term) | models.Q(semester='annual')
            )
        return qs
    
    def generate_verification_token(self):
        self.verification_token = uuid.uuid4()
        self.verification_token_created = timezone.now()
        self.save(update_fields=['verification_token', 'verification_token_created'])
        return self.verification_token

    def is_verification_token_valid(self):
        """
        Token expires after 7 days. Deliberately far longer than the 1-hour
        password-reset window: there's currently no self-service "resend"
        entry point for a user who isn't active yet (resend_verification
        requires login, which an unverified/inactive account can't do), so
        an expired link is a real dead-end requiring manual support — a
        generous window keeps that rare rather than routine.
        """
        from datetime import timedelta
        if not self.verification_token_created:
            return False
        return timezone.now() < self.verification_token_created + timedelta(days=7)

    def generate_password_reset_token(self):
        import uuid
        from django.utils import timezone
        self.password_reset_token = uuid.uuid4()
        self.password_reset_token_created = timezone.now()
        self.save(update_fields=['password_reset_token', 'password_reset_token_created'])
        return self.password_reset_token

    def is_reset_token_valid(self):
        """Token expires after 1 hour"""
        from django.utils import timezone
        from datetime import timedelta
        if not self.password_reset_token or not self.password_reset_token_created:
            return False
        return timezone.now() < self.password_reset_token_created + timedelta(hours=1)

    def clear_reset_token(self):
        self.password_reset_token = None
        self.password_reset_token_created = None
        self.save(update_fields=['password_reset_token', 'password_reset_token_created'])

# ─────────────────────────────────────────────────────────────────────────────
# PERMISSIONS MATRIX  (internal staff only — student/instructor excluded)
# ─────────────────────────────────────────────────────────────────────────────

class StaffPermissionsMatrix(models.Model):
    """
    Flat permission table — one row per (role OR user) × module.
    Applies to internal staff roles (admin, support, finance) and to
    instructors. Students are never looked up here.

    role set, user null  → role-level default
    user set, role null  → user-level override (supersedes role row)
    """

    STAFF_ROLES = [
        ('admin',           'Administrator'),
        # ('content_manager', 'Content Manager'),
        ('support',         'Support Staff'),
        # ('qa',              'QA Reviewer'),
        ('finance',         'Finance Manager'),
        ('instructor',      'Instructor'),
    ]

    MODULE_CHOICES = [
        ('dashboard',        'Dashboard'),
        ('user_management',  'User Management'),
        ('academics',        'Academics'),
        ('lms_courses',      'LMS Courses'),
        ('applications',     'Applications'),
        ('exams',            'Exams'),
        ('enrollments',      'Enrollments'),
        ('finance',          'Finance'),
        ('communications',   'Communications'),
        ('blog',             'Blog'),
        ('library',          'Library'),
        ('site_content',     'Site Content'),
        ('security_audit',   'Security & Audit'),
        ('instructor_courses',        'My Courses'),
        ('instructor_assessments',    'Assessments'),
        ('instructor_analytics',     'Analytics'),
        ('instructor_resources',     'Resources'),
        ('instructor_communications', 'Communications'),
        ('finance_payments',      'Payments'),
        ('finance_subscriptions', 'Subscriptions'),
        ('finance_payroll',       'Payroll'),
        ('support_tickets',         'Tickets'),
        ('support_knowledge_base',  'Knowledge Base'),
        ('support_communications',  'Communications'),
        ('support_analytics',       'Analytics'),
        ('support_config',          'Support Config'),
        ('academic_progression',    'Academic Progression'),
        ('results_publish',         'Results Publishing'),
        ('role_permissions',        'Roles & Permissions'),
    ]

    # Role-level defaults — mirrors sidebar sections visible per role
    ROLE_DEFAULT_PERMISSIONS = {
    'admin': {
        # 'dashboard':     {'can_view': True},  # dashboard access isn't matrix-gated — always default; only inner-page actions are
        'user_management': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'academics':       {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'lms_courses':     {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'applications':    {'can_view': True, 'can_edit': True},
        'exams':           {'can_view': True, 'can_edit': True, 'can_approve': True},
        'enrollments':     {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'finance':         {'can_view': True, 'can_edit': True, 'can_export': True},
        'communications':  {'can_view': True, 'can_create': True, 'can_delete': True},
        'blog':            {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'library':         {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'site_content':    {'can_view': True, 'can_edit': True},
        'security_audit':  {'can_view': True},
        'support_config':  {'can_view': True, 'can_create': True, 'can_edit': True},
        'academic_progression': {'can_view': True, 'can_edit': True, 'can_approve': True},
        # Kept separate from 'academic_progression' on purpose: releasing
        # results to the whole student body is a distinct, higher-blast-
        # radius action than running level-progression decisions, so a
        # staff member granted one shouldn't automatically get the other.
        'results_publish': {'can_view': True, 'can_edit': True, 'can_approve': True},
        # Deliberately its own module rather than riding on 'user_management':
        # a staff member can be granted the user list (user_management) without
        # also being able to reassign roles or edit the permission matrix itself.
        'role_permissions': {'can_view': True, 'can_edit': True},
    },
    'support': {
        # 'dashboard':    {'can_view': True},  # dashboard access isn't matrix-gated — always default; only inner-page actions are
        'user_management':{'can_view': True},
        'enrollments':    {'can_view': True},
        'applications':   {'can_view': True},
        'communications': {'can_view': True, 'can_create': True},
        'exams':          {'can_view': True},
        'support_tickets':        {'can_view': True, 'can_create': True, 'can_edit': True},
        'support_knowledge_base': {'can_view': True, 'can_create': True, 'can_edit': True},
        'support_communications': {'can_view': True, 'can_create': True},
        'support_analytics':      {'can_view': True},
    },
    'finance': {
        # 'dashboard':    {'can_view': True},  # dashboard access isn't matrix-gated — always default; only inner-page actions are
        'finance':        {'can_view': True, 'can_edit': True, 'can_export': True},
        'enrollments':    {'can_view': True},
        'user_management':{'can_view': True},
        'finance_payments':      {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True, 'can_export': True},
        'finance_subscriptions': {'can_view': True},
        'finance_payroll':       {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    },
    'instructor': {
        # 'dashboard':               {'can_view': True},  # dashboard access isn't matrix-gated — always default; only inner-page actions are
        'instructor_courses':        {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'instructor_assessments':    {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'instructor_analytics':      {'can_view': True, 'can_export': True},
        'instructor_resources':      {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
        'instructor_communications': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    },
}

    ALL_ACTION_FIELDS = [
        'can_view', 'can_create', 'can_edit', 'can_delete',
        'can_approve', 'can_export',
    ]

    # Core admin/management-portal modules — as opposed to the role-specific
    # instructor_*/finance_*/support_* modules, which belong to those roles'
    # own portals. Used by is_staff's full-bypass tier: is_staff unlocks every
    # module here unconditionally, but never the other roles' portal modules.
    ADMIN_PORTAL_MODULES = {
        'dashboard', 'user_management', 'academics', 'lms_courses',
        'applications', 'exams', 'enrollments', 'finance', 'communications',
        'blog', 'library', 'site_content', 'security_audit', 'support_config',
        'academic_progression', 'results_publish', 'role_permissions',
    }

    # Mirrors ADMIN_PORTAL_MODULES for the other three staff portals — used by
    # the view-level role gates (eduweb.decorators.is_finance_manager/
    # instructor_required, management.views.is_admin, support.permissions.
    # is_support_staff) so a user granted can_view on any module here via a
    # StaffPermissionsMatrix user-level override can actually open that
    # portal's views, not just see the link in the sidebar.
    INSTRUCTOR_PORTAL_MODULES = {
        'instructor_courses', 'instructor_assessments', 'instructor_analytics',
        'instructor_resources', 'instructor_communications',
    }
    FINANCE_PORTAL_MODULES = {'finance_payments', 'finance_subscriptions', 'finance_payroll'}
    SUPPORT_PORTAL_MODULES = {
        'support_tickets', 'support_knowledge_base', 'support_communications',
        'support_analytics', 'support_config',
    }

    role   = models.CharField(max_length=30, choices=STAFF_ROLES, null=True, blank=True)
    user   = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.CASCADE, related_name='permission_matrix_rows'
    )
    module = models.CharField(max_length=40, choices=MODULE_CHOICES)

    can_view    = models.BooleanField(default=False)
    can_create  = models.BooleanField(default=False)
    can_edit    = models.BooleanField(default=False)
    can_delete  = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_export  = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='permission_matrix_changes'
    )

    @classmethod
    def seed_defaults_for_role(cls, role_name):
        """
        Upsert role-default rows from ROLE_DEFAULT_PERMISSIONS.
        Safe to call multiple times — never overwrites user overrides.
        """
        module_defaults = cls.ROLE_DEFAULT_PERMISSIONS.get(role_name, {})
        for module_key, true_flags in module_defaults.items():
            field_values = {f: False for f in cls.ALL_ACTION_FIELDS}
            field_values.update(true_flags)
            cls.objects.update_or_create(
                role=role_name, module=module_key, user=None,
                defaults=field_values,
            )

    @classmethod
    def user_can_view_any(cls, user, modules):
        """
        True if `user` has can_view=True on at least one module in `modules`
        — checking a user-level override row first, else their role's row,
        else the hardcoded ROLE_DEFAULT_PERMISSIONS. Does NOT special-case
        is_superuser/is_staff — callers check those bypasses themselves
        first. Used by the coarse per-portal view gates (is_admin,
        is_finance_manager, instructor_required, is_support_staff) so a
        cross-department grant made via /management/role-assign/ actually
        unlocks that portal's views, not just its sidebar link.
        """
        if not modules or not getattr(user, 'is_authenticated', False):
            return False
        profile = getattr(user, 'profile', None)
        role = getattr(profile, 'role', None)

        # 'student' can never use this bypass, no matter what override rows
        # exist for them — this is the single choke point all four portal
        # gates (is_admin, is_finance_manager, instructor_required,
        # is_support_staff) route through, so this is enough to keep a
        # student account out of every staff portal even if a permissions
        # modal is ever used to grant them a module by mistake. Students are
        # still shown in the user-management/role-assignment picker (they're
        # ordinary accounts worth being able to view/manage there); this
        # only stops a grant from ever being *effective*.
        if role == 'student':
            return False

        user_rows = {
            r.module: r.can_view
            for r in cls.objects.filter(user=user, module__in=modules)
        }
        role_rows = {
            r.module: r.can_view
            for r in cls.objects.filter(role=role, user__isnull=True, module__in=modules)
        } if role else {}

        for m in modules:
            if m in user_rows:
                if user_rows[m]:
                    return True
            elif m in role_rows:
                if role_rows[m]:
                    return True
            elif cls.ROLE_DEFAULT_PERMISSIONS.get(role, {}).get(m, {}).get('can_view'):
                return True
        return False

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'module'],
                condition=models.Q(user=None),
                name='unique_staff_role_module'
            ),
            models.UniqueConstraint(
                fields=['user', 'module'],
                condition=models.Q(role=None),
                name='unique_staff_user_module'
            ),
            models.CheckConstraint(
                check=(
                    models.Q(role__isnull=False, user__isnull=True) |
                    models.Q(user__isnull=False, role__isnull=True)
                ),
                name='staff_matrix_role_xor_user'
            ),
        ]
        ordering = ['role', 'user', 'module']
        verbose_name        = 'Staff Permissions Matrix Row'
        verbose_name_plural = 'Staff Permissions Matrix'

    def __str__(self):
        target = f"Role:{self.role}" if self.role else f"User:{self.user_id}"
        return f"{target} | {self.get_module_display()}"

# ==================== VENDOR MANAGEMENT ====================
class Vendor(models.Model):
    """Vendor/Partner institutions"""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    email = models.EmailField()
    country = models.CharField(max_length=100, blank=True)
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ==================== SIGNALS ====================
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_save, sender=Enrollment)
def update_course_enrollment_count(sender, instance, created, **kwargs):
    """Update course enrollment count when new enrollment is created"""
    if created:
        instance.course.update_statistics()


@receiver(post_save, sender=Review)
def update_course_rating(sender, instance, created, **kwargs):
    """Update course rating when review is added/modified"""
    instance.course.update_statistics()


# @receiver(post_save, sender=UserProfile)
# def auto_assign_required_fees(sender, instance, **kwargs):
#     """
#     When a student's program is set or changed, auto-create FeePayment
#     records (status='pending') for every active AllRequiredPayments
#     that belongs to that program and doesn't already have a payment
#     record for this student.
#     """
#     if instance.role != 'student' or not instance.program:
#         return

#     required_fees = AllRequiredPayments.objects.filter(
#         program=instance.program,
#         who_to_pay='student',
#         is_active=True,
#     )

#     for fee in required_fees:
#         FeePayment.objects.get_or_create(
#             user=instance.user,
#             fee=fee,
#             defaults={
#                 'amount': fee.amount,
#                 'currency': fee.currency,
#                 'status': 'pending',
#             }
#         )

# ==================== STUDY GROUPS ====================
class StudyGroup(models.Model):
    """Study groups for collaborative learning"""
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    course = models.ForeignKey(
        'LMSCourse', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='study_groups'
    )
    
    # Settings
    max_members = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    
    # Creator
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='study_groups_created'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Study Group'
        verbose_name_plural = 'Study Groups'
        indexes = [
            models.Index(fields=['course', 'is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while StudyGroup.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)
    
    def member_count(self):
        """Get current member count"""
        return self.members.filter(is_active=True).count()
    
    def is_full(self):
        """Check if group is at max capacity"""
        return self.member_count() >= self.max_members


class StudyGroupMember(models.Model):
    """Members of study groups"""
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    ]
    
    study_group = models.ForeignKey(
        StudyGroup, 
        on_delete=models.CASCADE, 
        related_name='members'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='study_group_memberships'
    )
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='member'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-joined_at']
        verbose_name = 'Study Group Member'
        verbose_name_plural = 'Study Group Members'
        unique_together = [['study_group', 'user']]
        indexes = [
            models.Index(fields=['study_group', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} in {self.study_group.name}"

class StudyGroupMessage(models.Model):
    """Messages posted in a study group chat"""
    study_group = models.ForeignKey(
        StudyGroup,
        on_delete=models.CASCADE,
        related_name='group_messages'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='study_group_messages'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Study Group Message'
        verbose_name_plural = 'Study Group Messages'
        indexes = [
            models.Index(fields=['study_group', 'created_at']),
        ]

    def __str__(self):
        return f"{self.author.username} in {self.study_group.name}: {self.content[:50]}"
    
# ==================== BROADCAST CENTER ====================
class BroadcastMessage(models.Model):
    """Email broadcasts to filtered recipients"""
    FILTER_TYPE_CHOICES = [
        ('all_users', 'All Users'),
        ('role', 'By User Role'),
        ('faculty', 'By Faculty'),
        ('course', 'By Course (Admission)'),
        ('lms_course', 'By LMS Course'),
        ('application_status', 'By Application Status'),
        ('enrollment_status', 'By Enrollment Status'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    # Message Details
    subject = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    message = models.TextField()
    
    # Filtering
    filter_type = models.CharField(
        max_length=30, 
        choices=FILTER_TYPE_CHOICES
    )
    
    # Filter Values (JSON for flexibility)
    filter_values = models.JSONField(
        default=dict,
        help_text="Stores selected filters"
    )
    
    # Recipients
    recipient_count = models.IntegerField(default=0)
    recipient_emails = models.JSONField(
        default=list,
        help_text="List of recipient emails"
    )
    
    # Status
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='broadcasts_created'
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Broadcast Message'
        verbose_name_plural = 'Broadcast Messages'
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['filter_type']),
        ]
    
    def __str__(self):
        return f"{self.subject} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Auto-generate slug from subject
        if not self.slug:
            base_slug = slugify(self.subject)
            slug = base_slug
            counter = 1
            while BroadcastMessage.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

class StaffPayroll(models.Model):
    """
    Consolidated payroll model with integrated file storage
    Combines salary information and attachments in one table
    """
    
    # Status choices
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('on_hold', 'On Hold'),
    ]
    
    # Payment method choices
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
    ]
    
    # Month choices
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'),
        (4, 'April'), (5, 'May'), (6, 'June'),
        (7, 'July'), (8, 'August'), (9, 'September'),
        (10, 'October'), (11, 'November'), (12, 'December'),
    ]
    
    # =========================================================================
    # CORE FIELDS
    # =========================================================================
    
    payroll_reference = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        db_index=True
    )
    
    staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payrolls',
        limit_choices_to={
            'profile__role__in': [
                'instructor',
                'support',
                'admin',
                'finance'
            ]
        },
        help_text='Select staff member (non-students only)'
    )
    
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()
    
    # =========================================================================
    # SALARY FIELDS
    # =========================================================================
    
    base_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    allowances = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Housing, transport, etc.'
    )
    
    bonuses = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Performance bonuses'
    )
    
    gross_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    
    # =========================================================================
    # DEDUCTION FIELDS
    # =========================================================================
    
    tax_deduction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Income tax'
    )
    
    other_deductions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Insurance, loans, etc.'
    )
    
    net_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    
    # =========================================================================
    # PAYMENT FIELDS
    # =========================================================================
    
    payment_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='bank_transfer'
    )
    
    payment_date = models.DateField(null=True, blank=True)
    
    bank_name = models.CharField(
        max_length=100,
        blank=True,
        default=''
    )
    
    account_number = models.CharField(
        max_length=50,
        blank=True,
        default=''
    )

    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text='ISO 4217 currency code e.g. USD, GBP, EUR'
    )
    
    # =========================================================================
    # FILE ATTACHMENTS - CONSOLIDATED
    # =========================================================================
    
    attachment_1 = models.FileField(
        upload_to='payroll/attachments/%Y/%m/',
        blank=True,
        null=True,
        help_text='Salary slip, contract, etc.'
    )
    
    attachment_1_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Display name for attachment 1'
    )
    
    attachment_2 = models.FileField(
        upload_to='payroll/attachments/%Y/%m/',
        blank=True,
        null=True,
        help_text='Additional document'
    )
    
    attachment_2_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Display name for attachment 2'
    )
    
    attachment_3 = models.FileField(
        upload_to='payroll/attachments/%Y/%m/',
        blank=True,
        null=True,
        help_text='Additional document'
    )
    
    attachment_3_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Display name for attachment 3'
    )
    
    attachment_4 = models.FileField(
        upload_to='payroll/attachments/%Y/%m/',
        blank=True,
        null=True,
        help_text='Additional document'
    )
    
    attachment_4_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Display name for attachment 4'
    )
    
    attachment_5 = models.FileField(
        upload_to='payroll/attachments/%Y/%m/',
        blank=True,
        null=True,
        help_text='Additional document'
    )
    
    attachment_5_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Display name for attachment 5'
    )
    
    # =========================================================================
    # METADATA FIELDS
    # =========================================================================
    
    notes = models.TextField(blank=True, default='')
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payrolls_created'
    )
    
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payrolls_approved'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-year', '-month', 'staff__username']
        unique_together = ['staff', 'month', 'year']
        verbose_name = 'Staff Payroll'
        verbose_name_plural = 'Staff Payrolls'
        indexes = [
            models.Index(fields=['payroll_reference']),
            models.Index(fields=['staff', 'month', 'year']),
            models.Index(fields=['payment_status']),
        ]
    
    def __str__(self):
        return f"{self.staff.get_full_name()} - {self.get_month_name()} {self.year}"
    
    def save(self, *args, **kwargs):
        # Generate unique reference
        if not self.payroll_reference:
            self.payroll_reference = self.generate_reference()
        
        # Calculate gross salary
        self.gross_salary = (
            self.base_salary +
            self.allowances +
            self.bonuses
        )
        
        # Calculate net salary
        self.net_salary = (
            self.gross_salary -
            self.tax_deduction -
            self.other_deductions
        )
        
        # Auto-set attachment names from filename if not set
        for i in range(1, 6):
            file_field = getattr(self, f'attachment_{i}')
            name_field = getattr(self, f'attachment_{i}_name')
            
            if file_field and not name_field:
                setattr(
                    self,
                    f'attachment_{i}_name',
                    file_field.name.split('/')[-1]
                )
        
        super().save(*args, **kwargs)
    
    def generate_reference(self):
        """Generate unique payroll reference"""
        prefix = f"PAY{self.year}{self.month:02d}"
        unique_id = str(uuid.uuid4().hex)[:8].upper()
        return f"{prefix}-{unique_id}"
    
    def get_month_name(self):
        """Get month name from number"""
        months = [
            'January', 'February', 'March', 'April',
            'May', 'June', 'July', 'August',
            'September', 'October', 'November', 'December'
        ]
        return months[self.month - 1] if 1 <= self.month <= 12 else ''
    
    def get_attachments(self):
        """
        Get list of all attachments with metadata
        Returns list of dicts with 'file', 'name', 'number'
        """
        attachments = []
        for i in range(1, 6):
            file_field = getattr(self, f'attachment_{i}')
            if file_field:
                attachments.append({
                    'number': i,
                    'file': file_field,
                    'name': getattr(self, f'attachment_{i}_name') or file_field.name.split('/')[-1],
                    'url': file_field.url,
                    'size': file_field.size if hasattr(file_field, 'size') else 0,
                })
        return attachments
    
    def has_attachments(self):
        """Check if payroll has any attachments"""
        return any([
            self.attachment_1,
            self.attachment_2,
            self.attachment_3,
            self.attachment_4,
            self.attachment_5,
        ])
    
    def get_attachment_count(self):
        """Get count of attachments"""
        return len(self.get_attachments())
    
    def can_delete(self):
        """Check if payroll can be deleted"""
        return self.payment_status != 'paid'
    
    def delete_attachment(self, number):
        """
        Delete specific attachment by number (1-5)
        """
        if 1 <= number <= 5:
            file_field = getattr(self, f'attachment_{number}')
            if file_field:
                # Delete the file from storage
                file_field.delete(save=False)
                # Clear the fields
                setattr(self, f'attachment_{number}', None)
                setattr(self, f'attachment_{number}_name', '')
                self.save()
                return True
        return False

class ListOfCountry(models.Model):
    country = models.CharField(max_length=150, unique=True)
    country_code = models.CharField(max_length=10, unique=True)
    country_phonecode = models.CharField(max_length=10)
    nationality = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "List of Countries"
        ordering = ["country"]

    def __str__(self):
        return f"{self.country} ({self.country_phonecode})"

class FeePayment(models.Model):
    """Payment for student required fees"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
    ]

    # 🔥 KEY DIFFERENCE
    fee = models.ForeignKey(
        'AllRequiredPayments',
        on_delete=models.CASCADE,
        related_name='payments'
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE,
        related_name='student_fee_payments'
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True
    )

    payment_reference = models.CharField(
        max_length=100,
        unique=True,
        blank=True
    )

    gateway_payment_id = models.CharField(max_length=255, blank=True)

    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    payment_metadata = models.JSONField(default=dict, blank=True)

    failure_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Fee Payment'
        verbose_name_plural = 'Fee Payments'
        ordering = ['-created_at']
        unique_together = [['user', 'fee']]
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['status']),
        ]

    def save(self, *args, **kwargs):
        # Generate payment reference
        if not self.payment_reference:
            self.payment_reference = f"FEE-{uuid.uuid4().hex[:12].upper()}"

        # Default amount from fee
        if not self.amount:
            self.amount = self.fee.amount

        # Set paid timestamp
        if self.status == 'success' and not self.paid_at:
            self.paid_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {getattr(self.fee, 'purpose', 'N/A')} - {self.status}"

def library_file_upload_path(instance, filename):
    ext       = filename.split('.')[-1].lower()
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    cat_slug  = slugify(instance.category or 'misc')
    return f'library/{cat_slug}/{safe_name}'
 
 
def library_cover_upload_path(instance, filename):
    name, ext = os.path.splitext(filename)
    return f'library/covers/{slugify(name)}{ext}'
 
 
class LibraryItem(models.Model):
    """
    Single-table digital library.
 
    category / subcategory are plain text — no extra lookup tables needed.
    Use them exactly as they appear on the front-end:
 
        category = "Books"        subcategory = "Apologetics Books"
        category = "Periodicals"  subcategory = "Acta Theologica"
        category = "References"   subcategory = "Dictionaries"
        category = "References"   subcategory = "Commentaries"
        …
 
    Access modes (pick one or both per record):
        A. Upload a file  (PDF / DOCX / EPUB …)
        B. Paste an external URL  (Google Drive, Project Gutenberg, etc.)
    """
 
    # ── Category (top-bar tabs on the library page) ───────────────────────────
    CATEGORY_CHOICES = [
        ('Books',       'Books'),
        ('Periodicals', 'Periodicals'),
        ('References',  'References'),
        ('Other',       'Other'),
    ]
 
    # ── Access ────────────────────────────────────────────────────────────────
    ACCESS_CHOICES = [
        ('public',  'Public – anyone can access'),
        ('members', 'Members only – must be logged in'),
    ]
 
    # ── Language ──────────────────────────────────────────────────────────────
    LANGUAGE_CHOICES = [
        ('en',    'English'),
        ('es',    'Español (Spanish)'),
        ('fr',    'Français (French)'),
        ('pt_br', 'Português (Brazil)'),
        ('ja',    '日本語 (Japanese)'),
        ('zh',    '简体中文 (Chinese Simplified)'),
        ('ko',    '한국어 (Korean)'),
        ('ur',    'اردو (Urdu)'),
        ('ar',    'العربية (Arabic)'),
        ('hi',    'हिन्दी (Hindi)'),
        ('other', 'Other'),
    ]
 
    # ── Primary key ───────────────────────────────────────────────────────────
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=260, unique=True, blank=True)
 
    # ── Taxonomy — two plain text fields, zero extra tables ───────────────────
    category    = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default='Books',
        db_index=True,
        help_text="Top-level section: Books | Periodicals | References | Other"
    )
    subcategory = models.CharField(
        max_length=200, db_index=True,
        help_text=(
            "Sub-section label exactly as shown on the front-end, e.g. "
            "'Apologetics Books', 'Dictionaries', 'Acta Theologica', 'Commentaries' …"
        )
    )
 
    # ── Bibliographic metadata ────────────────────────────────────────────────
    title       = models.CharField(max_length=500)
    author      = models.CharField(max_length=300, blank=True,
                                   help_text="Author / Editor full name")
    publisher   = models.CharField(max_length=200, blank=True)
    year        = models.PositiveSmallIntegerField(null=True, blank=True,
                                                   help_text="Year of publication")
    edition     = models.CharField(max_length=50, blank=True,
                                   help_text="e.g. 'Vol. 2', '3rd Edition'")
    isbn        = models.CharField(max_length=30, blank=True,
                                   verbose_name='ISBN / ISSN')
    language    = models.CharField(max_length=10, choices=LANGUAGE_CHOICES,
                                   default='en')
    description = models.TextField(blank=True,
                                   help_text="Abstract, synopsis, or table of contents")
    tags        = models.CharField(max_length=500, blank=True,
                                   help_text="Comma-separated keywords for search")
 
    # ── Cover / thumbnail ─────────────────────────────────────────────────────
    cover_image = models.ImageField(
        upload_to=library_cover_upload_path, blank=True, null=True,
        help_text="Optional thumbnail shown on library cards"
    )
 
    # ── File upload ───────────────────────────────────────────────────────────
    file = models.FileField(
        upload_to=library_file_upload_path, blank=True, null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'epub', 'txt', 'pptx', 'xlsx']
        )],
        help_text="Upload PDF, DOCX, EPUB, TXT, PPTX or XLSX"
    )
    file_size_mb = models.DecimalField(max_digits=8, decimal_places=2,
                                       null=True, blank=True, editable=False,
                                       help_text="Auto-filled on save")
    file_type    = models.CharField(max_length=10, blank=True, editable=False,
                                    help_text="Auto-detected extension: pdf, docx …")
 
    # ── External link (alternative or supplement to upload) ───────────────────
    external_url = models.URLField(
        max_length=1000, blank=True,
        help_text=(
            "Paste a URL if the document is hosted externally "
            "(Google Drive, Project Gutenberg, archive.org, etc.)"
        )
    )
    external_url_label = models.CharField(
        max_length=100, blank=True, default='Read / Download',
        help_text="Front-end button label for the external link"
    )
 
    # ── Front-end behaviour flags ─────────────────────────────────────────────
    allow_download    = models.BooleanField(
        default=True,
        help_text="Show a Download button on the front-end"
    )
    allow_read_online = models.BooleanField(
        default=True,
        help_text="Show an embedded PDF viewer (Read Online) on the front-end"
    )
 
    # ── Access control ────────────────────────────────────────────────────────
    access = models.CharField(
        max_length=20, choices=ACCESS_CHOICES, default='public',
        help_text="Who can see and open this item"
    )
 
    # ── Stats & display flags ─────────────────────────────────────────────────
    view_count     = models.PositiveIntegerField(default=0, editable=False)
    download_count = models.PositiveIntegerField(default=0, editable=False)
    featured       = models.BooleanField(
        default=False,
        help_text="Pin this item to the library home / featured shelf"
    )
    is_active = models.BooleanField(default=True)
    order     = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order within the sub-category (lower number = first)"
    )
 
    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='library_items_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name        = 'Library Item'
        verbose_name_plural = 'Library Items'
        ordering            = ['category', 'subcategory', 'order', 'title']
        indexes = [
            models.Index(fields=['category', 'subcategory']),
            models.Index(fields=['access', 'is_active']),
            models.Index(fields=['featured']),
            models.Index(fields=['slug']),
        ]
 
    def __str__(self):
        author_str = f" — {self.author}" if self.author else ""
        return f"[{self.category} / {self.subcategory}] {self.title}{author_str}"
 
    def save(self, *args, **kwargs):
        # Auto-generate unique slug
        if not self.slug:
            base    = slugify(f"{self.title} {self.author}")[:250]
            slug    = base
            counter = 1
            while LibraryItem.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug    = f"{base}-{counter}"
                counter += 1
            self.slug = slug
 
        # Auto-fill file metadata
        if self.file:
            try:
                self.file_size_mb = round(self.file.size / (1024 * 1024), 2)
                self.file_type    = self.file.name.split('.')[-1].lower()
            except Exception:
                pass
 
        super().save(*args, **kwargs)
 
    # ── Convenience helpers used in templates / views ─────────────────────────
    def has_file(self):
        return bool(self.file)
 
    def has_external_url(self):
        return bool(self.external_url)
 
    def is_accessible(self):
        """True when at least one of file or external_url is present."""
        return self.has_file() or self.has_external_url()
 
    def increment_views(self):
        LibraryItem.objects.filter(pk=self.pk).update(
            view_count=models.F('view_count') + 1
        )
 
    def increment_downloads(self):
        LibraryItem.objects.filter(pk=self.pk).update(
            download_count=models.F('download_count') + 1
        )
 
    def get_file_icon(self):
        """Return a Bootstrap-icon class matching the detected file type."""
        icons = {
            'pdf':  'bi-file-earmark-pdf text-danger',
            'doc':  'bi-file-earmark-word text-primary',
            'docx': 'bi-file-earmark-word text-primary',
            'epub': 'bi-book text-success',
            'txt':  'bi-file-earmark-text text-secondary',
            'pptx': 'bi-file-earmark-slides text-warning',
            'xlsx': 'bi-file-earmark-spreadsheet text-success',
        }
        return icons.get(self.file_type, 'bi-file-earmark')
 
    @property
    def file_size_display(self):
        """Human-readable file size string."""
        if self.file_size_mb:
            return (f"{int(self.file_size_mb * 1024)} KB"
                    if self.file_size_mb < 1 else f"{self.file_size_mb} MB")
        return ''

    @property
    def tags_list(self):
        """Return tags as a clean list, split on comma."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

# =============================================================================
# COURSE REGISTRATION — student selects courses each session/term
# =============================================================================
class CourseRegistration(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('dropped',   'Dropped'),
    ]

    student  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_registrations')
    course   = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='registrations')
    session  = models.ForeignKey('AcademicSession', on_delete=models.CASCADE, related_name='registrations')
    term     = models.CharField(max_length=20, help_text="e.g. first, second, fall")
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    registered_at = models.DateTimeField(auto_now_add=True)
    dropped_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['student', 'course', 'session', 'term']]
        ordering = ['-registered_at']
        verbose_name = 'Course Registration'
        verbose_name_plural = 'Course Registrations'
        indexes = [
            models.Index(fields=['student', 'session', 'term']),
            models.Index(fields=['course', 'session']),
        ]

    def clean(self, skip_window_check=False):
        # 1. Block registration outside window (bypass for admin/seed use)
        if not skip_window_check and not self.session.is_registration_open:
            raise ValidationError("Course registration is not currently open.")
        # 2. Block re-registration of a dropped core course
        if self.course.course_type == 'core' and self.status == 'dropped':
            raise ValidationError("Core courses cannot be dropped.")
        # 3. Block duplicate
        qs = CourseRegistration.objects.filter(
            student=self.student, course=self.course,
            session=self.session, term=self.term
        ).exclude(pk=self.pk)
        if qs.filter(status__in=['pending', 'approved']).exists():
            raise ValidationError("Already registered for this course this term.")
        # 4. Prerequisite check
        for prereq in self.course.prerequisites.all():
            passed = CourseGrade.objects.filter(
                student=self.student, course=prereq, is_passed=True
            ).exists()
            if not passed:
                raise ValidationError(
                    f"Prerequisite not met: {prereq.code} must be passed first."
                )

    def save(self, *args, skip_window_check=False, skip_clean=False, **kwargs):
        if not skip_clean:
            self.clean(skip_window_check=skip_window_check)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} | {self.course.code} | {self.session} {self.term}"


def _score_to_grade(percentage):
    """Convert a numeric percentage to a Nigerian-scale letter grade."""
    if percentage >= 70:   return 'A'
    elif percentage >= 60: return 'B'
    elif percentage >= 50: return 'C'
    elif percentage >= 45: return 'D'
    else:                  return 'F'


class CourseGrade(models.Model):
    GRADE_CHOICES = [
        ('A', 'A'), ('B', 'B'), ('C', 'C'),
        ('D', 'D'), ('F', 'F'), ('I', 'Incomplete'), ('W', 'Withdrawn'),
    ]
    RESULT_STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('released',  'Released'),
        ('withheld',  'Withheld'),
    ]

    student      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_grades')
    course       = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='student_grades')
    lms_course   = models.ForeignKey(
        'LMSCourse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='student_grades',
        help_text="The LMS delivery this result is linked to (optional)"
    )
    session      = models.ForeignKey('AcademicSession', on_delete=models.CASCADE, related_name='grades')
    term         = models.CharField(max_length=20, blank=True, help_text="Term this grade belongs to")
    application  = models.ForeignKey('CourseApplication', on_delete=models.SET_NULL, null=True, blank=True, related_name='grades')

    score        = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade        = models.CharField(max_length=2, choices=GRADE_CHOICES, blank=True)
    credit_units = models.IntegerField(default=3)
    is_passed    = models.BooleanField(default=False)
    result_status = models.CharField(max_length=20, choices=RESULT_STATUS_CHOICES, default='pending')

    recorded_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='grades_recorded')
    recorded_at  = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student', 'course', 'session', 'term']]
        ordering = ['session', 'course__year_of_study', 'course__semester']
        verbose_name = 'Course Grade'
        verbose_name_plural = 'Course Grades'
        indexes = [
            models.Index(fields=['student', 'session']),
            models.Index(fields=['result_status']),
        ]

    def __str__(self):
        return f"{self.student.username} | {self.course.code} | {self.session} | {self.grade}"

    @property
    def grade_points(self):
        """Nigerian 5-point scale."""
        return {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'F': 0}.get(self.grade, 0)

    @property
    def weighted_points(self):
        return self.grade_points * self.credit_units

    @classmethod
    def compute_cgpa(cls, student):
        """
        Cumulative GPA (Nigerian 5-point scale) across every graded,
        non-withdrawn, *released* CourseGrade row for this student.

        This is the single canonical CGPA computation — the dashboard,
        Academic Records, and the end-of-session progression decision
        must all call this rather than each hand-rolling the same sum,
        so they can never silently disagree (e.g. via different rounding
        rules). Returns None if the student has no gradable records yet.

        Only `result_status='released'` rows count: a grade the registrar
        hasn't published yet must not move a student's CGPA, trigger
        progression/graduation, or appear on a transcript. See
        `publish_results()` for the admin-side release workflow.
        """
        grades = cls.objects.filter(
            student=student, result_status='released',
        ).exclude(grade='').exclude(grade='W')
        total_units = sum(g.credit_units for g in grades)
        if not total_units:
            return None
        weighted_sum = sum(g.weighted_points for g in grades)
        return (Decimal(weighted_sum) / Decimal(total_units)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @classmethod
    def build_transcript_snapshot(cls, student):
        """
        Compute this student's full grade transcript from live CourseGrade
        rows: per-session/semester GPA summaries plus cumulative GPA/class.
        Returns a plain-dict, JSON-safe structure so the exact same shape can
        either be rendered live or frozen verbatim into
        CourseApplication.transcript_snapshot once a student requests their
        transcript — shared between `student` (renders it, freezes it on
        request) and `management` (issues it) so neither app hand-rolls its
        own copy of this logic.

        Only `result_status='released'` rows are included — a course a
        student has completed but whose result the registrar hasn't
        published yet must not appear on a live view, a locked transcript
        snapshot, or an issued transcript. See `publish_results()`.
        """
        grades_qs = list(
            cls.objects
            .filter(student=student, result_status='released')
            .select_related('course', 'course__program', 'session')
            .order_by('-session__name', 'course__semester', 'course__year_of_study')
        )

        sessions_raw = {}
        for g in grades_qs:
            sess_key = g.session.name if g.session else 'Unassigned'
            # Grouped by level + semester, not semester alone — a session can
            # legitimately contain a lower-level carry-over course registered
            # alongside the student's current-level courses, and merging them
            # under one bare "First Semester" label would misrepresent which
            # level each grade actually belongs to.
            sem_key = f'Level {g.course.level} — {g.course.get_semester_display()}'
            sessions_raw.setdefault(sess_key, {}).setdefault(sem_key, []).append(g)

        session_summaries = []
        for sess_name, semesters in sorted(sessions_raw.items(), reverse=True):
            semester_blocks = []
            sess_total_weighted = 0.0
            sess_total_units    = 0
            sess_credits_earned = 0

            for sem_label, grades_list in semesters.items():
                sem_weighted = sum(g.grade_points * g.credit_units for g in grades_list if g.grade)
                sem_units    = sum(g.credit_units for g in grades_list if g.grade and g.grade != 'W')
                sem_gpa      = round(sem_weighted / sem_units, 2) if sem_units > 0 else None
                sem_credits  = sum(g.credit_units for g in grades_list if g.is_passed)

                semester_blocks.append({
                    'label':          sem_label,
                    'gpa':            sem_gpa,
                    'credits':        sem_credits,
                    'total_cu':       sem_units,
                    'total_weighted': round(sem_weighted, 0),
                    'grades': [
                        {
                            'display_code':    g.course.code,
                            'display_name':    g.course.name,
                            'credit_units':    g.credit_units,
                            # Cast Decimal -> float so this matches what comes
                            # back out of JSONField after a DB round-trip
                            # (Decimal isn't JSON-native; storing it raw would
                            # make a *live* score a Decimal but a *locked
                            # snapshot* score a string, subtly changing
                            # {% if g.score %} truthiness for 0.00).
                            'score':           float(g.score) if g.score is not None else None,
                            'grade':           g.grade,
                            'grade_points':    g.grade_points,
                            'weighted_points': g.weighted_points,
                            'is_passed':       g.is_passed,
                        }
                        for g in grades_list
                    ],
                })
                sess_total_weighted += sem_weighted
                sess_total_units    += sem_units
                sess_credits_earned += sem_credits

            sess_gpa = round(sess_total_weighted / sess_total_units, 2) if sess_total_units > 0 else None
            session_summaries.append({
                'name':      sess_name,
                'semesters': semester_blocks,
                'gpa':       sess_gpa,
                'credits':   sess_credits_earned,
            })

        gpa = cls.compute_cgpa(student)
        if gpa is None:               gpa_class = None
        elif gpa >= Decimal('4.5'):   gpa_class = 'First Class'
        elif gpa >= Decimal('3.5'):   gpa_class = 'Second Class Upper'
        elif gpa >= Decimal('2.4'):   gpa_class = 'Second Class Lower'
        elif gpa >= Decimal('1.5'):   gpa_class = 'Third Class'
        else:                         gpa_class = 'Pass'

        return {
            'generated_at':      timezone.now().isoformat(),
            'session_summaries': session_summaries,
            'gpa':               float(gpa) if gpa is not None else None,
            'gpa_class':         gpa_class,
            'credits_earned':    sum(g.credit_units for g in grades_qs if g.is_passed),
            'grade_count':       len(grades_qs),
        }

    EXAM_COMPONENT = 'exam'
    QUIZ_COMPONENT = 'quiz'
    ASSIGNMENT_COMPONENT = 'assignment'

    @classmethod
    def recompute_for_student_course(cls, student, course, session, term=''):
        """
        Recompute and persist this student's grade for `course` in `session`,
        blending exam/quiz/assignment scores using the course's configured
        weights (Course.exam_weight_pct/quiz_weight_pct/assignment_weight_pct).

        Assessment types with no recorded data for this student are dropped
        and the remaining weights re-normalized to sum to 100%, so e.g. an
        exam-only course grades entirely off its exam component. Safe to call
        repeatedly from any grading trigger point (lesson completion, exam
        grading, assignment grading) — always upserts a single row per
        (student, course, session, term).

        Returns the CourseGrade row, or None if the student has no active/
        completed enrollment in a delivery of this course for this session.
        """
        enrollment = (
            Enrollment.objects
            .filter(
                student=student,
                course__academic_course=course,
                course__session=session,
                status__in=['active', 'completed'],
            )
            .select_related('course')
            .first()
        )
        if not enrollment:
            return None

        lms_course = enrollment.course
        components = {}

        # ── Exam component: average of graded end-of-semester exam scores ──────
        exam_avg = (
            StudentExamResponse.objects
            .filter(
                student=student,
                exam__course=lms_course,
                exam__exam_type=Exam.END_OF_SEMESTER,
                status=StudentExamResponse.GRADED,
                score_percentage__isnull=False,
            )
            .aggregate(avg=Avg('score_percentage'))['avg']
        )
        if exam_avg is not None:
            components[cls.EXAM_COMPONENT] = float(exam_avg)

        # ── Quiz component: best attempt percentage per quiz, averaged ─────────
        quiz_attempts = (
            QuizAttempt.objects
            .filter(student=student, quiz__lesson__course=lms_course, is_completed=True)
            .values('quiz_id')
            .annotate(best=Max('percentage'))
        )
        quiz_scores = [float(row['best']) for row in quiz_attempts]
        if quiz_scores:
            components[cls.QUIZ_COMPONENT] = sum(quiz_scores) / len(quiz_scores)

        # ── Assignment component: graded submissions as % of max_score ─────────
        assignment_scores_qs = (
            AssignmentSubmission.objects
            .filter(
                student=student,
                assignment__lesson__course=lms_course,
                status='graded',
                score__isnull=False,
            )
            .annotate(
                pct=ExpressionWrapper(
                    F('score') * 100.0 / F('assignment__max_score'),
                    output_field=FloatField(),
                )
            )
            .values_list('pct', flat=True)
        )
        assignment_scores = [float(s) for s in assignment_scores_qs]
        if assignment_scores:
            components[cls.ASSIGNMENT_COMPONENT] = sum(assignment_scores) / len(assignment_scores)

        # ── Weighted blend, re-normalized over whichever components exist ──────
        if components:
            raw_weights = {
                cls.EXAM_COMPONENT: course.exam_weight_pct,
                cls.QUIZ_COMPONENT: course.quiz_weight_pct,
                cls.ASSIGNMENT_COMPONENT: course.assignment_weight_pct,
            }
            present_weight_sum = sum(raw_weights[c] for c in components)
            if present_weight_sum > 0:
                avg_score = sum(
                    components[c] * (raw_weights[c] / present_weight_sum)
                    for c in components
                )
            else:
                # Present components are all weighted 0 — split evenly instead.
                avg_score = sum(components.values()) / len(components)
        else:
            # No assessments graded yet — use lesson completion as a proxy.
            avg_score = float(enrollment.progress_percentage)

        letter_grade = _score_to_grade(avg_score)
        is_passed = avg_score >= 50  # configurable threshold

        application = (
            CourseApplication.objects
            .filter(user=student, program=course.program)
            .first()
        )

        row_exists = cls.objects.filter(
            student=student, course=course, session=session, term=term
        ).exists()

        defaults = {
            'score': round(avg_score, 2),
            'grade': letter_grade,
            'credit_units': course.credit_units,
            'is_passed': is_passed,
            'application': application,
            'lms_course': lms_course,
        }
        if not row_exists:
            # Only stamp recorded_by on first creation — never clobber a
            # human-recorded grade's ownership on subsequent auto-recomputes.
            defaults['recorded_by'] = None

        grade, _ = cls.objects.update_or_create(
            student=student, course=course, session=session, term=term,
            defaults=defaults,
        )

        if application:
            application.award_program_certificate()

        return grade

    @classmethod
    def publish_results(cls, session, term='', program=None, status='released', by=None):
        """
        Bulk-set result_status for every CourseGrade matching (session, term
        [, program]) — the admin "compile & approve results" action.

        `term` is always an exact match, including `''` (blank) — the
        results_publish admin page lists one row per distinct (session, term)
        pair, blank term included as its own row, so "release this row" must
        only ever touch that exact term value. It must NEVER silently expand
        to "every term in this session": CourseGrade.term is frequently blank
        in this dataset, and treating blank as a wildcard would release an
        entire session's results in one click regardless of what the admin
        actually selected on the page.

        Returns the number of rows updated. Deliberately a plain `.update()`
        (no per-row recompute) — publishing is a visibility/approval action,
        not a re-grading one; scores themselves are unaffected.
        """
        if status not in dict(cls.RESULT_STATUS_CHOICES):
            raise ValueError(f'Invalid result_status: {status!r}')

        qs = cls.objects.filter(session=session, term=term)
        if program:
            qs = qs.filter(course__program=program)

        return qs.update(result_status=status)


class CourseCarryOver(models.Model):
    """
    One row per student per course currently owed as a carry-over.
    Re-evaluated by the end-of-session progression run each time it
    executes — cleared automatically once a passing CourseGrade exists,
    rather than being hooked into every grade-writing code path.
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='carry_overs')
    course  = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='carry_over_records')
    first_failed_session = models.ForeignKey(
        'AcademicSession', on_delete=models.SET_NULL, null=True, related_name='+',
        help_text="Session in which this course was first failed."
    )
    first_failed_term = models.CharField(max_length=20, blank=True)
    attempts = models.PositiveSmallIntegerField(
        default=1, help_text="Number of times this course has been attempted and failed."
    )
    is_cleared = models.BooleanField(default=False)
    cleared_session = models.ForeignKey(
        'AcademicSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text="Session in which a passing grade finally cleared this carry-over."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student', 'course']]
        ordering = ['-updated_at']
        verbose_name = 'Course Carry-Over'
        verbose_name_plural = 'Course Carry-Overs'
        indexes = [
            models.Index(fields=['student', 'is_cleared']),
        ]

    def __str__(self):
        status = 'cleared' if self.is_cleared else f'open (attempt {self.attempts})'
        return f"{self.student.username} | {self.course.code} | {status}"

    @classmethod
    def sync_cleared_for_student(cls, student):
        """
        Live reconciliation — clears any open carry-over the student
        already has a released passing grade for, right now, rather than
        waiting for the next progression batch run to notice.

        Before this existed, `is_cleared` was a stored snapshot only ever
        updated inside management.progression.apply_progression_decision —
        so a student could already have a real, released passing grade for
        a carry-over course and still see it as open/locked on their own
        registration page (my_courses, register_semester_course) until an
        admin next happened to run progression for them. The stored flag
        and the live grade data it's supposed to reflect could silently
        drift apart with no reconciliation between them.

        Call this from every read path that checks is_cleared before using
        it. apply_progression_decision now calls this too instead of
        hand-rolling the same clearing condition a second time.

        Returns the number of rows cleared.
        """
        open_recs = list(
            cls.objects.filter(student=student, is_cleared=False).only('id', 'course_id')
        )
        if not open_recs:
            return 0

        passing_grade_sessions = {
            g['course_id']: g['session_id']
            for g in CourseGrade.objects.filter(
                student=student,
                course_id__in=[r.course_id for r in open_recs],
                is_passed=True, result_status='released',
            ).values('course_id', 'session_id')
        }

        cleared = 0
        for rec in open_recs:
            session_id = passing_grade_sessions.get(rec.course_id)
            if session_id is not None:
                cls.objects.filter(pk=rec.pk).update(
                    is_cleared=True, cleared_session_id=session_id, updated_at=timezone.now(),
                )
                cleared += 1
        return cleared


class ProgressionDecisionLog(ImmutableMixin, models.Model):
    """
    Immutable audit trail — one row per student per end-of-session
    progression run. Mirrors ExamStatusLog's ImmutableMixin pattern.
    """
    slug = models.SlugField(unique=True, max_length=220)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progression_logs')
    session = models.ForeignKey('AcademicSession', on_delete=models.CASCADE, related_name='progression_logs')

    previous_year_of_study = models.PositiveSmallIntegerField()
    new_year_of_study       = models.PositiveSmallIntegerField()
    previous_status = models.CharField(max_length=20)
    new_status      = models.CharField(max_length=20)

    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    core_courses_passed = models.BooleanField(default=False)

    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='progression_decisions_made')
    note = models.TextField(blank=True, help_text="Carried-over courses, attempt counts, and other decision context.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Progression Decision Log'
        verbose_name_plural = 'Progression Decision Logs'
        indexes = [
            models.Index(fields=['student', 'session']),
        ]

    def __str__(self):
        return (
            f"{self.student.username} | {self.session} | "
            f"{self.previous_status}→{self.new_status} "
            f"({self.previous_year_of_study}L→{self.new_year_of_study}L)"
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                ProgressionDecisionLog,
                f"pdl-{self.student_id}-{secrets.token_hex(4)}",
            )
        super().save(*args, **kwargs)

# =============================================================================
# EXAM MODULE — append to the bottom of eduweb/models.py
# =============================================================================
#
# Tables:
#   Exam                  — master record: scheduling, approval workflow
#   ExamQuestion          — permanent question bank / pool (never deleted)
#   StudentExamResponse   — one row per student per exam; question draw + answers + grading
#   ExamStatusLog         — immutable audit trail (uses ImmutableMixin already in file)
#
# All helpers used here (upload_path, unique_slug, ImmutableMixin, User,
# MinValueValidator, models, secrets, timezone) are already defined earlier
# in this same models.py — no extra imports needed.
#
# FK references use the actual class objects directly (same pattern as the
# rest of this file) — LMSCourse must be defined above this block in the
# same file. If it is in a different app, swap to string reference "eduweb.LMSCourse".
#
# TIMING MODEL (instruction window is always 10 minutes — fixed constant)
# ──────────────────────────────────────────────────────────────────────────
#   start_datetime − 10 min  →  instructions_open_at  (instruction page + countdown)
#   start_datetime           →  countdown hits 0 → questions auto-unlock
#   end_datetime             →  server fires auto-submit for all open attempts
#
# VISIBILITY WINDOW (computed — no stored overrides)
# ──────────────────────────────────────────────────
#   visible_from  = start_datetime − VISIBILITY_HOURS_BEFORE  (default 2 h)
#   visible_until = end_datetime   + VISIBILITY_HOURS_AFTER   (default 2 h)
#
# SECURITY MODEL
# ──────────────
#   • correct answers (is_correct) are stored ONLY in ExamQuestion.options
#   • the backend strips is_correct before sending any question to the frontend
#   • on submit the backend fetches ExamQuestion rows and grades server-side
#   • the frontend never receives the full question pool, only the student's
#     assigned subset, and never receives marks or correct-answer flags
# =============================================================================


class Exam(models.Model):
    """
    Master exam record.

    Lifecycle
    ─────────
    DRAFT → SUBMITTED → APPROVED → PUBLISHED
                      ↘ REJECTED → (instructor corrects & re-submits)

    Every status transition is written to ExamStatusLog (immutable).
    Rejection never deletes data — the instructor amends and re-submits.
    Students only see the exam once PUBLISHED and within the computed
    visible_from / visible_until window.

    This is a CBT / online-only exam system:
      • No delivery mode field — always online.
      • No venue or hall — no physical location.
      • No invigilators — proctoring (if any) is handled elsewhere.
      • academic_session and department are derived from the linked LMSCourse.
      • Student eligibility is determined by LMSCourse enrollment.
      • Visibility window and instruction window are computed properties.
      • Clash detection is a computed property — no stored clash_group.
    """

    # ── Exam type ──────────────────────────────────────────────────────────────
    CA                = "ca"
    MID_SEMESTER      = "mid_semester"
    END_OF_SEMESTER   = "end_of_semester"
    SUPPLEMENTARY     = "supplementary"
    RESIT             = "resit"
    PRACTICAL         = "practical"
    ORAL              = "oral"

    EXAM_TYPE_CHOICES = [
        (CA,              "Continuous Assessment"),
        (MID_SEMESTER,    "Mid-Semester Exam"),
        (END_OF_SEMESTER, "End-of-Semester Exam"),
        (SUPPLEMENTARY,   "Supplementary Exam"),
        (RESIT,           "Resit / Make-up Exam"),
        (PRACTICAL,       "Practical Exam"),
        (ORAL,            "Oral / Viva Exam"),
    ]

    # ── REMOVED: Delivery mode — this is an online/CBT system only ────────────
    # IN_PERSON = "in_person"
    # ONLINE    = "online"
    # HYBRID    = "hybrid"
    # MODE_CHOICES = [
    #     (IN_PERSON, "In-Person"),
    #     (ONLINE,    "Online"),
    #     (HYBRID,    "Hybrid"),
    # ]

    # ── Approval status ────────────────────────────────────────────────────────
    DRAFT      = "draft"
    SUBMITTED  = "submitted"
    APPROVED   = "approved"
    REJECTED   = "rejected"
    PUBLISHED  = "published"
    CANCELLED  = "cancelled"

    STATUS_CHOICES = [
        (DRAFT,     "Draft"),
        (SUBMITTED, "Submitted for Approval"),
        (APPROVED,  "Approved"),
        (REJECTED,  "Rejected"),
        (PUBLISHED, "Published"),
        (CANCELLED, "Cancelled"),
    ]

    # ── Question-import job status ─────────────────────────────────────────────
    IMPORT_NONE       = "none"
    IMPORT_PROCESSING = "processing"
    IMPORT_DONE       = "done"
    IMPORT_FAILED     = "failed"

    IMPORT_STATUS_CHOICES = [
        (IMPORT_NONE,       "No import"),
        (IMPORT_PROCESSING, "Processing"),
        (IMPORT_DONE,       "Done"),
        (IMPORT_FAILED,     "Failed"),
    ]

    # ── Timing / visibility constants (no DB columns needed) ──────────────────
    INSTRUCTION_WINDOW_MINUTES = 10   # instruction page opens this many mins before start
    VISIBILITY_HOURS_BEFORE    = 2    # exam card appears to students this many hours before start
    VISIBILITY_HOURS_AFTER     = 2    # exam card stays visible this many hours after end

    # =========================================================================
    # IDENTITY
    # =========================================================================
    slug           = models.SlugField(unique=True, max_length=220)
    reference_code = models.CharField(
        max_length=40, unique=True, db_index=True, blank=True,
        help_text="Auto-generated on save. e.g. EX-2025-4F2A.",
    )
    title = models.CharField(
        max_length=255,
        help_text="e.g. 'CSC301 — Data Structures End-of-Semester Exam 2025'",
    )
    description = models.TextField(
        blank=True,
        help_text="Internal description; not shown to students.",
    )

    # =========================================================================
    # CLASSIFICATION & RELATIONSHIPS
    # =========================================================================
    exam_type = models.CharField(
        max_length=30, choices=EXAM_TYPE_CHOICES, default=END_OF_SEMESTER,
    )

    # REMOVED: mode — always online/CBT, no need to store this
    # mode = models.CharField(
    #     max_length=20, choices=MODE_CHOICES, default=IN_PERSON,
    # )

    course = models.ForeignKey(
        "LMSCourse",
        on_delete=models.PROTECT,
        related_name="exams",
        help_text=(
            "LMS course this exam belongs to. "
            "Academic session, department, and eligible student level "
            "are all derived from here — no need to store them separately."
        ),
    )

    # REMOVED: academic_session — derivable via course.academic_session
    # academic_session = models.ForeignKey(
    #     AcademicSession, on_delete=models.SET_NULL,
    #     null=True, blank=True,
    #     related_name='exams',
    # )

    # REMOVED: department — derivable via course.course.department
    # department = models.ForeignKey(
    #     "Department",
    #     on_delete=models.SET_NULL,
    #     null=True, blank=True,
    #     related_name="exams",
    #     help_text="Denormalised from Course for fast timetable filtering.",
    # )

    instructor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="exams_as_instructor",
    )

    # REMOVED: invigilators — online/CBT exam, no invigilators needed
    # invigilators = models.ManyToManyField(
    #     User,
    #     blank=True,
    #     related_name="exams_as_invigilator",
    # )

    # =========================================================================
    # SCHEDULING
    # ─────────────────────────────────────────────────────────────────────────
    # start_datetime and end_datetime replace the old exam_date + start_time
    # + end_time split. Combining date and time into a single DateTimeField
    # removes the need to manually combine them in every property and view.
    #
    # duration_minutes, instructions_open_at, visible_from, visible_until,
    # and has_clash are all computed @properties — nothing extra is stored.
    # =========================================================================

    # REMOVED: separate date + time fields — replaced by the two DateTimeFields below
    # exam_date  = models.DateField(db_index=True)
    # start_time = models.TimeField(
    #     help_text="Exact exam start. The instruction-page countdown counts to this.",
    # )
    # end_time   = models.TimeField(
    #     help_text="Exam end time. Server fires auto-submit at this time.",
    # )

    start_datetime = models.DateTimeField(
        db_index=True,
        help_text="Exact exam start (date + time). The instruction-page countdown counts to this.",
    )
    end_datetime = models.DateTimeField(
        help_text="Exam end (date + time). Server fires auto-submit at this moment.",
    )

    # REMOVED: instruction_window_minutes — always 10 min, now a class constant above
    # instruction_window_minutes = models.PositiveIntegerField(
    #     default=10,
    #     help_text=(
    #         "Minutes before start_time the instruction page unlocks. "
    #         "The countdown reads down to start_time; questions auto-unlock at zero."
    #     ),
    # )

    # =========================================================================
    # REMOVED: VENUE / HALL — online exam, no physical location
    # =========================================================================
    # venue               = models.CharField(
    #     max_length=200, blank=True,
    #     help_text="Hall name, room number, or 'Online'.",
    # )
    # hall_capacity       = models.PositiveIntegerField(null=True, blank=True)
    # expected_candidates = models.PositiveIntegerField(null=True, blank=True)
    #
    # REMOVED: eligible_levels — students are already enrolled in the LMSCourse,
    # so their level is known. Only enrolled students can sit the exam.
    # eligible_levels = models.CharField(
    #     max_length=100, blank=True,
    #     help_text="Comma-separated student levels eligible, e.g. '200,300'.",
    # )

    # =========================================================================
    # QUESTION POOL CONFIGURATION
    # =========================================================================
    questions_per_student = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Questions served to each student. Blank = give all active questions.",
    )

    # REMOVED: difficulty_mix — not used in this system
    # difficulty_mix = models.JSONField(
    #     default=dict, blank=True,
    #     help_text='e.g. {"easy": 40, "medium": 40, "hard": 20}. Empty = ignore difficulty.',
    # )

    shuffle_questions = models.BooleanField(
        default=True,
        help_text="Serve questions in a different order to each student.",
    )
    shuffle_options = models.BooleanField(
        default=True,
        help_text="Shuffle MCQ answer options independently per student.",
    )
    total_marks = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Auto-summed from active pool questions, or set manually.",
    )
    pass_mark = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    show_result_immediately = models.BooleanField(
        default=False,
        help_text="Show score to student immediately after auto-graded submission.",
    )
    show_answers_after = models.DateTimeField(
        null=True, blank=True,
        help_text="When correct answers become visible to students.",
    )

    # =========================================================================
    # QUESTION IMPORT  (.docx / .xlsx → ExamQuestion rows via background task)
    # =========================================================================
    question_import_file = models.FileField(
        upload_to=upload_path("exam_question_imports"),
        null=True, blank=True,
        help_text="Upload .docx or .xlsx. Background task parses into ExamQuestion rows.",
    )
    import_status = models.CharField(
        max_length=20, choices=IMPORT_STATUS_CHOICES, default=IMPORT_NONE,
    )
    import_error_log = models.TextField(
        blank=True,
        help_text="Rows that failed parsing — shown to the instructor.",
    )

    # =========================================================================
    # REMOVED: FILE UPLOADS — not applicable for online/CBT exam
    # =========================================================================
    # REMOVED: timetable_file — no printed timetable needed for online exams
    # timetable_file = models.FileField(
    #     upload_to=upload_path("exam_timetables"),
    #     null=True, blank=True,
    # )
    # REMOVED: seating_plan_file — no physical seating for online exams
    # seating_plan_file = models.FileField(
    #     upload_to=upload_path("exam_seating_plans"),
    #     null=True, blank=True,
    # )

    # =========================================================================
    # APPROVAL WORKFLOW
    # =========================================================================
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=DRAFT, db_index=True,
    )
    submission_count = models.PositiveIntegerField(
        default=0,
        help_text="Increments on each instructor submission — tracks revision cycles.",
    )
    submitted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_submitted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_rejected",
    )
    rejected_at      = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    published_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_published",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_cancelled",
    )
    cancelled_at        = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    # =========================================================================
    # REMOVED: STUDENT VISIBILITY OVERRIDES
    # ─────────────────────────────────────────────────────────────────────────
    # Visibility is now fully computed from start_datetime / end_datetime
    # using the class constants VISIBILITY_HOURS_BEFORE / VISIBILITY_HOURS_AFTER.
    # No manual override fields are needed.
    # =========================================================================
    # visible_from_override = models.DateTimeField(
    #     null=True, blank=True,
    #     help_text=(
    #         "Optional. Override when students can first see this exam. "
    #         "Leave blank to default to exam_start_datetime."
    #     ),
    # )
    # visible_until_override = models.DateTimeField(
    #     null=True, blank=True,
    #     help_text=(
    #         "Optional. Override when this exam disappears from student view. "
    #         "Leave blank to default to exam_end_datetime."
    #     ),
    # )

    # =========================================================================
    # REMOVED: CLASH DETECTION FIELDS — clash is now a computed @property
    # ─────────────────────────────────────────────────────────────────────────
    # has_clash and clashing_exams are properties below.
    # clash_notes kept as a plain text field for manual staff annotations.
    # =========================================================================
    # clash_group = models.CharField(max_length=80, blank=True, db_index=True)
    # has_clash   = models.BooleanField(default=False)
    clash_notes = models.TextField(blank=True)

    # =========================================================================
    # INSTRUCTIONS & NOTES
    # =========================================================================
    instructions = models.TextField(
        blank=True,
        help_text="Shown to students on the instruction page during the countdown.",
    )
    special_instructions = models.TextField(
        blank=True,
        help_text="Additional notes shown on the exam listing (e.g. 'Have your matric card ready').",
    )
    internal_notes = models.TextField(
        blank=True,
        help_text="Staff-only — never visible to students.",
    )

    # REMOVED: has_accommodations / accommodation_notes — physical-exam concepts,
    # not applicable for a fully online/CBT system. If accessibility settings are
    # ever needed, store them on the student profile, not the exam.
    # has_accommodations  = models.BooleanField(default=False)
    # accommodation_notes = models.TextField(blank=True)

    # =========================================================================
    # STANDARD METADATA
    # =========================================================================
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exams_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering            = ["start_datetime"]
        verbose_name        = "Exam"
        verbose_name_plural = "Exams"
        indexes = [
            models.Index(fields=["start_datetime", "status"]),
            models.Index(fields=["course", "start_datetime"]),
            # REMOVED: academic_session indexes — session derived from LMSCourse
            # models.Index(fields=["academic_session", "exam_date"]),
            # models.Index(fields=["course", "academic_session"]),
        ]
        constraints = [
            # REMOVED: unique_exam_course_session_type — academic_session no longer stored
            # models.UniqueConstraint(
            #     fields=["course", "academic_session", "exam_type"],
            #     condition=models.Q(course__isnull=False),
            #     name="unique_exam_course_session_type",
            # ),
            models.CheckConstraint(
                check=models.Q(end_datetime__gt=models.F("start_datetime")),
                name="exam_end_after_start",
            ),
        ]

    def __str__(self):
        return (
            f"[{self.reference_code}] {self.title} | "
            f"{self.start_datetime:%Y-%m-%d %H:%M}–{self.end_datetime:%H:%M}"
        )

    # ── Validation ────────────────────────────────────────────────────────────

    def clean(self):
        super().clean()
        errors = {}

        # 1. end_datetime must be after start_datetime
        if self.start_datetime and self.end_datetime:
            if self.end_datetime <= self.start_datetime:
                errors["end_datetime"] = "end_datetime must be after start_datetime."
            else:
                dur = self.duration_minutes
                # 2. instruction window (fixed constant) must be smaller than exam duration
                if dur > 0 and self.INSTRUCTION_WINDOW_MINUTES >= dur:
                    errors["start_datetime"] = (
                        f"Exam duration ({dur} min) is too short for the "
                        f"{self.INSTRUCTION_WINDOW_MINUTES}-minute instruction window."
                    )

        # 3. pass_mark may not exceed total_marks
        if self.pass_mark is not None and self.total_marks:
            if self.pass_mark > self.total_marks:
                errors["pass_mark"] = "pass_mark cannot exceed total_marks."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.reference_code:
            year = self.start_datetime.year if self.start_datetime else timezone.now().year
            self.reference_code = f"EX-{year}-{secrets.token_hex(3).upper()}"
        if not self.slug:
            self.slug = unique_slug(Exam, self.reference_code)
        self.full_clean()
        super().save(*args, **kwargs)

    # ── Computed timing properties ─────────────────────────────────────────────

    @property
    def duration_minutes(self) -> int:
        """Total exam duration in minutes, computed from start/end datetimes."""
        if not (self.start_datetime and self.end_datetime):
            return 0
        return int((self.end_datetime - self.start_datetime).total_seconds() // 60)

    @property
    def instructions_open_at(self):
        """
        When the instruction page unlocks for students.
        = start_datetime − INSTRUCTION_WINDOW_MINUTES (always 10 min).
        The countdown reads down to start_datetime; questions auto-unlock at zero.
        """
        import datetime
        return self.start_datetime - datetime.timedelta(minutes=self.INSTRUCTION_WINDOW_MINUTES)

    # ── Computed visibility properties ────────────────────────────────────────
    #
    # Replaces the old visible_from_override / visible_until_override fields.
    # Window is derived purely from the exam datetimes + class-level constants.
    # To change the window institution-wide, adjust the constants at the top
    # of this class — no migration needed.

    @property
    def visible_from(self):
        """
        When students can first see this exam in their dashboard.
        Defaults to VISIBILITY_HOURS_BEFORE hours before start_datetime.
        """
        import datetime
        return self.start_datetime - datetime.timedelta(hours=self.VISIBILITY_HOURS_BEFORE)

    @property
    def visible_until(self):
        """
        When this exam disappears from student view.
        Defaults to VISIBILITY_HOURS_AFTER hours after end_datetime.
        """
        import datetime
        return self.end_datetime + datetime.timedelta(hours=self.VISIBILITY_HOURS_AFTER)

    @property
    def is_published(self):
        return self.status == self.PUBLISHED and self.is_active

    @property
    def is_visible_to_students(self):
        """True only when published, active, and within the computed visibility window."""
        now = timezone.now()
        return self.is_published and self.visible_from <= now <= self.visible_until

    # ── Computed clash properties ──────────────────────────────────────────────
    #
    # Replaces the old clash_group / has_clash fields.
    # Overlap condition: another exam's window intersects this one.
    # clash_notes (plain TextField above) is kept for manual staff annotations.

    @property
    def clashing_exams(self):
        """
        Queryset of other published exams whose time window overlaps this one.
        Overlap: other.start_datetime < self.end_datetime
              AND other.end_datetime  > self.start_datetime
        """
        if not (self.start_datetime and self.end_datetime):
            return Exam.objects.none()
        return (
            Exam.objects
            .filter(status=self.PUBLISHED, is_active=True)
            .filter(
                start_datetime__lt=self.end_datetime,
                end_datetime__gt=self.start_datetime,
            )
            .exclude(pk=self.pk)
        )

    @property
    def has_clash(self) -> bool:
        """True if any other published exam overlaps this exam's window."""
        return self.clashing_exams.exists()

    # ── Question pool helpers ──────────────────────────────────────────────────

    @property
    def active_question_count(self):
        return self.questions.filter(is_active=True).count()

    @property
    def computed_total_marks(self):
        from django.db.models import Sum
        result = self.questions.filter(is_active=True).aggregate(total=Sum("marks"))
        return result["total"] or 0


# =============================================================================
# TABLE 2 — EXAM QUESTION  (permanent question bank / pool)
# =============================================================================

class ExamQuestion(models.Model):
    """
    A single question in the exam question pool.

    Questions are NEVER deleted when an exam closes — they accumulate as the
    institution's permanent question bank.

    SECURITY: options stores is_correct per option. The view MUST strip
    is_correct before sending any question data to the frontend. Grading is
    always done server-side by reading this model.

    question_type behaviour:
      mcq           → exactly one correct option in options[]
      multi_select  → one or more correct options in options[]
      true_false    → two options: True / False
      short_answer  → no options; auto-graded via accepted_answers or manual
      essay         → no options; manual grading only
    """

    MCQ          = "mcq"
    MULTI_SELECT = "multi_select"
    TRUE_FALSE   = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY        = "essay"

    QUESTION_TYPE_CHOICES = [
        (MCQ,          "Multiple Choice (single answer)"),
        (MULTI_SELECT, "Multiple Choice (multiple answers)"),
        (TRUE_FALSE,   "True / False"),
        (SHORT_ANSWER, "Short Answer"),
        (ESSAY,        "Essay / Long Answer"),
    ]

    # REMOVED: difficulty — students only sit exams for courses they are enrolled
    # in, so academic level is already enforced at the Exam→LMSCourse level.
    # The Exam model also has difficulty_mix commented out, making per-question
    # difficulty unused end-to-end. Re-add if adaptive difficulty is ever needed.
    # EASY   = "easy"
    # MEDIUM = "medium"
    # HARD   = "hard"
    #
    # DIFFICULTY_CHOICES = [
    #     (EASY,   "Easy"),
    #     (MEDIUM, "Medium"),
    #     (HARD,   "Hard"),
    # ]

    # =========================================================================
    # IDENTITY
    # =========================================================================
    slug = models.SlugField(unique=True, max_length=220)

    # =========================================================================
    # POOL MEMBERSHIP
    # ─────────────────────────────────────────────────────────────────────────
    # exam is the "home" exam this question was originally created for / imported
    # into. To reuse across multiple exams without duplication, query by tags or
    # source_reference when picking for a new exam.
    # =========================================================================
    exam = models.ForeignKey(
        "Exam",
        on_delete=models.CASCADE,
        related_name="questions",
    )

    # =========================================================================
    # QUESTION CONTENT
    # =========================================================================
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPE_CHOICES, default=MCQ,
    )

    # REMOVED: difficulty — see note above at class constants.
    # difficulty = models.CharField(
    #     max_length=10, choices=DIFFICULTY_CHOICES, default=MEDIUM, db_index=True,
    # )

    marks = models.DecimalField(
        max_digits=6, decimal_places=2, default=1,
        validators=[MinValueValidator(0)],
    )
    image = models.ImageField(
        upload_to=upload_path("exam_question_images"),
        null=True, blank=True,
        help_text="Optional diagram or figure for the question.",
    )
    explanation = models.TextField(
        blank=True,
        help_text="Explanation shown to students after answers are released.",
    )

    # ── Answer options (MCQ / multi_select / true_false) ──────────────────────
    # Structure of each item:
    #   {"id": "opt-<uuid>", "text": "O(log n)", "is_correct": true}
    #   SECURITY: strip is_correct before sending to frontend.
    # Leave empty for short_answer / essay.
    options = models.JSONField(
        default=list, blank=True,
        help_text=(
            'Array of answer options. Each: {"id": "opt-uuid", "text": "...", "is_correct": bool}. '
            "Empty for short_answer / essay. SECURITY: strip is_correct before sending to frontend."
        ),
    )

    # Accepted exact-match strings for short_answer auto-grading.
    # e.g. ["binary search", "Binary Search"]
    # Leave empty for manual grading.
    accepted_answers = models.JSONField(
        default=list, blank=True,
        help_text="For short_answer only. Exact-match strings for auto-grading.",
    )

    # =========================================================================
    # BANK / POOL METADATA
    # =========================================================================

    # REMOVED: order — question sequencing is handled at the StudentExamResponse
    # level via assigned_question_ids (written once per student draw). When
    # shuffle_questions=True (the default on Exam), a stored order field is
    # entirely overridden. When shuffle is off, assigned_question_ids preserves
    # creation order (created_at). A stored order field adds maintenance burden
    # with no benefit in this CBT setup.
    # order = models.PositiveIntegerField(
    #     default=0, db_index=True,
    #     help_text="Default display order within the exam (overridden by shuffle).",
    # )

    tags = models.JSONField(
        default=list, blank=True,
        help_text='e.g. ["chapter-3", "sorting", "complexity"]',
    )
    source_reference = models.CharField(
        max_length=255, blank=True,
        help_text='e.g. "2019 Past Question Q4" or "Imported via Q-Bank"',
    )
    year_first_used = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Year this question was first used — helps avoid recent repeats.",
    )

    # ── Import traceability ────────────────────────────────────────────────────
    imported_from_file = models.CharField(
        max_length=255, blank=True,
        help_text="Original filename this question was parsed from, if imported.",
    )

    # REMOVED: import_row_number — parse-error tracing is handled in
    # Exam.import_error_log (text log written during the import job).
    # Storing a row number per question record adds a column that is only
    # meaningful during the import run and is never queried afterward.
    # import_row_number = models.PositiveIntegerField(
    #     null=True, blank=True,
    #     help_text="Row/paragraph number in import file — for parse-error tracing.",
    # )

    # =========================================================================
    # STANDARD METADATA
    # =========================================================================
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exam_questions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active  = models.BooleanField(
        default=True,
        help_text="Inactive questions are excluded from student draws.",
    )

    class Meta:
        ordering            = ["exam", "created_at"]   # order field removed
        verbose_name        = "Exam Question"
        verbose_name_plural = "Exam Questions"
        indexes = [
            # REMOVED: difficulty index — field no longer stored
            # models.Index(fields=["exam", "difficulty", "is_active"]),
            # REMOVED: order index — field no longer stored
            # models.Index(fields=["exam", "order"]),
            models.Index(fields=["exam", "is_active"]),
            models.Index(fields=["exam", "created_at"]),
        ]

    def __str__(self):
        return (
            f"[{self.exam.reference_code}] "
            f"({self.get_question_type_display()}) — {self.question_text[:80]}"
        )

    def clean(self):
        super().clean()
        errors = {}

        if self.question_type in (self.MCQ, self.TRUE_FALSE, self.MULTI_SELECT):
            if not self.options:
                errors['options'] = (
                    f"{self.get_question_type_display()} questions require at least one option."
                )
            else:
                correct = [o for o in self.options if o.get("is_correct")]
                if not correct:
                    errors['options'] = "At least one option must be marked is_correct."
                elif self.question_type == self.MCQ and len(correct) != 1:
                    errors['options'] = "MCQ questions must have exactly one correct option."
                elif self.question_type == self.TRUE_FALSE:
                    if len(self.options) != 2:
                        errors['options'] = "True/False questions must have exactly 2 options."
                    if len(correct) != 1:
                        errors['options'] = "True/False questions must have exactly one correct option."

        if self.question_type in (self.SHORT_ANSWER, self.ESSAY) and self.options:
            errors['options'] = (
                f"{self.get_question_type_display()} questions must not have options."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                ExamQuestion,
                f"eq-{self.exam_id}-{secrets.token_hex(4)}",
            )
        self.full_clean()
        super().save(*args, **kwargs)

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def option_count(self) -> int:
        """Number of answer options (meaningful for MCQ / multi_select / T/F)."""
        return len(self.options)

    @property
    def correct_option_count(self) -> int:
        """Number of options marked is_correct. Useful for grading validation."""
        return sum(1 for o in self.options if o.get("is_correct"))

    @property
    def has_image(self) -> bool:
        return bool(self.image)

    @property
    def is_auto_gradeable(self) -> bool:
        """
        True for question types that can be graded without human review.
        MCQ and True/False are always auto-gradeable.
        Multi-select is auto-gradeable.
        Short-answer is auto-gradeable only when accepted_answers is populated.
        Essay always requires manual grading.
        """
        if self.question_type in (self.MCQ, self.TRUE_FALSE, self.MULTI_SELECT):
            return True
        if self.question_type == self.SHORT_ANSWER:
            return bool(self.accepted_answers)
        return False  # essay

    @property
    def requires_manual_grading(self) -> bool:
        return not self.is_auto_gradeable

    def safe_options_for_student(self, shuffled_order: list = None) -> list:
        """
        Returns this question's options stripped of is_correct.
        Pass the shuffled_order list (of option IDs) from
        StudentExamResponse.assigned_options_order to preserve per-student shuffle.

        ALWAYS use this method when sending question data to the frontend.
        Never send raw .options — it contains is_correct flags.
        """
        clean_opts = [{"id": o["id"], "text": o["text"]} for o in self.options]
        if shuffled_order:
            order_map = {oid: idx for idx, oid in enumerate(shuffled_order)}
            clean_opts.sort(key=lambda o: order_map.get(o["id"], 9999))
        return clean_opts


# =============================================================================
# TABLE 3 — STUDENT EXAM RESPONSE
# =============================================================================

class StudentExamResponse(models.Model):
    """
    One row per student per exam. Created server-side the moment a student
    opens the instruction page.

    At that point the backend:
      1. Draws N questions from the pool (respects difficulty_mix).
      2. Shuffles them (if Exam.shuffle_questions = True).
      3. Shuffles each question's option order (if Exam.shuffle_options = True).
      4. Writes assigned_question_ids and assigned_options_order to this row.
      5. Returns ONLY question text + shuffled options (no is_correct) to frontend.

    On submit (student click or auto-submit at exam_end_datetime):
      1. Frontend sends {question_pk: selected_option_id_or_text} per answer.
      2. Backend fetches ExamQuestion rows and grades server-side.
      3. MCQ / multi_select / true_false → auto-graded into question_scores.
      4. short_answer → auto-graded if accepted_answers set, else pending manual.
      5. essay → pending manual grading.
      6. total_score, score_percentage, passed written to this row.
    """

    NOT_STARTED  = "not_started"
    INSTRUCTIONS = "instructions"
    IN_PROGRESS  = "in_progress"
    SUBMITTED    = "submitted"
    GRADED       = "graded"
    ABSENT       = "absent"

    ATTEMPT_STATUS_CHOICES = [
        (NOT_STARTED,  "Not Started"),
        (INSTRUCTIONS, "Reading Instructions"),
        (IN_PROGRESS,  "In Progress"),
        (SUBMITTED,    "Submitted"),
        (GRADED,       "Graded"),
        (ABSENT,       "Absent"),
    ]

    # =========================================================================
    # IDENTITY
    # =========================================================================
    slug = models.SlugField(unique=True, max_length=220)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================
    exam    = models.ForeignKey(
        Exam, on_delete=models.PROTECT, related_name="student_responses",
    )
    student = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="exam_responses",
    )

    # =========================================================================
    # SERVER-ASSIGNED QUESTION DRAW
    # ─────────────────────────────────────────────────────────────────────────
    # Both fields written ONCE when the instruction page opens. Never changed.
    #
    # assigned_question_ids:
    #   Ordered list of ExamQuestion PKs drawn for this student.
    #   e.g. [42, 17, 305, 88, ...]
    #
    # assigned_options_order:
    #   Maps each question PK (string key) → shuffled list of option IDs as
    #   presented to this student. Allows exact reconstruction for audit/review.
    #   e.g. {"42": ["opt-c", "opt-a", "opt-d", "opt-b"], "17": [...], ...}
    # =========================================================================
    assigned_question_ids  = models.JSONField(
        default=list,
        help_text="Ordered list of ExamQuestion PKs drawn for this student. Written once.",
    )
    assigned_options_order = models.JSONField(
        default=dict,
        help_text="Maps question PK → shuffled option ID list as shown to this student. Written once.",
    )

    # =========================================================================
    # ANSWERS
    # ─────────────────────────────────────────────────────────────────────────
    # Keyed by question PK (string). Updated incrementally via auto-save.
    #   mcq / true_false  → "opt-uuid-string"
    #   multi_select      → ["opt-uuid-1", "opt-uuid-2"]
    #   short_answer      → "the student's typed answer"
    #   essay             → "the student's long-form answer"
    # =========================================================================
    answers = models.JSONField(
        default=dict,
        help_text="Student answers keyed by question PK. Updated incrementally by auto-save.",
    )

    # =========================================================================
    # GRADING
    # ─────────────────────────────────────────────────────────────────────────
    # question_scores written by the grading routine on submit.
    # e.g. {
    #   "42": {"marks_awarded": 2,    "max_marks": 2, "is_correct": true},
    #   "88": {"marks_awarded": null, "max_marks": 5, "pending_manual": true}
    # }
    # =========================================================================
    question_scores      = models.JSONField(
        default=dict,
        help_text=(
            'Per-question grading breakdown. '
            'Each entry: {"marks_awarded": N|null, "max_marks": N, "is_correct": bool|null}. '
            "null marks_awarded = pending manual grading."
        ),
    )
    total_score          = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Null until fully graded.",
    )
    score_percentage     = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="(total_score / total_marks) × 100. Computed on grading completion.",
    )
    passed               = models.BooleanField(
        null=True,
        help_text="Null until graded. True if total_score >= Exam.pass_mark.",
    )
    overall_feedback     = models.TextField(blank=True)
    graded_by            = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exam_responses_graded",
    )
    graded_at            = models.DateTimeField(null=True, blank=True)
    pending_manual_count = models.PositiveIntegerField(
        default=0,
        help_text="Questions still awaiting manual grading.",
    )

    # =========================================================================
    # STATUS & TIMING
    # =========================================================================
    status                 = models.CharField(
        max_length=20, choices=ATTEMPT_STATUS_CHOICES,
        default=NOT_STARTED, db_index=True,
    )
    instructions_opened_at = models.DateTimeField(null=True, blank=True)
    exam_started_at        = models.DateTimeField(
        null=True, blank=True,
        help_text="When questions were revealed (countdown hit 0).",
    )
    last_autosave_at       = models.DateTimeField(null=True, blank=True)
    submitted_at           = models.DateTimeField(null=True, blank=True)
    auto_submitted         = models.BooleanField(
        default=False,
        help_text="True if submission was triggered by the server timer.",
    )
    time_spent_seconds     = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Seconds from exam_started_at to submitted_at.",
    )

    # =========================================================================
    # FORENSIC / SECURITY
    # =========================================================================
    ip_address        = models.GenericIPAddressField(null=True, blank=True)
    tab_switch_count  = models.PositiveIntegerField(default=0)
    invigilator_notes = models.TextField(blank=True)

    # =========================================================================
    # STANDARD METADATA
    # =========================================================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ["exam", "student"]
        verbose_name        = "Student Exam Response"
        verbose_name_plural = "Student Exam Responses"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="unique_student_exam_response",
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "status"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["exam", "total_score"]),
        ]

    def __str__(self):
        return (
            f"{self.student} | {self.exam.reference_code} | "
            f"{self.get_status_display()} | Score: {self.total_score}"
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                StudentExamResponse,
                f"ser-{self.exam_id}-{self.student_id}-{secrets.token_hex(3)}",
            )
        super().save(*args, **kwargs)

    @property
    def questions_answered(self):
        return len(self.answers) if self.answers else 0

    @property
    def is_complete(self):
        return self.status in (self.SUBMITTED, self.GRADED)

    @property
    def needs_manual_grading(self):
        return self.pending_manual_count > 0

    @property
    def auto_graded(self):
        """true if the attempt has been fully auto-graded (no pending manual questions)."""
        return self.status == self.graded and self.pending_manual_count == 0


# =============================================================================
# TABLE 4 — EXAM STATUS LOG  (immutable — uses ImmutableMixin from this file)
# =============================================================================

class ExamStatusLog(ImmutableMixin, models.Model):
    """
    Immutable audit trail of every status change on an Exam.

    Written on every transition:
      DRAFT → SUBMITTED       (instructor submits)
      SUBMITTED → APPROVED    (admin approves)
      SUBMITTED → REJECTED    (admin rejects)
      APPROVED → PUBLISHED    (instructor/admin publishes)
      any → CANCELLED

    Uses ImmutableMixin (same SEC-10/SEC-11 pattern as SaleStatusHistory /
    AuditLog already in this file) — update() and delete() are both blocked.
    """

    slug        = models.SlugField(unique=True, max_length=220)
    exam        = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="status_logs",
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status   = models.CharField(max_length=20)
    changed_by  = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="exam_status_changes",
    )
    note        = models.TextField(
        blank=True,
        help_text="Rejection reason, approval comment, cancellation note, etc.",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["-created_at"]
        verbose_name        = "Exam Status Log"
        verbose_name_plural = "Exam Status Logs"

    def __str__(self):
        return (
            f"{self.exam.reference_code} | "
            f"{self.from_status} → {self.to_status} "
            f"by {self.changed_by} @ {self.created_at:%Y-%m-%d %H:%M}"
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                ExamStatusLog,
                f"esl-{self.exam_id}-{secrets.token_hex(4)}",
            )
        super().save(*args, **kwargs)

# ==================== BADGE AUTO-AWARD ENGINE ====================

def check_and_award_badges(user):
    """
    Call this after any student action (quiz submit, lesson complete, etc.)
    It checks every milestone and silently awards badges the student hasn't got yet.
    Safe to call multiple times — unique_together on StudentBadge prevents duplicates.
    """
    from django.utils.text import slugify

    def _award(slug, name, description, icon, color, points, reason):
        """Get-or-create the badge then award it if not already held."""
        badge, _ = Badge.objects.get_or_create(
            slug=slug,
            defaults=dict(
                name=name, description=description,
                icon=icon, color=color, points=points,
                criteria=description, is_active=True,
            ),
        )
        StudentBadge.objects.get_or_create(
            student=user, badge=badge,
            defaults=dict(awarded_by=None, reason=reason),
        )

    # ── Lazy imports to avoid circular deps ──────────────────────────────────
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()

    # ── Gather student stats ──────────────────────────────────────────────────
    enrollments      = Enrollment.objects.filter(student=user)
    completed_enroll = enrollments.filter(status='completed')
    active_enroll    = enrollments.filter(status='active')

    lessons_completed = LessonProgress.objects.filter(
        enrollment__student=user, is_completed=True
    )
    total_lessons_done = lessons_completed.count()

    submissions = AssignmentSubmission.objects.filter(student=user, status='graded')
    total_subs  = submissions.count()
    on_time_subs = submissions.filter(
        submitted_at__lte=models.F('assignment__due_date')
    ).count() if submissions.exists() else 0

    quiz_attempts   = QuizAttempt.objects.filter(student=user, is_completed=True)
    passed_quizzes  = quiz_attempts.filter(passed=True)
    perfect_quizzes = quiz_attempts.filter(percentage=100)

    discussions = Discussion.objects.filter(author=user)
    replies     = DiscussionReply.objects.filter(author=user)

    total_courses_enrolled  = enrollments.count()
    total_courses_completed = completed_enroll.count()

    # ── 1. First Lesson ───────────────────────────────────────────────────────
    if total_lessons_done >= 1:
        _award('first-lesson', 'First Step',
               'Complete your first lesson', 'play-circle', 'blue', 5,
               'Completed first lesson')

    # ── 2. Lesson milestones ──────────────────────────────────────────────────
    for count, slug, name, pts in [
        (10,  'lessons-10',  'Lesson Learner',   10),
        (25,  'lessons-25',  'Dedicated Student', 15),
        (50,  'lessons-50',  'Knowledge Seeker',  20),
        (100, 'lessons-100', 'Century Learner',   30),
    ]:
        if total_lessons_done >= count:
            _award(slug, name, f'Complete {count} lessons',
                   'book-open', 'blue', pts, f'Completed {count} lessons')

    # ── 3. First Course Enrolled ──────────────────────────────────────────────
    if total_courses_enrolled >= 1:
        _award('first-enrollment', 'First Course Enrolled',
               'Enroll in your first course', 'bookmark', 'purple', 5,
               'Enrolled in first course')

    # ── 4. First Course Completed ─────────────────────────────────────────────
    if total_courses_completed >= 1:
        _award('first-course', 'First Course Completed',
               'Complete your first course', 'graduation-cap', 'green', 20,
               'Completed first course')

    # ── 5. Course milestones ──────────────────────────────────────────────────
    for count, slug, name, pts in [
        (3,  'courses-3',  'Course Collector',  20),
        (5,  'courses-5',  'Marathon Learner',  30),
        (10, 'courses-10', 'Super Achiever',    50),
    ]:
        if total_courses_completed >= count:
            _award(slug, name, f'Complete {count} or more courses',
                   'graduation-cap', 'gold', pts, f'Completed {count} courses')

    # ── 6. Assignment milestones ──────────────────────────────────────────────
    if total_subs >= 1:
        _award('first-assignment', 'First Submission',
               'Submit your first assignment', 'file-text', 'orange', 5,
               'First assignment submitted')

    for count, slug, name, pts in [
        (5,  'assignments-5',  'Assignment Starter', 10),
        (10, 'assignments-10', 'Hard Worker',        15),
        (20, 'assignments-20', 'Assignment Pro',     25),
        (50, 'assignments-50', 'Assignment Master',  40),
    ]:
        if total_subs >= count:
            _award(slug, name, f'Submit {count} assignments on time',
                   'file-check', 'orange', pts, f'Submitted {count} assignments')

    # ── 7. Perfect assignment score ───────────────────────────────────────────
    perfect_subs = [s for s in submissions if s.score == s.assignment.max_score]
    if perfect_subs:
        _award('perfect-score', 'Perfect Score',
               'Achieve 100% on a course final assessment', 'star', 'gold', 20,
               'Scored 100% on an assignment')

    # ── 8. Quiz milestones ────────────────────────────────────────────────────
    if quiz_attempts.exists():
        _award('first-quiz', 'Quiz Taker',
               'Complete your first quiz', 'help-circle', 'teal', 5,
               'Completed first quiz')

    for count, slug, name, pts in [
        (5,  'quizzes-5',  'Quiz Regular',  10),
        (10, 'quizzes-10', 'Quiz Veteran',  20),
        (25, 'quizzes-25', 'Quiz Master',   35),
    ]:
        if passed_quizzes.count() >= count:
            _award(slug, name, f'Pass {count} quizzes',
                   'check-circle', 'teal', pts, f'Passed {count} quizzes')

    if perfect_quizzes.exists():
        _award('quiz-perfect', 'Quiz Perfectionist',
               'Score 100% on a quiz', 'award', 'gold', 15,
               'Scored 100% on a quiz')

    if perfect_quizzes.count() >= 5:
        _award('quiz-perfect-5', 'Quiz Master',
               'Score 100% on 5 quizzes', 'award', 'gold', 30,
               'Scored 100% on 5 quizzes')

    # ── 9. Community ─────────────────────────────────────────────────────────
    if discussions.exists():
        _award('first-post', 'Conversationalist',
               'Start your first discussion', 'message-circle', 'purple', 5,
               'Started first discussion')

    total_community = discussions.count() + replies.count()
    for count, slug, name, pts in [
        (10, 'community-10', 'Community Helper',  15),
        (25, 'community-25', 'Community Star',    25),
        (50, 'community-50', 'Community Legend',  40),
    ]:
        if total_community >= count:
            _award(slug, name,
                   f'Contribute {count} discussions or replies',
                   'users', 'purple', pts,
                   f'{count} community contributions')

    # ── 10. Early Bird — lesson completed before 8 AM ─────────────────────────
    early_lessons = lessons_completed.filter(
        completed_at__hour__lt=8
    )
    if early_lessons.count() >= 7:
        _award('early-bird', 'Early Bird',
               'Complete lessons before 8 AM for 7 consecutive days',
               'sun', 'yellow', 20,
               'Early morning learner')

    # ── 11. Quick Learner — completed a course in under 7 days ───────────────
    for enrollment in completed_enroll:
        if enrollment.completed_at and enrollment.enrolled_at:
            days = (enrollment.completed_at - enrollment.enrolled_at).days
            if days <= 7:
                _award('quick-learner', 'Quick Learner',
                       'Complete a course in under 7 days',
                       'zap', 'yellow', 25,
                       'Finished a course in under 7 days')
                break

    # ── 12. Streak — 7 days consecutive lesson activity ──────────────────────
    activity_dates = set(
        lessons_completed
        .values_list('completed_at__date', flat=True)
        .distinct()
    )
    streak = 0
    check_date = now.date()
    while check_date in activity_dates:
        streak += 1
        check_date -= timedelta(days=1)

    if streak >= 7:
        _award('streak-7', '7-Day Streak',
               'Learn every day for 7 days in a row', 'flame', 'red', 20,
               f'{streak}-day learning streak')
    if streak >= 30:
        _award('streak-30', '30-Day Streak',
               'Learn every day for 30 days in a row', 'flame', 'red', 50,
               f'{streak}-day learning streak')

    # ── 13. Certificate earned ────────────────────────────────────────────────
    certs = Certificate.objects.filter(student=user)
    if certs.exists():
        _award('first-certificate', 'Certified!',
               'Earn your first certificate', 'award', 'green', 30,
               'First certificate earned')
    if certs.count() >= 3:
        _award('certificates-3', 'Certificate Collector',
               'Earn 3 certificates', 'award', 'green', 50,
               '3 certificates earned')