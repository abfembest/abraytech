"""
support/models.py

Uses eduweb's SupportTicket and TicketReply as the core ticket models.
Adds: SLA policies, departments, KB, FAQ, canned responses, chat sessions,
      agent profiles, announcements, audit log, and a lightweight
      SupportTicketExtra OneToOne for extra fields (SLA, tags, source, etc.)
"""
import uuid
import os
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Avg, Count

# Import the existing eduweb ticket models
from apps.eduweb.models import SupportTicket, TicketReply


# ─────────────────────────────────────────────────────────────────────────────
# Shared choices (used across KB, canned responses, chat)
# ─────────────────────────────────────────────────────────────────────────────

TICKET_CATEGORY_CHOICES = [
    ('technical', 'Technical Issue'),
    ('account', 'Account Access'),
    ('course', 'Course Content'),
    ('payment', 'Payment/Billing'),
    ('other', 'Other'),
]

SLA_BREACH_STATUS = [
    ('within', 'Within SLA'),
    ('at_risk', 'At Risk'),
    ('breached', 'Breached'),
]

KB_STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('published', 'Published'),
    ('archived', 'Archived'),
]

CHAT_STATUS_CHOICES = [
    ('waiting', 'Waiting'),
    ('active', 'Active'),
    ('ended', 'Ended'),
    ('missed', 'Missed'),
]

SATISFACTION_CHOICES = [
    (1, '1 – Very Poor'),
    (2, '2 – Poor'),
    (3, '3 – Neutral'),
    (4, '4 – Good'),
    (5, '5 – Excellent'),
]

ESCALATION_REASON_CHOICES = [
    ('sla_breach', 'SLA Breach'),
    ('complexity', 'Technical Complexity'),
    ('vip', 'VIP / Priority Student'),
    ('complaint', 'Formal Complaint'),
    ('management', 'Escalated to Management'),
    ('other', 'Other'),
]


# ─────────────────────────────────────────────────────────────────────────────
# SLA Policy
# ─────────────────────────────────────────────────────────────────────────────

class SLAPolicy(models.Model):
    """Defines response and resolution time targets per priority level."""
    name = models.CharField(max_length=100, unique=True)
    priority = models.CharField(max_length=20, choices=SupportTicket.PRIORITY_CHOICES, unique=True)
    first_response_hours = models.PositiveSmallIntegerField(default=4)
    resolution_hours = models.PositiveSmallIntegerField(default=24)
    escalation_hours = models.PositiveSmallIntegerField(default=8)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['resolution_hours']
        verbose_name = "SLA Policy"
        verbose_name_plural = "SLA Policies"

    def __str__(self):
        return f"{self.name} ({self.priority})"


# ─────────────────────────────────────────────────────────────────────────────
# Support Department
# ─────────────────────────────────────────────────────────────────────────────

class SupportDepartment(models.Model):
    """A team/unit within the support centre (e.g. Finance, Technical, Admissions)."""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    icon = models.CharField(max_length=60, default='fas fa-headset')
    head = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='headed_departments'
    )
    members = models.ManyToManyField(User, blank=True, related_name='support_departments')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def open_ticket_count(self):
        return SupportTicketExtra.objects.filter(
            department=self,
            ticket__status__in=['open', 'in_progress']
        ).count()


# ─────────────────────────────────────────────────────────────────────────────
# SupportTicketExtra — extends eduweb SupportTicket with SLA + dept + extras
# ─────────────────────────────────────────────────────────────────────────────

def ticket_attachment_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1]
    return f"support/attachments/{instance.ticket.ticket_id}/{uuid.uuid4().hex}.{ext}"


