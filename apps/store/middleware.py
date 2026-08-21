"""
apps/store/middleware.py
-------------------------
A logged-in store customer (profile.role == 'customer') only ever belongs
in /store/ — the rest of the site is the LMS/company site, which is not
theirs. Any request to a URL outside /store/ (and a small always-allowed
set: static/media, logout, the Django admin's own login gate) is
redirected back to the store, the same "lock navigation" shape as
apps.eduweb.exam_middleware.ExamLockMiddleware.

Not to be confused with apps.store.decorators.store_access, which does the
opposite direction (keeps everyone who ISN'T a customer OUT of /store/).
Together the two make /store/ and "everywhere else" mutually exclusive for
a logged-in customer.
"""

import logging

from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

_ALWAYS_ALLOWED = (
    '/store/',
    '/static/',
    '/media/',
    '/admin/',
    '/logout/',
)


def _is_allowed(path: str) -> bool:
    return any(path.startswith(p) for p in _ALWAYS_ALLOWED)


class StoreCustomerScopeMiddleware(MiddlewareMixin):
    """One profile lookup per request (via request.user.profile, already
    cached per-request by Django's related-object caching). Staff/
    superusers are never affected — this only ever applies to the
    'customer' role."""

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'customer':
            return None

        if _is_allowed(request.path_info):
            return None

        logger.info(
            'StoreCustomerScope: user=%s redirected from %s -> /store/',
            request.user.username, request.path_info,
        )
        return redirect('store:store_list')
