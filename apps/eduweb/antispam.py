"""
Bot checks for public forms (contact form on / and /contact/).

The math captcha alone is printed as plain text in the page, so any script
that scrapes the form can solve it. These checks sit alongside it:

- honeypot:   a visually hidden "website" input humans never fill in
- form token: a signed timestamp; a submit faster than MIN_FILL_SECONDS
              or with a missing/tampered/expired token is a bot
- rate limit: at most RATE_LIMIT submissions per IP per RATE_PERIOD
- links:      URLs in the name, or a message stuffed with links

Cloudflare Turnstile replaces the math captcha when TURNSTILE_SITE_KEY and
TURNSTILE_SECRET_KEY are set (see turnstile_enabled / verify_turnstile).
"""
import logging
import re
import time

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache

HONEYPOT_FIELD   = 'website'
TOKEN_FIELD      = 'form_token'
TOKEN_SALT       = 'eduweb.contact.form_token'
MIN_FILL_SECONDS = 3
MAX_TOKEN_AGE    = 60 * 60 * 24   # a page left open for a day still submits
RATE_LIMIT       = 5
RATE_PERIOD      = 60 * 60
MAX_LINKS        = 3

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
TURNSTILE_FIELD      = 'cf-turnstile-response'

_URL_RE = re.compile(r'(https?://|www\.|\[url|<a\s)', re.IGNORECASE)

# Verdicts returned by check_contact_submission()
BOT            = 'bot'    # drop silently, show the normal success message
RATE           = 'rate'   # tell the user to wait
TOO_MANY_LINKS = 'links'  # tell the user to trim links


def make_form_token():
    """Signed render timestamp, put in the form as a hidden input."""
    return signing.dumps(time.time(), salt=TOKEN_SALT)


def check_contact_submission(request):
    """Return None if the POST looks human, otherwise BOT, RATE or TOO_MANY_LINKS."""
    post = request.POST

    if post.get(HONEYPOT_FIELD, '').strip():
        return BOT

    try:
        rendered_at = signing.loads(post.get(TOKEN_FIELD, ''), salt=TOKEN_SALT, max_age=MAX_TOKEN_AGE)
    except signing.BadSignature:   # also covers SignatureExpired
        return BOT
    if time.time() - float(rendered_at) < MIN_FILL_SECONDS:
        return BOT

    if _URL_RE.search(post.get('name', '')):
        return BOT

    cache_key = f"contact_submit_{request.META.get('REMOTE_ADDR', '')}"
    count = cache.get(cache_key, 0)
    if count >= RATE_LIMIT:
        return RATE
    cache.set(cache_key, count + 1, RATE_PERIOD)

    if len(_URL_RE.findall(post.get('message', ''))) > MAX_LINKS:
        return TOO_MANY_LINKS

    return None


def turnstile_enabled():
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def turnstile_site_key():
    """Site key for the template widget, or '' to show the math captcha."""
    return settings.TURNSTILE_SITE_KEY if turnstile_enabled() else ''


def verify_turnstile(request):
    """Ask Cloudflare whether the widget token in the POST is valid."""
    token = request.POST.get(TURNSTILE_FIELD, '')
    if not token:
        return False
    try:
        resp = requests.post(TURNSTILE_VERIFY_URL, data={
            'secret':   settings.TURNSTILE_SECRET_KEY,
            'response': token,
            'remoteip': request.META.get('REMOTE_ADDR', ''),
        }, timeout=5)
        result = resp.json()
    except (requests.RequestException, ValueError):
        logger.warning("Turnstile verification request failed", exc_info=True)
        return False
    if not result.get('success'):
        logger.info("Turnstile rejected token: %s", result.get('error-codes'))
    return bool(result.get('success'))
