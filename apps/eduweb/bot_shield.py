"""
Bot-probe shield middleware — blocks scanner traffic before it reaches views.

Designed around the actual attack patterns from production error logs:
- Thousands of .php/.asp/.jsp/.cgi probes (WordPress/PHP scanners)
- Credential/secret file harvesting (/.ssh/, /.env, /backup.sql, etc.)
- WordPress path scanning (/wp-admin/, /wp-content/, /xmlrpc.php)
- Java actuator endpoint probing (/actuator/heapdump)

Runs as the FIRST middleware after SecurityMiddleware so blocked requests
never touch sessions, CSRF, auth, or any view code. Returns a bare 403
with no debug info. Uses no third-party libraries.
"""
import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

# ── Patterns matched against request.path_info ───────────────────────────────

_BLOCKED_EXTENSIONS = re.compile(
    r'\.(php\d?|asp|aspx|jsp|cgi|bak|old|save|orig|swp|sql|env|pem|key)$',
    re.IGNORECASE,
)

_BLOCKED_PATHS = re.compile(
    r'^/('
    r'wp-(admin|content|includes|login|json|mail|config|load)|'
    r'wordpress|xmlrpc|wlwmanifest|'
    r'\.well-known/(acme-challenge|traffic-advice)|'
    r'nc_assets|cgi-bin|'
    r'actuator|'
    r'\.(ssh|aws|git|env|bash_history|npmrc|vscode|config|DS_Store)|'
    r'(backup|database|dump|secrets|credentials|config)\.(sql|json|yml|yaml|env|xml|tar|gz|zip)|'
    r'server\.(key|pem|crt)|'
    r'storage/logs|'
    r'phpinfo|'
    r'vendor/(phpunit|autoload)|'
    r'feed/|'
    r'\.tmb|\.trash'
    r')(/|$)',
    re.IGNORECASE,
)

_BLOCKED_EXACT = frozenset({
    '/ads.txt',
    '/wp-login.php',
    '/xmlrpc.php',
    '/wp.php',
    '/admin.php',
})

# ── Aggressive-scanner detection ─────────────────────────────────────────────
# If one IP triggers SCAN_THRESHOLD blocked requests within SCAN_WINDOW
# seconds, block ALL requests from that IP for BLOCK_DURATION seconds.
# Read at first use, not at import, so the module can be imported before
# Django is fully configured.
_SCAN_THRESHOLD = None
_SCAN_WINDOW = None
_BLOCK_DURATION = None


def _get_thresholds():
    global _SCAN_THRESHOLD, _SCAN_WINDOW, _BLOCK_DURATION
    if _SCAN_THRESHOLD is None:
        _SCAN_THRESHOLD = getattr(settings, 'BOT_SHIELD_SCAN_THRESHOLD', 10)
        _SCAN_WINDOW = getattr(settings, 'BOT_SHIELD_SCAN_WINDOW', 60)
        _BLOCK_DURATION = getattr(settings, 'BOT_SHIELD_BLOCK_DURATION', 600)
    return _SCAN_THRESHOLD, _SCAN_WINDOW, _BLOCK_DURATION

_CACHE_PREFIX = 'botshield'

_BARE_403 = (
    b'<!doctype html><title>403</title><h1>403 Forbidden</h1>',
    'text/html',
)


def _client_ip(request):
    try:
        from apps.eduweb.antispam import client_ip
        return client_ip(request)
    except Exception:
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _is_blocked_path(path):
    if path in _BLOCKED_EXACT:
        return True
    if _BLOCKED_EXTENSIONS.search(path):
        return True
    if _BLOCKED_PATHS.search(path):
        return True
    return False


def _is_ip_banned(ip):
    return cache.get(f'{_CACHE_PREFIX}:ban:{ip}') is not None


def _record_strike(ip):
    """Record a blocked probe. Ban the IP if it exceeds the threshold."""
    threshold, window, block_dur = _get_thresholds()
    key = f'{_CACHE_PREFIX}:strikes:{ip}'
    try:
        strikes = cache.get(key)
        if strikes is None:
            cache.set(key, [time.time()], window)
            return False

        now = time.time()
        cutoff = now - window
        strikes = [t for t in strikes if t > cutoff]
        strikes.append(now)
        cache.set(key, strikes, window)

        if len(strikes) >= threshold:
            cache.set(f'{_CACHE_PREFIX}:ban:{ip}', True, block_dur)
            logger.warning(
                'BotShield: banned %s for %ds (%d probes in %ds)',
                ip, block_dur, len(strikes), window,
            )
            return True
    except Exception:
        pass
    return False


class BotShieldMiddleware:
    """Blocks scanner/bot probe requests before they reach any view."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Never block static/media — WhiteNoise handles those
        if path.startswith(('/static/', '/media/')):
            return self.get_response(request)

        ip = _client_ip(request)

        # Check if this IP is already banned from too many probes
        if _is_ip_banned(ip):
            return HttpResponse(*_BARE_403, status=403)

        # Check if the path matches known bot-probe patterns
        if _is_blocked_path(path):
            _record_strike(ip)
            return HttpResponse(*_BARE_403, status=403)

        return self.get_response(request)