class SupportTicketExtra(models.Model):
    """
    OneToOne extension of eduweb.SupportTicket.
    Stores SLA tracking, department assignment, tags, source, and escalation state
    without modifying the eduweb app.
    """
    SOURCE_CHOICES = [
        ('portal', 'Portal'),
        ('email', 'Email'),
        ('chat', 'Live Chat'),
        ('phone', 'Phone'),
        ('walk_in', 'Walk-in'),
        ('api', 'API'),
    ]

    ticket = models.OneToOneField(
        SupportTicket, on_delete=models.CASCADE, related_name='extra'
    )
    department = models.ForeignKey(
        SupportDepartment, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dept_tickets'
    )
    sla_policy = models.ForeignKey(
        SLAPolicy, null=True, blank=True, on_delete=models.SET_NULL
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='portal')
    tags = models.CharField(max_length=300, blank=True, help_text="Comma-separated tags")
    related_course = models.CharField(max_length=200, blank=True)
    internal_notes = models.TextField(blank=True, help_text="Visible to staff only")
    is_escalated = models.BooleanField(default=False)
    escalation_level = models.PositiveSmallIntegerField(default=0)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    # SLA tracking
    first_response_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, help_text="SLA resolution deadline")
    sla_breach_status = models.CharField(max_length=20, choices=SLA_BREACH_STATUS, default='within')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ticket Extra"
        verbose_name_plural = "Ticket Extras"

    def __str__(self):
        return f"Extra for {self.ticket.ticket_id}"

    def save(self, *args, **kwargs):
        if not self.due_at and self.sla_policy:
            self.due_at = timezone.now() + timezone.timedelta(
                hours=self.sla_policy.resolution_hours
            )
        super().save(*args, **kwargs)

    @property
    def sla_status(self):
        if not self.due_at or self.ticket.status in ['resolved', 'closed']:
            return 'within'
        now = timezone.now()
        time_left = (self.due_at - now).total_seconds() / 3600
        if time_left < 0:
            return 'breached'
        elif time_left < 2:
            return 'at_risk'
        return 'within'

    @property
    def is_overdue(self):
        return (
            self.due_at
            and timezone.now() > self.due_at
            and self.ticket.status not in ['resolved', 'closed']
        )

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Ticket Attachment
# ─────────────────────────────────────────────────────────────────────────────

class TicketAttachment(models.Model):
    """File attachments on eduweb SupportTickets or their replies."""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='attachments')
    reply = models.ForeignKey(
        TicketReply, null=True, blank=True,
        on_delete=models.CASCADE, related_name='attachments'
    )
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(
        upload_to=ticket_attachment_path,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'gif', 'xlsx', 'csv', 'txt', 'zip']
        )]
    )
    original_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if self.file and self.file.size > 10 * 1024 * 1024:
            raise ValidationError("Attachment cannot exceed 10 MB.")

    def __str__(self):
        return self.original_name

    @property
    def file_size_display(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size // 1024} KB"
        return f"{round(size / (1024*1024), 1)} MB"


# ─────────────────────────────────────────────────────────────────────────────
# Ticket History
# ─────────────────────────────────────────────────────────────────────────────

class TicketHistory(models.Model):
    """Immutable audit trail for eduweb SupportTicket state changes."""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    field_name = models.CharField(max_length=50)
    old_value = models.CharField(max_length=200, blank=True)
    new_value = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("TicketHistory records are immutable.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket.ticket_id}: {self.field_name} changed"


# ─────────────────────────────────────────────────────────────────────────────
# Escalation
# ─────────────────────────────────────────────────────────────────────────────

class TicketEscalation(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='escalations')
    escalated_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='escalated_tickets'
    )
    escalated_to = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='received_escalations'
    )
    reason = models.CharField(max_length=30, choices=ESCALATION_REASON_CHOICES)
    notes = models.TextField(blank=True)
    level = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Escalation L{self.level} for {self.ticket.ticket_id}"


# ─────────────────────────────────────────────────────────────────────────────
# CSAT Feedback
# ─────────────────────────────────────────────────────────────────────────────

