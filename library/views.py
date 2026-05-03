"""
library/views.py
All category/slug lookups are driven by the DB choices on LibraryItem.
CATEGORY_META is kept only for UI decoration (gradient, icon, description fallback).
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import FileResponse, Http404
from django.utils.text import slugify
from django.conf import settings

from eduweb.models import LibraryItem


# ── UI decoration only — NOT the source of truth for slugs/names ─────────────
CATEGORY_META = {
    'Books': {
        'description': (
            'A growing collection of theological, biblical, and Christian living books '
            'freely available for study and edification.'
        ),
        'gradient': 'from-gospel-50/60 to-gospel-100/40',
        'icon_svg': (
            '<svg class="w-5 h-5 text-gospel-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            'd="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13'
            'C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13'
            'C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13'
            'C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>'
        ),
    },
    'Periodicals': {
        'description': (
            'Academic and evangelical journals spanning biblical studies, theology, '
            'church history, and missiology.'
        ),
        'gradient': 'from-gold-100/60 to-gold-50/40',
        'icon_svg': (
            '<svg class="w-5 h-5 text-gold-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            'd="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7'
            'm2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"/></svg>'
        ),
    },
    'References': {
        'description': (
            'Commentaries, Bible notes, dictionaries, and theology references '
            'for in-depth biblical research.'
        ),
        'gradient': 'from-blue-50/60 to-blue-100/40',
        'icon_svg': (
            '<svg class="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            'd="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2'
            'M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>'
        ),
    },
    'Other': {
        'description': 'Miscellaneous resources, multimedia, and supplementary study materials.',
        'gradient': 'from-neutral-100/60 to-neutral-50/40',
        'icon_svg': (
            '<svg class="w-5 h-5 text-neutral-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            'd="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1'
            'M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"/></svg>'
        ),
    },
}


def _base_qs(user):
    """Active items, with public-access filter for anonymous users."""
    qs = LibraryItem.objects.filter(is_active=True)
    if not user.is_authenticated:
        qs = qs.filter(access='public')
    return qs


def _slug_to_category(slug):
    """
    Derive the canonical category name from a URL slug.
    Uses the LibraryItem.CATEGORY_CHOICES so we never rely on hardcoded dict keys.
    """
    choices = dict(LibraryItem.CATEGORY_CHOICES)
    for name in choices:
        if slugify(name) == slug:
            return name
    return None


def _category_slug(name):
    """Return the URL slug for a given category name."""
    return slugify(name)


def _nav_categories(user):
    """
    Returns a list of {name, slug} dicts for ALL active categories in the DB.
    Used to build dynamic nav links in the base template via context_processor
    or passed directly to each view. Here we pass it from each view.
    """
    qs = _base_qs(user)
    rows = (
        qs.values('category')
          .annotate(count=Count('id'))
          .order_by('category')
    )
    return [
        {'name': r['category'], 'slug': _category_slug(r['category']), 'count': r['count']}
        for r in rows
    ]


# ── Views ─────────────────────────────────────────────────────────────────────

def home(request):
    """
    Library landing — hero stats, featured shelf, category cards, recent additions.
    """
    qs = _base_qs(request.user)

    cat_rows = (
        qs.values('category')
          .annotate(count=Count('id'))
          .order_by('category')
    )

    categories = []
    for row in cat_rows:
        cat_name = row['category']
        cat_qs   = qs.filter(category=cat_name)
        meta     = CATEGORY_META.get(cat_name, {})

        top_subs = list(
            cat_qs.values_list('subcategory', flat=True)
                  .annotate(n=Count('id'))
                  .order_by('-n')[:3]
        )

        categories.append({
            'name':              cat_name,
            'slug':              _category_slug(cat_name),
            'count':             row['count'],
            'description':       meta.get('description', ''),
            'gradient':          meta.get('gradient', 'from-gospel-50 to-neutral-100'),
            'icon':              meta.get('icon_svg', ''),
            'top_subcategories': top_subs,
        })

    stats = [{'label': 'Total Resources', 'count': qs.count()}]
    for row in cat_rows:
        stats.append({'label': row['category'], 'count': row['count']})

    featured_items = qs.filter(featured=True).order_by('order', 'title')[:6]
    recent_items   = qs.order_by('-created_at')[:10]

    return render(request, 'library/home.html', {
        'categories':     categories,
        'stats':          stats,
        'featured_items': featured_items,
        'recent_items':   recent_items,
        'nav_categories': _nav_categories(request.user),  # dynamic nav
    })


def category(request, category_slug):
    """
    Category listing, grouped by subcategory.
    """
    cat_name = _slug_to_category(category_slug)
    if not cat_name:
        raise Http404(f"Library category '{category_slug}' not found.")

    meta = CATEGORY_META.get(cat_name, {})
    qs   = _base_qs(request.user).filter(category=cat_name)

    q          = request.GET.get('q', '').strip()
    active_sub = request.GET.get('sub', 'all')

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(tags__icontains=q)
        )

    sub_rows = (
        _base_qs(request.user)
        .filter(category=cat_name)
        .values('subcategory')
        .annotate(count=Count('id'))
        .order_by('subcategory')
    )
    subcategories = [
        {
            'name':  r['subcategory'],
            'slug':  slugify(r['subcategory']),
            'count': r['count'],
        }
        for r in sub_rows
    ]

    if active_sub and active_sub != 'all':
        matched_name = next(
            (s['name'] for s in subcategories if s['slug'] == active_sub),
            None
        )
        if matched_name:
            qs = qs.filter(subcategory=matched_name)

    qs = qs.order_by('subcategory', 'order', 'title')
    total_count = qs.count()

    paginator  = Paginator(qs, 48)
    page_obj   = paginator.get_page(request.GET.get('page'))
    page_items = list(page_obj.object_list)

    groups_dict = {}
    for item in page_items:
        sub = item.subcategory
        if sub not in groups_dict:
            groups_dict[sub] = {'name': sub, 'slug': slugify(sub), 'items': []}
        groups_dict[sub]['items'].append(item)
    groups = list(groups_dict.values())

    return render(request, 'library/category.html', {
        'category_name':        cat_name,
        'category_slug':        category_slug,
        'category_description': meta.get('description', ''),
        'subcategories':        subcategories,
        'active_sub':           active_sub,
        'groups':               groups,
        'total_count':          total_count,
        'page_obj':             page_obj,
        'nav_categories':       _nav_categories(request.user),  # dynamic nav
    })


def detail(request, slug):
    """Single item detail — metadata, PDF viewer, download button."""
    qs   = LibraryItem.objects.filter(is_active=True)
    item = get_object_or_404(qs, slug=slug)

    item.increment_views()

    related_items = (
        _base_qs(request.user)
        .filter(category=item.category, subcategory=item.subcategory)
        .exclude(pk=item.pk)
        .order_by('order', 'title')[:4]
    )

    category_slug = _category_slug(item.category)

    return render(request, 'library/detail.html', {
        'item':           item,
        'related_items':  related_items,
        'category_slug':  category_slug,
        'nav_categories': _nav_categories(request.user),  # dynamic nav
    })


def download(request, slug):
    """Serve file as attachment and increment counter."""
    qs   = LibraryItem.objects.filter(is_active=True)
    item = get_object_or_404(qs, slug=slug)

    if item.access == 'members' and not request.user.is_authenticated:
        login_url = getattr(settings, 'LOGIN_URL', '/accounts/login/')
        return redirect(f"{login_url}?next={request.path}")

    if not item.allow_download or not item.has_file():
        raise Http404("File not available for download.")

    item.increment_downloads()

    try:
        filename = item.file.name.split('/')[-1]
        return FileResponse(item.file.open('rb'), as_attachment=True, filename=filename)
    except FileNotFoundError:
        raise Http404("File not found on server.")


def search(request):
    """
    Global library search across all categories.
    ?q= ?cat= ?sort=relevance|newest|title ?page=
    """
    q          = request.GET.get('q', '').strip()
    active_cat = request.GET.get('cat', '')
    sort       = request.GET.get('sort', 'relevance')

    qs = _base_qs(request.user)

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(subcategory__icontains=q) |
            Q(description__icontains=q) |
            Q(tags__icontains=q) |
            Q(publisher__icontains=q)
        )

    if active_cat:
        qs = qs.filter(category=active_cat)

    if sort == 'newest':
        qs = qs.order_by('-created_at')
    elif sort == 'title':
        qs = qs.order_by('title')
    else:
        qs = qs.order_by('category', 'subcategory', 'order', 'title')

    search_base = _base_qs(request.user)
    if q:
        search_base = search_base.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(tags__icontains=q)
        )
    category_counts = (
        search_base
        .values('category')
        .annotate(count=Count('id'))
        .order_by('category')
    )

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'library/search.html', {
        'query':           q,
        'active_cat':      active_cat,
        'sort':            sort,
        'page_obj':        page_obj,
        'category_counts': category_counts,
        'nav_categories':  _nav_categories(request.user),  # dynamic nav
    })