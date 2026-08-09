from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from .models import CourseApplication


def is_finance_manager(user):
    """
    Allow authenticated finance-role users, superusers, or anyone granted
    can_view on a finance_* module via StaffPermissionsMatrix (e.g. a
    support agent given cross-department access through
    /management/role-assign/). Shared by `finance` and `payment`
    (previously two byte-for-byte-identical local copies).
    """
    if not (user.is_authenticated and hasattr(user, 'profile')):
        return False
    if user.is_superuser or user.profile.role == 'finance':
        return True
    from .models import StaffPermissionsMatrix
    return StaffPermissionsMatrix.user_can_view_any(user, StaffPermissionsMatrix.FINANCE_PORTAL_MODULES)


def check_for_auth(view_func):
    """
    Prevents authenticated users from accessing public pages.
    Redirects based on role and account status.
    Anonymous users can proceed to public pages.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if role == 'admin' or request.user.is_superuser:
            messages.info(
                request, 
                'Admin users should use the admin dashboard.'
            )
            return redirect('management:dashboard')

        elif role == 'instructor':
            messages.info(
                request, 
                'Instructor users should use the instructor dashboard.'
            )
            return redirect('instructor:dashboard')
        
        elif role == 'finance':
            messages.info(
                request, 
                'Finance users should use the finance dashboard.'
            )
            return redirect('finance:dashboard')

        elif role == 'student':
            application = (
                CourseApplication.objects
                .filter(user=request.user)
                .first()
            )
            
            if application and application.can_access_student_portal():
                return redirect('students:dashboard')
            
            if application:
                messages.info(
                    request,
                    'You have an active application. Check your status.'
                )
                return redirect('eduweb:application_status')
            else:
                messages.info(
                    request, 
                    'Complete your application to get started.'
                )
                return redirect('eduweb:apply')

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def applicant_required(view_func):
    """
    For pages that require student role authentication.
    Checks: authentication, account status, email verification, role.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access this page.'
            )
            return redirect('eduweb:auth_page')

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        elif role == 'instructor':
            messages.info(
                request, 
                'Instructor users should use the instructor dashboard.'
            )
            return redirect('instructor:dashboard')
        
        elif role == 'finance':
            messages.info(
                request, 
                'Finance users should use the finance dashboard.'
            )
            return redirect('finance:dashboard')

        elif role == 'student':
            return view_func(request, *args, **kwargs)

        # Fallback - unrecognised role
        messages.warning(request, 'Access denied.')
        return redirect('eduweb:auth_page')

    return _wrapped_view


def smart_redirect_applicant(view_func):
    """
    Smart redirect for student applicants on specific pages.
    Checks: authentication, account status, email verification, role.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access this page.'
            )
            return redirect('eduweb:auth_page')

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        elif role == 'instructor':
            messages.info(
                request, 
                'Instructor users should use the instructor dashboard.'
            )
            return redirect('instructor:dashboard')
        
        elif role == 'finance':
            messages.info(
                request, 
                'Finance users should use the finance dashboard.'
            )
            return redirect('finance:dashboard')

        elif role == 'student':
            application = (
                CourseApplication.objects
                .filter(user=request.user)
                .first()
            )
            
            if application and application.can_access_student_portal():
                messages.success(
                    request,
                    'Welcome! Your admission is complete.'
                )
                return redirect('students:dashboard')
            
            has_application = application is not None
            current_view = request.resolver_match.url_name

            if current_view == 'apply' and has_application:
                messages.info(
                    request, 
                    'You already have an application. View your status.'
                )
                return redirect('eduweb:application_status')

            if current_view == 'application_status' and not has_application:
                messages.info(
                    request, 
                    'Please submit your application first.'
                )
                return redirect('eduweb:apply')

            return view_func(request, *args, **kwargs)

        # Fallback - unrecognised role
        messages.warning(request, 'Access denied.')
        return redirect('eduweb:auth_page')

    return _wrapped_view


def instructor_required(view_func):
    """
    For instructor dashboard and related pages.
    Checks: authentication, account status, email verification, role.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access the instructor dashboard.'
            )
            return redirect('eduweb:auth_page')

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if role != 'instructor' and not request.user.is_superuser:
            from .models import StaffPermissionsMatrix
            if not StaffPermissionsMatrix.user_can_view_any(
                request.user, StaffPermissionsMatrix.INSTRUCTOR_PORTAL_MODULES
            ):
                messages.warning(
                    request,
                    'Access denied. Instructor role required.'
                )
                return redirect('eduweb:auth_page')

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def admin_required(view_func):
    """
    For admin dashboard and related pages.
    Checks: authentication, account status, email verification, role.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access the admin dashboard.'
            )
            return redirect('eduweb:auth_page')

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if role != 'admin' and not request.user.is_superuser:
            messages.warning(
                request, 
                'Access denied. Admin role required.'
            )
            return redirect('eduweb:auth_page')

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def finance_required(view_func):
    """
    For finance dashboard and related pages.
    Checks: authentication, account status, email verification, role.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access the finance dashboard.'
            )
            return redirect('eduweb:auth_page')

        # Check if account is inactive
        if not request.user.is_active:
            messages.warning(
                request, 
                'Your account is inactive. Please verify your email.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        # Check if email is verified
        if not request.user.profile.email_verified:
            messages.warning(
                request, 
                'Please verify your email before accessing your account.'
            )
            logout(request)
            return redirect('eduweb:auth_page')

        role = request.user.profile.role

        if role != 'finance' and not (request.user.is_superuser and role == 'admin'):
            messages.warning(
                request, 
                'Access denied. Finance role required.'
            )
            return redirect('eduweb:auth_page')

        return view_func(request, *args, **kwargs)

    return _wrapped_view