from django.shortcuts import render

# Create your views here.
# portfolio/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import Project


def project_detail_or_selector(request, slug=None):
    """If slug is valid → show project detail. Else → show project selector with dynamic loading."""
    if slug:
        try:
            project = Project.objects.prefetch_related('dashboard_images').get(slug=slug)
            # Render full project detail page (existing layered slider)
            images_data = [
                {
                    'url': img.image.url,
                    'title': img.title,
                    'summary': img.summary,
                    'order': img.order,
                }
                for img in project.dashboard_images.all().order_by('order')
            ]
            context = {
                'project': project,
                'images_data': images_data,
                'total_images': len(images_data),
                'is_selector_mode': False,   # flag for template
            }
            return render(request, 'portfolio/project_detail.html', context)
        except Project.DoesNotExist:
            # Invalid slug – fall through to selector mode
            pass

    # Selector mode: no slug or invalid slug
    all_projects = Project.objects.all().prefetch_related('dashboard_images')
    context = {
        'all_projects': all_projects,
        'is_selector_mode': True,
    }
    return render(request, 'portfolio/project_detail.html', context)


def project_api_data(request, slug):
    """API endpoint that returns full image URLs."""
    project = get_object_or_404(Project, slug=slug)
    
    # Build list with absolute image URLs
    images = []
    for img in project.dashboard_images.all().order_by('order'):
        images.append({
            'image': request.build_absolute_uri(img.image.url),  # Full URL (e.g., http://.../media/dashboard_images/...)
            'title': img.title,
            'summary': img.summary,
            'order': img.order,
        })
    
    return JsonResponse({
        'project': {
            'name': project.name,
            'description': project.description,
            'client': project.client,
            'technologies': project.technologies,
        },
        'images': images,
    })