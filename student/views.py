from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Avg, Prefetch, Max, Sum, F, FloatField
from django.utils import timezone
from django.core.paginator import Paginator
from functools import wraps
from datetime import timedelta
from decimal import Decimal
from django.db import models
import json
import random

from eduweb.models import (
    LMSCourse, Enrollment, Lesson, LessonProgress,
    CourseCategory, Assignment, AssignmentSubmission,
    Certificate, Announcement, Quiz, QuizAttempt,
    QuizAnswer, QuizQuestion, QuizResponse, StudyGroup, StudyGroupMember,
    Discussion, DiscussionReply, Badge,
    StudentBadge, LessonSection,
    Message, Notification, Review, StudyGroupMessage,
    FeePayment, CourseGrade, CourseApplication, Exam, StudentExamResponse,
    Course, AcademicSession, CourseRegistration,
)

from .forms import AssignmentSubmissionForm, SettingsForm, ProfileUpdateForm, ReplyCreateForm, ThreadCreateForm, StudyGroupMessageForm, StudentSupportTicketForm

from django.core.mail import send_mail
from django.conf import settings


# maps international/alias term keys → the canonical semester keys used on course.semester.
# academicsession stores term_dates with keys from term_choices (first/second/third/fall/spring/summer/annual).
# course.semester only uses first/second/annual.
# this single map is the only place that relationship is defined.
term_normalisation_map = {
    # nigerian semester terms (already canonical — map to themselves)
    'first':  'first',
    'second': 'second',
    'third':  'second',   # third semester/harmattan treated as second semester
    'annual': 'annual',
    # international semester equivalents
    'fall':   'first',
    'spring': 'second',
    'summer': 'annual',
    'autumn': 'first',    # autumn = fall = first semester
}


