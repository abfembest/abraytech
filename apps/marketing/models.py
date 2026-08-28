from django.contrib.auth.models import User
from django.db import models


class Lead(models.Model):
    """A prospect a marketer has recorded and is (or was) pursuing."""

    SOURCE_CHOICES = [
        ('referral', 'Referral'),
        ('social_media', 'Social Media'),
        ('event', 'Event'),
        ('cold_outreach', 'Cold Outreach'),
        ('website', 'Website'),
        ('advertisement', 'Advertisement'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('qualified', 'Qualified'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]

    marketer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leads')
    name = models.CharField(max_length=200)
    organization = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='other')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        indexes = [
            models.Index(fields=['marketer', 'status']),
        ]

    def __str__(self):
        return f"{self.name}{f' ({self.organization})' if self.organization else ''}"


class LeadActivity(models.Model):
    """Timeline entry — one row per note/status change, so admin has an
    actual activity trail to monitor, not just a static lead list."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    marketer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    note = models.TextField()
    status_at_time = models.CharField(max_length=20, choices=Lead.STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Lead Activity'
        verbose_name_plural = 'Lead Activities'

    def __str__(self):
        return f"{self.lead.name} — {self.get_status_at_time_display()} ({self.created_at:%Y-%m-%d})"


class LeadMessage(models.Model):
    """Admin<->marketer chat. One channel per marketer (`marketer` = whose
    channel this is, regardless of who wrote the message) rather than a
    sender/recipient pair — a marketer has exactly one conversation admin
    reads/replies into, no recipient-picker UI needed. `lead` is optional:
    set it to scope the message to that lead ("over a lead"); leave it
    blank for general chat ("or whatever")."""

    marketer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_channel_messages')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Lead Message'
        verbose_name_plural = 'Lead Messages'
        indexes = [
            models.Index(fields=['marketer', 'lead', 'created_at']),
        ]

    def __str__(self):
        return f"{self.sender.username}: {self.body[:40]}"
