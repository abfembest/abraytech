"""
Bot checks for public forms (contact form on / and /contact/).

The math captcha alone is printed as plain text in the page, so any script
that scrapes the form can solve it. These checks sit alongside it:

- honeypot:   a visually hidden "website" input humans never fill in
- form token: a signed timestamp; a submit faster than MIN_FILL_SECONDS
              or with a missing/tampered/expired token is a bot
- rate limit: at most RATE_LIMIT submissions per IP per RATE_PERIOD
              (IP from client_ip(), which only trusts proxy headers set
              by Cloudflare or a proxy on this machine)
- links:      URLs in the name, or a message stuffed with links

Cloudflare Turnstile replaces the math captcha when TURNSTILE_SITE_KEY and
TURNSTILE_SECRET_KEY are set (see turnstile_enabled / verify_turnstile).
"""
import ipaddress
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

# Published at https://www.cloudflare.com/ips/ - update if Cloudflare adds ranges.
_CLOUDFLARE_NETS = [ipaddress.ip_network(n) for n in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22',
    '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20',
    '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32',
    '2405:8100::/32', '2a06:98c0::/29', '2c0f:f248::/32',
)]

_URL_RE = re.compile(r'(https?://|www\.|\[url|<a\s)', re.IGNORECASE)

# Verdicts returned by check_contact_submission()
BOT            = 'bot'    # drop silently, show the normal success message
RATE           = 'rate'   # tell the user to wait
TOO_MANY_LINKS = 'links'  # tell the user to trim links


def make_form_token():
    """Signed render timestamp, put in the form as a hidden input."""
    return signing.dumps(time.time(), salt=TOKEN_SALT)


def _parse_ip(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def client_ip(request):
    """The visitor's IP, safe to use as a rate-limit key.

    Forwarding headers are only trusted when the direct peer is a proxy we
    know about; otherwise anyone could send a fake header per request and
    dodge the limit.
    - peer is Cloudflare          -> CF-Connecting-IP
    - peer is loopback/private    -> last X-Forwarded-For entry (the one our
                                     own proxy appended)
    - anything else               -> REMOTE_ADDR
    """
    remote = request.META.get('REMOTE_ADDR', '')
    peer = _parse_ip(remote)
    if peer is None:
        return remote

    if any(peer in net for net in _CLOUDFLARE_NETS):
        cf_ip = _parse_ip(request.META.get('HTTP_CF_CONNECTING_IP', ''))
        if cf_ip:
            return str(cf_ip)

    if peer.is_loopback or peer.is_private:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        last = _parse_ip(forwarded.split(',')[-1]) if forwarded else None
        if last:
            return str(last)

    return remote


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

    cache_key = f"contact_submit_{client_ip(request)}"
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
            'remoteip': client_ip(request),
        }, timeout=5)
        result = resp.json()
    except (requests.RequestException, ValueError):
        logger.warning("Turnstile verification request failed", exc_info=True)
        return False
    if not result.get('success'):
        logger.info("Turnstile rejected token: %s", result.get('error-codes'))
    return bool(result.get('success'))