def student_required(view_func):
    """Decorator to ensure only students with approved portal access can access"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(
                request, 
                'Please login to access this page.'
            )
            return redirect('eduweb:auth_page')
        
        # Check if user has profile
        if not hasattr(request.user, 'profile'):
            messages.error(
                request, 
                'Profile not found. Please contact support.'
            )
            return redirect('eduweb:index')
        
        if request.user.profile.role != 'student':
            messages.error(
                request, 
                'Access denied. Students only.'
            )
            return redirect(
                'management:dashboard' 
                if request.user.is_staff 
                else 'eduweb:index'
            )

        # Block access if application hasn't been approved yet
        from eduweb.models import CourseApplication
        application = CourseApplication.objects.filter(user=request.user).first()
        if not application or not application.can_access_student_portal():
            messages.warning(
                request,
                'Your application is still being processed. You cannot access the student portal yet.'
            )
            if application:
                return redirect('eduweb:application_status')
            return redirect('eduweb:apply')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# ==================== NOTIFICATION HELPER ====================

def _notify(user, notification_type, title, message, link=''):
    """
    Create a Notification for a student. Silently fails so it never
    breaks the main action. Auto-purges notifications older than 30 days.
    """
    try:
        Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
        )
        cutoff = timezone.now() - timedelta(days=30)
        Notification.objects.filter(user=user, created_at__lt=cutoff).delete()
    except Exception:
        pass

def _get_eligible_exams(user):
    """
    Returns published Exam queryset for exams the student is eligible to see.
    Rules:
      1. Exam must be PUBLISHED
      2. Exam.course (LMSCourse) must belong to current academic session
      3. Exam.course.term must match the current term of that session
      4. Student must have an ACTIVE enrollment in that LMSCourse
    """
    current_session = AcademicSession.get_current()
    if not current_session:
        return Exam.objects.none()

    current_term = current_session.get_current_term()

    qs = Exam.objects.filter(
        status=Exam.PUBLISHED,
        course__session=current_session,          # LMSCourse.session
        course__enrollments__student=user,        # Enrollment.student
        course__enrollments__status='active',     # Enrollment.status
    ).select_related('course').distinct()
    # If the session has a current term, also filter by it
    # (blank term on LMSCourse means it matches any term — don't exclude those)
    if current_term:
        qs = qs.filter(
            models.Q(course__term=current_term) | models.Q(course__term='')
        )

    return qs

@login_required
@student_required
def dashboard(request):
    """Student dashboard — courses, assignments, announcements, academic identity."""
    user = request.user

    # ── Academic identity (needed by multiple sections below) ────────────────
    profile         = getattr(user, 'profile', None)
    current_session = AcademicSession.get_current()
    current_term    = current_session.get_current_term() if current_session else None

    department = None
    faculty    = None
    if profile and profile.program:
        department = getattr(profile.program, 'department', None)
        faculty    = getattr(department, 'faculty', None) if department else None

    # ── Semester-registered courses (Course model, not LMS Enrollments) ──────
    # Mirror the logic from my_courses so the dashboard is always consistent.
    semester_courses        = []
    registered_course_ids   = set()
    registered_credit_total = 0
    registration_submitted  = False
    registration_finalized  = False

    if profile and profile.program and current_session and current_term:
        normalised_term = term_normalisation_map.get(current_term, current_term)

        # All courses offered for this student's program / year / term
        semester_courses = list(
            Course.objects
            .filter(
                program=profile.program,
                year_of_study=profile.year_of_study,
                is_active=True,
            )
            .filter(Q(semester=normalised_term) | Q(semester='annual'))
            .prefetch_related('prerequisites')
            .order_by('course_type', 'name')
        )

        existing_regs = CourseRegistration.objects.filter(
            student=user,
            session=current_session,
            term__in=[current_term, normalised_term],
            status__in=['pending', 'approved'],
        ).select_related('course')

        registered_course_ids  = {r.course_id for r in existing_regs}
        registration_submitted = existing_regs.exists()
        registration_finalized = (
            registration_submitted
            and not existing_regs.filter(status='pending').exists()
        )

        for course in semester_courses:
            course.is_registered = course.id in registered_course_ids
            course.is_core       = course.course_type == 'core'

        registered_credit_total = (
            CourseRegistration.objects
            .filter(
                student=user,
                session=current_session,
                status__in=['pending', 'approved'],
            )
            .aggregate(total=Sum('course__credit_units'))['total'] or 0
        )

    try:
        # ── Active LMS enrollments (last 5 recently accessed) ─────────────────
        enrollments = (
            Enrollment.objects
            .filter(student=user, status='active')
            .select_related('course')
            .prefetch_related(
                Prefetch(
                    'course__lessons',
                    queryset=Lesson.objects.filter(is_active=True),
                    to_attr='active_lessons',
                ),
                Prefetch(
                    'lesson_progress',
                    queryset=LessonProgress.objects.filter(is_completed=True),
                    to_attr='completed_progress',
                ),
            )
            .order_by('-last_accessed')[:5]
        )

        # Attach completed count from prefetch — zero extra queries
        for enrollment in enrollments:
            enrollment.completed_lessons_count = len(enrollment.completed_progress)

        # ── Pending assignments ───────────────────────────────────────────────
        pending_assignments = (
            Assignment.objects
            .filter(
                lesson__course__enrollments__student=user,
                lesson__course__enrollments__status='active',
                due_date__gte=timezone.now(),
                is_active=True,
            )
            .exclude(
                Q(submissions__student=user) &
                Q(submissions__status__in=['submitted', 'graded'])
            )
            .select_related('lesson__course')
            .distinct()
            .order_by('due_date')[:5]
        )

        # ── Recent announcements ──────────────────────────────────────────────
        announcements = (
            Announcement.objects
            .filter(
                Q(announcement_type='system') |
                Q(
                    course__enrollments__student=user,
                    announcement_type='course',
                ),
                is_active=True,
                publish_date__lte=timezone.now(),
            )
            .filter(
                Q(expiry_date__isnull=True) |
                Q(expiry_date__gte=timezone.now())
            )
            .distinct()
            .order_by('-priority', '-publish_date')[:5]
        )

        # ── Admission / application history ───────────────────────────────────
        admission_history = (
            CourseApplication.objects
            .filter(Q(user=user) | Q(email=user.email))
            .select_related('program', 'program__department__faculty', 'academic_session')
            .order_by('-created_at')[:5]
        )

        # ── Summary statistics ────────────────────────────────────────────────
        stats = {
            'total_enrolled': (
                Enrollment.objects.filter(student=user).count()
            ),
            'completed_courses': (
                Enrollment.objects.filter(student=user, status='completed').count()
            ),
            'certificates_earned': (
                Certificate.objects.filter(student=user).count()
            ),
        }

    except Exception:
        messages.error(
            request,
            'An error occurred loading the dashboard. Please try again.'
        )
        enrollments         = []
        pending_assignments = []
        announcements       = []
        admission_history   = []
        stats = {
            'total_enrolled':      0,
            'completed_courses':   0,
            'certificates_earned': 0,
        }

    # ── Outstanding fees ──────────────────────────────────────────────────────
    try:
        outstanding_items, _ = _get_outstanding_for_student(user)
        outstanding_count    = len(outstanding_items)
        outstanding_total    = sum(
            (item['payment']['amount'] if isinstance(item['payment'], dict) else item['payment'].amount)
            for item in outstanding_items
        )
        _first = outstanding_items[0]['payment'] if outstanding_items else None
        outstanding_currency = (
            _first.get('currency', 'USD') if isinstance(_first, dict)
            else getattr(_first, 'currency', 'USD')
        ) if _first else 'USD'
    except Exception:
        outstanding_count    = 0
        outstanding_total    = Decimal('0.00')
        outstanding_currency = 'USD'

    # ── Upcoming exams ────────────────────────────────────────────────────────
    now = timezone.now()
    upcoming_exams = (
        Exam.objects
        .filter(
            status=Exam.PUBLISHED,
            is_active=True,
            course__in=Enrollment.objects.filter(
                student=user, status='active'
            ).values('course_id'),
            end_datetime__gt=now,
        )
        .select_related('course')
        .order_by('start_datetime')[:3]
    )

    # ── Recent released grades ────────────────────────────────────────────────
    recent_grades = (
        CourseGrade.objects
        .filter(student=user, result_status='released')
        .select_related('course', 'session')
        .order_by('-recorded_at')[:5]
    )

    context = {
        'page_title':               'My Dashboard',
        # LMS enrolled courses
        'enrollments':              enrollments,
        'pending_assignments':      pending_assignments,
        'announcements':            announcements,
        'admission_history':        admission_history,
        'total_enrolled':           stats['total_enrolled'],
        'completed_courses':        stats['completed_courses'],
        'certificates_earned':      stats['certificates_earned'],
        # Fees
        'outstanding_count':        outstanding_count,
        'outstanding_total':        outstanding_total,
        'outstanding_currency':     outstanding_currency,
        # Academic identity
        'profile':                  profile,
        'department':               department,
        'faculty':                  faculty,
        # Semester-registered courses (Course model)
        'semester_courses':         semester_courses,
        'registered_course_ids':    registered_course_ids,
        'registered_credit_total':  registered_credit_total,
        'registration_submitted':   registration_submitted,
        'registration_finalized':   registration_finalized,
        # Exams & grades
        'upcoming_exams':           upcoming_exams,
        'recent_grades':            recent_grades,
    }

    return render(request, 'students/dashboard.html', context)

@login_required
@student_required
def my_courses(request):
    """
    Semester registration panel + enrolled LMS courses.
    - Student picks session & term manually (defaults to current).
    - All courses for their program/year/term load automatically.
    - Credit counter enforces program max from backend.
    - Finalize & Enroll only enabled when core credits are all selected
      and total does not exceed program max_credits_per_semester.
    - LMS course cards only appear after successful enrollment.
    """
    user = request.user
    profile = getattr(user, 'profile', None)

    # ── Session / Term selector ────────────────────────────────────────────
    # Always use the current session — students cannot switch sessions here.
    current_session  = AcademicSession.get_current()
    selected_session = current_session
    all_sessions     = [current_session] if current_session else []

    # Term is derived automatically from session.term_dates — never from GET params.
    selected_term = ''

    if not selected_term and selected_session:
        selected_term = selected_session.get_current_term() or ''
        # if no term is currently active by date, fall back to the first term
        # defined in term_dates so courses still load
        if not selected_term and selected_session.term_dates:
            selected_term = selected_session.term_dates[0].get('term', '')
        # last resort: use first semester
        if not selected_term:
            selected_term = 'first'

    # Check if the selected term is currently active within this session's term_dates
    def _term_is_active(session, term):
        """Returns True if today falls within the term window in session.term_dates."""
        if not session or not term or not session.term_dates:
            return False
        from datetime import date as _date
        today = timezone.now().date()
        normalised = term_normalisation_map.get(term, term)
        for entry in session.term_dates:
            if entry.get('term') in (term, normalised):
                try:
                    start = _date.fromisoformat(entry['start'])
                    end   = _date.fromisoformat(entry['end'])
                    if start <= today <= end:
                        return True
                except (KeyError, ValueError):
                    pass
        return False

    selected_term_is_active = _term_is_active(selected_session, selected_term)

    registration_open = (
        selected_session is not None
        and selected_session.status != 'closed'
        and selected_session.is_registration_open
    )

    # ── Semester courses ───────────────────────────────────────────────────
    semester_courses        = []
    registered_course_ids   = set()
    registered_courses      = []
    registration_submitted  = False
    registration_finalized  = False
    registered_credit_total = 0
    core_credit_total       = 0
    semester_courses_debug  = {}

    # Pull max from Program model — never hardcoded
    max_credits_per_semester = (
        profile.program.max_credits_per_semester
        if profile and profile.program
        else 24
    )

    if profile and profile.program and selected_session and selected_term:
        normalised_term = term_normalisation_map.get(selected_term, selected_term)

        semester_courses = list(
            Course.objects
            .filter(
                program=profile.program,
                year_of_study=profile.year_of_study,
                is_active=True,
            )
            .filter(Q(semester=normalised_term) | Q(semester='annual'))
            .prefetch_related('prerequisites')
            .order_by('course_type', 'name')
        )

        existing_regs = CourseRegistration.objects.filter(
            student=user,
            session=selected_session,
            term__in=[selected_term, normalised_term],
            status__in=['pending', 'approved'],
        ).select_related('course')

        registered_course_ids  = {r.course_id for r in existing_regs}
        registered_courses     = list(existing_regs)
        registration_submitted = existing_regs.exists()
        # True when ALL existing registrations for this term are approved (finalized)
        registration_finalized = (
            registration_submitted
            and not existing_regs.filter(status='pending').exists()
        )

        # Build a map of course_id → registration status for the template
        reg_status_map = {r.course_id: r.status for r in existing_regs}

        for course in semester_courses:
            course.is_registered = course.id in registered_course_ids
            course.is_core       = course.course_type == 'core'
            course.registration_status = reg_status_map.get(course.id, '')  # 'pending' | 'approved' | ''
            if course.course_type == 'core':
                core_credit_total += course.credit_units

        registered_credit_total = sum(
            c.credit_units for c in semester_courses if c.is_registered
        )

        semester_courses_debug = {
            'program': str(profile.program),
            'year_of_study': profile.year_of_study,
            'term': selected_term,
            'normalised_term': normalised_term,
            'max_cu': max_credits_per_semester,
            'core_cu': core_credit_total,
            'count': len(semester_courses),
        }
    else:
        semester_courses_debug = {
            'profile_exists': bool(profile),
            'program': str(getattr(profile, 'program', None)) if profile else None,
            'session': str(selected_session),
            'term': selected_term,
        }

    # Finalize allowed only when all core courses are selected and max not exceeded
    can_finalize = (
        registered_credit_total >= core_credit_total
        and registered_credit_total <= max_credits_per_semester
        and registered_credit_total > 0
    )

    # count only pending (newly selected, not yet approved) courses for the confirm modal
    new_registration_count = sum(
        1 for c in semester_courses
        if c.is_registered and getattr(c, 'registration_status', '') == 'pending'
    )

    # ── LMS Enrollments — only show courses for selected session ──────────
    status_filter = request.GET.get('status', 'active')
    if status_filter not in ['active', 'completed']:
        status_filter = 'active'

    try:
        # Only show enrollments for sessions where the student has approved registrations
        approved_session_ids = CourseRegistration.objects.filter(
            student=user, status='approved'
        ).values_list('session_id', flat=True).distinct()

        enrollment_qs = Enrollment.objects.filter(student=user)
        if selected_session:
            # Normalise term for matching (fall→first, spring→second, etc.)
            _norm_term = term_normalisation_map.get(selected_term, selected_term) if selected_term else None
            session_term_filter = Q(course__session=selected_session) & Q(course__session__in=approved_session_ids)
            enrollment_qs = enrollment_qs.filter(session_term_filter)

        if status_filter == 'all':
            enrollment_qs = enrollment_qs.filter(status__in=['active', 'completed'])
        else:
            enrollment_qs = enrollment_qs.filter(status=status_filter)

        enrollments = (
            enrollment_qs
            .select_related('course', 'course__instructor')
            .prefetch_related(
                Prefetch(
                    'course__lessons',
                    queryset=Lesson.objects.filter(is_active=True),
                    to_attr='active_lessons',
                )
            )
            .order_by('-enrolled_at')
        )

        for enrollment in enrollments:
            enrollment.completed_lessons_count = LessonProgress.objects.filter(
                enrollment=enrollment, is_completed=True
            ).count()

    except Exception:
        messages.error(request, 'Error loading your enrolled courses. Please try again.')
        enrollments = []

    # ── Academic identity ──────────────────────────────────────────────────
    department = faculty = None
    if profile and profile.program:
        department = getattr(profile.program, 'department', None)
        faculty    = getattr(department, 'faculty', None) if department else None

    # Build term label from session's own term_dates JSON entries
    term_label = ''
    if selected_session and selected_term:
        term_label_map = dict(AcademicSession.TERM_CHOICES)
        term_label = term_label_map.get(selected_term, selected_term.title())

    context = {
        'page_title':               'My Courses',
        'all_sessions':             all_sessions,
        'new_registration_count':   new_registration_count,
        'status_options':           [('active', 'Active'), ('completed', 'Completed')],
        'selected_session':         selected_session,
        'selected_term':            selected_term,
        'term_label':               term_label,
        'registration_open':        registration_open,
        'selected_term_is_active':  selected_term_is_active,
        'semester_courses':         semester_courses,
        'registered_course_ids':    registered_course_ids,
        'registered_courses':       registered_courses,
        'registered_credit_total':  registered_credit_total,
        'max_credits_per_semester': max_credits_per_semester,
        'core_credit_total':        core_credit_total,
        'can_finalize':             can_finalize,
        'registration_submitted':   registration_submitted,
        'registration_finalized':   registration_finalized,
        'enrollments':              enrollments,
        'status_filter':            status_filter,
        'profile':                  profile,
        'department':               department,
        'faculty':                  faculty,
        }

    return render(request, 'students/my_courses.html', context)

@login_required
@student_required
def register_semester_course(request, course_slug):
    """
    Add course with dynamic max credit check from Program model.
    """
    if request.method != 'POST':
        return redirect('students:my_courses')

    profile = getattr(request.user, 'profile', None)
    session_id = request.POST.get('session_id')
    term_override = request.POST.get('term_override', '').strip()
    try:
        current_session = AcademicSession.objects.get(pk=session_id) if session_id else AcademicSession.get_current()
    except AcademicSession.DoesNotExist:
        current_session = AcademicSession.get_current()
    current_term = term_override or (current_session.get_current_term() if current_session else None)

    if not current_session or not current_term or not profile or not profile.program:
        messages.error(request, 'Missing session or program information.')
        return redirect('students:my_courses')

    if current_session.status == 'closed':
        messages.error(request, f'The session "{current_session}" has ended. No changes are allowed.')
        return redirect('students:my_courses')

    if not current_session.is_registration_open:
        reg_open, reg_close = current_session.get_registration_window()
        window_str = current_session.registration_window_for_term(current_session.get_current_term())
        messages.error(request, f'Course registration for "{current_session}" is currently closed. Registration opens: {window_str}.')
        return redirect('students:my_courses')

    course = get_object_or_404(
        Course,
        slug=course_slug,
        program=profile.program,
        year_of_study=profile.year_of_study,
        is_active=True,
    )

    # Dynamic max from the Program model
    MAX_CREDITS_PER_SEMESTER = getattr(profile.program, 'max_credits_per_semester', 24)

    normalised_term = current_term.lower().replace(' semester', '').strip() if current_term else current_term

    current_total = CourseRegistration.objects.filter(
        student=request.user,
        session=current_session,
        term__in=[current_term, normalised_term],
        status__in=['pending', 'approved'],
    ).exclude(course=course).aggregate(
        total=Sum('course__credit_units')
    )['total'] or 0

    if current_total + course.credit_units > MAX_CREDITS_PER_SEMESTER:
        messages.error(
            request,
            f'Cannot add "{course.name}" — it would exceed the maximum '
            f'of {MAX_CREDITS_PER_SEMESTER} credit units for this semester '
            f'(you currently have {current_total} CU).'
        )
        return redirect('students:my_courses')

    reg, created = CourseRegistration.objects.get_or_create(
        student=request.user,
        course=course,
        session=current_session,
        term=current_term,
        defaults={'status': 'pending'},
    )

    if created:
        messages.success(request, f'✅ "{course.name}" ({course.credit_units} CU) added.')
        _notify(
            user=request.user,
            notification_type='enrollment',
            title='Course Added',
            message=f'You added {course.code} — {course.name} to your {current_term} semester registration.',
            link='/student/courses/',
        )
    elif reg.status == 'dropped':
        reg.status = 'pending'
        reg.dropped_at = None
        reg.save(update_fields=['status', 'dropped_at'])
        messages.success(request, f'✅ "{course.name}" re-added.')
    else:
        messages.info(request, f'You are already registered for "{course.name}".')

    from django.urls import reverse
    return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

@login_required
@student_required
def drop_semester_course(request, course_slug):
    """
    Remove a non-core Course from the student's semester registration.
    Core courses cannot be dropped.
    """
    if request.method != 'POST':
        return redirect('students:my_courses')

    profile = getattr(request.user, 'profile', None)
    session_id    = request.POST.get('session_id', '').strip()
    term_override = request.POST.get('term_override', '').strip()

    try:
        current_session = AcademicSession.objects.get(pk=session_id) if session_id else AcademicSession.get_current()
    except AcademicSession.DoesNotExist:
        current_session = AcademicSession.get_current()

    current_term = term_override or (current_session.get_current_term() if current_session else None)

    if not current_session or not current_term:
        messages.error(request, 'No active academic session found.')
        return redirect('students:my_courses')

    if current_session.status == 'closed':
        messages.error(request, f'The session "{current_session}" has ended. No changes are allowed.')
        return redirect('students:my_courses')

    if not current_session.is_registration_open:
        reg_open, reg_close = current_session.get_registration_window()
        window_str = current_session.registration_window_for_term(current_session.get_current_term())
        messages.error(request, f'Course registration for "{current_session}" is currently closed. Registration opens: {window_str}.')
        return redirect('students:my_courses')

    course = get_object_or_404(Course, slug=course_slug)

    if course.course_type == 'core':
        messages.error(request, f'"{course.name}" is a core course and cannot be removed.')
        return redirect('students:my_courses')

    reg = CourseRegistration.objects.filter(
        student=request.user,
        course=course,
        session=current_session,
        term=current_term,
        status__in=['pending', 'approved'],
    ).first()

    if reg:
        reg.status = 'dropped'
        reg.dropped_at = timezone.now()
        reg.save(update_fields=['status', 'dropped_at'], skip_clean=True)
        messages.success(request, f'"{course.name}" removed from your semester registration.')
    else:
        messages.warning(request, 'Registration record not found.')

    from django.urls import reverse
    return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

@login_required
@student_required
def register_all_semester_courses(request):
    """
    Finalize semester registration AND auto-enroll student into
    the linked LMSCourse for every registered academic Course.
    """
    if request.method != 'POST':
        return redirect('students:my_courses')

    profile = getattr(request.user, 'profile', None)

    session_id    = request.POST.get('session_id', '').strip()
    term_override = request.POST.get('term_override', '').strip()

    try:
        current_session = AcademicSession.objects.get(pk=session_id) if session_id else AcademicSession.get_current()
    except AcademicSession.DoesNotExist:
        current_session = AcademicSession.get_current()

    current_term = term_override or (current_session.get_current_term() if current_session else None)

    if not current_session or not current_term:
        messages.error(request, 'No active academic session found.')
        return redirect('students:my_courses')

    if current_session.status == 'closed':
        messages.error(request, f'The session "{current_session}" has ended. No changes are allowed.')
        return redirect('students:my_courses')

    if not current_session.is_registration_open:
        reg_open, reg_close = current_session.get_registration_window()
        window_str = current_session.registration_window_for_term(current_session.get_current_term())
        messages.error(request, f'Course registration for "{current_session}" is currently closed. Registration opens: {window_str}.')
        return redirect('students:my_courses')

    if not profile or not profile.program:
        messages.error(request, 'No program assigned to your profile.')
        return redirect('students:my_courses')

    normalised_term = term_normalisation_map.get(current_term, current_term)

    MAX_CU = profile.program.max_credits_per_semester

    # Get all pending/approved registrations for this session/term
    registered_regs = CourseRegistration.objects.filter(
        student=request.user,
        session=current_session,
        term__in=[current_term, normalised_term],
        status__in=['pending', 'approved'],
    ).select_related('course')

    # Validate: check credit total doesn't exceed max
    total_cu = sum(r.course.credit_units for r in registered_regs)
    if total_cu > MAX_CU:
        messages.error(
            request,
            f'Your selected courses total {total_cu} CU which exceeds the '
            f'maximum of {MAX_CU} CU for this semester. Please remove some courses first.'
        )
        from django.urls import reverse
        return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

    # Validate: ensure all core courses for this term are selected
    core_courses = Course.objects.filter(
        program=profile.program,
        year_of_study=profile.year_of_study,
        course_type='core',
        is_active=True,
    ).filter(Q(semester=normalised_term) | Q(semester='annual'))

    registered_course_ids = {r.course_id for r in registered_regs}
    missing_core = [c.name for c in core_courses if c.id not in registered_course_ids]

    if missing_core:
        messages.error(
            request,
            f'You must include all core courses before finalizing. '
            f'Missing: {", ".join(missing_core)}.'
        )
        from django.urls import reverse
        return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

    if total_cu == 0:
        messages.error(request, 'You have not selected any courses yet.')
        from django.urls import reverse
        return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

    # ── Step 1: Build LMS course lookup (FK match first, code fallback) ──────
    registered_academic_course_ids = [reg.course_id for reg in registered_regs]
    registered_course_codes = [
        reg.course.code.strip().upper()
        for reg in registered_regs
        if reg.course.code
    ]

    by_fk = LMSCourse.objects.filter(
        academic_course_id__in=registered_academic_course_ids,
    ).filter(Q(session=current_session) | Q(session__isnull=True))

    by_code = LMSCourse.objects.filter(
        academic_course__isnull=True,
        code__in=registered_course_codes,
    ).filter(
        Q(session=current_session) | Q(session__isnull=True)
    ) if registered_course_codes else LMSCourse.objects.none()

    from itertools import chain
    seen_lms_ids = set()
    lms_courses_to_enroll = []
    for lms in chain(by_fk, by_code):
        if lms.pk not in seen_lms_ids:
            seen_lms_ids.add(lms.pk)
            lms_courses_to_enroll.append(lms)

    # Build a map: academic_course_id → lms_course (for later lookup per reg)
    lms_by_academic_id = {}
    for lms in lms_courses_to_enroll:
        if lms.academic_course_id:
            lms_by_academic_id[lms.academic_course_id] = lms
        elif lms.code:
            # code-based fallback: map by code
            lms_by_academic_id[('code', lms.code.strip().upper())] = lms

    # ── Step 2: Per-registration — enroll only if LMS course exists AND has content ──
    enrolled_count = 0
    pending_count = 0

    for reg in registered_regs:
        # Find the matching LMS course for this specific registration
        lms_course = lms_by_academic_id.get(reg.course_id)
        if not lms_course and reg.course.code:
            lms_course = lms_by_academic_id.get(('code', reg.course.code.strip().upper()))

        has_lms   = lms_course is not None
        has_content = has_lms and lms_course.lessons.filter(is_active=True).exists()

        if has_lms and has_content:
            # ✅ LMS course exists and has content → enroll and approve
            enrollment, created = Enrollment.objects.get_or_create(
                student=request.user,
                course=lms_course,
                defaults={
                    'enrolled_by': request.user,
                    'status': 'active',
                },
            )
            if created or (not created and enrollment.status == 'dropped'):
                if not created:
                    enrollment.status = 'active'
                    enrollment.save(update_fields=['status'])
                enrolled_count += 1

            # Only approve if we actually enrolled
            if reg.status == 'pending':
                reg.status = 'approved'
                reg.save(update_fields=['status'])
        else:
            # ⏳ LMS course missing or has no content → keep as pending
            pending_count += 1
            # Leave reg.status = 'pending' — do NOT approve

    total_registered = registered_regs.count()

    if pending_count > 0 and enrolled_count > 0:
        messages.warning(
            request,
            f'⚠️ Partially finalized — {enrolled_count} course(s) enrolled. '
            f'{pending_count} course(s) are pending because their LMS content is not ready yet. '
            f'They will appear as "Register" buttons and you can retry enrollment later.'
        )
    elif pending_count > 0 and enrolled_count == 0:
        messages.warning(
            request,
            f'⚠️ Registration saved ({total_registered} course(s)) but no LMS courses are ready for enrollment yet. '
            f'Your registrations are saved as pending. Use the "Register" button per course to retry once content is available.'
        )
    else:
        messages.success(
            request,
            f'✅ Registration finalized — {total_registered} course(s) registered '
            f'and {enrolled_count} LMS course(s) enrolled for '
            f'{current_term.title()} Semester, {current_session}.'
        )

    _notify(
        user=request.user,
        notification_type='enrollment',
        title='Semester Registration Confirmed',
        message=(
            f'Your {current_term.title()} Semester registration for {current_session} '
            f'is complete. {total_registered} courses registered, {enrolled_count} enrolled, '
            f'{pending_count} pending LMS readiness.'
        ),
        link='/student/courses/',
    )

    from django.urls import reverse
    return redirect(f"{reverse('students:my_courses')}?session_id={current_session.pk}&term={current_term}")

@login_required
@student_required
def retry_lms_enrollment(request, course_slug):
    """
    Retry LMS enrollment for a single pending CourseRegistration.
    Called when student clicks the "Register" button on a pending course row.
    Returns JSON so the template can update the button without a page reload.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required.'}, status=405)

    session_id    = request.POST.get('session_id', '').strip()
    term_override = request.POST.get('term_override', '').strip()

    try:
        current_session = AcademicSession.objects.get(pk=session_id) if session_id else AcademicSession.get_current()
    except AcademicSession.DoesNotExist:
        current_session = AcademicSession.get_current()

    current_term = term_override or (current_session.get_current_term() if current_session else None)

    course = get_object_or_404(
        Course, slug=course_slug,
        program=request.user.profile.program,
        is_active=True,
    )

    reg = CourseRegistration.objects.filter(
        student=request.user,
        course=course,
        session=current_session,
        term__in=[current_term, term_normalisation_map.get(current_term, current_term)],
        status='pending',
    ).first()

    if not reg:
        return JsonResponse({
            'status': 'error',
            'message': 'No pending registration found for this course.',
        })

    # Find matching LMS course
    lms_course = None
    if course.code:
        lms_course = LMSCourse.objects.filter(
            Q(academic_course=course) |
            Q(academic_course__isnull=True, code__iexact=course.code)
        ).filter(
            Q(session=current_session) | Q(session__isnull=True)
        ).first()

    if not lms_course:
        return JsonResponse({
            'status': 'pending',
            'message': 'Course is not yet ready for enrollment. Please check back later.',
        })

    has_content = lms_course.lessons.filter(is_active=True).exists()
    if not has_content:
        return JsonResponse({
            'status': 'pending',
            'message': 'Course is not yet ready for enrollment — content has not been published.',
        })

    # ✅ LMS course exists and has content — enroll now
    enrollment, created = Enrollment.objects.get_or_create(
        student=request.user,
        course=lms_course,
        defaults={'enrolled_by': request.user, 'status': 'active'},
    )
    if not created and enrollment.status == 'dropped':
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])

    reg.status = 'approved'
    reg.save(update_fields=['status'])

    _notify(
        user=request.user,
        notification_type='enrollment',
        title='Course Enrollment Confirmed',
        message=f'You have been enrolled in {course.code} — {course.name}.',
        link='/student/courses/',
    )

    return JsonResponse({
        'status': 'enrolled',
        'message': f'Successfully enrolled in {course.name}.',
    })

