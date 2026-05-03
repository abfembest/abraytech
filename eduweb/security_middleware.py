import logging
from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

INACTIVITY_TIMEOUT = getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', 15)  # minutes

_PASSTHROUGH_PATHS = {
    '/auth/',
    '/logout/',
    '/verify-email/',
    '/resend-verification/',
    '/forgot-password/',
    '/reset-password/',
    '/static/',
    '/media/',
    '/admin/',
}


def _is_passthrough(path):
    return any(path.startswith(p) for p in _PASSTHROUGH_PATHS)


class SessionSecurityMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        if _is_passthrough(request.path_info):
            return None

        now = timezone.now()
        last_activity = request.session.get('last_activity')

        if last_activity:
            try:
                idle_seconds = (
                    now - timezone.datetime.fromisoformat(last_activity)
                ).total_seconds()
                if idle_seconds > INACTIVITY_TIMEOUT * 60:
                    self._expire_session(request)
                    return None
            except (ValueError, TypeError):
                pass

        request.session['last_activity'] = now.isoformat()
        return None

    def _expire_session(self, request):
        user = request.user
        logger.info('Inactivity timeout for user=%s', user.username)

        try:
            profile = user.profile
            profile.is_logged_in = False
            profile.active_session_key = ''
            profile.save(update_fields=['is_logged_in', 'active_session_key'])
        except Exception:
            logger.exception('Failed to clear profile for user=%s', user.username)

        logout(request)  # clears session data and rotates the key