from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.db.models import Q, Count, Avg, Prefetch, Max, Sum, F, FloatField
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from functools import wraps
from datetime import timedelta
from decimal import Decimal
from django.db import models, transaction, IntegrityError
from django.core.exceptions import ValidationError
import json
import random
import logging

from apps.eduweb.models import (
    LMSCourse, Enrollment, Lesson, LessonProgress,
    Assignment, AssignmentSubmission,
    Certificate, Announcement, Quiz, QuizAttempt,
    QuizAnswer, QuizQuestion, QuizResponse, StudyGroup, StudyGroupMember,
    Discussion, DiscussionReply, Badge,
    StudentBadge, LessonSection,
    Message, Notification, Review, StudyGroupMessage,
    FeePayment, CourseGrade, CourseApplication, Exam, StudentExamResponse,
    Course, CourseRegistration,
)

from .forms import AssignmentSubmissionForm, ReplyCreateForm, ThreadCreateForm, StudyGroupMessageForm

logger = logging.getLogger(__name__)


def _registrable_course_ids(profile):
    """
    Course IDs a student is allowed to register for right now: every active
    course they haven't already passed. The catalog is flat — any accepted
    student can register for any course, regardless of program/level — so
    the only exclusion is a course they've already completed.
    """
    if not profile:
        return Course.objects.none().values_list('id', flat=True)

    # result_status='released' — an unpublished pass isn't confirmed to the
    # student yet, so it must not silently drop the course from their
    # registrable list while they're still waiting on the official result.
    passed_course_ids = CourseGrade.objects.filter(
        student=profile.user, is_passed=True, result_status='released',
    ).values_list('course_id', flat=True)

    return Course.objects.filter(
        is_active=True,
    ).exclude(
        pk__in=passed_course_ids,
    ).values_list('id', flat=True)


def _overdue_required_fees(user):
    """
    Overdue, unpaid AllRequiredPayments for this student (program/level-scoped,
    via the same _get_outstanding_for_student used by the "My Payments" page —
    single source of truth for "what does this student owe"). Excludes
    auto-generated certificate fees: those are earned post-completion and
    have nothing to do with registration eligibility.

    Used to gate *new* course registration only (register_semester_course) —
    per product decision, already-registered courses and finalizing/enrolling
    in courses already added stay unaffected, and portal access itself is
    gated separately (see can_access_student_portal / student_required).
    """
    outstanding, _paid = _get_outstanding_for_student(user)
    return [
        item for item in outstanding
        if item['is_overdue'] and not item['is_certificate_fee']
    ]


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
        
        if request.user.profile.role != 'student' and not request.user.is_superuser:
            messages.error(
                request, 
                'Access denied. Students only.'
            )
            return redirect(
                'management:dashboard' 
                if request.user.is_staff 
                else 'eduweb:index'
            )

        # Superuser bypasses application check entirely
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Block access if application hasn't been approved yet
        from apps.eduweb.models import CourseApplication
        application = CourseApplication.objects.filter(user=request.user).first()
        if not application or not application.can_access_student_portal():
            if application and not application.is_paid:
                messages.warning(
                    request,
                    'Please complete your application fee payment to access the student portal.'
                )
            else:
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

@login_required
@student_required
def dashboard(request):
    """Student dashboard — courses, assignments, announcements, academic identity."""
    user = request.user

    # ── Academic identity (needed by multiple sections below) ────────────────
    profile = getattr(user, 'profile', None)

    department = None
    faculty    = None
    if profile and profile.program:
        department = getattr(profile.program, 'department', None)
        faculty    = getattr(department, 'faculty', None) if department else None

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
            .select_related('program', 'program__department__faculty')
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
        logger.exception('Failed to load dashboard data for user=%s', user.pk)
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
        # Defaulting to "nothing owed" on failure is a deliberate choice to
        # keep the dashboard usable, but a wrong balance is a real financial
        # risk, so this must never fail silently server-side.
        logger.exception('Failed to compute outstanding fees for user=%s', user.pk)
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
        .select_related('course')
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
        # Exams & grades
        'upcoming_exams':           upcoming_exams,
        'recent_grades':            recent_grades,
    }

    return render(request, 'students/dashboard.html', context)