@login_required
@student_required
def course_catalog(request):
    profile         = getattr(request.user, 'profile', None)
    current_session = AcademicSession.get_current()
    search_query    = request.GET.get('q', '').strip()
    term_filter     = request.GET.get('term', '').strip()

    courses = LMSCourse.objects.filter(
        is_published=True,
        academic_course__program=profile.program,
        academic_course__year_of_study=profile.year_of_study,
        academic_course__is_active=True,
    ).filter(
        Q(session=current_session) | Q(session__isnull=True)
    )

    if term_filter:
        courses = courses.filter(term=term_filter)
    if search_query:
        courses = courses.filter(Q(title__icontains=search_query) | Q(code__icontains=search_query))

    courses = courses.select_related('academic_course', 'instructor', 'session').distinct()

    enrolled_course_ids = set(
        Enrollment.objects
        .filter(student=request.user, status__in=['active', 'completed'])
        .values_list('course_id', flat=True)
    )
    registered_academic_ids = set(
        CourseRegistration.objects
        .filter(student=request.user, session=current_session, status__in=['pending', 'approved'])
        .values_list('course_id', flat=True)
    ) if current_session else set()

    # Enrolled first → registered → locked
    courses = sorted(courses, key=lambda c: (
        0 if c.id in enrolled_course_ids else
        1 if c.academic_course_id in registered_academic_ids else 2
    ))

    context = {
        'page_title':              'Course Catalog',
        'courses':                 Paginator(courses, 12).get_page(request.GET.get('page', 1)),
        'enrolled_ids':            enrolled_course_ids,
        'registered_academic_ids': registered_academic_ids,
        'search_query':            search_query,
        'term_filter':             term_filter,
        'term_choices':            LMSCourse._meta.get_field('term').choices,
    }
    return render(request, 'students/course_catalog.html', context)


@login_required
@student_required
def course_detail(request, course_slug):
    """
    Display comprehensive course details
    - Uses slug for SEO-friendly URLs
    - Efficient queries with select_related/prefetch_related
    - Different views for enrolled vs non-enrolled students
    - Security: Validates enrollment status
    """
    try:
        # Fetch course with related data in single query
        course = get_object_or_404(
            LMSCourse.objects
            .select_related('instructor')
            .prefetch_related(
                Prefetch(
                    'sections',
                    queryset=LessonSection.objects
                    .filter(is_active=True)
                    .prefetch_related(
                        Prefetch(
                            'lessons',
                            queryset=Lesson.objects.filter(is_active=True).order_by('display_order'),
                            to_attr='active_lessons'
                        )
                    )
                    .order_by('display_order'),
                    to_attr='active_sections'
                )
            ),
            slug=course_slug,
            is_published=True
        )
        
        # Check if student is enrolled
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course
        ).select_related('course').first()
        
        # Prepare sections with filtered lessons
        sections = course.active_sections
        
        for section in sections:
            if enrollment:
                # Enrolled: show all lessons
                section.filtered_lessons = section.active_lessons
            else:
                # Not enrolled: show only preview lessons
                section.filtered_lessons = [
                    lesson for lesson in section.active_lessons 
                    if lesson.is_preview
                ]
        
        # Calculate progress for enrolled students
        if enrollment:
            completed_count = LessonProgress.objects.filter(
                enrollment=enrollment,
                is_completed=True
            ).count()
            enrollment.completed_lessons_count = completed_count
            
            # Get the first incomplete lesson for "Continue Learning" button
            first_incomplete_lesson = None
            for section in sections:
                for lesson in section.filtered_lessons:
                    # Check if lesson is not completed
                    is_completed = LessonProgress.objects.filter(
                        enrollment=enrollment,
                        lesson=lesson,
                        is_completed=True
                    ).exists()
                    
                    if not is_completed:
                        first_incomplete_lesson = lesson
                        break
                if first_incomplete_lesson:
                    break
            
            enrollment.next_lesson = first_incomplete_lesson
        
        existing_review = None
        if enrollment:
            existing_review = Review.objects.filter(
                course=course,
                student=request.user
            ).first()

        # ── Enrollment eligibility check ──────────────────────────────────
        # Student can only enroll if they have an approved CourseRegistration
        # for the academic course linked to this LMS course in its session/term.
        can_enroll = False
        enroll_blocked_reason = ''

        if enrollment:
            # Already enrolled — no need to check further
            can_enroll = True
        elif course.academic_course and course.session:
            # Check for an approved registration for this academic course + session + term
            _TERM_MAP = {'fall': 'first', 'spring': 'second', 'summer': 'annual', 'third': 'second'}
            lms_term = course.term or ''
            lms_term_norm = _TERM_MAP.get(lms_term, lms_term)

            term_filter = Q(term=lms_term) | Q(term=lms_term_norm) if lms_term else Q()

            approved_reg = CourseRegistration.objects.filter(
                student=request.user,
                course=course.academic_course,
                session=course.session,
                status='approved',
            ).filter(term_filter).first()

            if approved_reg:
                # Also check session is not closed and registration window is valid
                if course.session.status == 'closed':
                    can_enroll = False
                    enroll_blocked_reason = 'This course belongs to a session that has ended.'
                else:
                    can_enroll = True
            else:
                can_enroll = False
                enroll_blocked_reason = (
                    'You have not registered for this course in your semester registration. '
                    'Go to My Courses, select the correct session and semester, add this course, '
                    'then finalize your registration to gain access.'
                )
        else:
            # Standalone LMS course with no academic course link — open enrollment
            can_enroll = True

        context = {
            'page_title': course.title,
            'course': course,
            'enrollment': enrollment,
            'sections': sections,
            'existing_review': existing_review,
            'can_enroll': can_enroll,
            'enroll_blocked_reason': enroll_blocked_reason,
        }
        
        return render(request, 'students/course_detail.html', context)
        
    except Exception as e:
        # Log error in production
        messages.error(
            request,
            'An error occurred loading the course. Please try again.'
        )
        return redirect('students:course_catalog')


@login_required
@student_required
def enroll_course(request, course_slug):
    """
    Enroll in a course.
    All LMS courses are free — enrollment is immediate.
    """
    
    # Get course by slug
    course = get_object_or_404(
        LMSCourse, 
        slug=course_slug, 
        is_published=True
    )
    
    # Check existing enrollment
    existing = Enrollment.objects.filter(
        student=request.user,
        course=course
    ).first()
    
    if existing:
        messages.info(
            request, 
            'You are already enrolled in this course.'
        )
        return redirect('students:course_detail', course_slug=course_slug)

    # ── Registration gate: only enroll if student has an approved registration ──
    if course.academic_course and course.session:
        _TERM_MAP = {'fall': 'first', 'spring': 'second', 'summer': 'annual', 'third': 'second'}
        lms_term = course.term or ''
        lms_term_norm = _TERM_MAP.get(lms_term, lms_term)
        term_filter = Q(term=lms_term) | Q(term=lms_term_norm) if lms_term else Q()

        approved_reg = CourseRegistration.objects.filter(
            student=request.user,
            course=course.academic_course,
            session=course.session,
            status='approved',
        ).filter(term_filter).first()

        if not approved_reg:
            messages.error(
                request,
                'You cannot enroll in this course directly. Please register for it through '
                'your semester course registration (My Courses), finalize your registration, '
                'and you will be enrolled automatically.'
            )
            return redirect('students:course_detail', course_slug=course_slug)

        if course.session.status == 'closed':
            messages.error(request, 'Enrollment is closed — this course belongs to a past session.')
            return redirect('students:course_detail', course_slug=course_slug)

    # Enroll directly (standalone LMS course or registration confirmed above)
    try:
        Enrollment.objects.create(
            student=request.user,
            course=course,
            enrolled_by=request.user,
            status='active',
        )
        messages.success(
            request,
            f'Successfully enrolled in {course.title}!'
        )
        _notify(
            user=request.user,
            notification_type='enrollment',
            title=f'Enrolled in {course.title}',
            message=f'You have successfully enrolled in "{course.title}". Start learning now!',
            link=f'/student/courses/{course.slug}/',
        )
    except Exception as e:
        messages.error(
            request,
            'An error occurred during enrollment. Please try again.'
        )
    
    return redirect('students:course_detail', course_slug=course_slug)

@login_required
@student_required
def lesson_view(request, course_slug, lesson_slug):
    """
    View lesson content using slug
    Tracks progress and provides navigation
    """
    # Get lesson by slug
    lesson = get_object_or_404(
        Lesson.objects.select_related(
            'course', 
            'section'
        ),
        course__slug=course_slug,
        slug=lesson_slug,
        is_active=True
    )
    
    # Verify enrollment — preview lessons are accessible without enrollment
    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=lesson.course,
        status__in=['active', 'completed']
    ).first()

    if not enrollment and not lesson.is_preview:
        messages.error(request, 'You must be enrolled to access this lesson.')
        return redirect('students:course_detail', course_slug=course_slug)

    # Track progress only for enrolled students
    progress = None
    if enrollment:
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={'last_accessed': timezone.now()}
        )
        if not created:
            progress.last_accessed = timezone.now()
            progress.save(update_fields=['last_accessed'])

    # Get all lessons in course for navigation
    all_lessons = list(
        Lesson.objects.filter(
            course=lesson.course,
            is_active=True
        ).select_related('section')
        .order_by('section__display_order', 'display_order')
    )

    # Get completed lesson IDs — only meaningful if enrolled
    completed_lesson_ids = set()
    if enrollment:
        completed_lesson_ids = set(
            LessonProgress.objects.filter(
                enrollment=enrollment,
                is_completed=True
            ).values_list('lesson_id', flat=True)
        )

    # Add completion status to all lessons
    for l in all_lessons:
        l.is_completed = l.id in completed_lesson_ids

    # Find current lesson index for prev/next navigation
    try:
        current_index = next(
            i for i, l in enumerate(all_lessons)
            if l.id == lesson.id
        )
    except StopIteration:
        current_index = None

    prev_lesson = None
    next_lesson = None
    if current_index is not None:
        if current_index > 0:
            prev_lesson = all_lessons[current_index - 1]
        if current_index < len(all_lessons) - 1:
            next_lesson = all_lessons[current_index + 1]

    # Attach completed count to enrollment object if enrolled
    if enrollment:
        enrollment.completed_lessons = len(completed_lesson_ids)

    context = {
        'page_title': lesson.title,
        'lesson': lesson,
        'enrollment': enrollment,
        'progress': progress,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
    }

    return render(request, 'students/lesson.html', context)

def _score_to_grade(percentage):
    """Convert numeric percentage to letter grade."""
    if percentage >= 70:   return 'A'
    elif percentage >= 60: return 'B'
    elif percentage >= 50: return 'C'
    elif percentage >= 45: return 'D'
    else:                  return 'F'


def _record_academic_grade(user, enrollment, lms_course):
    """
    Automatically record a CourseGrade when a linked LMS course is completed.
    Derives score from quiz attempts and graded assignment submissions
    in this course. Falls back to 0 if no assessments exist yet.
    Uses the current active AcademicSession.
    """
    from eduweb.models import AcademicSession, CourseApplication

    academic_course = lms_course.academic_course
    session = AcademicSession.get_current()
    if not session:
        return  # No active session — grade cannot be pinned to a session yet

    # ── Quiz score: best attempt percentage per quiz in this course ───────
    quiz_attempts = (
        QuizAttempt.objects
        .filter(
            student=user,
            quiz__lesson__course=lms_course,
            is_completed=True,
        )
        .values('quiz_id')
        .annotate(best=Max('percentage'))
    )
    quiz_scores = [float(row['best']) for row in quiz_attempts]

    # ── Assignment score: graded submissions as percentage of max_score ───
    assignment_scores_qs = (
        AssignmentSubmission.objects
        .filter(
            student=user,
            assignment__lesson__course=lms_course,
            status='graded',
            score__isnull=False,
        )
        .annotate(
            pct=F('score') * 100.0 / F('assignment__max_score')
        )
        .values_list('pct', flat=True)
    )
    assignment_scores = [float(s) for s in assignment_scores_qs]

    # ── Combined average ──────────────────────────────────────────────────
    all_scores = quiz_scores + assignment_scores
    if all_scores:
        avg_score = sum(all_scores) / len(all_scores)
    else:
        # No assessments graded yet — use lesson completion as proxy (100%)
        avg_score = float(enrollment.progress_percentage)

    letter_grade = _score_to_grade(avg_score)
    is_passed = avg_score >= 50  # configurable threshold

    # ── Link to CourseApplication if available ────────────────────────────
    application = (
        CourseApplication.objects
        .filter(user=user, program=academic_course.program)
        .first()
    )

    # ── Create or update CourseGrade ──────────────────────────────────────
    CourseGrade.objects.update_or_create(
        student=user,
        course=academic_course,
        session=session,
        defaults={
            'score':        round(avg_score, 2),
            'grade':        letter_grade,
            'credit_units': academic_course.credit_units,
            'is_passed':    is_passed,
            'application':  application,
            'recorded_by':  None,
        }
    )

    # Check if student has now completed all core courses in the program
    if application:
        application.award_program_certificate()

