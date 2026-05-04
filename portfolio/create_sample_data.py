# Sample management command to create initial data (optional)
# python manage.py shell -c "exec(open('create_sample_data.py').read())"
"""
create_sample_data.py
from portfolio.models import Project, DashboardImage
from django.core.files.uploadedfile import SimpleUploadedFile
import requests
from io import BytesIO

project = Project.objects.create(
    name="DigitalMedics AI Platform",
    slug="digitalmedics",
    description="Intelligent healthcare dashboard with real-time patient analytics and predictive insights.",
    client="MediHealth Systems",
    technologies="React, Django, TensorFlow, Tailwind"
)

# Download sample images (replace with actual image URLs or use local)
sample_urls = [
    "https://placehold.co/1200x675/3b82f6/white?text=Dashboard+Overview",
    "https://placehold.co/1200x675/8b5cf6/white?text=Patient+Analytics",
    "https://placehold.co/1200x675/10b981/white?text=Revenue+Metrics"
]

for idx, url in enumerate(sample_urls):
    response = requests.get(url)
    img_name = f"dashboard_{idx}.jpg"
    img_file = SimpleUploadedFile(img_name, response.content, content_type='image/jpeg')
    DashboardImage.objects.create(
        project=project,
        image=img_file,
        title=f"Screen {idx+1}: {'Overview' if idx==0 else 'Analytics' if idx==1 else 'Reports'}",
        summary=f"This dashboard provides {['real-time stats', 'patient insights', 'financial KPIs'][idx]} for informed decision making.",
        order=idx
    )
print("Sample project created!")
"""