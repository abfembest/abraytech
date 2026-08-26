"""
Search-engine / AI-crawler discovery endpoints for the public site:
robots.txt, sitemap.xml, and llms.txt.

Kept out of views.py (already huge) since these are cross-app concerns —
sitemap.xml in particular reaches into apps.store and apps.eduweb models
that have nothing else to do with each other.

No django.contrib.sitemaps / django.contrib.sites dependency on purpose:
this project doesn't run the Sites framework (see get_current_site usage
elsewhere, which falls back to RequestSite), and hand-rolling ~40 lines of
XML is simpler than wiring up a framework whose main value — multi-site
support — this single-site project doesn't need.
"""
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from .models import BlogPost, BlogCategory, Program, Service, Project, LibraryItem


def _abs(request, path):
    return request.build_absolute_uri(path)


def robots_txt(request):
    """Allow public marketing/store/blog/program content; keep every
    authenticated portal, checkout/account flow, and API endpoint out of
    the crawl — those pages are either behind login (useless to a crawler)
    or duplicate/transactional (cart, checkout, order confirmation)."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        "Disallow: /admin/",
        "Disallow: /management/",
        "Disallow: /student/",
        "Disallow: /instructor/",
        "Disallow: /finance/",
        "Disallow: /payment/",
        "Disallow: /chatbot/",
        "Disallow: /support/",
        "",
        "Disallow: /auth/",
        "Disallow: /admission/register/",
        "Disallow: /verify-otp/",
        "Disallow: /verify-email/",
        "Disallow: /forgot-password/",
        "Disallow: /reset-password/",
        "Disallow: /account/",
        "Disallow: /my-profile/",
        "Disallow: /my-settings/",
        "Disallow: /application_status/",
        "Disallow: /payments/",
        "Disallow: /api/",
        "",
        "Disallow: /store/cart/",
        "Disallow: /store/checkout/",
        "Disallow: /store/orders/",
        "Disallow: /store/account/",
        "",
        "Disallow: /library/*/download/",
        "",
        f"Sitemap: {_abs(request, reverse('eduweb:sitemap_xml'))}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


# (path, changefreq, priority) — every static (non-model-driven) public page.
_STATIC_URLS = [
    ("eduweb:index", "daily", "1.0"),
    ("eduweb:about", "monthly", "0.8"),
    ("eduweb:all_programs", "weekly", "0.8"),
    ("eduweb:admission_requirement", "monthly", "0.6"),
    ("eduweb:research", "monthly", "0.5"),
    ("eduweb:campus_life", "monthly", "0.5"),
    ("eduweb:blog", "daily", "0.7"),
    ("eduweb:services_list", "monthly", "0.8"),
    ("eduweb:industries_list", "monthly", "0.6"),
    ("eduweb:projects_list", "monthly", "0.7"),
    ("eduweb:consultation_booking", "monthly", "0.6"),
    ("eduweb:team", "monthly", "0.5"),
    ("eduweb:faq", "monthly", "0.6"),
    ("eduweb:careers", "weekly", "0.6"),
    ("eduweb:contact", "monthly", "0.7"),
    ("eduweb:privacy", "yearly", "0.2"),
    ("eduweb:terms", "yearly", "0.2"),
    ("eduweb:cookies", "yearly", "0.2"),
    ("store:store_list", "daily", "0.9"),
    ("library:home", "weekly", "0.5"),
]


def sitemap_xml(request):
    from apps.store.models import Product

    now = timezone.now().date().isoformat()
    entries = []

    for url_name, changefreq, priority in _STATIC_URLS:
        entries.append((reverse(url_name), now, changefreq, priority))

    for post in BlogPost.objects.filter(status="published").only("slug", "publish_date"):
        entries.append((
            reverse("eduweb:blog_detail", args=[post.slug]),
            post.publish_date.date().isoformat(),
            "monthly", "0.6",
        ))

    for cat in BlogCategory.objects.filter(is_active=True).only("slug"):
        entries.append((reverse("eduweb:blog_category", args=[cat.slug]), now, "weekly", "0.4"))

    for program in Program.objects.filter(is_active=True).only("slug"):
        entries.append((reverse("eduweb:program_detail", args=[program.slug]), now, "monthly", "0.7"))

    for service in Service.objects.filter(is_active=True).only("slug"):
        entries.append((reverse("eduweb:service_detail", args=[service.slug]), now, "monthly", "0.7"))

    for project in Project.objects.filter(is_active=True).only("slug"):
        entries.append((reverse("eduweb:project_detail", args=[project.slug]), now, "monthly", "0.6"))

    for product in Product.objects.filter(is_active=True).only("slug"):
        entries.append((reverse("store:product_detail", args=[product.slug]), now, "weekly", "0.7"))

    for item in LibraryItem.objects.filter(is_active=True, access="public").only("slug"):
        entries.append((reverse("library:detail", args=[item.slug]), now, "monthly", "0.4"))

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, changefreq, priority in entries:
        xml_parts.append(
            f"<url><loc>{_abs(request, path)}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>"
        )
    xml_parts.append("</urlset>")

    return HttpResponse("\n".join(xml_parts), content_type="application/xml")


def llms_txt(request):
    """The llms.txt convention (https://llmstxt.org) — a plain-Markdown
    briefing for AI assistants/agents (ChatGPT, Claude, Perplexity, etc.)
    that mirrors what robots.txt/sitemap.xml do for search crawlers: point
    them at what this site is and where the canonical content lives, in a
    format built for an LLM's context window rather than a browser."""
    from .models import SiteConfig

    site_config = SiteConfig.get()
    school_name = site_config.school_name or "Abraytech"
    tagline = site_config.tagline or "Software development, cybersecurity, AI & data, and IT consulting."

    def u(name, *args):
        return _abs(request, reverse(name, args=args) if args else reverse(name))

    lines = [
        f"# {school_name}",
        "",
        f"> {tagline}",
        "",
        f"{school_name} is a technology services, training, and product company. "
        "This file lists the site's primary public pages for AI assistants and "
        "agents summarizing or citing this site — each link is the canonical, "
        "up-to-date source for that topic.",
        "",
        "## Company",
        f"- [About]({u('eduweb:about')}): Who we are, our team, and our history.",
        f"- [Services]({u('eduweb:services_list')}): Software development, cybersecurity, AI & data, IT consulting.",
        f"- [Industries]({u('eduweb:industries_list')}): Industry verticals we serve.",
        f"- [Projects]({u('eduweb:projects_list')}): Case studies and completed client work.",
        f"- [Careers]({u('eduweb:careers')}): Open roles.",
        f"- [Contact]({u('eduweb:contact')}): How to reach us.",
        f"- [FAQ]({u('eduweb:faq')}): Common questions about our services and programs.",
        "",
        "## Training / Programs",
        f"- [All Programs]({u('eduweb:all_programs')}): Full catalog of training programs by faculty/department.",
        f"- [Admission Requirements]({u('eduweb:admission_requirement')}): How to apply and what's required.",
        "",
        "## Store",
        f"- [Store]({u('store:store_list')}): Products and tools sold directly by {school_name}.",
        "",
        "## Blog",
        f"- [Blog]({u('eduweb:blog')}): Articles on technology, training, and company news.",
        "",
        "## Legal",
        f"- [Privacy Policy]({u('eduweb:privacy')})",
        f"- [Terms of Service]({u('eduweb:terms')})",
        "",
        "## Machine-readable",
        f"- [sitemap.xml]({u('eduweb:sitemap_xml')}): Full list of indexable URLs.",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