@login_required
@student_required
def certificate_print(request, certificate_id):
    cert = get_object_or_404(
        Certificate,
        certificate_id=certificate_id,
        student=request.user,
    )
    # Redirect to payment if not yet unlocked
    if cert.payment_status != 'paid':
        messages.warning(request, 'Please complete payment to access your certificate.')
        return redirect('students:my_payments')

    if cert.certificate_type == 'program' and cert.program:
        cert.display_title = cert.program.name
        cert.display_subtitle = (
            cert.program.department.faculty.name
            if cert.program.department else ''
        )
        cert.issuer = 'MIU Academic Office'
        cert.is_program_cert = True
    else:
        cert.display_title = cert.course.title if cert.course else 'Course Certificate'
        cert.display_subtitle = ''
        cert.is_program_cert = False
        cert.issuer = (
            cert.course.instructor.get_full_name()
            if cert.course and cert.course.instructor else 'MIU Staff'
        )

    return render(request, 'students/certificate_print.html', {'cert': cert})

@login_required
@student_required
def mark_lesson_complete(request, course_slug, lesson_slug):
    """
    Mark lesson as complete via AJAX
    Updates enrollment progress
    """
    from django.http import JsonResponse
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method'
        }, status=400)
    
    # Get lesson
    lesson = get_object_or_404(
        Lesson,
        course__slug=course_slug,
        slug=lesson_slug,
        is_active=True
    )
    
    # Verify enrollment — allow preview lessons for non-enrolled students
    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=lesson.course,
        status__in=['active', 'completed']
    ).first()

    if not enrollment and not lesson.is_preview:
        messages.error(request, 'You must be enrolled to access this lesson.')
        return redirect('students:course_detail', course_slug=course_slug)
    
    try:
        # Get or create progress
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )
        
        # Mark as complete
        if not progress.is_completed:
            progress.is_completed = True
            progress.completion_percentage = 100
            progress.completed_at = timezone.now()
            progress.save()
            
            # Update enrollment progress
            if hasattr(enrollment, 'update_progress'):
                enrollment.update_progress()
                enrollment.refresh_from_db()
                # Notify when the entire course is completed
                if enrollment.status == 'completed':
                    lms_course = enrollment.course

                    if lms_course.academic_course_id:
                        # Linked to an academic Course — record grade automatically
                        _record_academic_grade(request.user, enrollment, lms_course)
                        _notify(
                            user=request.user,
                            notification_type='enrollment',
                            title=f'Unit Completed: {lms_course.title}',
                            message=f'You have completed \"{lms_course.title}\". '
                                    f'Your academic grade has been recorded.',
                            link='/student/grades/',
                        )
                    else:
                        # Standalone LMS course — issue individual certificate
                        if lms_course.has_certificate:
                            cert, created = Certificate.objects.get_or_create(
                                student=request.user,
                                course=lms_course,
                                certificate_type='lms_course',
                                defaults={
                                    'completion_date': timezone.now().date(),
                                    'payment_status': 'unpaid' if lms_course.certificate_fee > 0 else 'paid',
                                }
                            )
                            _notify(
                                user=request.user,
                                notification_type='enrollment',
                                title=f'Course Completed: {lms_course.title}',
                                message=f'Congratulations! You have completed \"{lms_course.title}\". '
                                        + ('Pay your certificate fee to download your certificate.' if lms_course.certificate_fee > 0 else 'Your certificate is ready to download.'),
                                link='/student/certificates/',
                            )

        return JsonResponse({
            'success': True,
            'message': 'Lesson marked as complete',
            'progress': float(enrollment.progress_percentage),
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'An error occurred. Please try again.'
        }, status=500)


@login_required
@student_required
def assignments(request):
    """
    Display student's assignments with filtering
    Supports: pending, submitted, graded, all
    """
    # Get and validate status filter
    status_filter = request.GET.get('status', 'pending').lower()
    valid_statuses = ['pending', 'submitted', 'graded', 'all']
    
    if status_filter not in valid_statuses:
        status_filter = 'pending'
    
    try:
        # Get user's enrolled course IDs
        enrolled_course_ids = (
            Enrollment.objects
            .filter(
                student=request.user,
                status__in=['active', 'completed']
            )
            .values_list('course_id', flat=True)
        )
        
        # Base query: assignments from enrolled courses
        assignments_query = (
            Assignment.objects
            .filter(
                lesson__course_id__in=enrolled_course_ids,
                is_active=True
            )
            .select_related(
                'lesson__course',
            )
            .prefetch_related(
                Prefetch(
                    'submissions',
                    queryset=AssignmentSubmission.objects.filter(
                        student=request.user
                    ).select_related('graded_by'),
                    to_attr='user_submissions'
                )
            )
            .order_by('due_date')
        )
        
        # Apply status filtering
        if status_filter == 'pending':
            # Not submitted OR draft status
            assignments_query = assignments_query.exclude(
                submissions__student=request.user,
                submissions__status__in=['submitted', 'graded']
            ).distinct()
            
        elif status_filter == 'submitted':
            # Submitted but not graded
            assignments_query = assignments_query.filter(
                submissions__student=request.user,
                submissions__status='submitted'
            ).distinct()
            
        elif status_filter == 'graded':
            # Graded assignments
            assignments_query = assignments_query.filter(
                submissions__student=request.user,
                submissions__status='graded'
            ).distinct()
        
        # For 'all', no additional filtering needed
        
        # Execute query
        assignments_list = list(assignments_query)
        
        # Add submission info and overdue status
        for assignment in assignments_list:
            # Get user's submission if exists
            assignment.submission = (
                assignment.user_submissions[0] 
                if assignment.user_submissions 
                else None
            )
            
            if not assignment.submission or assignment.submission.status == 'draft':
                assignment._is_overdue_override = timezone.now() > assignment.due_date
            else:
                assignment._is_overdue_override = False
                
    except Exception as e:
        messages.error(
            request,
            'Error loading assignments. Please try again.'
        )
        assignments_list = []
    
    context = {
        'page_title': 'My Assignments',
        'assignments': assignments_list,
        'status_filter': status_filter,
    }
    
    return render(request, 'students/assignments.html', context)


@login_required
@student_required
def assignment_detail(request, course_slug, assignment_slug):
    """
    View assignment details
    Uses course slug and assignment slug for SEO-friendly URLs
    """
    # Get assignment with related data
    assignment = get_object_or_404(
        Assignment.objects.select_related(
            'lesson__course',
            'lesson__section'
        ),
        lesson__course__slug=course_slug,
        slug=assignment_slug,
        is_active=True
    )
    
    # Verify student is enrolled in the course
    enrollment = get_object_or_404(
        Enrollment,
        student=request.user,
        course=assignment.lesson.course,
        status__in=['active', 'completed']
    )
    
    # Get student's submission if exists
    try:
        submission = AssignmentSubmission.objects.select_related(
            'graded_by'
        ).get(
            assignment=assignment,
            student=request.user
        )
    except AssignmentSubmission.DoesNotExist:
        submission = None
    
    # Check if overdue
    is_overdue = (
        timezone.now() > assignment.due_date 
        and not submission
    )
    
    context = {
        'page_title': assignment.title,
        'assignment': assignment,
        'submission': submission,
        'enrollment': enrollment,
        'is_overdue': is_overdue,
    }
    
    return render(request, 'students/assignment_detail.html', context)


@login_required
@student_required
def submit_assignment(request, course_slug, assignment_slug):
    """
    Handle assignment submission
    Uses Django forms for validation
    """
    # Get assignment
    assignment = get_object_or_404(
        Assignment.objects.select_related('lesson__course'),
        lesson__course__slug=course_slug,
        slug=assignment_slug,
        is_active=True
    )
    
    # Verify enrollment
    enrollment = get_object_or_404(
        Enrollment,
        student=request.user,
        course=assignment.lesson.course,
        status__in=['active', 'completed']
    )
    
    # Check if already submitted
    existing_submission = AssignmentSubmission.objects.filter(
        assignment=assignment,
        student=request.user,
        status__in=['submitted', 'graded']
    ).first()
    
    if existing_submission:
        messages.info(
            request,
            'You have already submitted this assignment.'
        )
        return redirect(
            'students:assignment_detail',
            course_slug=course_slug,
            assignment_slug=assignment_slug
        )
    
    # Check if overdue and late submissions not allowed
    is_overdue = timezone.now() > assignment.due_date
    
    if is_overdue and not assignment.allow_late_submission:
        messages.error(
            request,
            'This assignment is past due and no longer accepts submissions.'
        )
        return redirect(
            'students:assignment_detail',
            course_slug=course_slug,
            assignment_slug=assignment_slug
        )
    
    if request.method == 'POST':
        form = AssignmentSubmissionForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Create or update submission
                submission, created = AssignmentSubmission.objects.get_or_create(
                    assignment=assignment,
                    student=request.user,
                    defaults={
                        'submission_text': form.cleaned_data['submission_text'],
                        'status': 'submitted',
                        'submitted_at': timezone.now(),
                        'is_late': is_overdue,
                    }
                )
                
                # If not created, update existing draft
                if not created:
                    submission.submission_text = (
                        form.cleaned_data['submission_text']
                    )
                    submission.status = 'submitted'
                    submission.submitted_at = timezone.now()
                    submission.is_late = is_overdue
                
                # Handle file upload
                if 'attachment' in request.FILES:
                    submission.attachment = request.FILES['attachment']
                
                submission.save()
                
                # Success message
                if is_overdue:
                    messages.warning(
                        request,
                        f'Assignment submitted successfully! '
                        f'Note: This is a late submission and may '
                        f'incur a {assignment.late_penalty_percent}% penalty.'
                    )
                else:
                    messages.success(
                        request,
                        'Assignment submitted successfully!'
                    )
                _notify(
                    user=request.user,
                    notification_type='assignment',
                    title=f'Assignment Submitted: {assignment.title}',
                    message=(
                        f'Your submission for "{assignment.title}" has been received'
                        + (' (late submission — a penalty may apply).' if is_overdue
                           else '. You will be notified when it is graded.')
                    ),
                    link=f'/student/courses/{course_slug}/assignments/{assignment_slug}/',
                )
                
                return redirect(
                    'students:assignment_detail',
                    course_slug=course_slug,
                    assignment_slug=assignment_slug
                )
                
            except Exception as e:
                messages.error(
                    request,
                    'Error submitting assignment. Please try again.'
                )
        else:
            messages.error(
                request,
                'Please correct the errors in the form.'
            )
    else:
        # GET request - redirect to detail page
        return redirect(
            'students:assignment_detail',
            course_slug=course_slug,
            assignment_slug=assignment_slug
        )
    
    # If form errors, redirect back with messages
    return redirect(
        'students:assignment_detail',
        course_slug=course_slug,
        assignment_slug=assignment_slug
    )


# ==================== QUIZZES ====================
@login_required
@student_required
def quiz_list(request):
    """
    List all quizzes with filtering and status
    """
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')

    # Get enrolled course IDs
    enrolled_courses = Enrollment.objects.filter(
        student=request.user,
        status='active'
    ).values_list('course_id', flat=True)

    # Base queryset with optimization
    quizzes = Quiz.objects.filter(
        lesson__course_id__in=enrolled_courses,
        is_active=True
    ).select_related(
        'lesson',
        'lesson__course',
    ).prefetch_related(
        'questions'
    ).order_by('-created_at')

    # Annotate with attempt information
    quiz_list = []
    for quiz in quizzes:
        # Get all attempts for this quiz
        attempts = QuizAttempt.objects.filter(
            quiz=quiz,
            student=request.user,
            is_completed=True
        )

        # Calculate statistics
        attempt_count = attempts.count()
        best_score = (
            attempts.aggregate(Max('percentage'))
            ['percentage__max'] or 0
        )
        latest_attempt = attempts.order_by(
            '-completed_at'
        ).first()

        # Determine status
        has_passed = attempts.filter(passed=True).exists()
        can_attempt = (
            quiz.max_attempts == 0 or
            attempt_count < quiz.max_attempts
        )

        # Determine quiz status
        if has_passed:
            quiz_status = 'passed'
        elif attempt_count > 0 and not can_attempt:
            quiz_status = 'failed'
        elif attempt_count > 0:
            quiz_status = 'pending'
        else:
            quiz_status = 'not_started'

        # Apply status filter
        if status_filter != 'all':
            if status_filter != quiz_status:
                continue

        # Add computed fields
        quiz.attempt_count = attempt_count
        quiz.best_score = best_score
        quiz.latest_attempt = latest_attempt
        quiz.has_passed = has_passed
        quiz.can_attempt = can_attempt
        quiz.quiz_status = quiz_status

        quiz_list.append(quiz)

    context = {
        'page_title': 'Quizzes',
        'quizzes': quiz_list,
        'status_filter': status_filter,
    }

    return render(request, 'students/quiz_list.html', context)


@login_required
@student_required
def quiz_detail(request, course_slug, lesson_slug, quiz_slug):
    """
    View quiz details using slug-based URL
    """
    # Get quiz with related data
    quiz = get_object_or_404(
        Quiz.objects.select_related(
            'lesson',
            'lesson__course',
        ).prefetch_related('questions'),
        slug=quiz_slug,
        lesson__slug=lesson_slug,
        lesson__course__slug=course_slug
    )

    # Verify enrollment
    enrollment = get_object_or_404(
        Enrollment,
        student=request.user,
        course=quiz.lesson.course
    )

    # Get previous attempts
    attempts = QuizAttempt.objects.filter(
        quiz=quiz,
        student=request.user,
        is_completed=True
    ).select_related('quiz').order_by('-completed_at')

    # Check if can attempt
    attempt_count = attempts.count()
    can_attempt = (
        quiz.max_attempts == 0 or
        attempt_count < quiz.max_attempts
    )

    # Get best score
    best_score = (
        attempts.aggregate(Max('percentage'))
        ['percentage__max'] or 0
    )

    context = {
        'page_title': quiz.title,
        'quiz': quiz,
        'attempts': attempts,
        'attempt_count': attempt_count,
        'can_attempt': can_attempt,
        'best_score': best_score,
        'enrollment': enrollment,
    }

    return render(request, 'students/quiz_detail.html', context)