@login_required
@student_required
def my_courses(request):
    """
    "My Courses" — everything the student is already taking: courses
    auto-registered for them from their chosen program on admission, plus
    anything they've added since from the catalog. Browsing/registering for
    *more* courses happens on the catalog and course-detail pages, not here.
    """
    user = request.user
    profile = getattr(user, 'profile', None)

    registrations = list(
        CourseRegistration.objects.filter(
            student=user, status__in=['pending', 'approved'],
        )
        .select_related('course', 'course__program')
        .order_by('-registered_at')
    )

    try:
        enrollment_by_academic_course_id = {
            e.course.academic_course_id: e
            for e in (
                Enrollment.objects.filter(student=user, status__in=['active', 'completed'])
                .select_related('course', 'course__instructor', 'course__academic_course')
                .prefetch_related(
                    Prefetch(
                        'course__lessons',
                        queryset=Lesson.objects.filter(is_active=True),
                        to_attr='active_lessons',
                    )
                )
                .annotate(
                    completed_lessons_count=Count(
                        'lesson_progress',
                        filter=Q(lesson_progress__is_completed=True),
                        distinct=True,
                    )
                )
            )
            if e.course.academic_course_id
        }
    except Exception:
        logger.exception('Failed to load enrolled courses for user=%s', user.pk)
        messages.error(request, 'Error loading your courses. Please try again.')
        enrollment_by_academic_course_id = {}

    rows = [
        {
            'course': reg.course,
            'is_core': reg.course.course_type == 'core',
            'status': reg.status,
            'enrollment': enrollment_by_academic_course_id.get(reg.course_id),
        }
        for reg in registrations
    ]

    # ── Academic identity ──────────────────────────────────────────────────
    department = faculty = None
    if profile and profile.program:
        department = getattr(profile.program, 'department', None)
        faculty    = getattr(department, 'faculty', None) if department else None

    context = {
        'page_title':  'My Courses',
        'rows':        rows,
        'profile':     profile,
        'department':  department,
        'faculty':     faculty,
    }

    return render(request, 'students/my_courses.html', context)

def _enroll_in_lms_course_for(user, course):
    """
    Given an academic Course a student is registered for, find its matching
    LMSCourse delivery (by academic_course FK, falling back to a matching
    code on a standalone LMS course) and enroll the student if one exists
    and has published content. Returns the Enrollment if one was
    created/activated, else None (course content is not ready yet).
    """
    lms_course = None
    if course.pk:
        lms_course = LMSCourse.objects.filter(academic_course=course).first()
    if not lms_course and course.code:
        lms_course = LMSCourse.objects.filter(
            academic_course__isnull=True, code__iexact=course.code,
        ).first()
    if not lms_course:
        return None
    if not lms_course.lessons.filter(is_active=True).exists():
        return None

    enrollment, created = Enrollment.objects.get_or_create(
        student=user,
        course=lms_course,
        defaults={'enrolled_by': user, 'status': 'active'},
    )
    if not created and enrollment.status == 'dropped':
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])
    return enrollment


@login_required
@student_required
def register_semester_course(request, course_slug):
    """
    Register for a course from the flat catalog -- any accepted student can
    register for any active course. Auto-enrolls in the linked LMS delivery
    immediately if one exists with published content.
    """
    if request.method != 'POST':
        return redirect('students:my_courses')

    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'No student profile found.')
        return redirect('students:my_courses')

    overdue_fees = _overdue_required_fees(request.user)
    if overdue_fees:
        owed = ', '.join(
            f"{item['payment'].purpose} ({item['payment'].currency} {item['payment'].amount})"
            for item in overdue_fees
        )
        messages.error(
            request,
            f'You have overdue required payment(s): {owed}. '
            f'Please clear these before registering for new courses.'
        )
        return redirect('students:my_payments')

    course = get_object_or_404(
        Course.objects.filter(pk__in=_registrable_course_ids(profile)),
        slug=course_slug,
        is_active=True,
    )

    # transaction.atomic() + IntegrityError guard closes the double-submit
    # race window (double-click, two tabs) -- CourseRegistration's
    # unique_together=('student','course') means a concurrent duplicate
    # INSERT now degrades to a friendly message instead of an unhandled 500.
    try:
        with transaction.atomic():
            reg, created = CourseRegistration.objects.get_or_create(
                student=request.user,
                course=course,
                defaults={'status': 'pending'},
            )
    except ValidationError as e:
        messages.error(request, f'Cannot register for "{course.name}": {"; ".join(e.messages)}')
        return redirect('students:my_courses')
    except IntegrityError:
        logger.warning(
            'Concurrent duplicate registration attempt: user=%s course=%s',
            request.user.pk, course.pk,
        )
        messages.info(request, f'You are already registered for "{course.name}".')
        return redirect('students:my_courses')

    if not created:
        if reg.status == 'dropped':
            reg.status = 'pending'
            reg.dropped_at = None
            reg.save(update_fields=['status', 'dropped_at'])
        else:
            messages.info(request, f'You are already registered for "{course.name}".')
            return redirect('students:my_courses')

    enrollment = _enroll_in_lms_course_for(request.user, course)
    if enrollment:
        reg.status = 'approved'
        reg.save(update_fields=['status'])
        messages.success(request, f'"{course.name}" registered -- you are enrolled and can start now.')
    else:
        messages.success(
            request,
            f'"{course.name}" ({course.credit_units} CU) registered -- '
            f'course content is not published yet, you will be enrolled once it is.'
        )

    _notify(
        user=request.user,
        notification_type='enrollment',
        title='Course Registered',
        message=f'You registered for {course.code} -- {course.name}.',
        link='/student/courses/',
    )

    return redirect('students:my_courses')

