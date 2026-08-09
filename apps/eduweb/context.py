"""
context.py — Global template context processors for the eduweb app.

All processors listed here must also be registered in settings.py:

    TEMPLATES = [{
        ...
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'eduweb.context.site_config_context',
                'eduweb.context.navigation_data',
                'eduweb.context.student_counts',
                'eduweb.context.admin_counts',
            ],
        },
    }]
"""

import logging
from django.template import Library
from .models import (
    Faculty, Program, CourseApplication,
    Message, Notification, SupportTicket, ContactMessage,
    SiteConfig, AcademicSession, StudentExamResponse,
)

logger = logging.getLogger(__name__)
register = Library()


# ─────────────────────────────────────────────────────────────────────────────
# 1. SITE CONFIG
#    Injects `site_config` into EVERY template automatically.
#    Views no longer need to pass 'site' or 'site_config' manually.
# ─────────────────────────────────────────────────────────────────────────────
def site_config_context(request):
    """
    Makes {{ site_config }} available in every template.
    Returns a safe fallback object if no SiteConfig row exists yet,
    so templates never crash on {{ site_config.field|default:"..." }}.
    """
    try:
        site = SiteConfig.get()
    except Exception:
        site = None

    if site is None:
        class _EmptySiteConfig:
            """Dummy fallback so attribute lookups return '' instead of crashing."""
            def __getattr__(self, name):
                return ''
            def __bool__(self):
                return False
        site = _EmptySiteConfig()

    return {'site_config': site}


