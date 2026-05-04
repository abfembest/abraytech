from django.db import models
from django.urls import reverse

class Project(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    client = models.CharField(max_length=200, blank=True)
    technologies = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('portfolio:project_detail', kwargs={'slug': self.slug})

class DashboardImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='dashboard_images')
    image = models.ImageField(upload_to='dashboard_images/%Y/%m/')
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, help_text="Brief description of this dashboard screen")
    order = models.PositiveIntegerField(default=0, help_text="Display order (ascending)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        unique_together = [['project', 'order']]

    def __str__(self):
        return f"{self.project.name} - {self.title}"