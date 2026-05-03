from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from eduweb.models import Faculty, Department, Program, BlogPost


# ──────────────────────────────────────────────
# Helper: MELBAC faculty slugs (subset of all faculties)
MELBAC_FACULTY_SLUGS = [
    'faculty-of-christian-education',
    'faculty-of-church-management-administration',
    'faculty-of-arts',
]
# ──────────────────────────────────────────────


def index(request):
    """MELBAC public homepage."""
    faculties = (
        Faculty.objects
        .filter(slug__in=MELBAC_FACULTY_SLUGS, is_active=True)
        .prefetch_related('departments__programs')
        .order_by('display_order')
    )
    recent_posts = (
        BlogPost.objects
        .filter(status='published')
        .select_related('author')
        .order_by('-publish_date')[:6]
    )
    context = {
        'faculties':     faculties,
        'recent_posts':  recent_posts,
    }
    return render(request, 'melbac/index.html', context)


def about(request):
    """MELBAC About page."""
    return render(request, 'melbac/about.html', {})


def academics(request):
    """Academics overview — faculties, departments, programs, calendar."""
    faculties = (
        Faculty.objects
        .filter(slug__in=MELBAC_FACULTY_SLUGS, is_active=True)
        .prefetch_related('departments', 'departments__programs')
        .order_by('display_order')
    )
    return render(request, 'melbac/academics.html', {'faculties': faculties})


def admissions(request):
    """
    Admissions page — all degree levels, requirements, programs.
    No DB query needed; content is static/template-driven.
    """
    return render(request, 'melbac/admissions.html', {})


def activities(request):
    """Student Activities page."""
    return render(request, 'melbac/activities.html', {})


def contact(request):
    """Contact page — renders form and handles POST submission."""
    from eduweb.models import ContactMessage

    if request.method == 'POST':
        name    = request.POST.get('name', '').strip()
        email   = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', 'other')
        message = request.POST.get('message', '').strip()

        if name and email and message:
            ContactMessage.objects.create(
                user=request.user if request.user.is_authenticated else None,
                name=name,
                email=email,
                subject=subject,
                message=message,
            )
            messages.success(request, 'Your message has been received. We will respond shortly.')
            return redirect('melbac:contact')
        else:
            messages.error(request, 'Please fill in all required fields.')

    return render(request, 'melbac/contact.html', {})


def blog_list(request):
    """MELBAC blog listing."""
    posts = (
        BlogPost.objects
        .filter(status='published')
        .select_related('author')
        .order_by('-publish_date')
    )
    return render(request, 'melbac/blog.html', {'posts': posts})


def blog_detail(request, slug):
    """
    Blog post detail page.
    Fetches the post by slug, plus prev/next navigation posts
    and 5 recent posts for the sidebar.
    """
    post = get_object_or_404(
        BlogPost.objects.select_related('author'),
        slug=slug,
        status='published',
    )

    # Previous post (older — lower publish_date)
    prev_post = (
        BlogPost.objects
        .filter(status='published', publish_date__lt=post.publish_date)
        .order_by('-publish_date')
        .first()
    )

    # Next post (newer — higher publish_date)
    next_post = (
        BlogPost.objects
        .filter(status='published', publish_date__gt=post.publish_date)
        .order_by('publish_date')
        .first()
    )

    # Recent posts for sidebar (exclude current)
    recent_posts = (
        BlogPost.objects
        .filter(status='published')
        .exclude(slug=slug)
        .order_by('-publish_date')[:5]
    )

    context = {
        'post':         post,
        'prev_post':    prev_post,
        'next_post':    next_post,
        'recent_posts': recent_posts,
    }
    return render(request, 'melbac/blog_detail.html', context)