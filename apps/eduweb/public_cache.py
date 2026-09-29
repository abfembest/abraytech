"""
Cache for data the public pages and the site-wide nav read on every request
(SiteConfig, nav dropdowns, homepage sections).

Every key includes a "public content version". Saving or deleting any model
in PUBLIC_MODELS bumps that version, so an admin edit shows up on the next
request instead of after a timeout.

Every function falls back to the database if the cache backend fails (for
example, the DatabaseCache table has not been created yet), so a cache
problem can slow a page down but never break it.
"""
import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)

TIMEOUT = 60 * 10
VERSION_KEY = 'public_content_version'

# (app_label, model_name) of everything cached public pages display.
PUBLIC_MODELS = [
    ('eduweb', 'SiteConfig'), ('eduweb', 'SiteHistoryMilestone'),
    ('eduweb', 'Faculty'), ('eduweb', 'Department'), ('eduweb', 'Program'),
    ('eduweb', 'Course'), ('eduweb', 'CourseIntake'),
    ('eduweb', 'Service'), ('eduweb', 'Industry'),
    ('eduweb', 'Project'), ('eduweb', 'ProjectImage'),
    ('eduweb', 'Testimonial'), ('eduweb', 'SocialPost'),
    ('eduweb', 'BlogPost'), ('eduweb', 'BlogCategory'),
    ('eduweb', 'InstitutionMember'), ('eduweb', 'InstitutionPartner'),
    ('eduweb', 'JobListing'),
    ('support', 'FAQ'), ('support', 'FAQCategory'),
    ('store', 'Product'),
]


def _version():
    version = cache.get(VERSION_KEY)
    if version is None:
        version = 1
        cache.add(VERSION_KEY, version, None)
    return version


def get_or_set(name, compute):
    """Return the cached value for `name`, computing and storing it on a miss.
    `compute` must return plain data (lists/dicts/model instances), never an
    unevaluated QuerySet."""
    try:
        key = f'public:{_version()}:{name}'
        value = cache.get(key)
    except Exception:
        logger.exception('public_cache: cache unavailable for %s, using the database', name)
        return compute()

    if value is None:
        value = compute()
        try:
            cache.set(key, value, TIMEOUT)
        except Exception:
            logger.exception('public_cache: could not store %s', name)
    return value


def bump_version(**kwargs):
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)
    except Exception:
        logger.exception('public_cache: could not bump the content version')


def connect_signals():
    from django.apps import apps

    for app_label, model_name in PUBLIC_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        uid = f'public_cache_{app_label}_{model_name}'
        post_save.connect(bump_version, sender=model, dispatch_uid=f'{uid}_save')
        post_delete.connect(bump_version, sender=model, dispatch_uid=f'{uid}_delete')
