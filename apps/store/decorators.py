from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


def store_access(view_func):
    """
    Browsing/cart/checkout gate for the public store. Store accounts
    (profile.role == 'customer') are deliberately separate from LMS
    accounts — an authenticated student/instructor/finance/admin/support
    account is redirected to their own portal, the same way
    eduweb.decorators.check_for_auth does for the rest of the public site,
    rather than being allowed to browse the store under their school
    identity. Anonymous visitors, and 'customer' accounts, pass straight
    through.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        if not request.user.is_active:
            messages.warning(
                request,
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        if not request.user.profile.email_verified:
            messages.warning(
                request,
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if role == 'customer':
            return view_func(request, *args, **kwargs)

        messages.info(request, "The store is only available to store accounts — you're signed in with your school account.")

        if role == 'admin' or request.user.is_superuser:
            return redirect('management:dashboard')
        elif role == 'instructor':
            return redirect('instructor:dashboard')
        elif role == 'finance':
            return redirect('finance:dashboard')
        elif role == 'support':
            return redirect('support:dashboard')
        elif role == 'student':
            from apps.eduweb.models import CourseApplication
            application = CourseApplication.objects.filter(user=request.user).first()
            if application and application.can_access_student_portal():
                return redirect('students:dashboard')
            if application:
                return redirect('eduweb:application_status')
            return redirect('eduweb:apply')

        return redirect('eduweb:index')

    return _wrapped_view