class TicketFeedback(models.Model):
    ticket = models.OneToOneField(SupportTicket, on_delete=models.CASCADE, related_name='feedback')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=SATISFACTION_CHOICES)
    comment = models.TextField(blank=True)
    response_speed_rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=SATISFACTION_CHOICES)
    agent_helpfulness_rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=SATISFACTION_CHOICES)
    would_recommend = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.ticket.ticket_id} — {self.rating}/5"


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

def kb_image_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1]
    return f"support/kb/{uuid.uuid4().hex}.{ext}"


class KBCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fa-book')
    color = models.CharField(max_length=20, default='blue')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "KB Category"
        verbose_name_plural = "KB Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def article_count(self):
        return self.articles.filter(status='published').count()


class KBArticle(models.Model):
    category = models.ForeignKey(KBCategory, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=250)
    slug = models.SlugField(unique=True, blank=True, max_length=270)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    cover_image = models.ImageField(upload_to=kb_image_path, blank=True, null=True)
    status = models.CharField(max_length=20, choices=KB_STATUS_CHOICES, default='draft')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kb_articles')
    tags = models.CharField(max_length=300, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    related_articles = models.ManyToManyField('self', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_pinned', '-published_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:260]
            self.slug = base
            counter = 1
            while KBArticle.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{counter}"
                counter += 1
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def helpfulness_score(self):
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return None
        return round((self.helpful_count / total) * 100)

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# FAQ
# ─────────────────────────────────────────────────────────────────────────────

class FAQCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    icon = models.CharField(max_length=50, default='fa-question-circle')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "FAQ Category"
        verbose_name_plural = "FAQ Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class FAQ(models.Model):
    category = models.ForeignKey(FAQCategory, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=350)
    answer = models.TextField()
    is_published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'order']

    def __str__(self):
        return self.question[:80]


# ─────────────────────────────────────────────────────────────────────────────
# Canned Responses
# ─────────────────────────────────────────────────────────────────────────────

class CannedResponse(models.Model):
    title = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=50, choices=TICKET_CATEGORY_CHOICES, blank=True)
    body = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


# ─────────────────────────────────────────────────────────────────────────────
# Live Chat
# ─────────────────────────────────────────────────────────────────────────────

class ChatSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    agent = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='handled_chats'
    )
    status = models.CharField(max_length=20, choices=CHAT_STATUS_CHOICES, default='waiting')
    subject = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=50, choices=TICKET_CATEGORY_CHOICES, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_comment = models.TextField(blank=True)
    wait_time_seconds = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    converted_to_ticket = models.ForeignKey(
        SupportTicket, null=True, blank=True, on_delete=models.SET_NULL
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Chat {self.session_id} — {self.student}"


class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


# ─────────────────────────────────────────────────────────────────────────────
# Agent Profile
# ─────────────────────────────────────────────────────────────────────────────

class AgentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agent_profile')
    department = models.ForeignKey(
        SupportDepartment, null=True, blank=True, on_delete=models.SET_NULL
    )
    is_available = models.BooleanField(default=True)
    max_tickets = models.PositiveSmallIntegerField(default=20)
    specializations = models.CharField(max_length=500, blank=True)
    bio = models.TextField(blank=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_resolved = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Agent: {self.user.get_full_name() or self.user.username}"

    @property
    def current_load(self):
        return SupportTicket.objects.filter(
            assigned_to=self.user,
            status__in=['open', 'in_progress']
        ).count()

    @property
    def load_percentage(self):
        if self.max_tickets == 0:
            return 100
        return min(100, round((self.current_load / self.max_tickets) * 100))


# ─────────────────────────────────────────────────────────────────────────────
# Announcements
# ─────────────────────────────────────────────────────────────────────────────

class SupportAnnouncement(models.Model):
    title = models.CharField(max_length=250)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    target_role = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        return self.expires_at and timezone.now() > self.expires_at


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────

class SupportAuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("SupportAuditLog is immutable.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.actor} — {self.action} at {self.created_at}"
