from django.shortcuts import render

# Create your views here.
# portfolio/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import Project

def project_detail(request, slug):
    """Display project with all dashboard images for the layered slider."""
    project = get_object_or_404(Project, slug=slug)
    dashboard_images = project.dashboard_images.all().prefetch_related('project')
    
    # Prepare image data for JavaScript (lazy loading ready)
    images_data = []
    for img in dashboard_images:
        images_data.append({
            'url': img.image.url,
            'title': img.title,
            'summary': img.summary,
            'order': img.order,
        })
    
    context = {
        'project': project,
        'images_data': images_data,
        'total_images': len(images_data),
    }
    return render(request, 'portfolio/project_detail.html', context)

def project_api_data(request, slug):
    """Optional API endpoint for async data fetching (used for dynamic updates)."""
    project = get_object_or_404(Project, slug=slug)
    images = project.dashboard_images.all().values('image', 'title', 'summary', 'order')
    return JsonResponse({
        'project': {
            'name': project.name,
            'description': project.description,
        },
        'images': list(images),
    })