@login_required
@student_required
def drop_semester_course(request, course_slug):
    """
    Remove a non-core Course from the student's registration.
    Core courses cannot be dropped.
    """
    if request.method != 'POST':
        return redirect('students:my_courses')

    course = get_object_or_404(Course, slug=course_slug)

    if course.course_type == 'core':
        messages.error(request, f'"{course.name}" is a core course and cannot be removed.')
        return redirect('students:my_courses')

    reg = CourseRegistration.objects.filter(
        student=request.user,
        course=course,
        status__in=['pending', 'approved'],
    ).first()

    if reg:
        was_approved = reg.status == 'approved'
        reg.status = 'dropped'
        reg.dropped_at = timezone.now()
        reg.save(update_fields=['status', 'dropped_at'], skip_clean=True)

        # An approved registration may already have an active LMS Enrollment --
        # drop it too, otherwise the student keeps lesson/quiz/exam access for
        # a course they no longer have a registration for.
        if was_approved and course.code:
            lms_course = LMSCourse.objects.filter(
                Q(academic_course=course) | Q(academic_course__isnull=True, code__iexact=course.code)
            ).first()
            if lms_course:
                Enrollment.objects.filter(
                    student=request.user, course=lms_course, status='active',
                ).update(status='dropped')

        messages.success(request, f'"{course.name}" removed from your registration.')
    else:
        messages.warning(request, 'Registration record not found.')

    return redirect('students:my_courses')

@login_required
@student_required
def retry_lms_enrollment(request, course_slug):
    """
    Retry LMS enrollment for a pending CourseRegistration whose linked LMS
    content was not published yet at registration time. Returns JSON so the
    template can update the button without a page reload.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required.'}, status=405)

    try:
        return _retry_lms_enrollment(request, course_slug)
    except Http404:
        raise
    except Exception:
        # This is an AJAX/JSON endpoint -- an unhandled exception must never
        # surface as an HTML 500 page, which the calling JS can't parse.
        logger.exception(
            'retry_lms_enrollment failed for user=%s course_slug=%s',
            request.user.pk, course_slug,
        )
        return JsonResponse({
            'status': 'error',
            'message': 'Something went wrong. Please try again.',
        }, status=500)


def _retry_lms_enrollment(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug, is_active=True)

    reg = CourseRegistration.objects.filter(
        student=request.user,
        course=course,
        status='pending',
    ).first()

    if not reg:
        return JsonResponse({
            'status': 'error',
            'message': 'No pending registration found for this course.',
        })

    enrollment = _enroll_in_lms_course_for(request.user, course)
    if not enrollment:
        return JsonResponse({
            'status': 'pending',
            'message': 'Course is not yet ready for enrollment. Please check back later.',
        })

    reg.status = 'approved'
    reg.save(update_fields=['status'])

    _notify(
        user=request.user,
        notification_type='enrollment',
        title='Course Enrollment Confirmed',
        message=f'You have been enrolled in {course.code} -- {course.name}.',
        link='/student/courses/',
    )

    return JsonResponse({
        'status': 'enrolled',
        'message': f'Successfully enrolled in {course.name}.',
    })

@login_required
@student_required
def course_catalog(request):
    """Flat catalog of every published LMS course — open to any accepted student."""
    search_query = request.GET.get('q', '').strip()

    enrolled_course_ids = set(
        Enrollment.objects
        .filter(student=request.user, status__in=['active', 'completed'])
        .values_list('course_id', flat=True)
    )

    courses = LMSCourse.objects.filter(is_published=True)

    if search_query:
        courses = courses.filter(Q(title__icontains=search_query) | Q(code__icontains=search_query))

    courses = courses.select_related('academic_course', 'instructor').distinct()

    registered_academic_ids = set(
        CourseRegistration.objects
        .filter(student=request.user, status__in=['pending', 'approved'])
        .values_list('course_id', flat=True)
    )

    # Enrolled first → registered → everything else
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
            completed_lesson_ids = set(
                LessonProgress.objects.filter(
                    enrollment=enrollment,
                    is_completed=True
                ).values_list('lesson_id', flat=True)
            )
            enrollment.completed_lessons_count = len(completed_lesson_ids)

            # Get the first incomplete lesson for "Continue Learning" button
            first_incomplete_lesson = None
            for section in sections:
                for lesson in section.filtered_lessons:
                    if lesson.id not in completed_lesson_ids:
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

        # Any published course can be enrolled in directly from this page —
        # enroll_course() registers the linked academic course (if any) in
        # the same action, so there's nothing to gate here.
        context = {
            'page_title': course.title,
            'course': course,
            'enrollment': enrollment,
            'sections': sections,
            'existing_review': existing_review,
        }
        
        return render(request, 'students/course_detail.html', context)

    except Http404:
        # A missing/unpublished course must actually 404, not get swallowed
        # into the generic handler below and mis-reported as a transient error.
        raise
    except Exception:
        logger.exception('Failed to load course detail for slug=%s user=%s', course_slug, request.user.pk)
        messages.error(
            request,
            'An error occurred loading the course. Please try again.'
        )
        return redirect('students:course_catalog')


@login_required
@student_required
def enroll_course(request, course_slug):
    """
    Enroll in a course directly from the catalog/course-detail page.
    All LMS courses are free — enrollment is immediate. If this course
    delivers an academic Course, register for it (creating the record if
    needed) in the same action — there's no separate "register first"
    step; clicking Enroll here is the registration.
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

    # Enroll directly, registering for the linked academic course too if
    # there is one. get_or_create + IntegrityError guard closes the race
    # window between the `existing` check above and this write —
    # Enrollment's unique_together=('student','course') means a
    # double-submit (double click, two tabs) can no longer create
    # duplicate enrollment rows or surface a misleading "error" for what
    # was actually a successful enroll.
    try:
        with transaction.atomic():
            if course.academic_course:
                CourseRegistration.objects.get_or_create(
                    student=request.user, course=course.academic_course,
                    defaults={'status': 'approved'},
                )
            enrollment, created = Enrollment.objects.get_or_create(
                student=request.user,
                course=course,
                defaults={'enrolled_by': request.user, 'status': 'active'},
            )
    except IntegrityError:
        logger.warning(
            'Concurrent duplicate enrollment attempt: user=%s course=%s',
            request.user.pk, course.pk,
        )
        created = False
    except Exception:
        logger.exception(
            'Enrollment failed for user=%s course=%s', request.user.pk, course.pk
        )
        messages.error(request, 'An error occurred during enrollment. Please try again.')
        return redirect('students:course_detail', course_slug=course_slug)

    if created:
        if course.academic_course:
            CourseRegistration.objects.filter(
                student=request.user, course=course.academic_course, status='pending',
            ).update(status='approved')
        messages.success(request, f'Successfully enrolled in {course.title}!')
        _notify(
            user=request.user,
            notification_type='enrollment',
            title=f'Enrolled in {course.title}',
            message=f'You have successfully enrolled in "{course.title}". Start learning now!',
            link=f'/student/courses/{course.slug}/',
        )
    else:
        messages.info(request, 'You are already enrolled in this course.')

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