@login_required
@student_required
def quiz_take(request, course_slug, lesson_slug, quiz_slug):
    """
    Take quiz using slug-based URL
    """
    # Get quiz
    quiz = get_object_or_404(
        Quiz.objects.select_related(
            'lesson__course'
        ).prefetch_related('questions__answers'),
        slug=quiz_slug,
        lesson__slug=lesson_slug,
        lesson__course__slug=course_slug
    )

    # Verify enrollment
    enrollment = get_object_or_404(
        Enrollment,
        student=request.user,
        course=quiz.lesson.course,
        status='active'
    )

    # Check attempt limits
    attempts_count = QuizAttempt.objects.filter(
        quiz=quiz,
        student=request.user,
        is_completed=True
    ).count()

    if (
        quiz.max_attempts > 0 and
        attempts_count >= quiz.max_attempts
    ):
        messages.error(request, 'Maximum attempts reached.')
        return redirect(
            'students:quiz_detail',
            course_slug=course_slug,
            lesson_slug=lesson_slug,
            quiz_slug=quiz_slug
        )

    # Create new attempt
    attempt = QuizAttempt.objects.create(
        quiz=quiz,
        student=request.user,
        started_at=timezone.now()
    )

    # Get questions
    questions = quiz.questions.filter(
        is_active=True
    ).prefetch_related('answers').order_by('display_order')

    # Shuffle if enabled
    if quiz.shuffle_questions:
        questions = questions.order_by('?')

    context = {
        'page_title': f'Taking: {quiz.title}',
        'quiz': quiz,
        'attempt': attempt,
        'questions': questions,
        'course_slug': course_slug,
        'lesson_slug': lesson_slug,
        'quiz_slug': quiz_slug,
    }

    return render(request, 'students/quiz_take.html', context)


@login_required
@student_required
def quiz_submit(request, attempt_id):
    """
    Submit quiz answers
    """
    if request.method != 'POST':
        return redirect('students:quiz_list')

    # Get attempt
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related(
            'quiz__lesson__course'
        ),
        id=attempt_id,
        student=request.user
    )

    # Check if already completed
    if attempt.is_completed:
        messages.warning(request, 'Quiz already submitted.')
        return redirect(
            'students:quiz_result',
            attempt_id=attempt_id
        )

    # Process answers
    total_score = Decimal('0.00')
    max_score = Decimal('0.00')

    for key, value in request.POST.items():
        if key.startswith('question_'):
            try:
                question_id = int(key.split('_')[1])
                question = attempt.quiz.questions.get(
                    id=question_id
                )
                max_score += question.points

                # Get selected answer
                selected_answer = QuizAnswer.objects.get(
                    id=int(value)
                )

                # Calculate points
                points_earned = (
                    question.points
                    if selected_answer.is_correct
                    else Decimal('0.00')
                )

                # Create response record
                QuizResponse.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_answer=selected_answer,
                    is_correct=selected_answer.is_correct,
                    points_earned=points_earned
                )

                # Add to total score
                if selected_answer.is_correct:
                    total_score += question.points

            except (
                QuizAnswer.DoesNotExist,
                QuizQuestion.DoesNotExist,
                ValueError
            ):
                continue

    # Calculate percentage
    percentage = (
        (total_score / max_score * 100)
        if max_score > 0
        else Decimal('0.00')
    )

    # Calculate time taken
    time_delta = timezone.now() - attempt.started_at
    time_taken = int(time_delta.total_seconds() / 60)

    # Update attempt
    attempt.score = total_score
    attempt.max_score = max_score
    attempt.percentage = percentage
    attempt.passed = percentage >= attempt.quiz.passing_score
    attempt.is_completed = True
    attempt.completed_at = timezone.now()
    attempt.time_taken_minutes = time_taken
    attempt.save()

    passed_label = 'Passed ✓' if attempt.passed else 'Not passed'
    _notify(
        user=request.user,
        notification_type='grade',
        title=f'Quiz Result: {attempt.quiz.title}',
        message=f'You scored {attempt.percentage:.1f}% on "{attempt.quiz.title}" — {passed_label}.',
        link=f'/student/quizzes/attempt/{attempt_id}/result/',
    )
    messages.success(request, 'Quiz submitted successfully!')
    return redirect('students:quiz_result', attempt_id=attempt_id)


@login_required
@student_required
def quiz_result(request, attempt_id):
    """
    View quiz results
    """
    # Get attempt with related data
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related(
            'quiz',
            'quiz__lesson',
            'quiz__lesson__course'
        ),
        id=attempt_id,
        student=request.user
    )

    # Get all responses with related data
    answers = attempt.responses.select_related(
        'question',
        'selected_answer'
    ).order_by('question__display_order')

    # Calculate statistics
    total_questions = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    incorrect_answers = total_questions - correct_answers

    context = {
        'page_title': 'Quiz Results',
        'attempt': attempt,
        'answers': answers,
        'total_questions': total_questions,
        'correct_answers': correct_answers,
        'incorrect_answers': incorrect_answers,
        'course_slug': attempt.quiz.lesson.course.slug,
        'lesson_slug': attempt.quiz.lesson.slug,
        'quiz_slug': attempt.quiz.slug,
        'attempt_count': QuizAttempt.objects.filter(
            quiz=attempt.quiz,
            student=request.user,
            is_completed=True
        ).count(),
    }

    return render(request, 'students/quiz_result.html', context)


# ==================== COMMUNITY & DISCUSSIONS ====================
@login_required
@student_required
def community(request):
    """
    Community discussion forum with filtering and search
    """
    user = request.user
    
    # Get filter and search parameters
    filter_type = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Base queryset with optimizations
    threads = Discussion.objects.select_related(
        'author',
        'course'
    ).annotate(
        reply_count=Count('replies'),
        views=F('views_count')
    )
    
    # Apply filters
    if filter_type == 'my_courses':
        # Show discussions from user's enrolled courses
        enrolled_course_ids = Enrollment.objects.filter(
            student=user,
            status='active'
        ).values_list('course_id', flat=True)
        threads = threads.filter(course_id__in=enrolled_course_ids)
    elif filter_type == 'my_posts':
        # Show user's own discussions
        threads = threads.filter(author=user)
    
    # Apply search
    if search_query:
        threads = threads.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query)
        )
    
    # Order threads
    threads = threads.order_by('-is_pinned', '-created_at')
    
    # Paginate
    paginator = Paginator(threads, 15)
    page_number = request.GET.get('page', 1)
    
    try:
        threads = paginator.get_page(page_number)
    except Exception:
        threads = paginator.get_page(1)
    
    context = {
        'page_title': 'Community',
        'threads': threads,
        'filter_type': filter_type,
        'search_query': search_query,
    }
    
    return render(request, 'students/community.html', context)


@login_required
@student_required
def thread_detail(request, thread_id):
    """
    View individual discussion thread with replies
    """
    thread = get_object_or_404(
        Discussion.objects.select_related('author', 'course'),
        id=thread_id
    )
    
    # Increment view count
    thread.views_count = F('views_count') + 1
    thread.save(update_fields=['views_count'])
    thread.refresh_from_db()
    
    # Get replies
    replies = thread.replies.select_related(
        'author'
    ).order_by('created_at')
    
    # Handle new reply with form
    if request.method == 'POST':
        form = ReplyCreateForm(request.POST)
        
        if form.is_valid():
            reply = form.save(commit=False)
            reply.discussion = thread
            reply.author = request.user
            reply.save()
            
            messages.success(request, 'Reply posted successfully!')
            # Notify thread author if they are not the one replying
            if thread.author != request.user:
                _notify(
                    user=thread.author,
                    notification_type='message',
                    title=f'New Reply on Your Thread: {thread.title}',
                    message=(
                        f'{request.user.get_full_name() or request.user.username} '
                        f'replied to your discussion "{thread.title}".'
                    ),
                    link=f'/student/community/thread/{thread_id}/',
                )
            return redirect('students:thread_detail', thread_id=thread_id)
    else:
        form = ReplyCreateForm()
    
    context = {
        'page_title': thread.title,
        'thread': thread,
        'replies': replies,
        'reply_form': form,
    }
    
    return render(request, 'students/thread_detail.html', context)


@login_required
@student_required
def create_thread(request):
    """
    Create a new discussion thread using Django form
    """
    if request.method == 'POST':
        form = ThreadCreateForm(
            user=request.user,
            data=request.POST
        )
        
        if form.is_valid():
            thread = form.save(commit=False)
            thread.author = request.user
            thread.save()
            
            messages.success(
                request,
                'Discussion created successfully!'
            )
            _notify(
                user=request.user,
                notification_type='announcement',
                title=f'Discussion Created: {thread.title}',
                message=f'Your discussion thread "{thread.title}" is now live in the community.',
                link=f'/student/community/thread/{thread.id}/',
            )
            return redirect('students:thread_detail', thread_id=thread.id)
    else:
        form = ThreadCreateForm(user=request.user)
    
    context = {
        'page_title': 'Create Discussion',
        'form': form,
    }
    
    return render(request, 'students/create_thread.html', context)


# ==================== STUDY GROUPS ====================
@login_required
@student_required
def study_groups(request):
    """
    List study groups - user's groups and available groups
    """
    user = request.user
    
    # Get user's study groups
    my_group_ids = StudyGroupMember.objects.filter(
        user=user,
        is_active=True
    ).values_list('study_group_id', flat=True)
    
    my_groups = StudyGroup.objects.filter(
        id__in=my_group_ids,
        is_active=True
    ).select_related('course').annotate(
        member_count=Count(
            'members',
            filter=Q(members__is_active=True)
        )
    )
    
    # Get available groups (not full, public, not already joined)
    available_groups = StudyGroup.objects.filter(
        is_active=True,
        is_public=True
    ).exclude(
        id__in=my_group_ids
    ).select_related('course').annotate(
        member_count=Count(
            'members',
            filter=Q(members__is_active=True)
        )
    ).order_by('-created_at')
    
    # Annotate whether each group is full
    for group in available_groups:
        group.is_full = group.member_count >= group.max_members
    
    context = {
        'page_title': 'Study Groups',
        'my_groups': my_groups,
        'available_groups': available_groups,
    }
    
    return render(request, 'students/study_groups.html', context)


@login_required
@student_required
def study_group_detail(request, group_id):
    """
    View study group details and members
    """
    group = get_object_or_404(
        StudyGroup.objects.select_related('course', 'created_by'),
        id=group_id
    )
    
    # Check if user is a member
    is_member = StudyGroupMember.objects.filter(
        study_group=group,
        user=request.user,
        is_active=True
    ).exists()
    
    # Get members
    members = group.members.filter(
        is_active=True
    ).select_related('user')
    
    # Handle message form (only for members)
    if request.method == 'POST' and is_member:
        form = StudyGroupMessageForm(request.POST)
        if form.is_valid():
            StudyGroupMessage.objects.create(
                study_group=group,
                author=request.user,
                content=form.cleaned_data['message']
            )
            messages.success(request, 'Message posted!')
            # Notify all other group members of a new message
            other_members = StudyGroupMember.objects.filter(
                study_group=group,
                is_active=True,
            ).exclude(user=request.user).select_related('user')
            for member in other_members:
                _notify(
                    user=member.user,
                    notification_type='message',
                    title=f'New Message in {group.name}',
                    message=f'{request.user.get_full_name() or request.user.username} posted in "{group.name}".',
                    link=f'/student/study-groups/{group_id}/',
                )
            return redirect('students:study_group_detail', group_id=group_id)
        messages.error(request, 'Please enter a valid message.')
    else:
        form = StudyGroupMessageForm()

    # Fetch group messages (latest 50)
    group_messages = (
        StudyGroupMessage.objects
        .filter(study_group=group)
        .select_related('author')
        .order_by('created_at')[:50]
    )
    
    member_count = members.count()
    context = {
        'page_title': group.name,
        'group': group,
        'is_member': is_member,
        'members': members,
        'member_count': member_count,
        'available_slots': group.max_members - member_count,
        'message_form': form if is_member else None,
        'group_messages': group_messages if is_member else [],
    }
    
    return render(request, 'students/study_group_detail.html', context)


@login_required
@student_required
def join_study_group(request, group_id):
    """
    Join a study group
    """
    if request.method != 'POST':
        return redirect('students:study_groups')
    
    group = get_object_or_404(
        StudyGroup,
        id=group_id,
        is_active=True
    )
    
    # Check if already a member
    existing = StudyGroupMember.objects.filter(
        study_group=group,
        user=request.user
    ).first()
    
    if existing and existing.is_active:
        messages.info(
            request,
            'You are already a member of this group.'
        )
        return redirect(
            'students:study_group_detail',
            group_id=group_id
        )
    
    # Check if group is full
    current_count = group.members.filter(is_active=True).count()
    if current_count >= group.max_members:
        messages.error(request, 'This study group is full.')
        return redirect('students:study_groups')
    
    # Join group
    if existing:
        existing.is_active = True
        existing.save()
    else:
        StudyGroupMember.objects.create(
            study_group=group,
            user=request.user,
            role='member'
        )
    
    messages.success(
        request,
        f'Successfully joined {group.name}!'
    )
    _notify(
        user=request.user,
        notification_type='system',
        title=f'Joined Study Group: {group.name}',
        message=f'You are now a member of the study group "{group.name}". '
                f'Connect and collaborate with other students.',
        link=f'/student/study-groups/{group_id}/',
    )
    return redirect('students:study_group_detail', group_id=group_id)

# ==================== ACHIEVEMENTS ====================
@login_required
@student_required
def achievements(request):
    """
    View achievements and badges with statistics
    """
    user = request.user
    
    # Get user's earned badges
    user_badges = (
        StudentBadge.objects
        .filter(student=user)
        .select_related('badge')
        .order_by('-awarded_at')
    )
    
    # Get all available badges
    all_badges = Badge.objects.filter(is_active=True)
    
    # Separate earned and unearned badges
    earned_badge_ids = user_badges.values_list('badge_id', flat=True)
    unearned_badges = all_badges.exclude(id__in=earned_badge_ids)
    
    # Calculate completed courses
    completed_courses = Enrollment.objects.filter(
        student=user,
        status='completed'
    ).count()
    
    # Calculate total points from badges
    total_points = user_badges.aggregate(
        total=Sum('badge__points')
    )['total'] or 0
    
    context = {
        'page_title': 'Achievements',
        'user_badges': user_badges,
        'unearned_badges': unearned_badges,
        'completed_courses': completed_courses,
        'total_points': total_points,
    }
    
    return render(request, 'students/achievements.html', context)


