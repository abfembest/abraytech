from django.db import models
from django.db import models
from django.utils import timezone

class ChatSession(models.Model):
    first_name = models.CharField(max_length=100)
    email = models.EmailField()
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def close(self):
        self.is_active = False
        self.save()

    def __str__(self):
        return f"Session {self.id} - {self.first_name}"

class ChatMessage(models.Model):
    SENDER_CHOICES = [('user', 'User'), ('bot', 'Bot')]
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

class IntentResponse(models.Model):
    intent = models.CharField(max_length=100, unique=True)
    response_text = models.TextField(help_text="Use \n for line breaks")

    def __str__(self):
        return self.intent
