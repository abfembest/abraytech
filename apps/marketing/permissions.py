from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


def is_marketing_admin(user):
    """True for superuser or an actual 'admin'-role account — the same
    direct check apps/eduweb/decorators.py::finance_required uses for
    finance, no StaffPermissionsMatrix cross-department grant involved."""
    if not (user.is_authenticated and hasattr(user, 'profile')):
        return False
    return user.is_superuser or user.profile.role == 'admin'


def marketing_required(view_func):
    """For the marketing portal (dashboard, leads, chat).
    Checks: authentication, account status, email verification, role.
    Same shape as apps/eduweb/decorators.py::finance_required."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Please login to access the marketing portal.')
            return redirect('eduweb:auth_page')

        if not request.user.is_active:
            messages.warning(request, 'Your account is inactive. Please verify your email.')
            logout(request)
            return redirect('eduweb:auth_page')

        if not request.user.profile.email_verified:
            messages.warning(request, 'Please verify your email before accessing your account.')
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role
        if role != 'marketer' and not is_marketing_admin(request.user):
            messages.warning(request, 'Access denied. Marketer or admin role required.')
            return redirect('eduweb:auth_page')

        return view_func(request, *args, **kwargs)

    return _wrapped_view