# ==================== GRADES ====================
@login_required
@student_required
def grades(request):
    """
    View grades and performance across all courses
    """
    user = request.user
    
    # Get all enrollments with optimized queries
    enrollments = (
        Enrollment.objects
        .filter(student=user)
        .select_related('course', 'course__instructor')
        .prefetch_related('course__lessons')
        .order_by('-enrolled_at')
    )
    
    # Add progress data to each enrollment
    for enrollment in enrollments:
        # Get completed lessons count
        completed_count = LessonProgress.objects.filter(
            enrollment=enrollment,
            is_completed=True
        ).count()
        
        total_lessons = enrollment.course.lessons.filter(
            is_active=True
        ).count()
        
        # Calculate progress percentage
        enrollment.completed_lessons = completed_count
        enrollment.progress_percentage = (
            (completed_count / total_lessons * 100) 
            if total_lessons > 0 
            else 0
        )
        
        # Get current grade (average of graded assignments)
        from django.db.models import FloatField
        grade_data = AssignmentSubmission.objects.filter(
            student=user,
            assignment__lesson__course=enrollment.course,
            status='graded',
            score__isnull=False
        ).aggregate(
            avg_score=Avg(
                F('score') * 100.0 / F('assignment__max_score'),
                output_field=FloatField()
            )
        )
        
        enrollment.current_grade = grade_data['avg_score']
    
    # Get graded assignment submissions — evaluate to list so .passed sticks
    submissions = list(
        AssignmentSubmission.objects
        .filter(student=user, status='graded')
        .select_related(
            'assignment',
            'assignment__lesson',
            'assignment__lesson__course'
        )
        .order_by('-graded_at')
    )

    for submission in submissions:
        submission.passed = (
            submission.score >= submission.assignment.passing_score
            if submission.score is not None
            else False
        )
    
    # Academic course grades (from program — recorded by lecturers)
    # academic_grades = (
    #     CourseGrade.objects
    #     .filter(student=user)
    #     .select_related('course', 'course__program', 'session')
    #     .order_by('session__name', 'course__year_of_study', 'course__semester')
    # )

    # Quiz attempts — best attempt per quiz for graded display
    quiz_attempts = list(
        QuizAttempt.objects
        .filter(student=user, is_completed=True)
        .select_related('quiz', 'quiz__lesson', 'quiz__lesson__course')
        .order_by('-completed_at')
    )

    context = {
        'page_title': 'Grades & Performance',
        'enrollments': enrollments,
        'submissions': submissions,
        'quiz_attempts': quiz_attempts,
        # 'academic_grades': academic_grades,
    }
    
    return render(request, 'students/grades.html', context)


# ==================== PROGRESS ====================
@login_required
@student_required
def progress(request):
    """
    View detailed learning progress across all courses
    """
    user = request.user
    
    # Get all enrollments with related data
    enrollments = (
        Enrollment.objects
        .filter(student=user)
        .select_related('course', 'course__instructor')
        .prefetch_related(
            'course__sections',
            'course__sections__lessons',
            'course__lessons'
        )
        .order_by('-enrolled_at')
    )
    
    # Add detailed progress data to each enrollment
    for enrollment in enrollments:
        # Get completed lessons
        completed_progress = LessonProgress.objects.filter(
            enrollment=enrollment,
            is_completed=True
        ).values_list('lesson_id', flat=True)
        
        enrollment.completed_lesson_ids = set(completed_progress)
        
        # Count completed lessons
        enrollment.completed_lessons = len(completed_progress)
        
        # Calculate progress percentage
        total_lessons = enrollment.course.lessons.filter(
            is_active=True
        ).count()
        
        enrollment.progress_percentage = (
            (enrollment.completed_lessons / total_lessons * 100) 
            if total_lessons > 0 
            else 0
        )
        
        # Add section progress
        for section in enrollment.course.sections.all():
            section_lessons = section.lessons.filter(is_active=True)
            total = section_lessons.count()
            completed = sum(
                1 for lesson in section_lessons 
                if lesson.id in enrollment.completed_lesson_ids
            )
            section.progress_percentage = (
                (completed / total * 100) if total > 0 else 0
            )
            section.total_lessons = total

        enrollment.assignment_count = Assignment.objects.filter(
            lesson__course=enrollment.course
        ).count()
        enrollment.quiz_count = Quiz.objects.filter(
            lesson__course=enrollment.course
        ).count()
    
    # Calculate learning activity for last 28 days
    from datetime import datetime, timedelta
    today = timezone.now().date()
    start_date = today - timedelta(days=27)  # 28 days including today
    
    activity_data = []
    for i in range(28):
        date = start_date + timedelta(days=i)
        
        # Count activities for this day
        lessons_completed = LessonProgress.objects.filter(
            enrollment__student=user,
            completed_at__date=date
        ).count()
        
        assignments_submitted = AssignmentSubmission.objects.filter(
            student=user,
            submitted_at__date=date
        ).count()
        
        quizzes_taken = QuizAttempt.objects.filter(
            student=user,
            started_at__date=date
        ).count()
        
        # Calculate activity level (0-3)
        total_activities = (
            lessons_completed + 
            assignments_submitted + 
            quizzes_taken
        )
        
        if total_activities == 0:
            level = 0
        elif total_activities <= 2:
            level = 1
        elif total_activities <= 5:
            level = 2
        else:
            level = 3
        
        activity_data.append({
            'date': date,
            'level': level,
            'count': total_activities,
            'lessons': lessons_completed,
            'assignments': assignments_submitted,
            'quizzes': quizzes_taken,
        })
    
    context = {
        'page_title': 'My Progress',
        'enrollments': enrollments,
        'activity_data': activity_data,
        'completed_count': sum(1 for e in enrollments if e.status == 'completed'),
        'active_count': sum(1 for e in enrollments if e.status == 'active'),
    }
    
    return render(request, 'students/progress.html', context)


# ==================== CERTIFICATES ====================
@login_required
@student_required
def certificates(request):
    """
    List all earned certificates (LMS course + academic program).
    Each certificate is gated by its own payment_status field.
    """
    user = request.user

    # Get all certificates — LMS and program — with their related objects
    certificates = (
        Certificate.objects
        .filter(student=user)
        .select_related('course', 'course__instructor', 'program', 'program__department')
        .order_by('-issued_date')
    )

    # Annotate each cert with a display label and instructor name
    for cert in certificates:
        if cert.certificate_type == 'program' and cert.program:
            cert.display_title = cert.program.name
            cert.display_subtitle = (
                cert.program.department.faculty.name
                if cert.program.department else ''
            )
            cert.instructor_name = 'MIU Academic Office'
            cert.is_program_cert = True
        else:
            cert.display_title = cert.course.title if cert.course else 'Course Certificate'
            cert.display_subtitle = ''
            cert.is_program_cert = False
            if cert.course and cert.course.instructor:
                cert.instructor_name = (
                    cert.course.instructor.get_full_name()
                    or cert.course.instructor.username
                )
            else:
                cert.instructor_name = 'MIU Staff'
        cert.is_unlocked = cert.payment_status == 'paid'

    context = {
        'page_title': 'My Certificates',
        'certificates': certificates,
    }

    return render(request, 'students/certificates.html', context)


def _cert_is_unlocked(cert):
    """True if student can view/download this certificate."""
    return cert.payment_status == 'paid'


# ==================== PROFILE & SETTINGS ====================
@login_required
@student_required
def profile(request):
    """
    View and edit user profile using Django form
    """
    user = request.user
    profile = user.profile
    
    # Get statistics for sidebar
    stats = {
        'total_enrolled': Enrollment.objects.filter(
            student=user
        ).count(),
        'completed_courses': Enrollment.objects.filter(
            student=user,
            status='completed'
        ).count(),
        'certificates_earned': Certificate.objects.filter(
            student=user
        ).count(),
        'total_hours': 0,  # Calculate from lesson progress
    }
    
    if request.method == 'POST':
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=profile
        )
        
        if form.is_valid():
            # Update user fields
            user.first_name = form.cleaned_data.get('first_name', '')
            user.last_name = form.cleaned_data.get('last_name', '')
            user.email = form.cleaned_data.get('email', '')
            user.save()
            
            # Update profile
            form.save()
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('students:profile')
    else:
        # Populate form with current data
        initial_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        }
        form = ProfileUpdateForm(instance=profile, initial=initial_data)
    
    context = {
        'page_title': 'My Profile',
        'form': form,
        **stats,
    }
    
    return render(request, 'students/profile.html', context)


@login_required
@student_required
def settings(request):
    """
    Account settings and preferences using Django form
    """
    user = request.user
    profile = user.profile
    
    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=profile)
        
        if form.is_valid():
            form.save()
            
            # Handle password change
            current_password = request.POST.get(
                'current_password',
                ''
            ).strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get(
                'confirm_password',
                ''
            ).strip()
            
            if current_password and new_password:
                if not user.check_password(current_password):
                    messages.error(
                        request,
                        'Current password is incorrect.'
                    )
                elif new_password != confirm_password:
                    messages.error(
                        request,
                        'New passwords do not match.'
                    )
                elif len(new_password) < 8:
                    messages.error(
                        request,
                        'Password must be at least 8 characters.'
                    )
                else:
                    user.set_password(new_password)
                    user.save()
                    messages.success(
                        request,
                        'Password updated successfully! '
                        'Please login again.'
                    )
                    return redirect('eduweb:auth_page')
            
            if not (current_password and new_password):
                messages.success(
                    request,
                    'Settings updated successfully!'
                )
            
            return redirect('students:settings')
    else:
        form = SettingsForm(instance=profile)
    
    context = {
        'page_title': 'Settings',
        'form': form,
    }
    
    return render(request, 'students/settings.html', context)

@login_required
@student_required
def help_support(request):
    """Help and support page with FAQs and ticket submission"""
    
    if request.method == 'POST':
        form = StudentSupportTicketForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Get current course if student is enrolled
            current_course = None
            enrollments = Enrollment.objects.filter(
                student=request.user,
                status='active'
            ).first()
            
            if enrollments:
                current_course = enrollments.course.title
            
            # Send email to support team
            subject = (
                f"[STUDENT-{form.cleaned_data['priority'].upper()}] "
                f"{form.cleaned_data['subject']}"
            )
            
            message = f"""
New Support Ticket from Student

From: {request.user.get_full_name()} ({request.user.email})
Student ID: {request.user.id}
Current Course: {current_course or 'None'}
Category: {form.cleaned_data['category']}
Priority: {form.cleaned_data['priority']}

Message:
{form.cleaned_data['message']}

---
User Role: Student
Submission Time: {timezone.now()}
            """
            
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False,
                )
                
                messages.success(
                    request,
                    'Your support ticket has been submitted! '
                    'Our team will get back to you within 24-48 hours.'
                )
                _notify(
                    user=request.user,
                    notification_type='system',
                    title='Support Ticket Submitted',
                    message=f'Your ticket "{form.cleaned_data["subject"]}" has been received. We will respond within 24-48 hours.',
                    link='/student/help-support/',
                )
                return redirect('students:help_support')
            
            except Exception as e:
                messages.error(
                    request,
                    'An error occurred while submitting your ticket. '
                    'Please try again later.'
                )
    else:
        form = StudentSupportTicketForm()
    
    # Student-specific FAQs
    faqs = [
        {
            'question': 'How do I enroll in a course?',
            'answer': (
                'Go to Browse Catalog, find the course you want, '
                'and click the Enroll button. Some courses may '
                'require payment before enrollment.'
            )
        },
        {
            'question': 'How do I submit an assignment?',
            'answer': (
                'Navigate to the Assignments page, select the '
                'assignment, and use the submission form to upload '
                'your work. Make sure to submit before the deadline!'
            )
        },
        {
            'question': 'Can I retake a quiz?',
            'answer': (
                'This depends on the course settings. Some quizzes '
                'allow multiple attempts while others are one-time. '
                'Check the quiz instructions for details.'
            )
        },
        {
            'question': 'How do I track my progress?',
            'answer': (
                'Visit your Dashboard or the Progress page to see '
                'completion rates, grades, and overall performance '
                'across all your enrolled courses.'
            )
        },
        {
            'question': 'When will I receive my certificate?',
            'answer': (
                'Certificates are issued automatically when you '
                'complete all course requirements and achieve the '
                'passing grade. Check the Certificates page.'
            )
        },
        {
            'question': 'How do I contact my instructor?',
            'answer': (
                'You can post questions in the course discussion '
                'forum, or use the messaging feature to contact '
                'your instructor directly.'
            )
        },
        {
            'question': 'What if I miss a deadline?',
            'answer': (
                'Contact your instructor immediately. Some '
                'assignments allow late submissions with a penalty. '
                'Extensions are at the instructor\'s discretion.'
            )
        },
        {
            'question': 'How do I join a study group?',
            'answer': (
                'Go to Study Groups, browse available groups, and '
                'click Join. You can also create your own study '
                'group for others to join.'
            )
        },
    ]
    
    # Quick links for students
    quick_links = [
        {
            'title': 'Getting Started Guide',
            'icon': 'fa-rocket',
            'url': '#',
            'description': 'New to the platform? Start here'
        },
        {
            'title': 'Video Tutorials',
            'icon': 'fa-video',
            'url': '#',
            'description': 'Watch step-by-step guides'
        },
        {
            'title': 'Study Tips',
            'icon': 'fa-lightbulb',
            'url': '#',
            'description': 'Learn effective study strategies'
        },
        {
            'title': 'Community Forum',
            'icon': 'fa-users',
            'url': '#',
            'description': 'Connect with fellow students'
        },
    ]
    
    context = {
        'form': form,
        'faqs': faqs,
        'quick_links': quick_links,
        'page_title': 'Help & Support',
    }
    
    return render(request, 'students/help_support.html', context)

def _get_outstanding_for_student(user):
    """
    Returns (outstanding, paid) for a student's required fees.

    Includes:
    1. AllRequiredPayments for the student's program (admin-created fees)
    2. Auto-generated certificate fees for any completed courses that have
       has_certificate=True and no certificate fee has been paid yet.

    outstanding → list of dicts: {'payment': AllRequiredPayments or dict, 'is_overdue': bool, 'is_certificate_fee': bool}
    paid        → list of AllRequiredPayments instances already settled
    """
    from eduweb.models import AllRequiredPayments, Enrollment, FeePayment, Certificate

    profile = getattr(user, 'profile', None)
    if not profile or not profile.program:
        return [], []

    # ── 1. Standard admin-created required fees ───────────────────────────
    student_level = profile.current_level  # e.g. 200 for year 2

    required_qs = AllRequiredPayments.objects.filter(
        program=profile.program,
        who_to_pay='student',
        is_active=True,
    ).filter(
        models.Q(level__isnull=True) | models.Q(level=student_level)
    ).select_related('program', 'program__department', 'program__department__faculty', 'academic_session')

    paid_fee_ids = set(
        FeePayment.objects.filter(
            user=user,
            status='success',
            fee__in=required_qs,
        ).values_list('fee_id', flat=True)
    )

    today = timezone.now().date()
    outstanding, paid = [], []

    for rp in required_qs:
        if rp.pk in paid_fee_ids:
            paid.append(rp)
        else:
            outstanding.append({
                'payment': rp,
                'is_overdue': rp.due_date < today,
                'is_certificate_fee': False,
            })

    # ── 2. Auto certificate fees for completed courses ────────────────────
    # Find all completed enrollments where the course issues a certificate
    completed_enrollments = (
        Enrollment.objects
        .filter(student=user, status='completed')
        .select_related('course')
    )

    for enrollment in completed_enrollments:
        course = enrollment.course
        cert_fee = getattr(course, 'certificate_fee', None)

        # Skip entirely if the model has no certificate fee field
        if not cert_fee:
            continue

        cert = Certificate.objects.filter(
            student=user, course=course, certificate_type='lms_course'
        ).first()

        if cert and cert.payment_status == 'paid':
            paid.append({
                'purpose': f'Certificate Fee — {course.title}',
                'amount': cert_fee,
                'is_certificate_fee': True,
                'course': course,
            })
        elif (not cert or cert.payment_status == 'unpaid') and cert_fee > 0:
            outstanding.append({
                'payment': {
                    'purpose': f'Certificate Fee — {course.title}',
                    'amount': cert_fee,
                    'due_date': today,
                    'is_certificate_fee': True,
                    'course': course,
                    'pk': f'cert_{course.pk}',
                },
                'is_overdue': False,
                'is_certificate_fee': True,
            })

    return outstanding, paid

