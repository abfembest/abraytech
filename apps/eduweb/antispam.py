"""
Bot checks for public forms (contact form on / and /contact/).

The math captcha alone is printed as plain text in the page, so any script
that scrapes the form can solve it. These checks sit alongside it:

- honeypot:   a visually hidden "website" input humans never fill in
- form token: a signed timestamp; a submit faster than MIN_FILL_SECONDS
              or with a missing/tampered/expired token is a bot
- rate limit: at most RATE_LIMIT submissions per IP per RATE_PERIOD
- links:      URLs in the name, or a message stuffed with links
"""
import re
import time

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
