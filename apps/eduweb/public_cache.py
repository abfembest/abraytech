"""
Cache for data the public pages and the site-wide nav read on every request
(SiteConfig, nav dropdowns, homepage sections).

Every key includes a "public content version". Saving or deleting any model
in PUBLIC_MODELS bumps that version, so an admin edit shows up within a few
seconds (VERSION_TTL) instead of after the full timeout.

Every function falls back to the database if the cache backend fails (for
example, the DatabaseCache table has not been created yet), so a cache
problem can slow a page down but never break it.
"""
import logging
import time

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


# The version is re-read from the cache at most every VERSION_TTL seconds per
# process, not once per cached item (with the database cache each read is a
# query). Edits in this process update it at once; others within seconds.
VERSION_TTL = 5
# Values already fetched in this process for the current version, so pages
# don't re-read the cache table for data they just used. Emptied whenever
# the version changes.
_local = {'version': None, 'read_at': 0.0, 'items': {}}


def _version():
    now = time.monotonic()
    if _local['version'] is not None and now - _local['read_at'] < VERSION_TTL:
        return _local['version']
    version = cache.get(VERSION_KEY)
    if version is None:
        # Start from the clock, not 1: if the key was evicted, restarting at
        # an old number could bring back entries cached under it.
        cache.add(VERSION_KEY, int(time.time()), None)
        version = cache.get(VERSION_KEY) or int(time.time())
    if version != _local['version']:
        _local['items'] = {}
    _local.update(version=version, read_at=now)
    return version


def get_or_set(name, compute):
    """Return the cached value for `name`, computing and storing it on a miss.
    `compute` must return plain data (lists/dicts/model instances), never an
    unevaluated QuerySet."""
    try:
        key = f'public:{_version()}:{name}'
        if key in _local['items']:
            return _local['items'][key]
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
    _local['items'][key] = value
    return value


def bump_version(**kwargs):
    try:
        version = cache.incr(VERSION_KEY)
    except ValueError:  # key missing (evicted): start a fresh, higher number
        version = int(time.time())
        cache.set(VERSION_KEY, version, None)
    except Exception:
        logger.exception('public_cache: could not bump the content version')
        _local.update(version=None, items={})
        return
    _local.update(version=version, read_at=time.monotonic(), items={})


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