# ==================== MY PAYMENTS (outstanding table) ====================

@login_required
@student_required
def my_payments(request):
    """
    Student-facing outstanding fees dashboard.
    Fetches all AllRequiredPayments for the student's faculty/department
    that have not yet been paid.
    """
    outstanding_payments, paid_payments = _get_outstanding_for_student(
        request.user
    )

    total_outstanding = sum(
        (item['payment']['amount'] if isinstance(item['payment'], dict) else item['payment'].amount)
        for item in outstanding_payments
    )

    # Derive display currency from first outstanding item; fall back to USD
    _first = outstanding_payments[0]['payment'] if outstanding_payments else None
    display_currency = (
        _first.get('currency', 'USD') if isinstance(_first, dict)
        else getattr(_first, 'currency', 'USD')
    ) if _first else 'USD'

    profile = request.user.profile
    context = {
        'page_title': 'My Payments',
        'outstanding_payments': outstanding_payments,
        'paid_payments': paid_payments,
        'total_outstanding': total_outstanding,
        'display_currency': display_currency,
        'student_level': profile.current_level,
        'student_program': profile.program,
        'student_faculty': profile.faculty,
        'student_department': profile.department,
    }
    return render(request, 'students/my_payments.html', context)

# ===========================================================================
# INBOX / MESSAGING
# ===========================================================================

@login_required
@student_required
def inbox(request):
    """
    Student inbox.  Shows received & sent messages (root messages only).
    Marks all unread received messages as read when the page is opened.
    """
    user = request.user

    received = (
        Message.objects
        .filter(recipient=user, parent__isnull=True)
        .select_related('sender')
        .order_by('-created_at')
    )

    sent = (
        Message.objects
        .filter(sender=user, parent__isnull=True)
        .select_related('recipient')
        .order_by('-created_at')
    )

    # Grab the unread count BEFORE we mark them read (for flash badge)
    unread_count = received.filter(is_read=False).count()

    # Mark all unread as read
    Message.objects.filter(
        recipient=user,
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())

    context = {
        'page_title': 'My Inbox',
        'received': received,
        'sent': sent,
        'unread_count': unread_count,
    }
    return render(request, 'students/inbox.html', context)


@login_required
@student_required
def compose_message(request):
    """
    Compose and send a new message to an instructor or admin.
    Accepts ?to=<user_id> query-param to pre-fill the recipient.
    """
    from .forms import MessageComposeForm

    if request.method == 'POST':
        form = MessageComposeForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.save()
            messages.success(request, 'Message sent successfully!')
            _notify(
                user=msg.recipient,
                notification_type='message',
                title=f'New Message from {request.user.get_full_name() or request.user.username}',
                message=f'You have a new message: "{msg.subject}"',
                link=f'/student/inbox/{msg.id}/',
            )
            from eduweb.emailservices import send_new_message_email
            send_new_message_email(msg.recipient, request.user, msg)
            return redirect('students:inbox')
        messages.error(request, 'Please fix the errors below.')
    else:
        initial = {}
        to_id = request.GET.get('to')
        if to_id:
            try:
                from django.contrib.auth.models import User as AuthUser
                initial['recipient'] = AuthUser.objects.get(pk=to_id)
            except Exception:
                pass
        form = MessageComposeForm(initial=initial)

    return render(request, 'students/compose_message.html', {
        'page_title': 'Compose Message',
        'form': form,
    })


@login_required
@student_required
def message_thread(request, message_id):
    """
    View a full message thread and reply to it.
    Only the sender or recipient can access.
    """
    msg = get_object_or_404(
        Message.objects.select_related('sender', 'recipient'),
        pk=message_id,
    )

    # Security: only sender or recipient may view
    if msg.sender != request.user and msg.recipient != request.user:
        messages.error(request, 'You do not have permission to view this message.')
        return redirect('students:inbox')

    # Mark as read if current user is the recipient
    if msg.recipient == request.user and not msg.is_read:
        msg.mark_as_read()

    thread_replies = (
        Message.objects
        .filter(parent=msg)
        .select_related('sender', 'recipient')
        .order_by('created_at')
    )

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if len(body) >= 5:
                reply_to = msg.sender if msg.recipient == request.user else msg.recipient
                Message.objects.create(
                    sender=request.user,
                    recipient=reply_to,
                    subject=f'Re: {msg.subject}',
                    body=body,
                    parent=msg,
                )
                messages.success(request, 'Reply sent!')
                _notify(
                    user=reply_to,
                    notification_type='message',
                    title=f'Reply from {request.user.get_full_name() or request.user.username}',
                    message=f'New reply on: "{msg.subject}"',
                    link=f'/student/inbox/{msg.id}/',
                )
                from eduweb.emailservices import send_new_message_email
                send_new_message_email(reply_to, request.user, msg)
                return redirect('students:message_thread', message_id=message_id)
        messages.error(request, 'Reply must be at least 5 characters.')

    return render(request, 'students/message_thread.html', {
        'page_title': msg.subject,
        'message': msg,
        'thread_replies': thread_replies,
    })


# ===========================================================================
# NOTIFICATIONS
# ===========================================================================

@login_required
@student_required
def notifications_view(request):
    """
    Student notifications page.
    - Shows last 30 days only (older ones auto-purged by _notify).
    - Paginated at 15 per page.
    - Marks ALL as read if ?mark_all=1 is passed.
    """
    if request.GET.get('mark_all') == '1':
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return redirect('students:notifications_view')

    notifs = (
        Notification.objects
        .filter(user=request.user)
        .order_by('-created_at')
    )
    unread_count = notifs.filter(is_read=False).count()
    page_obj = Paginator(notifs, 15).get_page(request.GET.get('page', 1))

    return render(request, 'students/notifications.html', {
        'page_title': 'Notifications',
        'notifications': page_obj,
        'unread_count': unread_count,
    })


@login_required
@student_required
def mark_notification_read(request, notification_id):
    notif = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    notif.mark_as_read()
    return JsonResponse({'success': True})


# ===========================================================================
# COURSE REVIEW
# ===========================================================================

@login_required
@student_required
def submit_review(request, course_slug):
    """
    Submit or update a star rating + text review for a course.
    Student must be enrolled. POST-only; redirects back to course detail.
    """
    if request.method != 'POST':
        return redirect('students:course_detail', course_slug=course_slug)

    course = get_object_or_404(LMSCourse, slug=course_slug, is_published=True)

    # Must be enrolled
    get_object_or_404(Enrollment, student=request.user, course=course)

    try:
        rating = int(request.POST.get('rating', 0))
        if not 1 <= rating <= 5:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, 'Please select a rating between 1 and 5.')
        return redirect('students:course_detail', course_slug=course_slug)

    review_text = request.POST.get('review_text', '').strip()

    _, created = Review.objects.update_or_create(
        course=course,
        student=request.user,
        defaults={'rating': rating, 'review_text': review_text},
    )

    if created:
        messages.success(request, 'Thank you! Your review has been submitted.')
        _notify(
            user=request.user,
            notification_type='enrollment',
            title=f'Review Submitted: {course.title}',
            message=f'You rated "{course.title}" {rating}/5 stars. Thank you for your feedback!',
            link=f'/student/courses/{course_slug}/',
        )
    else:
        messages.success(request, 'Your review has been updated.')

    return redirect('students:course_detail', course_slug=course_slug)

# ===========================================================================
# CREATE STUDY GROUP
# ===========================================================================