# ─────────────────────────────────────────────────────────────────────────────
# 2. NAVIGATION DATA
#    Injects faculties + programs for the nav dropdowns in base.html,
#    plus the `has_pending_application` flag for the CTA button logic.
#
#    KEY FIXES:
#    ① Faculty  — NO .only() at all. The Faculty model's related Department
#      __str__ accesses `faculty.code`, which was deferred by .only(), causing
#      silent query failures and {{ faculty.name }} rendering literally.
#      Faculty nav has very few rows so fetching full instances is fine.
#
#    ② Program  — NO .only() at all. The Program model has NO `icon` field,
#      so .only('name','slug','icon',...) made Django return an empty queryset,
#      producing "No programs available" in the nav dropdown.
#      NOTE for base.html: since Program has no `icon` field, the
#      <i data-lucide="{{ course.icon }}"> lines will render blank icons.
#      Either add an `icon` field to Program in models.py, or replace those
#      lines in base.html with a static fallback icon e.g. data-lucide="book".
# ─────────────────────────────────────────────────────────────────────────────
def navigation_data(request):
    """Inject navigation data into every template via base.html."""

    # Full model instances — no .only() so all attribute access is safe
    try:
        faculties = list(
            Faculty.objects
            .filter(is_active=True)
            .order_by('name')
        )
    except Exception:
        logger.exception('navigation_data: failed to fetch faculties')
        faculties = []

    # Full model instances — Program has no `icon` field so .only() must never
    # list it. select_related pulls department + faculty in one query.
    try:
        courses = list(
            Program.objects
            .filter(is_active=True)
            .select_related('department__faculty')
            .order_by('name')[:11]
        )
    except Exception:
        logger.exception('navigation_data: failed to fetch programs')
        courses = []

    # Pending application check — only for authenticated students
    has_pending_application = False
    try:
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            if request.user.profile.role == 'student':
                has_pending_application = CourseApplication.objects.filter(
                    user=request.user
                ).exists()
    except Exception:
        logger.exception('navigation_data: failed to check pending application')

    return {
        'all_faculties': faculties,
        'all_courses': courses,
        'has_pending_application': has_pending_application,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. STUDENT BADGE COUNTS
#    Unread messages + notifications for the student nav bar badges.
# ─────────────────────────────────────────────────────────────────────────────
def student_counts(request):
    """
    Inject unread notification count and nav bell notifications for ALL
    authenticated roles. Also injects unread_messages_count for students,
    and current_session / current_term / registration_open for the student
    academic status bar in base.html.
    """
    if not request.user.is_authenticated:
        return {}
    if not hasattr(request.user, 'profile'):
        return {}

    try:
        unread_notifs_qs = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).order_by('-created_at')

        result = {
            'unread_notifications_count': unread_notifs_qs.count(),
            'nav_notifications': list(unread_notifs_qs[:5]),
            'unread_messages_count': 0,
        }

        # Unread messages only meaningful for students (inbox feature)
        if request.user.profile.role == 'student':
            result['unread_messages_count'] = Message.objects.filter(
                recipient=request.user,
                is_read=False,
                parent__isnull=True,
            ).count()

            # Academic status bar data — session, term, registration window
            cs = AcademicSession.get_current()
            result['current_session']   = cs
            result['current_term']      = cs.get_current_term() if cs else None
            result['registration_open'] = cs.is_registration_open if cs else False
            if cs:
                _ro, _rc = cs.get_registration_window()
                result['reg_open']  = _ro
                result['reg_close'] = _rc
            else:
                result['reg_open'] = result['reg_close'] = None

            # Student academic identity — profile, department, faculty
            # Available globally so views don't need to re-fetch them.
            profile    = request.user.profile
            department = getattr(profile.program, 'department', None) if getattr(profile, 'program', None) else None
            faculty    = getattr(department, 'faculty', None) if department else None
            result['student_profile']     = profile
            result['student_department']  = department
            result['student_faculty']     = faculty

            # Matric number — derived property on CourseApplication (see
            # CourseApplication.matric_number for the actual format/logic).
            accepted_application = (
                request.user.applications
                .filter(admission_number__isnull=False)
                .select_related('program__department')
                .order_by('-admission_accepted_at')
                .first()
            )
            result['matric_number'] = (
                accepted_application.matric_number if accepted_application else None
            )

        return result

    except Exception:
        logger.exception('student_counts: failed to fetch counts')
        return {
            'unread_messages_count': 0,
            'unread_notifications_count': 0,
            'nav_notifications': [],
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. INSTRUCTOR BADGE COUNTS
#    Unread notifications for the instructor nav bar bell.
# ─────────────────────────────────────────────────────────────────────────────
def instructor_counts(request):
    """
    Inject unread notification count and the 5 most recent unread notifications
    for the instructor nav bell dropdown.
    """
    if not request.user.is_authenticated:
        return {}
    if not hasattr(request.user, 'profile'):
        return {}
    if request.user.profile.role != 'instructor':
        return {}

    try:
        unread_notifs_qs = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).order_by('-created_at')

        # Exam responses submitted but still awaiting manual grading (short-
        # answer/essay questions) — surfaced as the "My Exams" sidebar badge.
        pending_exam_count = StudentExamResponse.objects.filter(
            exam__instructor=request.user,
            status=StudentExamResponse.SUBMITTED,
            pending_manual_count__gt=0,
        ).count()

        return {
            'instructor_unread_notifications_count': unread_notifs_qs.count(),
            'instructor_nav_notifications': list(unread_notifs_qs[:5]),
            'instructor_pending_exam_count': pending_exam_count,
        }
    except Exception:
        logger.exception('instructor_counts: failed to fetch counts')
        return {
            'instructor_unread_notifications_count': 0,
            'instructor_nav_notifications': [],
            'instructor_pending_exam_count': 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. ADMIN BADGE COUNTS
#    Open tickets + unread contact messages for the admin nav bar.
# ─────────────────────────────────────────────────────────────────────────────
def admin_counts(request):
    """Inject admin badge counts into every template."""
    if not request.user.is_authenticated:
        return {}
    if not hasattr(request.user, 'profile'):
        return {}
    if request.user.profile.role not in ('admin',) and not request.user.is_staff:
        return {}

    try:
        cs = AcademicSession.get_current()
        return {
            'open_tickets_count': SupportTicket.objects.filter(
                status__in=['open', 'in_progress']
            ).count(),
            'unread_contact_count': ContactMessage.objects.filter(
                is_read=False
            ).count(),
            'current_session': cs,
            'current_term': cs.get_current_term() if cs else None,
            'registration_open': cs.is_registration_open if cs else False,
        }
    except Exception:
        logger.exception('admin_counts: failed to fetch counts')
        return {
            'open_tickets_count': 0,
            'unread_contact_count': 0,
            'current_session': None,
            'current_term': None,
            'registration_open': False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. TEMPLATE FILTER — currency_symbol
#    Usage in templates:  {{ payment.currency|currency_symbol }}
# ─────────────────────────────────────────────────────────────────────────────
@register.filter
def currency_symbol(currency_code):
    """Return the currency symbol for a given currency code string."""
    symbols = {
        'USD': '$',
        'GBP': '£',
        'EUR': '€',
        'JPY': '¥',
        'CAD': 'C$',
        'AUD': 'A$',
        'NGN': '₦',
    }
    if not currency_code:
        return ''
    return symbols.get(str(currency_code).upper(), str(currency_code) + ' ')

def permissions_context(request):
    """
    expose request.permissions (set by sessionsecuritymiddleware) to templates.
    returns empty dict if middleware hasn't run or user is not staff.
    """
    return {
        'permissions': getattr(request, 'permissions', {})
    }