def _record_academic_grade(user, enrollment, lms_course):
    """
    Recompute this student's official CourseGrade when a linked LMS course
    is completed, via the shared weighted exam/quiz/assignment blend.
    """
    academic_course = lms_course.academic_course
    if not academic_course:
        return

    try:
        CourseGrade.recompute_for_student_course(user, academic_course)
    except Exception:
        logger.exception(
            'Failed to recompute CourseGrade for user=%s course=%s',
            user.pk, academic_course.pk,
        )

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
        cert.issuer = 'Abraytech Academic Office'
        cert.is_program_cert = True
    else:
        cert.display_title = cert.course.title if cert.course else 'Course Certificate'
        cert.display_subtitle = ''
        cert.is_program_cert = False
        cert.issuer = (
            cert.course.instructor.get_full_name()
            if cert.course and cert.course.instructor else 'Abraytech Staff'
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

    if not enrollment:
        # Preview access with no enrollment — LessonProgress.enrollment is a
        # required FK, so there's nothing to track completion against yet.
        # (Previously this fell through to get_or_create(enrollment=None,...),
        # which always raised IntegrityError and surfaced as a generic 500.)
        return JsonResponse({
            'success': False,
            'message': 'Enroll in this course to track your lesson progress.',
        }, status=400)

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
        
    except Exception:
        logger.exception(
            'mark_lesson_complete failed for user=%s lesson=%s/%s',
            request.user.pk, course_slug, lesson_slug,
        )
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
            
            # Django templates silently refuse to resolve underscore-prefixed
            # attributes, and Assignment.is_overdue is a read-only @property
            # (no setter) — so this must be a differently-named, non-
            # underscore attribute for the template to actually see it.
            if not assignment.submission or assignment.submission.status == 'draft':
                assignment.overdue_status = timezone.now() > assignment.due_date
            else:
                assignment.overdue_status = False
                
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
                # Create or update submission. transaction.atomic() +
                # unique_together=('assignment','student') on the model
                # means a double-submit (double-click, two tabs) can't
                # create duplicate submission rows.
                with transaction.atomic():
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
                
                # Handle file upload — use the form's cleaned_data, not the
                # raw request.FILES, so any validation/normalisation done in
                # AssignmentSubmissionForm.clean_attachment is actually honored.
                if form.cleaned_data.get('attachment'):
                    submission.attachment = form.cleaned_data['attachment']
                
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
                
            except IntegrityError:
                logger.warning(
                    'Concurrent duplicate assignment submission: user=%s assignment=%s',
                    request.user.pk, assignment.pk,
                )
                messages.info(request, 'You have already submitted this assignment.')
            except Exception:
                logger.exception(
                    'Assignment submission failed for user=%s assignment=%s',
                    request.user.pk, assignment.pk,
                )
                messages.error(
                    request,
                    'Error submitting assignment. Please try again.'
                )
        else:
            # Surface the actual validation reasons (e.g. "file too large",
            # "submission text too short") instead of a generic message.
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
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

    # Annotate with attempt information. Bulk-fetch every completed attempt
    # for every quiz on this page in one query and group in Python — this
    # used to run 4 separate queries per quiz in the loop below
    # (.count()/.aggregate(Max)/.order_by().first()/.filter(passed=True)
    # .exists()), invisible at low course-catalog volume but measured at 72
    # of 95 total queries on this page for 18 quizzes post-reseed.
    quizzes = list(quizzes)
    all_attempts = (
        QuizAttempt.objects
        .filter(quiz_id__in=[q.id for q in quizzes], student=request.user, is_completed=True)
        .order_by('quiz_id', '-completed_at')
    )
    attempts_by_quiz = {}
    for a in all_attempts:
        attempts_by_quiz.setdefault(a.quiz_id, []).append(a)

    quiz_list = []
    for quiz in quizzes:
        # All completed attempts for this quiz, most recent first (the
        # ordering above is preserved per-group by insertion order).
        attempts = attempts_by_quiz.get(quiz.id, [])

        # Calculate statistics
        attempt_count = len(attempts)
        best_score = max((a.percentage for a in attempts), default=0) or 0
        latest_attempt = attempts[0] if attempts else None

        # Determine status
        has_passed = any(a.passed for a in attempts)
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

    try:
        with transaction.atomic():
            # Re-check under the transaction — a concurrent double-submit
            # (double-click, duplicate tab) could both pass the is_completed
            # check above before either write lands.
            attempt = QuizAttempt.objects.select_for_update().get(pk=attempt.pk)
            if attempt.is_completed:
                messages.warning(request, 'Quiz already submitted.')
                return redirect('students:quiz_result', attempt_id=attempt_id)

            has_pending_manual_grading = False

            for key, value in request.POST.items():
                if key.startswith('question_'):
                    try:
                        question_id = int(key.split('_')[1])
                        question = attempt.quiz.questions.get(
                            id=question_id
                        )
                    except (QuizQuestion.DoesNotExist, ValueError):
                        continue

                    max_score += question.points

                    if question.question_type in ('short_answer', 'essay'):
                        # No automatic "correct answer" concept for free text —
                        # record it for an instructor to grade manually. Counted
                        # into max_score (the quiz's true total) but not yet
                        # into total_score, so the percentage understates the
                        # result until graded rather than silently dropping
                        # these questions and their points from the quiz.
                        text_value = str(value).strip()
                        if not text_value:
                            continue
                        QuizResponse.objects.create(
                            attempt=attempt,
                            question=question,
                            text_response=text_value,
                            is_correct=False,
                            points_earned=Decimal('0.00'),
                            needs_grading=True,
                        )
                        has_pending_manual_grading = True
                        continue

                    try:
                        # Scope the answer lookup to this question — otherwise a
                        # student could submit any QuizAnswer id from any question
                        # in the system (e.g. one they know is correct on a
                        # different quiz) and be awarded full points for it here.
                        selected_answer = question.answers.get(
                            id=int(value)
                        )
                    except (QuizAnswer.DoesNotExist, ValueError):
                        continue

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

            # Calculate percentage
            percentage = (
                (total_score / max_score * 100)
                if max_score > 0
                else Decimal('0.00')
            )

            # Calculate time taken
            time_delta = timezone.now() - attempt.started_at
            time_taken = int(time_delta.total_seconds() / 60)

            # Update attempt. passed/percentage are provisional while any
            # response still needs manual grading — quiz_result.html shows a
            # "pending" banner and instructor grading recomputes both once
            # every short-answer/essay response has a score.
            attempt.score = total_score
            attempt.max_score = max_score
            attempt.percentage = percentage
            attempt.passed = percentage >= attempt.quiz.passing_score
            attempt.pending_manual_grading = has_pending_manual_grading
            attempt.is_completed = True
            attempt.completed_at = timezone.now()
            attempt.time_taken_minutes = time_taken
            attempt.save()
    except IntegrityError:
        logger.warning(
            'Concurrent duplicate quiz submission: attempt=%s user=%s',
            attempt_id, request.user.pk,
        )
        messages.warning(request, 'Quiz already submitted.')
        return redirect('students:quiz_result', attempt_id=attempt_id)

    # This attempt's percentage feeds the quiz component of the student's
    # unified CourseGrade (CourseGrade.recompute_for_student_course) — the
    # other three trigger points (lesson completion, exam auto-grading,
    # instructor grading) all recompute immediately, so a quiz shouldn't be
    # the one score type that only updates whenever some unrelated lesson
    # later happens to be marked complete in the same course.
    lms_course = attempt.quiz.lesson.course
    academic_course = lms_course.academic_course
    if academic_course:
        try:
            CourseGrade.recompute_for_student_course(request.user, academic_course)
        except Exception:
            logger.exception(
                'Failed to recompute CourseGrade after quiz submission for user=%s quiz=%s',
                request.user.pk, attempt.quiz_id,
            )

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
    pending_grading_count = answers.filter(needs_grading=True).count()
    incorrect_answers = total_questions - correct_answers - pending_grading_count

    context = {
        'page_title': 'Quiz Results',
        'attempt': attempt,
        'answers': answers,
        'total_questions': total_questions,
        'correct_answers': correct_answers,
        'incorrect_answers': incorrect_answers,
        'pending_grading_count': pending_grading_count,
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
        # get_page() already handles PageNotAnInteger/EmptyPage internally —
        # reaching here means something unexpected (e.g. a DB error), so log it.
        logger.exception('Failed to paginate community threads, page=%s', page_number)
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
    enrollments = list(
        Enrollment.objects
        .filter(student=user)
        .select_related('course', 'course__instructor')
        .prefetch_related('course__lessons')
        .order_by('-enrolled_at')
    )

    # Bulk-computed per enrollment/course — replaces what used to be 3
    # queries run inside the per-enrollment loop below (N+1).
    enrollment_ids = [e.id for e in enrollments]
    course_ids = {e.course_id for e in enrollments}

    completed_by_enrollment = dict(
        LessonProgress.objects
        .filter(enrollment_id__in=enrollment_ids, is_completed=True)
        .values_list('enrollment_id')
        .annotate(c=Count('id'))
    )
    total_lessons_by_course = dict(
        Lesson.objects
        .filter(course_id__in=course_ids, is_active=True)
        .values_list('course_id')
        .annotate(c=Count('id'))
    )
    avg_score_by_course = dict(
        AssignmentSubmission.objects
        .filter(
            student=user,
            assignment__lesson__course_id__in=course_ids,
            status='graded',
            score__isnull=False,
        )
        .values_list('assignment__lesson__course_id')
        .annotate(avg=Avg(F('score') * 100.0 / F('assignment__max_score'), output_field=FloatField()))
    )

    for enrollment in enrollments:
        completed_count = completed_by_enrollment.get(enrollment.id, 0)
        total_lessons = total_lessons_by_course.get(enrollment.course_id, 0)

        enrollment.completed_lessons = completed_count
        enrollment.progress_percentage = (
            (completed_count / total_lessons * 100)
            if total_lessons > 0
            else 0
        )
        enrollment.current_grade = avg_score_by_course.get(enrollment.course_id)
    
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
    
    # Academic course grades (from program — recorded by lecturers).
    # result_status='released' — a compiled-but-unapproved grade must not
    # appear here; see CourseGrade.publish_results.
    academic_grades = (
        CourseGrade.objects
        .filter(student=user, result_status='released')
        .select_related('course', 'course__program')
        .order_by('course__code')
    )
    pending_results_count = CourseGrade.objects.filter(
        student=user, result_status__in=['pending', 'withheld'],
    ).count()

    # Quiz attempts — best attempt per quiz for graded display
    quiz_attempts = list(
        QuizAttempt.objects
        .filter(student=user, is_completed=True)
        .select_related('quiz', 'quiz__lesson', 'quiz__lesson__course')
        .order_by('-completed_at')
    )

    # Canonical CGPA — same CourseGrade.compute_cgpa used by the dashboard,
    # Academic Records, and progression logic, so this page can't disagree
    # with any of them.
    cgpa = CourseGrade.compute_cgpa(user)

    completed_courses_count = sum(1 for e in enrollments if e.status == 'completed')

    context = {
        'page_title': 'Grades & Performance',
        'enrollments': enrollments,
        'enrollments_count': len(enrollments),
        'submissions': submissions,
        'submissions_count': len(submissions),
        'quiz_attempts': quiz_attempts,
        'academic_grades': academic_grades,
        'cgpa': cgpa,
        'pending_results_count': pending_results_count,
        'completed_courses_count': completed_courses_count,
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
    
    # Get all enrollments with related data. The section/lesson prefetches use
    # to_attr with an is_active filter baked in so the per-section loop below
    # can read the prefetch cache instead of re-querying per section (Django
    # only serves .all() from cache — any further .filter() call bypasses it).
    enrollments = list(
        Enrollment.objects
        .filter(student=user)
        .select_related('course', 'course__instructor')
        .prefetch_related(
            Prefetch(
                'course__sections',
                queryset=LessonSection.objects.order_by('display_order'),
            ),
            Prefetch(
                'course__sections__lessons',
                queryset=Lesson.objects.filter(is_active=True),
                to_attr='active_lessons_list',
            ),
        )
        .order_by('-enrolled_at')
    )

    enrollment_ids = [e.id for e in enrollments]
    course_ids = {e.course_id for e in enrollments}

    # Bulk-computed replacements for what used to be several queries per
    # enrollment (lesson totals, completed lessons, assignment/quiz counts)
    # plus a query per course section — all N+1 patterns.
    completed_lesson_ids_by_enrollment = {}
    for enrollment_id, lesson_id in (
        LessonProgress.objects
        .filter(enrollment_id__in=enrollment_ids, is_completed=True)
        .values_list('enrollment_id', 'lesson_id')
    ):
        completed_lesson_ids_by_enrollment.setdefault(enrollment_id, set()).add(lesson_id)

    total_lessons_by_course = dict(
        Lesson.objects
        .filter(course_id__in=course_ids, is_active=True)
        .values_list('course_id')
        .annotate(c=Count('id'))
    )
    # First active lesson per course (for the "Continue Learning" link) —
    # bulk-computed in the same ordering the template used to get for free
    # via enrollment.course.lessons.first (Lesson.Meta.ordering =
    # ['course', 'section', 'display_order']), so this replaces a per-row
    # `.first`/`.count` template call (an N+1 the view already eliminates
    # everywhere else) rather than changing which lesson counts as "first".
    first_lesson_by_course = {}
    for lesson in (
        Lesson.objects
        .filter(course_id__in=course_ids, is_active=True)
        .order_by('course_id', 'section_id', 'display_order')
    ):
        first_lesson_by_course.setdefault(lesson.course_id, lesson)
    assignment_count_by_course = dict(
        Assignment.objects
        .filter(lesson__course_id__in=course_ids)
        .values_list('lesson__course_id')
        .annotate(c=Count('id'))
    )
    quiz_count_by_course = dict(
        Quiz.objects
        .filter(lesson__course_id__in=course_ids)
        .values_list('lesson__course_id')
        .annotate(c=Count('id'))
    )

    # Add detailed progress data to each enrollment
    for enrollment in enrollments:
        completed_lesson_ids = completed_lesson_ids_by_enrollment.get(enrollment.id, set())
        enrollment.completed_lesson_ids = completed_lesson_ids
        enrollment.completed_lessons = len(completed_lesson_ids)

        total_lessons = total_lessons_by_course.get(enrollment.course_id, 0)
        enrollment.total_lesson_count = total_lessons
        enrollment.first_lesson = first_lesson_by_course.get(enrollment.course_id)
        enrollment.progress_percentage = (
            (enrollment.completed_lessons / total_lessons * 100)
            if total_lessons > 0
            else 0
        )

        # Add section progress — reads the prefetched, already-filtered
        # active_lessons_list, no additional query per section.
        for section in enrollment.course.sections.all():
            section_lessons = section.active_lessons_list
            total = len(section_lessons)
            completed = sum(
                1 for lesson in section_lessons
                if lesson.id in completed_lesson_ids
            )
            section.progress_percentage = (
                (completed / total * 100) if total > 0 else 0
            )
            section.total_lessons = total

        enrollment.assignment_count = assignment_count_by_course.get(enrollment.course_id, 0)
        enrollment.quiz_count = quiz_count_by_course.get(enrollment.course_id, 0)
    
    # Calculate learning activity for last 28 days
    from datetime import datetime, timedelta
    from collections import Counter
    today = timezone.now().date()
    start_date = today - timedelta(days=27)  # 28 days including today

    lesson_counts = Counter(
        LessonProgress.objects.filter(
            enrollment__student=user,
            completed_at__date__gte=start_date,
            completed_at__date__lte=today,
        ).values_list('completed_at__date', flat=True)
    )
    assignment_counts = Counter(
        AssignmentSubmission.objects.filter(
            student=user,
            submitted_at__date__gte=start_date,
            submitted_at__date__lte=today,
        ).values_list('submitted_at__date', flat=True)
    )
    quiz_counts = Counter(
        QuizAttempt.objects.filter(
            student=user,
            started_at__date__gte=start_date,
            started_at__date__lte=today,
        ).values_list('started_at__date', flat=True)
    )

    activity_data = []
    for i in range(28):
        date = start_date + timedelta(days=i)

        # Count activities for this day
        lessons_completed = lesson_counts.get(date, 0)
        assignments_submitted = assignment_counts.get(date, 0)
        quizzes_taken = quiz_counts.get(date, 0)

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
        'enrollments_count': len(enrollments),
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
            cert.instructor_name = 'Abraytech Academic Office'
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
                cert.instructor_name = 'Abraytech Staff'
        cert.is_unlocked = cert.payment_status == 'paid'

    context = {
        'page_title': 'My Certificates',
        'certificates': certificates,
    }

    return render(request, 'students/certificates.html', context)


# NOTE: "My Profile" and "Settings" are now single shared pages for every
# role — see eduweb.views.profile / eduweb.views.settings
# (templates/account/profile.html, templates/account/settings.html), routed
# at eduweb:profile / eduweb:settings. There is no per-app students:profile
# or students:settings view any more.

# NOTE: "Help & Support" is now a single shared page for every role — see
# support.views.submit_ticket (templates/support/submit_ticket.html), routed
# at support:submit_ticket. There is no per-app students:help_support any more.

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
    from apps.eduweb.models import AllRequiredPayments, Enrollment, FeePayment, Certificate

    profile = getattr(user, 'profile', None)
    if not profile or not profile.program:
        return [], []

    # ── 1. Standard admin-created required fees ───────────────────────────
    required_qs = AllRequiredPayments.objects.filter(
        program=profile.program,
        who_to_pay='student',
        is_active=True,
    ).select_related('program', 'program__department', 'program__department__faculty')

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
            from apps.eduweb.emailservices import send_new_message_email
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
            except (AuthUser.DoesNotExist, ValueError, TypeError):
                # Invalid/unknown ?to= — just skip the pre-fill, not a real error.
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
                from apps.eduweb.emailservices import send_new_message_email
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
    # Freezes a snapshot of the current grade record at request time — the UI
    # promises requesting locks the transcript so later-recorded results can't
    # silently change an already-requested document.
    if request.method == 'POST' and request.POST.get('action') == 'request_transcript':
        application_qs = CourseApplication.objects.filter(user=user, status='approved')
        if application_qs.exists():
            app = application_qs.order_by('-created_at').first()
            if not app.transcript_requested:
                app.transcript_requested = True
                app.transcript_snapshot = CourseGrade.build_transcript_snapshot(user)
                app.save(update_fields=['transcript_requested', 'transcript_snapshot'])
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
        .select_related('program', 'program__department__faculty')
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
            .order_by('name')
        )
    core_courses     = [c for c in program_courses if c.course_type == 'core']
    elective_courses = [c for c in program_courses if c.course_type == 'elective']
    other_courses    = [c for c in program_courses if c.course_type not in ('core', 'elective')]
    total_credits_required = program.credits_required if program else 0

    # ── 3. Official course grades — locked snapshot once requested, else live ─
    # Unified via CourseGrade.recompute_for_student_course, blending exam/quiz/
    # assignment scores per the course's configured weights. Superseded the old
    # StudentExamResponse-only proxy, which disagreed with the dashboard and
    # "Grades & Performance" pages.
    if application and application.transcript_requested and application.transcript_snapshot:
        snapshot = application.transcript_snapshot
    else:
        snapshot = CourseGrade.build_transcript_snapshot(user)

    grades         = snapshot['grades']
    gpa            = snapshot['gpa']
    gpa_class      = snapshot['gpa_class']
    credits_earned = snapshot['credits_earned']
    grade_count    = snapshot['grade_count']

    # ── 4. Credits ────────────────────────────────────────────────────────────
    credits_remaining = max(0, total_credits_required - credits_earned)
    graduation_pct    = (
        round(credits_earned / total_credits_required * 100, 1)
        if total_credits_required > 0 else 0
    )

    # ── 8. LMS enrollments (informational only) ───────────────────────────────
    lms_enrollments = (
        Enrollment.objects
        .filter(student=user)
        .select_related('course')
        .order_by('-enrolled_at')
    )

    # ── 9. Certificates ───────────────────────────────────────────────────────
    certificates = (
        Certificate.objects
        .filter(student=user)
        .select_related('course', 'program')
        .order_by('-issued_date')
    )

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
        'grade_count':             grade_count,
        'grades':                  grades,
        'gpa':                     gpa,
        'gpa_class':               gpa_class,
        'lms_enrollments':         lms_enrollments,
        'certificates':            certificates,
        'transcript_locked':       bool(application and application.transcript_requested and application.transcript_snapshot),
        'transcript_generated_at': parse_datetime(snapshot['generated_at']) if snapshot.get('generated_at') else None,
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
    now  = timezone.now()
    user = request.user

    # ── Base queryset: published exams for courses this student is enrolled in ──
    base_qs = (
        Exam.objects
        .filter(
            is_active=True,
            course__enrollments__student=user,
            course__enrollments__status__in=['active', 'completed'],
        )
        .select_related('course')
        .order_by('start_datetime')
        .distinct()
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
@student_required
def exam_instructions(request, slug):
    exam = get_object_or_404(
        Exam.objects.filter(
            is_active=True,
            course__enrollments__student=request.user,
            course__enrollments__status__in=['active', 'completed'],
        ).distinct(),
        slug=slug,
    )
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
@student_required
def start_exam(request, slug):
    exam = get_object_or_404(
        Exam.objects.filter(
            is_active=True,
            course__enrollments__student=request.user,
            course__enrollments__status__in=['active', 'completed'],
        ).distinct(),
        slug=slug,
    )
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
@student_required
def get_exam_data(request, slug):
    exam     = get_object_or_404(
        Exam.objects.filter(
            is_active=True,
            course__enrollments__student=request.user,
            course__enrollments__status__in=['active', 'completed'],
        ).distinct(),
        slug=slug,
    )
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

    response = get_object_or_404(
        StudentExamResponse.objects.select_related('exam'),
        exam__slug=slug, student=request.user,
    )

    if response.status not in (
        StudentExamResponse.INSTRUCTIONS, StudentExamResponse.IN_PROGRESS
    ):
        return JsonResponse({'error': 'Exam not in progress'}, status=400)

    # Server-authoritative deadline — the client's own countdown timer (which
    # triggers the auto-submit) can be blocked, delayed, or tampered with, so
    # answer edits must also be rejected here once the exam has genuinely
    # ended, not just when the client believes it has.
    if timezone.now() >= response.exam.end_datetime:
        return JsonResponse({'error': 'The exam time window has ended.'}, status=400)

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
        # Always increment server-side, atomically — never trust the
        # client-supplied count. This field is shown to staff on the exam
        # integrity review page (management/exam_responses.html) as an
        # authoritative violation count, so a student's own browser must
        # never be able to set or suppress it directly.
        updated = (
            StudentExamResponse.objects
            .filter(exam__slug=slug, student=request.user)
            .update(tab_switch_count=F('tab_switch_count') + 1)
        )
        if not updated:
            logger.warning(
                'flag_tab_switch: no StudentExamResponse for user=%s exam_slug=%s',
                request.user.pk, slug,
            )
    except Exception:
        logger.exception(
            'flag_tab_switch failed for user=%s exam_slug=%s', request.user.pk, slug
        )
    # Deliberately always returns ok — the client (a student mid-exam) must
    # never learn whether server-side tracking succeeded or failed.
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

    if is_fully_graded:
        academic_course = exam.course.academic_course
        if academic_course:
            try:
                CourseGrade.recompute_for_student_course(request.user, academic_course)
            except Exception:
                logger.exception(
                    'Failed to recompute CourseGrade after exam submission for user=%s exam=%s',
                    request.user.pk, exam.pk,
                )

    return JsonResponse({
        'status':           'submitted',
        'score':            total_score,
        'score_percentage': score_pct,
        'passed':           response.passed,
        'pending_manual':   pending_manual,
        'fully_graded':     is_fully_graded,
    })