@login_required
@student_required
def create_study_group(request):
    """
    Create a new study group. The creator is automatically joined as admin.
    """
    from .forms import StudyGroupCreateForm

    if request.method == 'POST':
        form = StudyGroupCreateForm(user=request.user, data=request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()

            StudyGroupMember.objects.create(
                study_group=group,
                user=request.user,
                role='admin',
            )

            messages.success(request, f'Study group "{group.name}" created!')
            _notify(
                user=request.user,
                notification_type='system',
                title=f'Study Group Created: {group.name}',
                message=f'Your study group "{group.name}" is live. Share it with others to grow your group!',
                link=f'/student/study-groups/{group.id}/',
            )
            return redirect('students:study_group_detail', group_id=group.id)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = StudyGroupCreateForm(user=request.user)

    return render(request, 'students/create_study_group.html', {
        'page_title': 'Create Study Group',
        'form': form,
    })

@login_required
@student_required
def academic_records(request):
    user = request.user

    # ── Transcript request (POST, once only) ─────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'request_transcript':
        application_qs = CourseApplication.objects.filter(user=user, status='approved')
        if application_qs.exists():
            app = application_qs.order_by('-created_at').first()
            if not app.transcript_requested:
                app.transcript_requested = True
                app.save(update_fields=['transcript_requested'])
                messages.success(request, 'Your transcript request has been submitted successfully.')
            else:
                messages.info(request, 'You have already requested your transcript.')
        else:
            messages.error(request, 'No approved application found for your account.')
        return redirect('students:academic_records')

    # ── 1. Application / Admission info ──────────────────────────────────────
    application = (
        CourseApplication.objects
        .filter(user=user, status='approved')
        .select_related('program', 'program__department__faculty', 'academic_session')
        .order_by('-created_at')
        .first()
    )
    program = application.program if application else None

    # ── 2. Program requirements ───────────────────────────────────────────────
    program_courses = []
    if program:
        program_courses = list(
            Course.objects
            .filter(program=program, is_active=True)
            .select_related('program')
            .order_by('year_of_study', 'semester')
        )
    core_courses     = [c for c in program_courses if c.course_type == 'core']
    elective_courses = [c for c in program_courses if c.course_type == 'elective']
    other_courses    = [c for c in program_courses if c.course_type not in ('core', 'elective')]
    total_credits_required = program.credits_required if program else 0

    # ── 3. End-of-semester exam responses (submitted + graded only) ───────────
    #
    # SOURCE OF TRUTH: StudentExamResponse where:
    #   • exam.exam_type == 'end_of_semester'
    #   • status == 'graded'   (fully graded — total_score is set)
    #
    # Each response is enriched with display helpers so the template
    # can treat it identically to the old CourseGrade objects.
    # ─────────────────────────────────────────────────────────────────────────
    GRADE_POINTS = {'A': 5.0, 'B': 4.0, 'C': 3.0, 'D': 2.0, 'F': 0.0, 'I': 0.0, 'W': 0.0}

    def score_to_grade(pct):
        """Nigerian grading: score_percentage → letter grade."""
        if pct is None:
            return ''
        pct = float(pct)
        if pct >= 70:   return 'A'
        if pct >= 60:   return 'B'
        if pct >= 50:   return 'C'
        if pct >= 45:   return 'D'
        return 'F'

    exam_responses = list(
        StudentExamResponse.objects
        .filter(
            student=user,
            status=StudentExamResponse.GRADED,
            exam__exam_type=Exam.END_OF_SEMESTER,
            exam__show_result_immediately=True,      # admin must release results
        )
        .select_related(
            'exam',
            'exam__course',
            'exam__course__academic_course',
            'exam__course__academic_course__program',
            'exam__course__session',
        )
        .order_by(
            'exam__course__session__name',
            'exam__course__term',
            'exam__course__academic_course__year_of_study',
        )
    )

    # Build synthetic grade-like objects the template can consume
    class ExamGradeProxy:
        """Wraps a StudentExamResponse to look like a CourseGrade row."""
        def __init__(self, response):
            self._r = response
            lms   = response.exam.course          # LMSCourse
            acad  = lms.academic_course           # Course or None

            # ── Display fields ────────────────────────────────────────────
            self.display_name  = acad.name if acad else lms.title
            self.display_code  = lms.code or (acad.code if acad else '')
            self.credit_units  = acad.credit_units if acad else 3
            self.score         = response.score_percentage  # shown as %
            self.grade         = score_to_grade(response.score_percentage)
            self.grade_points  = GRADE_POINTS.get(self.grade, 0)
            self.weighted_points = self.grade_points * self.credit_units
            self.is_passed     = self.grade not in ('F', 'I', 'W', '')
            self.result_status = 'released'        # graded = released to student

            # ── Grouping keys ─────────────────────────────────────────────
            sess = lms.session
            self.sess_key = sess.name if sess else 'Unassigned'

            # Semester label
            if acad and acad.semester:
                self.sem_key = acad.get_semester_display()
            elif lms.term:
                self.sem_key = lms.get_term_display()
            else:
                self.sem_key = 'Unknown'

            # ── Exam meta (for tooltip / detail) ─────────────────────────
            self.exam_title    = response.exam.title
            self.exam_ref      = response.exam.reference_code
            self.total_score   = response.total_score
            self.max_score     = response.exam.total_marks if hasattr(response.exam, 'total_marks') else None
            self.graded_at     = response.graded_at
            self.submitted_at  = response.submitted_at

    proxies = [ExamGradeProxy(r) for r in exam_responses]

    # ── 4. Credits ────────────────────────────────────────────────────────────
    credits_earned    = sum(p.credit_units for p in proxies if p.is_passed)
    credits_remaining = max(0, total_credits_required - credits_earned)
    graduation_pct    = (
        round(credits_earned / total_credits_required * 100, 1)
        if total_credits_required > 0 else 0
    )

    # ── 5. Cumulative GPA — Nigerian 5-point scale ────────────────────────────
    weighted_sum    = sum(p.grade_points * p.credit_units for p in proxies if p.grade)
    total_gpa_units = sum(p.credit_units for p in proxies if p.grade and p.grade != 'W')
    gpa = round(weighted_sum / total_gpa_units, 2) if total_gpa_units > 0 else None

    if gpa is None:       gpa_class = None
    elif gpa >= 4.5:      gpa_class = 'First Class'
    elif gpa >= 3.5:      gpa_class = 'Second Class Upper'
    elif gpa >= 2.4:      gpa_class = 'Second Class Lower'
    elif gpa >= 1.5:      gpa_class = 'Third Class'
    else:                 gpa_class = 'Pass'

    # ── 6. Group by session → semester ───────────────────────────────────────
    sessions_raw = {}
    for p in proxies:
        sessions_raw.setdefault(p.sess_key, {}).setdefault(p.sem_key, []).append(p)

    session_summaries = []
    for sess_name, semesters in sorted(sessions_raw.items(), reverse=True):
        semester_blocks = []
        sess_total_weighted = 0.0
        sess_total_units    = 0
        sess_credits_earned = 0

        for sem_label, grades_list in semesters.items():
            sem_weighted = sum(p.grade_points * p.credit_units for p in grades_list if p.grade)
            sem_units    = sum(p.credit_units for p in grades_list if p.grade and p.grade != 'W')
            sem_gpa      = round(sem_weighted / sem_units, 2) if sem_units > 0 else None
            sem_credits  = sum(p.credit_units for p in grades_list if p.is_passed)

            semester_blocks.append({
                'label':          sem_label,
                'grades':         grades_list,
                'gpa':            sem_gpa,
                'credits':        sem_credits,
                'total_cu':       sem_units,
                'total_weighted': round(sem_weighted, 0),
            })
            sess_total_weighted += sem_weighted
            sess_total_units    += sem_units
            sess_credits_earned += sem_credits

        sess_gpa = round(sess_total_weighted / sess_total_units, 2) if sess_total_units > 0 else None
        session_summaries.append({
            'name':      sess_name,
            'semesters': semester_blocks,
            'gpa':       sess_gpa,
            'credits':   sess_credits_earned,
        })

    # ── 8. LMS enrollments (informational only) ───────────────────────────────
    lms_enrollments = (
        Enrollment.objects
        .filter(student=user)
        .select_related('course', 'course__session')
        .order_by('-enrolled_at')
    )

    # ── 9. Certificates ───────────────────────────────────────────────────────
    certificates = (
        Certificate.objects
        .filter(student=user)
        .select_related('course', 'program')
        .order_by('-issued_date')
    )

    # academic_grades kept for backward compat with any other template refs
    academic_grades = proxies

    context = {
        'page_title':              'Academic Records',
        'application':             application,
        'program':                 program,
        'program_courses':         program_courses,
        'core_courses':            core_courses,
        'elective_courses':        elective_courses,
        'other_courses':           other_courses,
        'total_credits_required':  total_credits_required,
        'credits_earned':          credits_earned,
        'credits_remaining':       credits_remaining,
        'graduation_pct':          graduation_pct,
        'academic_grades':         academic_grades,
        'session_summaries':       session_summaries,
        'gpa':                     gpa,
        'gpa_class':               gpa_class,
        'lms_enrollments':         lms_enrollments,
        'certificates':            certificates,
    }
    return render(request, 'students/academic_records.html', context)

# ══════════════════════════════════════════════════════════════════════════════
#  EXAM VIEWS  —  drop-in replacements for the exam section in views.py
#
#  Changes from previous version:
#   - exam_instructions: passes standard_rules list + exam_end_iso
#   - start_exam:        passes exam_end_iso (needed by exams.html timer)
#   - exam_list:         unchanged (still correct)
#   - get_exam_data:     unchanged
#   - save_answer:       unchanged
#   - flag_tab_switch:   unchanged
#   - submit_exam:       unchanged
# ══════════════════════════════════════════════════════════════════════════════

# ─── Standard exam rules shown on instructions page ───────────────────────────
STANDARD_EXAM_RULES = [
    "Do not refresh or close the browser window during the exam.",
    "All answers are auto-saved as you select them.",
    "The timer will automatically submit your answers when time runs out.",
    "Switching browser tabs is logged and may be reported to your invigilator.",
    "Ensure you have a stable internet connection before starting.",
    "Do not communicate with other candidates during the exam.",
    "The Back button on your browser is disabled once the exam begins.",
]


# ─────────────────────────────────────────────────────────────────────────────
#  EXAM LIST / TIMETABLE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@student_required
def exam_list(request):
    now             = timezone.now()
    user            = request.user
    current_session = AcademicSession.get_current()
    current_term    = current_session.get_current_term() if current_session else None
 
    # ── Base queryset: published exams for courses this student is enrolled in ──
    base_qs = (
        Exam.objects
        .filter(
            is_active=True,
            course__session=current_session,
            course__enrollments__student=user,
            course__enrollments__status__in=['active', 'completed'],
        )
        .select_related('course', 'course__session')
        .order_by('start_datetime')
        .distinct()
    )
 
    if current_term:
        base_qs = base_qs.filter(
            Q(course__term=current_term) | Q(course__term='')
        )
 
    # ── 1. ALL EXAMS for the semester timetable table ──────────────────────────
    #    Shows every exam that has been created (draft/submitted/approved/published/cancelled)
    #    so students can see the full semester schedule even before exams go live.
    all_exams = base_qs.exclude(status=Exam.REJECTED)
 
    # ── 2. ACTIVE / IMMINENT CARDS — published only, within visibility window ──
    published_qs = base_qs.filter(status=Exam.PUBLISHED)
 
    context_items = []
    for exam in published_qs:
        if now < exam.visible_from or now > exam.visible_until:
            continue  # outside the 2-hour visibility window
 
        start_dt = exam.start_datetime
        end_dt   = exam.end_datetime
 
        response = StudentExamResponse.objects.filter(
            exam=exam, student=user
        ).first()
 
        context_items.append({
            'exam':                     exam,
            'can_read':                 now >= exam.instructions_open_at,
            'can_start':                now >= start_dt,
            'is_live':                  start_dt <= now < end_dt,
            'student_status':           response.status if response else 'not_started',
            'instructions_open_at_iso': exam.instructions_open_at.isoformat(),
            'exam_start_datetime_iso':  start_dt.isoformat(),
            'exam_end_datetime_iso':    end_dt.isoformat(),
        })
 
    return render(request, 'students/examlist.html', {
        'exams':     context_items,
        'all_exams': all_exams,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  INSTRUCTION PAGE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_instructions(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    now  = timezone.now()

    if now < exam.instructions_open_at:
        return redirect('students:exam_list')

    if now >= exam.end_datetime:
        return redirect('students:exam_list')

    response, _ = StudentExamResponse.objects.get_or_create(
        exam=exam,
        student=request.user,
        defaults={'status': StudentExamResponse.INSTRUCTIONS},
    )
    if response.status == StudentExamResponse.NOT_STARTED:
        response.status = StudentExamResponse.INSTRUCTIONS
    if not response.instructions_opened_at:
        response.instructions_opened_at = now
    response.save(update_fields=['status', 'instructions_opened_at'])

    secs = max(0, int((exam.start_datetime - now).total_seconds()))
    h, m, s = min(secs // 3600, 99), (secs % 3600) // 60, secs % 60

    # Pre-render units as (value_str, label) pairs for the template
    countdown_units = [
        (str(h).zfill(2), 'hrs'),
        (str(m).zfill(2), 'min'),
        (str(s).zfill(2), 'sec'),
    ]

    return render(request, 'students/examinstructions.html', {
        'exam':            exam,
        'exam_start_iso':  exam.start_datetime.isoformat(),
        'exam_end_iso':    exam.end_datetime.isoformat(),
        'countdown_units': countdown_units,
        'standard_rules':  STANDARD_EXAM_RULES,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  START EXAM  (assigns questions, then renders CBT page)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def start_exam(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    now  = timezone.now()

    if now < exam.start_datetime:
        return redirect('students:exam_instructions', slug=slug)
    if now >= exam.end_datetime:
        return redirect('students:exam_list')

    response, _ = StudentExamResponse.objects.get_or_create(
        exam=exam,
        student=request.user,
        defaults={'status': StudentExamResponse.INSTRUCTIONS},
    )
    if response.status in (StudentExamResponse.SUBMITTED, StudentExamResponse.GRADED):
        return redirect('students:exam_list')

    if not response.assigned_question_ids:
        questions = list(exam.questions.filter(is_active=True))
        if exam.shuffle_questions:
            random.shuffle(questions)
        if exam.questions_per_student:
            questions = questions[:exam.questions_per_student]

        options_map = {}
        for q in questions:
            opts = q.options.copy()
            if exam.shuffle_options:
                random.shuffle(opts)
            options_map[str(q.id)] = [opt['id'] for opt in opts]

        response.assigned_question_ids  = [q.id for q in questions]
        response.assigned_options_order = options_map
        response.status                 = StudentExamResponse.IN_PROGRESS
        response.exam_started_at        = now
        response.save(update_fields=[
            'assigned_question_ids', 'assigned_options_order',
            'status', 'exam_started_at',
        ])
    elif response.status != StudentExamResponse.IN_PROGRESS:
        response.status = StudentExamResponse.IN_PROGRESS
        response.save(update_fields=['status'])

    return render(request, 'students/exams.html', {
        'exam':         exam,
        'exam_end_iso': exam.end_datetime.isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
#  GET EXAM DATA  (JSON — questions + server-authoritative time remaining)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def get_exam_data(request, slug):
    exam     = get_object_or_404(Exam, slug=slug)
    response, _ = StudentExamResponse.objects.get_or_create(
    exam=exam,
    student=request.user,
    defaults={'status': StudentExamResponse.INSTRUCTIONS},
)
    questions_data = []
    for qid in response.assigned_question_ids:
        try:
            q = exam.questions.get(id=qid)
        except Exception:
            continue

        ordered_ids = response.assigned_options_order.get(str(qid), [])
        opt_lookup  = {opt['id']: opt for opt in q.options}
        options     = [
            {'id': oid, 'text': opt_lookup[oid]['text']}
            for oid in ordered_ids
            if oid in opt_lookup
        ]

        questions_data.append({
            'id':        q.id,
            'text':      q.question_text,
            'options':   options,
            'marks':     str(q.marks),
            'image_url': request.build_absolute_uri(q.image.url) if q.image else None,
        })

    now       = timezone.now()
    total_sec = exam.duration_minutes * 60
    wall_secs = max(0, int((exam.end_datetime - now).total_seconds()))

    if response.exam_started_at:
        elapsed   = int((now - response.exam_started_at).total_seconds())
        remaining = max(0, total_sec - elapsed)
    else:
        remaining = total_sec

    remaining = min(remaining, wall_secs)

    return JsonResponse({
        'questions':      questions_data,
        'time_remaining': remaining,
        'duration':       total_sec,
        'saved_answers':  response.answers,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  AUTO-SAVE SINGLE ANSWER
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@student_required
def save_answer(request, slug):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if 'question_id' not in data or 'answer' not in data:
        return JsonResponse({'error': 'Missing question_id or answer'}, status=400)

    response = get_object_or_404(StudentExamResponse, exam__slug=slug, student=request.user)

    if response.status not in (
        StudentExamResponse.INSTRUCTIONS, StudentExamResponse.IN_PROGRESS
    ):
        return JsonResponse({'error': 'Exam not in progress'}, status=400)

    response.answers[str(data['question_id'])] = data['answer']
    response.last_autosave_at = timezone.now()
    response.save(update_fields=['answers', 'last_autosave_at'])

    return JsonResponse({'status': 'saved'})


# ─────────────────────────────────────────────────────────────────────────────
#  FLAG TAB SWITCH (security — silent)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@student_required
def flag_tab_switch(request, slug):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        data     = json.loads(request.body)
        response = StudentExamResponse.objects.filter(
            exam__slug=slug, student=request.user
        ).first()
        if response:
            response.tab_switch_count = data.get('count', response.tab_switch_count + 1)
            response.save(update_fields=['tab_switch_count'])
    except Exception:
        pass
    return JsonResponse({'ok': True})


# ─────────────────────────────────────────────────────────────────────────────
#  SUBMIT + AUTO-GRADE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@student_required
def submit_exam(request, slug):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    response = get_object_or_404(StudentExamResponse, exam__slug=slug, student=request.user)

    if response.status in (StudentExamResponse.SUBMITTED, StudentExamResponse.GRADED):
        return JsonResponse({'status': 'already_submitted'})

    exam = response.exam
    now  = timezone.now()

    # ── Pre-fetch all assigned questions in one query ─────────────────────────
    assigned_ids = response.assigned_question_ids or []
    questions    = {q.id: q for q in exam.questions.filter(id__in=assigned_ids)}

    # ── Grade every question ──────────────────────────────────────────────────
    question_scores   = {}
    total_score       = 0.0
    total_marks       = 0.0
    pending_manual    = 0

    for qid in assigned_ids:
        q = questions.get(qid)
        if not q:
            continue

        max_marks = float(q.marks)
        total_marks += max_marks
        answer = response.answers.get(str(qid))

        # ── MCQ / True-False: single option ID ───────────────────────────────
        if q.question_type in (q.MCQ, q.TRUE_FALSE):
            correct_ids = {opt['id'] for opt in q.options if opt.get('is_correct')}
            if answer and answer in correct_ids:
                awarded = max_marks
            else:
                awarded = 0.0
            total_score += awarded
            question_scores[str(qid)] = {
                'marks_awarded':   awarded,
                'max_marks':       max_marks,
                'is_correct':      awarded == max_marks,
                'pending_manual':  False,
            }

        # ── Multi-select: list of option IDs, all-or-nothing scoring ─────────
        elif q.question_type == q.MULTI_SELECT:
            correct_ids  = {opt['id'] for opt in q.options if opt.get('is_correct')}
            selected     = set(answer) if isinstance(answer, list) else set()
            is_correct   = selected == correct_ids
            awarded      = max_marks if is_correct else 0.0
            total_score += awarded
            question_scores[str(qid)] = {
                'marks_awarded':  awarded,
                'max_marks':      max_marks,
                'is_correct':     is_correct,
                'pending_manual': False,
            }

        # ── Short answer: exact-match auto-grade if accepted_answers set ──────
        elif q.question_type == q.SHORT_ANSWER:
            if q.accepted_answers:
                normalised   = (answer or '').strip().lower()
                is_correct   = normalised in [a.strip().lower() for a in q.accepted_answers]
                awarded      = max_marks if is_correct else 0.0
                total_score += awarded
                question_scores[str(qid)] = {
                    'marks_awarded':  awarded,
                    'max_marks':      max_marks,
                    'is_correct':     is_correct,
                    'pending_manual': False,
                }
            else:
                # Needs manual grading
                pending_manual += 1
                question_scores[str(qid)] = {
                    'marks_awarded':  None,
                    'max_marks':      max_marks,
                    'is_correct':     None,
                    'pending_manual': True,
                }

        # ── Essay: always manual ──────────────────────────────────────────────
        elif q.question_type == q.ESSAY:
            pending_manual += 1
            question_scores[str(qid)] = {
                'marks_awarded':  None,
                'max_marks':      max_marks,
                'is_correct':     None,
                'pending_manual': True,
            }

    # ── Compute percentage & pass/fail ────────────────────────────────────────
    score_pct = round((total_score / total_marks) * 100, 2) if total_marks > 0 else 0.0
    is_fully_graded = pending_manual == 0

    # ── Write everything to DB ────────────────────────────────────────────────
    response.question_scores      = question_scores
    response.total_score          = total_score
    response.score_percentage     = score_pct
    response.pending_manual_count = pending_manual
    response.submitted_at         = now
    response.status               = (
        StudentExamResponse.GRADED if is_fully_graded else StudentExamResponse.SUBMITTED
    )
    if is_fully_graded:
        response.passed     = score_pct >= float(exam.pass_mark)
        response.graded_at  = now
        response.graded_by  = None   # system-graded
    else:
        response.passed = None       # awaits manual grading

    if response.exam_started_at:
        response.time_spent_seconds = int((now - response.exam_started_at).total_seconds())

    response.save(update_fields=[
        'question_scores', 'total_score', 'score_percentage',
        'pending_manual_count', 'submitted_at', 'status',
        'passed', 'graded_at', 'graded_by', 'time_spent_seconds',
    ])

    return JsonResponse({
        'status':           'submitted',
        'score':            total_score,
        'score_percentage': score_pct,
        'passed':           response.passed,
        'pending_manual':   pending_manual,
        'fully_graded':     is_fully_graded,
    })