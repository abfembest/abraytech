import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg, Sum, Q, F
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import TruncDate, TruncMonth
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from eduweb.models import (
    LMSCourse, Lesson, LessonSection, Quiz, QuizQuestion,
    QuizAnswer, Assignment, AssignmentSubmission, Enrollment,
    Announcement, Review, Notification, Course, CourseGrade, ExamQuestion
)
from .forms import (
    CourseForm, CourseObjectivesForm, LessonForm, SectionForm,
    QuizForm, QuizQuestionForm, QuizAnswerForm, AssignmentForm,
    AnnouncementForm, InstructorProfileForm, InstructorSettingsForm, PasswordChangeForm, SupportTicketForm, ExamForm
)
from eduweb.decorators import instructor_required

from eduweb.models import (
    LMSCourse, Lesson, LessonSection, Quiz, QuizQuestion,
    QuizAnswer, Assignment, AssignmentSubmission, Enrollment,
    Announcement, Review, Notification,
    QuizAttempt, QuizResponse, Message, Discussion, DiscussionReply, Exam
)

# ── Notification helper ────────────────────────────────────────────────────
def _notify_instructor(instructor, title, message, notif_type='system', link=''):
    """
    Create a Notification for an instructor and prune old ones beyond 100.
    notif_type must be one of Notification.NOTIFICATION_TYPE_CHOICES keys.
    Silently fails so it never breaks the main action.
    """
    try:
        Notification.objects.create(
            user=instructor,
            notification_type=notif_type,
            title=title,
            message=message,
            link=link,
        )
        # Keep only the latest 100 notifications per instructor
        old_ids = (
            Notification.objects
            .filter(user=instructor)
            .order_by('-created_at')
            .values_list('id', flat=True)[100:]
        )
        if old_ids:
            Notification.objects.filter(id__in=list(old_ids)).delete()
    except Exception:
        pass

# ==================== DASHBOARD ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def dashboard(request):
    """Instructor dashboard with comprehensive statistics"""
    courses = LMSCourse.objects.filter(
        instructor=request.user
    ).annotate(
        enrollments_count=Count('enrollments')
    ).prefetch_related('enrollments')[:5]
    
    # Statistics
    total_courses = LMSCourse.objects.filter(
        instructor=request.user
    ).count()
    
    published_courses = LMSCourse.objects.filter(
        instructor=request.user,
        is_published=True
    ).count()
    
    total_students = Enrollment.objects.filter(
        course__instructor=request.user
    ).values('student').distinct().count()
    
    pending_submissions = AssignmentSubmission.objects.filter(
        assignment__lesson__course__instructor=request.user,
        status='submitted'
    ).count()
    
    # Recent enrollments
    recent_enrollments = Enrollment.objects.filter(
        course__instructor=request.user
    ).select_related(
        'student',
        'course'
    ).order_by('-enrolled_at')[:10]
    
    context = {
        'courses': courses,
        'total_courses': total_courses,
        'published_courses': published_courses,
        'total_students': total_students,
        'pending_submissions': pending_submissions,
        'recent_enrollments': recent_enrollments,
    }
    return render(request, 'instructor/dashboard.html', context)


# ==================== COURSE MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_list(request):
    """List all instructor courses with statistics"""
    courses = LMSCourse.objects.filter(
        instructor=request.user
    ).annotate(
        enrollment_count=Count('enrollments')
    ).order_by('-created_at')

    return render(request, 'instructor/course_list.html', {
        'courses': courses,
    })

@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_manage_default(request):
    """
    Redirects to course_manage for the first course the instructor owns.
    Used by sidebar links so no pre-selected course is ever needed.
    """
    tab = request.GET.get('tab', 'overview')
    first_course = LMSCourse.objects.filter(instructor=request.user).order_by('title').first()
    if first_course:
        return redirect(f"{reverse('instructor:course_manage', kwargs={'slug': first_course.slug})}?tab={tab}")
    # No courses yet — send to course list with a helpful message
    messages.info(request, "No courses have been assigned to you yet. Please contact the administration.")
    return redirect('instructor:course_list')


@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_manage(request, slug=None):
    """
    Single unified page that consolidates:
      - Overview / Edit Course     (tab: overview)
      - Content / Lessons+Sections (tab: content)
      - Assessments: Quiz, Assignment, Exam  (tab: assessments)
      - Students                   (tab: students)
      - Announcements              (tab: announcements)
      - Discussions                (tab: discussions)

    All forms POST to their existing dedicated URLs — this view only
    serves the GET and passes all the data needed to render every tab.
    """
    # Support ?course=<id> switcher from the dropdown on the manage page
    course_id = request.GET.get('course')
    if course_id:
        course = get_object_or_404(LMSCourse, id=course_id, instructor=request.user)
        return redirect('instructor:course_manage', slug=course.slug)

    course = get_object_or_404(LMSCourse, slug=slug, instructor=request.user)
    active_tab = request.GET.get('tab', 'overview')
 
    # ── All courses for the switcher dropdown ──────────────────────────────
    all_courses = LMSCourse.objects.filter(
        instructor=request.user
    ).order_by('title')
 
    # ── TAB: overview ─────────────────────────────────────────────────────
    course_form = CourseForm(instance=course)
 
    stats = {
        'total_students': course.enrollments.count(),
        'total_lessons':  course.lessons.count(),
        'total_sections': course.sections.count(),
    }
 
    # ── TAB: content ──────────────────────────────────────────────────────
    sections = course.sections.prefetch_related(
        'lessons'
    ).order_by('display_order')
 
    all_lessons  = course.lessons.all()
    video_count  = all_lessons.filter(lesson_type='video').count()
    quiz_count   = all_lessons.filter(lesson_type='quiz').count()
 
    # Inline lesson / section forms for modals
    lesson_form  = LessonForm(course=course)
    section_form = SectionForm()
 
    # ── TAB: assessments ──────────────────────────────────────────────────
    quiz_lessons = course.lessons.filter(
        lesson_type='quiz'
    ).prefetch_related(
        'quizzes__questions'
    ).order_by('display_order')
 
    assignment_lessons = course.lessons.filter(
        lesson_type='assignment'
    ).prefetch_related(
        'assignments__submissions'
    ).order_by('display_order')
 
    # Exams that belong to this course
    try:
        course_exams = Exam.objects.filter(
            course=course,
            created_by=request.user
        ).order_by('-created_at')
    except Exception:
        course_exams = Exam.objects.filter(
            created_by=request.user
        ).order_by('-created_at')[:10]
 
    # Flat list of quiz-lesson slugs for the legacy "Manage Quizzes" button
    lessons_for_quiz = list(quiz_lessons)
 
    # Blank forms for modals
    quiz_form       = QuizForm()
    assignment_form_modal = AssignmentForm()
 
    # ── TAB: students ─────────────────────────────────────────────────────
    enrollments = course.enrollments.select_related(
        'student'
    ).order_by('-enrolled_at')
 
    enrollments_count           = enrollments.count()
    active_enrollments_count    = enrollments.filter(status='active').count()
    completed_enrollments_count = enrollments.filter(status='completed').count()
    pending_submissions_count   = AssignmentSubmission.objects.filter(
        assignment__lesson__course=course,
        status='submitted'
    ).count()
 
    # Students NOT yet enrolled — only users with role='student'
    enrolled_ids = enrollments.values_list('student_id', flat=True)
    available_students = User.objects.filter(
        is_active=True,
        profile__role='student'
    ).exclude(
        id__in=enrolled_ids
    ).order_by('first_name', 'last_name')
 
    # ── TAB: announcements ────────────────────────────────────────────────
    announcements = Announcement.objects.filter(
        course=course
    ).order_by('-publish_date')
 
    announcement_form = AnnouncementForm()
 
    # ── TAB: discussions ──────────────────────────────────────────────────
    discussions_qs = Discussion.objects.filter(
        course=course
    ).select_related('author').prefetch_related(
        'replies'
    ).order_by('-is_pinned', '-created_at')
 
    discussions_count = discussions_qs.count()
 
    # ── Today's date for enrol-student modal default ───────────────────────
    from datetime import date
    today = date.today().isoformat()
 
    context = {
        # navigation / switcher
        'course':       course,
        'all_courses':  all_courses,
        'active_tab':   active_tab,
 
        # overview
        'course_form': course_form,
        'stats':       stats,
 
        # content
        'sections':     sections,
        'video_count':  video_count,
        'quiz_count':   quiz_count,
        'lesson_form':  lesson_form,
        'section_form': section_form,
 
        # assessments
        'quiz_lessons':        quiz_lessons,
        'assignment_lessons':  assignment_lessons,
        'course_exams':        course_exams,
        'lessons_for_quiz':    lessons_for_quiz,
        'quiz_form':           quiz_form,
        'assignment_form_modal': assignment_form_modal,
 
        # students
        'enrollments':                  enrollments,
        'enrollments_count':            enrollments_count,
        'active_enrollments_count':     active_enrollments_count,
        'completed_enrollments_count':  completed_enrollments_count,
        'pending_submissions_count':    pending_submissions_count,
        'available_students':           available_students,
        'today':                        today,
 
        # announcements
        'announcements':    announcements,
        'announcement_form': announcement_form,
 
        # discussions
        'discussions':       discussions_qs,
        'discussions_count': discussions_count,
    }
 
    return render(request, 'instructor/course_manage.html', context)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_create(request):
    """Course creation is reserved for admins only."""
    messages.error(request, "Courses are created and assigned by the administration. Contact an admin to have a course assigned to you.")
    return redirect('instructor:course_list')


@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_edit(request, slug):
    """Edit course using slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        form = CourseForm(
            request.POST,
            request.FILES,
            instance=course
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Course "{course.title}" updated successfully!'
            )
            # If the POST came from the manage page, go back there
            next_url = request.POST.get('next') or request.META.get('HTTP_REFERER', '')
            if 'manage' in next_url:
                return redirect(f"{reverse('instructor:course_manage', kwargs={'slug': course.slug})}?tab=overview")
            return redirect('instructor:course_edit', slug=course.slug)
    else:
        form = CourseForm(instance=course)
    
    # Course statistics
    stats = {
        'total_students': course.enrollments.count(),
        'total_lessons': course.lessons.count(),
        'total_sections': course.sections.count(),
    }
    
    return render(request, 'instructor/course_form.html', {
        'form': form,
        'course': course,
        'stats': stats,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_objectives(request, slug):
    """Manage course objectives using slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        form = CourseObjectivesForm(request.POST, instance=course)
        if form.is_valid():
            # Process objectives
            objectives_text = form.cleaned_data.get('objectives', '')
            prerequisites_text = form.cleaned_data.get('prerequisites', '')
            
            # Split and filter empty lines
            course.learning_objectives = [
                obj.strip()
                for obj in objectives_text.split('\n')
                if obj.strip()
            ]
            course.prerequisites = [
                req.strip()
                for req in prerequisites_text.split('\n')
                if req.strip()
            ]
            course.save()
            
            messages.success(request, 'Learning objectives updated!')
            return redirect('instructor:course_edit', slug=course.slug)
    else:
        initial = {
            'objectives': '\n'.join(course.learning_objectives or []),
            'prerequisites': '\n'.join(course.prerequisites or []),
        }
        form = CourseObjectivesForm(initial=initial)
    
    return render(request, 'instructor/course_objectives.html', {
        'form': form,
        'course': course,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_delete(request, slug):
    """Course deletion is not permitted for instructors."""
    raise PermissionDenied


# ==================== SECTION MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def section_create(request, course_slug):
    """Create section using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        form = SectionForm(request.POST)
        if form.is_valid():
            section = form.save(commit=False)
            section.course = course
            section.save()
            messages.success(request, 'Section created successfully!')
            return redirect(
                'instructor:lesson_list',
                course_slug=course.slug
            )
    else:
        form = SectionForm()
    
    return render(request, 'instructor/section_form.html', {
        'form': form,
        'course': course,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def section_edit(request, course_slug, section_id):
    """Edit section using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    section = get_object_or_404(
        LessonSection,
        id=section_id,
        course=course
    )
    
    if request.method == 'POST':
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            form.save()
            messages.success(request, 'Section updated successfully!')
            return redirect(
                'instructor:lesson_list',
                course_slug=course.slug
            )
    else:
        form = SectionForm(instance=section)
    
    return render(request, 'instructor/section_form.html', {
        'form': form,
        'course': course,
        'section': section,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def section_delete(request, course_slug, section_id):
    """Delete section using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    section = get_object_or_404(
        LessonSection,
        id=section_id,
        course=course
    )
    
    section_title = section.title
    section.delete()
    messages.success(request, f'Section "{section_title}" deleted successfully!')
    return redirect('instructor:lesson_list', course_slug=course.slug)


# ==================== LESSON MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def lesson_list(request, course_slug):
    """List lessons using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    sections = course.sections.all().prefetch_related(
        'lessons'
    ).order_by('display_order')
    
    # Get lesson type counts
    all_lessons = course.lessons.all()
    video_count = all_lessons.filter(lesson_type='video').count()
    quiz_count = all_lessons.filter(lesson_type='quiz').count()
    
    context = {
        'course': course,
        'sections': sections,
        'video_count': video_count,
        'quiz_count': quiz_count,
    }
    
    return render(request, 'instructor/lesson_list.html', context)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def lesson_create(request, course_slug):
    """Create lesson using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, course=course)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.course = course
            lesson.save()
            messages.success(request, 'Lesson created successfully!')
            # Notify enrolled students about new lesson content
            if lesson.is_active:
                enrolled = Enrollment.objects.filter(
                    course=course, status='active'
                ).select_related('student')
                for enrollment in enrolled:
                    _notify_instructor(
                        instructor=enrollment.student,
                        title=f'New Lesson: {lesson.title}',
                        message=f'A new lesson "{lesson.title}" is now available in "{course.title}".',
                        notif_type='announcement',
                        link=f'/courses/{course.slug}/',
                    )
            return redirect(
                'instructor:lesson_list',
                course_slug=course.slug
            )
    else:
        form = LessonForm(course=course)
    
    return render(request, 'instructor/lesson_form.html', {
        'form': form,
        'course': course,
        'lesson': None,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def lesson_edit(request, course_slug, lesson_slug):
    """Edit lesson using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    if request.method == 'POST':
        form = LessonForm(
            request.POST,
            request.FILES,
            instance=lesson,
            course=course
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Lesson updated successfully!')
            return redirect(
                'instructor:lesson_list',
                course_slug=course.slug
            )
    else:
        form = LessonForm(instance=lesson, course=course)
    
    return render(request, 'instructor/lesson_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def lesson_delete(request, course_slug, lesson_slug):
    """Delete lesson using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    lesson_title = lesson.title
    lesson.delete()
    messages.success(request, f'Lesson "{lesson_title}" deleted successfully!')
    return redirect('instructor:lesson_list', course_slug=course.slug)


# ==================== QUIZ MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_list(request, course_slug, lesson_slug):
    """List quizzes using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    quizzes = lesson.quizzes.all().prefetch_related(
        'questions'
    ).order_by('display_order')
    
    return render(request, 'instructor/quiz_list.html', {
        'course': course,
        'lesson': lesson,
        'quizzes': quizzes,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_create(request, course_slug, lesson_slug):
    """Create quiz using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    if request.method == 'POST':
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.lesson = lesson
            quiz.save()
            messages.success(request, 'Quiz created successfully!')
            # Notify enrolled students about the new quiz
            enrolled = Enrollment.objects.filter(
                course=course, status='active'
            ).select_related('student')
            for enrollment in enrolled:
                _notify_instructor(
                    instructor=enrollment.student,
                    title=f'New Quiz: {quiz.title}',
                    message=f'A new quiz "{quiz.title}" has been added to "{course.title}" in the lesson "{lesson.title}".',
                    notif_type='quiz',
                    link=f'/courses/{course.slug}/',
                )
            return redirect(
                'instructor:quiz_questions',
                course_slug=course.slug,
                lesson_slug=lesson.slug,
                quiz_slug=quiz.slug
            )
    else:
        form = QuizForm()
    
    return render(request, 'instructor/quiz_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'quiz': None,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_edit(request, course_slug, lesson_slug, quiz_slug):
    """Edit quiz using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    quiz = get_object_or_404(
        Quiz,
        slug=quiz_slug,
        lesson=lesson
    )
    
    if request.method == 'POST':
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, 'Quiz updated successfully!')
            return redirect(
                'instructor:quiz_questions',
                course_slug=course.slug,
                lesson_slug=lesson.slug,
                quiz_slug=quiz.slug
            )
    else:
        form = QuizForm(instance=quiz)
    
    return render(request, 'instructor/quiz_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'quiz': quiz,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_questions(request, course_slug, lesson_slug, quiz_slug):
    """Manage quiz questions using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    quiz = get_object_or_404(
        Quiz,
        slug=quiz_slug,
        lesson=lesson
    )
    
    questions = quiz.questions.all().prefetch_related(
        'answers'
    ).order_by('display_order')
    
    return render(request, 'instructor/quiz.html', {
        'course': course,
        'lesson': lesson,
        'quiz': quiz,
        'questions': questions,
    })


# ==================== QUESTION MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def question_create(request, course_slug, lesson_slug, quiz_slug):
    """Create question using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    quiz = get_object_or_404(
        Quiz,
        slug=quiz_slug,
        lesson=lesson
    )
    
    if request.method == 'POST':
        form = QuizQuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.quiz = quiz
            question.save()
            messages.success(request, 'Question created successfully!')
            
            if question.question_type == 'multiple_choice':
                return redirect(
                    'instructor:question_answers',
                    course_slug=course.slug,
                    lesson_slug=lesson.slug,
                    quiz_slug=quiz.slug,
                    question_id=question.id
                )
            return redirect(
                'instructor:quiz_questions',
                course_slug=course.slug,
                lesson_slug=lesson.slug,
                quiz_slug=quiz.slug
            )
    else:
        form = QuizQuestionForm()
    
    return render(request, 'instructor/question_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'quiz': quiz,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def question_answers(request, course_slug, lesson_slug, quiz_slug, question_id):
    """Manage question answers using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    quiz = get_object_or_404(
        Quiz,
        slug=quiz_slug,
        lesson=lesson
    )
    question = get_object_or_404(
        QuizQuestion,
        id=question_id,
        quiz=quiz
    )
    
    if request.method == 'POST':
        form = QuizAnswerForm(request.POST)
        if form.is_valid():
            answer = form.save(commit=False)
            answer.question = question
            answer.save()
            messages.success(request, 'Answer added successfully!')
            return redirect(
                'instructor:question_answers',
                course_slug=course.slug,
                lesson_slug=lesson.slug,
                quiz_slug=quiz.slug,
                question_id=question.id
            )
    else:
        form = QuizAnswerForm()
    
    answers = question.answers.all().order_by('display_order')
    
    return render(request, 'instructor/answer_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'quiz': quiz,
        'question': question,
        'answers': answers,
    })

# ==================== ASSIGNMENT MANAGEMENT ====================
# ==================== ASSIGNMENT MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def assignment_list(request, course_slug, lesson_slug):
    """List assignments using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    assignments = lesson.assignments.all().order_by('display_order')
    
    return render(request, 'instructor/assignments.html', {
        'course': course,
        'lesson': lesson,
        'assignments': assignments,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def assignment_create(request, course_slug, lesson_slug):
    """Create assignment using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.lesson = lesson
            assignment.save()
            messages.success(request, 'Assignment created successfully!')
            # Notify enrolled students about the new assignment
            enrolled = Enrollment.objects.filter(
                course=course, status='active'
            ).select_related('student')
            for enrollment in enrolled:
                _notify_instructor(
                    instructor=enrollment.student,
                    title=f'New Assignment: {assignment.title}',
                    message=f'A new assignment "{assignment.title}" has been posted in "{course.title}". '
                            f'Due: {assignment.due_date.strftime("%b %d, %Y") if assignment.due_date else "No deadline"}.',
                    notif_type='assignment',
                    link=f'/courses/{course.slug}/',
                )
            return redirect(
                'instructor:assignment_list',
                course_slug=course.slug,
                lesson_slug=lesson.slug
            )
    else:
        form = AssignmentForm()
    
    return render(request, 'instructor/assignment_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'assignment': None,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def assignment_edit(request, course_slug, lesson_slug, assignment_slug):
    """Edit assignment using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    lesson = get_object_or_404(
        Lesson,
        slug=lesson_slug,
        course=course
    )
    assignment = get_object_or_404(
        Assignment,
        slug=assignment_slug,
        lesson=lesson
    )
    
    if request.method == 'POST':
        form = AssignmentForm(
            request.POST,
            request.FILES,
            instance=assignment
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Assignment updated successfully!')
            return redirect(
                'instructor:assignment_list',
                course_slug=course.slug,
                lesson_slug=lesson.slug
            )
    else:
        form = AssignmentForm(instance=assignment)
    
    return render(request, 'instructor/assignment_form.html', {
        'form': form,
        'course': course,
        'lesson': lesson,
        'assignment': assignment,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def assignment_submissions(request, course_slug, assignment_slug):
    """View submissions using slugs"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    assignment = get_object_or_404(
        Assignment,
        slug=assignment_slug,
        lesson__course=course
    )
    
    submissions = assignment.submissions.all().select_related(
        'student'
    ).order_by('-submitted_at')
    
    pending_count = submissions.filter(status='submitted').count()
    graded_count = submissions.filter(status='graded').count()
    late_count = submissions.filter(is_late=True).count()

    return render(request, 'instructor/assignment_submissions.html', {
        'course': course,
        'assignment': assignment,
        'submissions': submissions,
        'pending_count': pending_count,
        'graded_count': graded_count,
        'late_count': late_count,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def grade_submission(request, course_slug, submission_id):
    """Grade submission using course slug and submission ID"""
    # Get the submission first
    submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    
    # Get assignment from the submission
    assignment = submission.assignment
    
    # Verify course ownership
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    # Verify the assignment belongs to this course
    if assignment.lesson.course != course:
        raise PermissionDenied("This submission does not belong to your course.")
    
    if request.method == 'POST':
        score = request.POST.get('score')
        feedback = request.POST.get('feedback', '')
        
        submission.score = score
        submission.feedback = feedback
        submission.status = 'graded'
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        
        messages.success(request, 'Submission graded successfully!')
        # Notify the student that their submission was graded
        _notify_instructor(
            instructor=submission.student,
            title='Assignment Graded',
            message=f'Your submission for "{assignment.title}" in "{course.title}" has been graded. Score: {submission.score}.',
            notif_type='grade',
            link=f'/student/courses/{course.slug}/assignments/{assignment.slug}/',
        )
        from eduweb.emailservices import send_assignment_graded_email
        send_assignment_graded_email(submission.student, submission)
        return redirect(
            'instructor:assignment_submissions',
            course_slug=course.slug,
            assignment_slug=assignment.slug
        )
    
    return render(request, 'instructor/grade_submission.html', {
        'course': course,
        'assignment': assignment,
        'submission': submission,
    })


# ==================== STUDENT MANAGEMENT ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def students_list(request, course_slug):
    """List students using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    enrollments = course.enrollments.all().select_related(
        'student'
    ).order_by('-enrolled_at')
    
    return render(request, 'instructor/students.html', {
        'course': course,
        'enrollments': enrollments,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def student_progress(request, course_slug, student_id):
    """View student progress using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    enrollment = get_object_or_404(
        Enrollment,
        course=course,
        student_id=student_id
    )
    
    lesson_progress = enrollment.lesson_progress.all().select_related(
        'lesson'
    ).order_by('lesson__display_order')
    
    return render(request, 'instructor/student_detail_progress.html', {
        'course': course,
        'enrollment': enrollment,
        'lesson_progress': lesson_progress,
    })

@login_required(login_url='eduweb:auth_page')
@instructor_required
def enroll_student(request, course_slug):
    """Manually enroll a student in a course"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        enrollment_date = request.POST.get('enrollment_date')
        send_welcome = request.POST.get('send_welcome_email') == 'on'
        
        try:
            student = User.objects.get(id=student_id, profile__role='student', is_active=True)
            
            # Check if already enrolled
            if Enrollment.objects.filter(
                course=course,
                student=student
            ).exists():
                messages.warning(
                    request,
                    f'{student.get_full_name()} is already enrolled in this course.'
                )
            else:
                # Create enrollment
                from datetime import datetime
                parsed_date = None
                if enrollment_date:
                    try:
                        parsed_date = datetime.strptime(enrollment_date, '%Y-%m-%d')
                    except (ValueError, TypeError):
                        parsed_date = None
                enrollment = Enrollment.objects.create(
                    course=course,
                    student=student,
                    enrolled_at=parsed_date or timezone.now(),
                    status='active'
                )
                
                # Send welcome email if requested
                if send_welcome:
                    # TODO: Implement email sending functionality
                    pass
                
                messages.success(
                    request,
                    f'{student.get_full_name()} has been successfully enrolled in {course.title}!'
                )
                _notify_instructor(
                    instructor=request.user,
                    title='Student Enrolled',
                    message=f'{student.get_full_name() or student.username} was manually enrolled in "{course.title}".',
                    notif_type='enrollment',
                    link=f'/instructor/courses/{course.slug}/students/',
                )
                # Also notify the student they have been enrolled
                _notify_instructor(
                    instructor=student,
                    title=f'Enrolled in {course.title}',
                    message=f'You have been enrolled in "{course.title}". You can start learning now.',
                    notif_type='enrollment',
                    link=f'/courses/{course.slug}/',
                )
        except User.DoesNotExist:
            messages.error(request, 'Student not found.')
    
    return redirect('instructor:students_list', course_slug=course.slug)

# ==================== ANNOUNCEMENTS ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def announcement_create(request, course_slug):
    """Create announcement using course slug"""
    course = get_object_or_404(
        LMSCourse,
        slug=course_slug,
        instructor=request.user
    )
    
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.course = course
            announcement.announcement_type = 'course'
            announcement.created_by = request.user
            announcement.save()
            messages.success(request, 'Announcement created successfully!')
            # Notify all enrolled students about the new announcement
            enrolled_students = Enrollment.objects.filter(
                course=course, status='active'
            ).select_related('student')
            for enrollment in enrolled_students:
                _notify_instructor(
                    instructor=enrollment.student,
                    title=f'New Announcement: {announcement.title}',
                    message=f'Your instructor posted a new announcement in "{course.title}".',
                    notif_type='announcement',
                    link=f'/courses/{course.slug}/',
                )
            # Also notify the instructor themselves (confirmation)
            _notify_instructor(
                instructor=request.user,
                title='Announcement Published',
                message=f'Your announcement "{announcement.title}" was published to "{course.title}".',
                notif_type='announcement',
                link=f'/instructor/courses/{course.slug}/announcements/',
            )
            return redirect('instructor:course_edit', slug=course.slug)
    else:
        form = AnnouncementForm()
    
    return render(request, 'instructor/announcement_form.html', {
        'form': form,
        'course': course,
    })

# ==================== ASSESSMENT OVERVIEW VIEWS ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def all_quizzes(request):
    """View all quizzes across all instructor's courses"""
    courses = LMSCourse.objects.filter(instructor=request.user)
    quizzes = Quiz.objects.filter(
        lesson__course__in=courses
    ).select_related(
        'lesson',
        'lesson__course'
    ).prefetch_related('questions').order_by('-created_at')
    
    context = {
        'quizzes': quizzes,
    }
    return render(request, 'instructor/all_quizzes.html', context)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def all_assignments(request):
    """View all assignments across all instructor's courses"""
    courses = LMSCourse.objects.filter(instructor=request.user)
    assignments = Assignment.objects.filter(
        lesson__course__in=courses
    ).select_related(
        'lesson',
        'lesson__course'
    ).order_by('-created_at')
    
    context = {
        'assignments': assignments,
    }
    return render(request, 'instructor/all_assignments.html', context)

@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def delete_answer(request, course_slug, lesson_slug, quiz_slug, question_id, answer_id):
    """Delete a quiz answer"""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    lesson = get_object_or_404(Lesson, slug=lesson_slug, course=course)
    quiz = get_object_or_404(Quiz, slug=quiz_slug, lesson=lesson)
    question = get_object_or_404(QuizQuestion, id=question_id, quiz=quiz)
    answer = get_object_or_404(QuizAnswer, id=answer_id, question=question)
    
    answer.delete()
    messages.success(request, 'Answer deleted successfully!')
    
    return redirect('instructor:question_answers', 
                    course_slug=course.slug, 
                    lesson_slug=lesson.slug, 
                    quiz_slug=quiz.slug, 
                    question_id=question.id)

@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def delete_question(request, course_slug, lesson_slug, quiz_slug, question_id):
    """Delete a quiz question"""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    lesson = get_object_or_404(Lesson, slug=lesson_slug, course=course)
    quiz = get_object_or_404(Quiz, slug=quiz_slug, lesson=lesson)
    question = get_object_or_404(QuizQuestion, id=question_id, quiz=quiz)
    
    question.delete()
    messages.success(request, 'Question deleted successfully!')
    
    return redirect('instructor:quiz_questions', 
                    course_slug=course.slug, 
                    lesson_slug=lesson.slug, 
                    quiz_slug=quiz.slug)

@login_required(login_url='eduweb:auth_page')
@instructor_required
def course_statistics(request):
    """
    Course statistics overview
    Shows enrollment trends, completion rates, and performance metrics
    """
    courses = LMSCourse.objects.filter(
        instructor=request.user
    ).annotate(
        enrollment_count=Count('enrollments'),
        avg_rating=Avg('reviews__rating'),
        completion_count=Count(
            'enrollments',
            filter=Q(enrollments__status='completed')
        )
    ).order_by('-created_at')
    
    # Overall statistics
    total_enrollments = Enrollment.objects.filter(
        course__instructor=request.user
    ).count()
    
    active_students = Enrollment.objects.filter(
        course__instructor=request.user,
        status='active'
    ).count()
    
    completed_courses = Enrollment.objects.filter(
        course__instructor=request.user,
        status='completed'
    ).count()
    
    avg_course_rating = Review.objects.filter(
        course__instructor=request.user,
        is_approved=True
    ).aggregate(Avg('rating'))['rating__avg'] or 0
    
    # Enrollment trends (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_enrollments = Enrollment.objects.filter(
        course__instructor=request.user,
        enrolled_at__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('enrolled_at')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Convert to list for JSON serialization
    enrollment_data = []
    for item in daily_enrollments:
        enrollment_data.append({
            'date': item['date'].isoformat(),
            'count': item['count']
        })
    
    context = {
        'courses': courses,
        'total_enrollments': total_enrollments,
        'active_students': active_students,
        'completed_courses': completed_courses,
        'avg_course_rating': round(avg_course_rating, 1),
        'daily_enrollments': json.dumps(enrollment_data),
    }
    
    return render(
        request, 
        'instructor/analytics/course_statistics.html', 
        context
    )


@login_required(login_url='eduweb:auth_page')
@instructor_required
def student_analytics_progress(request):
    """
    Student progress tracking
    Shows individual student performance across all courses
    """
    # Get all courses taught by instructor
    instructor_courses = LMSCourse.objects.filter(
        instructor=request.user
    )
    
    # Filter by course if specified
    course_id = request.GET.get('course')
    if course_id:
        enrollments = Enrollment.objects.filter(
            course_id=course_id,
            course__instructor=request.user
        )
        selected_course = get_object_or_404(
            LMSCourse, 
            id=course_id, 
            instructor=request.user
        )
    else:
        enrollments = Enrollment.objects.filter(
            course__instructor=request.user
        )
        selected_course = None
    
    # Get enrollments with related data
    enrollments = enrollments.select_related(
        'student', 
        'course'
    ).annotate(
        total_lessons=Count('course__lessons', distinct=True),
        avg_quiz_score=Avg(
            'student__quiz_attempts__percentage',
            filter=Q(student__quiz_attempts__quiz__lesson__course=F('course'))
        )
    ).order_by('-enrolled_at')
    
    # Student performance summary
    total_students = enrollments.count()
    struggling_students = enrollments.filter(
        progress_percentage__lt=30
    ).count()
    high_performers = enrollments.filter(
        progress_percentage__gte=80
    ).count()
    
    context = {
        'enrollments': enrollments,
        'courses': instructor_courses,
        'selected_course': selected_course,
        'total_students': total_students,
        'struggling_students': struggling_students,
        'high_performers': high_performers,
    }
    
    return render(
        request, 
        'instructor/analytics/student_progress.html', 
        context
    )


@login_required(login_url='eduweb:auth_page')
@instructor_required
def reviews_ratings(request):
    """
    Course reviews and ratings analysis
    Shows detailed feedback and rating trends
    """
    # Get all reviews for instructor's courses
    reviews = Review.objects.filter(
        course__instructor=request.user,
        is_approved=True
    ).select_related(
        'student', 
        'course'
    ).order_by('-created_at')
    
    # Filter by course if specified
    course_id = request.GET.get('course')
    if course_id:
        reviews = reviews.filter(course_id=course_id)
        selected_course = get_object_or_404(
            LMSCourse, 
            id=course_id, 
            instructor=request.user
        )
    else:
        selected_course = None
    
    # Rating statistics
    total_reviews = reviews.count()
    avg_rating = reviews.aggregate(
        Avg('rating')
    )['rating__avg'] or 0
    
    # Rating distribution
    rating_distribution = {
        5: reviews.filter(rating=5).count(),
        4: reviews.filter(rating=4).count(),
        3: reviews.filter(rating=3).count(),
        2: reviews.filter(rating=2).count(),
        1: reviews.filter(rating=1).count(),
    }
    
    # Course breakdown
    course_ratings = LMSCourse.objects.filter(
        instructor=request.user
    ).annotate(
        review_count=Count('reviews', filter=Q(reviews__is_approved=True)),
        avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True))
    ).filter(
        review_count__gt=0
    ).order_by('-avg_rating')
    
    # Monthly trend (last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_reviews = reviews.filter(
        created_at__gte=six_months_ago
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        count=Count('id'),
        avg=Avg('rating')
    ).order_by('month')
    
    # Convert to list for JSON serialization
    monthly_data = []
    for item in monthly_reviews:
        monthly_data.append({
            'month': item['month'].isoformat(),
            'count': item['count'],
            'avg': float(item['avg'])
        })
    
    context = {
        'reviews': reviews[:50],  # Limit to recent 50
        'courses': LMSCourse.objects.filter(
            instructor=request.user
        ),
        'selected_course': selected_course,
        'total_reviews': total_reviews,
        'avg_rating': round(avg_rating, 1),
        'rating_distribution': rating_distribution,
        'course_ratings': course_ratings,
        'monthly_reviews': json.dumps(monthly_data),
    }
    
    return render(
        request, 
        'instructor/analytics/reviews_ratings.html', 
        context
    )

@login_required(login_url='eduweb:auth_page')
@instructor_required
def resources(request):
    """
    Pool and display all resources from courses assigned to this instructor
    that already have content (lessons) created for them.
    Supports tab-based pagination via ?videos_page=, ?docs_page=, ?assignments_page=
    """
    import re

    ITEMS_PER_PAGE = 10

    # Only courses assigned to this instructor that have at least one lesson
    instructor_courses = LMSCourse.objects.filter(
        instructor=request.user
    ).prefetch_related(
        'lessons',
        'lessons__assignments'
    ).annotate(
        lesson_count=Count('lessons')
    ).filter(
        lesson_count__gt=0          # only courses with content created
    )

    def extract_youtube_url(raw):
        if raw.strip().startswith('http'):
            raw = raw.strip()
            match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', raw)
            if match:
                return f'https://www.youtube.com/watch?v={match.group(1)}'
            return raw
        match = re.search(r'src=["\']([^"\']+)["\']', raw)
        if match:
            src = match.group(1)
            vid_match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', src)
            if vid_match:
                return f'https://www.youtube.com/watch?v={vid_match.group(1)}'
            return src
        return None

    lesson_videos = []
    lesson_docs = []
    assignment_files = []

    for course in instructor_courses:
        for lesson in course.lessons.all():
            if lesson.video_url:
                clean_url = extract_youtube_url(lesson.video_url)
                if clean_url:
                    lesson_videos.append({
                        'course': course,
                        'lesson': lesson,
                        'url': clean_url,
                        'type': 'video',
                        'uploaded': lesson.created_at,
                    })
            if lesson.file:
                lesson_docs.append({
                    'course': course,
                    'lesson': lesson,
                    'file': lesson.file,
                    'name': lesson.file.name.split('/')[-1],
                    'type': 'document',
                    'uploaded': lesson.created_at,
                })
            for assignment in lesson.assignments.all():
                if assignment.attachment:
                    assignment_files.append({
                        'course': course,
                        'lesson': lesson,
                        'assignment': assignment,
                        'file': assignment.attachment,
                        'name': assignment.attachment.name.split('/')[-1],
                        'type': 'assignment',
                        'uploaded': assignment.created_at,
                    })

    # ── Pagination per tab ────────────────────────────────────────────────
    def paginate(items, page_param):
        paginator = Paginator(items, ITEMS_PER_PAGE)
        page_num  = request.GET.get(page_param, 1)
        return paginator.get_page(page_num)

    videos_page      = paginate(lesson_videos,     'videos_page')
    docs_page        = paginate(lesson_docs,        'docs_page')
    assignments_page = paginate(assignment_files,   'assignments_page')

    stats = {
        'total_videos':      len(lesson_videos),
        'total_docs':        len(lesson_docs),
        'total_assignments': len(assignment_files),
        'total_courses':     instructor_courses.count(),
    }

    context = {
        'lesson_videos':     videos_page,
        'lesson_docs':       docs_page,
        'assignment_files':  assignments_page,
        'stats':             stats,
        'courses':           instructor_courses,
    }

    return render(request, 'instructor/resources.html', context)

# ==================== PROFILE VIEW ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def instructor_profile(request):
    """View and edit instructor profile"""
    
    # Get instructor statistics
    total_courses = LMSCourse.objects.filter(
        instructor=request.user
    ).count()
    
    total_students = Enrollment.objects.filter(
        course__instructor=request.user
    ).values('student').distinct().count()
    
    avg_rating = LMSCourse.objects.filter(
        instructor=request.user
    ).aggregate(avg_rating=Avg('average_rating'))['avg_rating'] or 0
    
    total_reviews = LMSCourse.objects.filter(
        instructor=request.user
    ).aggregate(
        total=Count('reviews')
    )['total']
    
    if request.method == 'POST':
        form = InstructorProfileForm(
            request.POST,
            request.FILES,
            instance=request.user.profile,
            user=request.user
        )
        
        if form.is_valid():
            # Update User model fields
            user = request.user
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            
            # Update Profile model fields
            form.save()
            
            messages.success(
                request,
                'Your profile has been updated successfully!'
            )
            return redirect('instructor:profile')
    else:
        form = InstructorProfileForm(
            instance=request.user.profile,
            user=request.user
        )
    
    context = {
        'form': form,
        'page_title': 'My Profile',
        'total_courses': total_courses,
        'total_students': total_students,
        'avg_rating': round(avg_rating, 1),
        'total_reviews': total_reviews,
    }
    return render(request, 'instructor/profile.html', context)


# ==================== SETTINGS VIEW ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def instructor_settings(request):
    """Manage instructor account settings"""
    
    settings_form = InstructorSettingsForm(
        instance=request.user.profile
    )
    password_form = PasswordChangeForm(user=request.user)
    
    if request.method == 'POST':
        if 'update_settings' in request.POST:
            settings_form = InstructorSettingsForm(
                request.POST,
                instance=request.user.profile
            )
            
            if settings_form.is_valid():
                settings_form.save()
                messages.success(
                    request,
                    'Settings updated successfully!'
                )
                return redirect('instructor:settings')
        
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(
                user=request.user,
                data=request.POST
            )
            
            if password_form.is_valid():
                # Change password
                new_password = password_form.cleaned_data['new_password']
                request.user.set_password(new_password)
                request.user.save()
                
                # Keep user logged in
                update_session_auth_hash(request, request.user)
                
                messages.success(
                    request,
                    'Your password has been changed successfully!'
                )
                return redirect('instructor:settings')
    
    context = {
        'settings_form': settings_form,
        'password_form': password_form,
        'page_title': 'Settings',
    }
    return render(request, 'instructor/settings.html', context)


# ==================== HELP & SUPPORT VIEW ====================
@login_required(login_url='eduweb:auth_page')
@instructor_required
def help_support(request):
    """Help and support page with FAQs and ticket submission"""
    
    if request.method == 'POST':
        form = SupportTicketForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Send email to support team
            subject = f"[{form.cleaned_data['priority'].upper()}] {form.cleaned_data['subject']}"
            message = f"""
New Support Ticket from Instructor

From: {request.user.get_full_name()} ({request.user.email})
Category: {form.cleaned_data['category']}
Priority: {form.cleaned_data['priority']}

Message:
{form.cleaned_data['message']}

---
User ID: {request.user.id}
Role: Instructor
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
                    'Your support ticket has been submitted successfully! '
                    'Our team will get back to you within 24-48 hours.'
                )
                _notify_instructor(
                    instructor=request.user,
                    title='Support Ticket Submitted',
                    message=f'Your ticket "{form.cleaned_data["subject"]}" has been received. We will respond within 24-48 hours.',
                    notif_type='system',
                    link='/instructor/help-support/',
                )
                return redirect('instructor:help_support')
            
            except Exception as e:
                messages.error(
                    request,
                    'An error occurred while submitting your ticket. '
                    'Please try again later.'
                )
    else:
        form = SupportTicketForm()
    
    # FAQs data
    faqs = [
        {
            'question': 'How do I create a new course?',
            'answer': 'Navigate to Courses > Create Course from the sidebar menu. '
                     'Fill in the course details, upload a thumbnail, and click Save. '
                     'You can then add sections, lessons, and assessments.'
        },
        {
            'question': 'How do I upload course materials?',
            'answer': 'When creating or editing a lesson, you can upload videos, '
                     'documents, and other materials. Supported formats include '
                     'PDF, DOCX, MP4, and more.'
        },
        {
            'question': 'How do I grade student assignments?',
            'answer': 'Go to Assessments > All Assignments and click on any assignment. '
                     'You\'ll see all submissions. Click on a submission to view, '
                     'provide feedback, and assign a grade.'
        },
        {
            'question': 'Can I track student progress?',
            'answer': 'Yes! Go to Analytics > Student Progress to view detailed '
                     'reports on each student\'s performance, completion rates, '
                     'and engagement metrics.'
        },
        {
            'question': 'How do I communicate with students?',
            'answer': 'You can create announcements for your courses, respond to '
                     'discussion forum posts, and provide feedback on assignments. '
                     'Students can also message you directly.'
        },
        {
            'question': 'What payment methods are supported?',
            'answer': 'We support credit/debit cards, bank transfers, and various '
                     'mobile payment options. Payments are processed securely and '
                     'you receive monthly payouts.'
        },
        {
            'question': 'How do I issue certificates?',
            'answer': 'Certificates are automatically generated when students complete '
                     'all course requirements. You can customize certificate templates '
                     'in your course settings.'
        },
        {
            'question': 'What are the video upload limits?',
            'answer': 'Video files should not exceed 2GB per file. We recommend '
                     'using MP4 format at 1080p resolution for best quality and '
                     'compatibility.'
        },
    ]
    
    # Quick links
    quick_links = [
        {
            'title': 'Getting Started Guide',
            'icon': 'fa-book-open',
            'url': '#',
            'description': 'Learn the basics of creating and managing courses'
        },
        {
            'title': 'Video Tutorials',
            'icon': 'fa-video',
            'url': '#',
            'description': 'Watch step-by-step video guides'
        },
        {
            'title': 'Best Practices',
            'icon': 'fa-lightbulb',
            'url': '#',
            'description': 'Tips for creating engaging course content'
        },
        {
            'title': 'Community Forum',
            'icon': 'fa-users',
            'url': '#',
            'description': 'Connect with other instructors'
        },
    ]
    
    context = {
        'form': form,
        'faqs': faqs,
        'quick_links': quick_links,
        'page_title': 'Help & Support',
    }
    return render(request, 'instructor/help_support.html', context)

# ============================================================
# 1.  ANNOUNCEMENT LIST / EDIT / DELETE
# ============================================================

@login_required(login_url='eduweb:auth_page')
@instructor_required
def announcement_list(request, course_slug):
    """List all announcements for a course."""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    announcements_qs = course.announcements.all().order_by('-publish_date')

    paginator = Paginator(announcements_qs, 10)
    page = request.GET.get('page')
    announcements = paginator.get_page(page)

    return render(request, 'instructor/announcements_list.html', {
        'course': course,
        'announcements': announcements,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def announcement_edit(request, course_slug, announcement_slug):
    """Edit an existing announcement."""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    announcement = get_object_or_404(Announcement, slug=announcement_slug, course=course)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated successfully!')
            _notify_instructor(
                instructor=request.user,
                title='Announcement Updated',
                message=f'Your announcement "{announcement.title}" in "{course.title}" was updated.',
                notif_type='announcement',
                link=f'/instructor/courses/{course.slug}/announcements/',
            )
            return redirect('instructor:announcement_list', course_slug=course.slug)
    else:
        form = AnnouncementForm(instance=announcement)

    return render(request, 'instructor/announcement_form.html', {
        'form': form,
        'course': course,
        'announcement': announcement,
        'editing': True,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def announcement_delete(request, course_slug, announcement_slug):
    """Delete an announcement (POST only)."""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    announcement = get_object_or_404(Announcement, slug=announcement_slug, course=course)

    if request.method == 'POST':
        announcement.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('instructor:announcement_list', course_slug=course.slug)


# ============================================================
# 2.  QUIZ RESULTS — QuizAttempt + QuizResponse
# ============================================================

@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_results(request, course_slug, lesson_slug, quiz_slug):
    """Show all student attempts for a quiz."""
    from eduweb.models import Lesson, Quiz
    course  = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    lesson  = get_object_or_404(Lesson, slug=lesson_slug, course=course)
    quiz    = get_object_or_404(Quiz, slug=quiz_slug, lesson=lesson)

    attempts = QuizAttempt.objects.filter(
        quiz=quiz, is_completed=True
    ).select_related('student').order_by('-started_at')

    total_attempts = attempts.count()
    passed_count   = attempts.filter(passed=True).count()
    failed_count   = total_attempts - passed_count
    pass_rate      = (passed_count / total_attempts * 100) if total_attempts else 0
    avg_score      = attempts.aggregate(avg=Avg('percentage'))['avg'] or 0

    return render(request, 'instructor/quiz_results.html', {
        'course':        course,
        'lesson':        lesson,
        'quiz':          quiz,
        'attempts':      attempts,
        'total_attempts': total_attempts,
        'passed_count':  passed_count,
        'failed_count':  failed_count,
        'pass_rate':     pass_rate,
        'avg_score':     avg_score,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def quiz_attempt_detail(request, course_slug, lesson_slug, quiz_slug, attempt_id):
    """Detailed breakdown of a single student's quiz attempt."""
    from eduweb.models import Lesson, Quiz
    course  = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    lesson  = get_object_or_404(Lesson, slug=lesson_slug, course=course)
    quiz    = get_object_or_404(Quiz, slug=quiz_slug, lesson=lesson)
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, quiz=quiz)

    responses       = attempt.responses.select_related(
        'question', 'selected_answer'
    ).prefetch_related('question__answers').order_by('question__display_order')
    correct_count   = responses.filter(is_correct=True).count()
    total_questions = responses.count()

    return render(request, 'instructor/quiz_attempt_detail.html', {
        'course':          course,
        'lesson':          lesson,
        'quiz':            quiz,
        'attempt':         attempt,
        'responses':       responses,
        'correct_count':   correct_count,
        'total_questions': total_questions,
    })


# ============================================================
# 3.  MESSAGES — Inbox / Sent / Thread / Compose / Reply
# ============================================================

@login_required(login_url='eduweb:auth_page')
@instructor_required
def messages_inbox(request):
    """Show received messages (most recent per thread)."""
    received = Message.objects.filter(
        recipient=request.user, parent__isnull=True
    ).select_related('sender').order_by('-created_at')

    unread_count = received.filter(is_read=False).count()

    return render(request, 'instructor/messages_inbox.html', {
        'messages_list': received,
        'active_folder': 'inbox',
        'unread_count':  unread_count,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def messages_sent(request):
    """Show sent messages."""
    sent = Message.objects.filter(
        sender=request.user, parent__isnull=True
    ).select_related('recipient').order_by('-created_at')

    return render(request, 'instructor/messages_inbox.html', {
        'messages_list': sent,
        'active_folder': 'sent',
        'unread_count':  0,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def message_thread(request, message_id):
    """Display a full conversation thread."""
    root = get_object_or_404(
        Message, id=message_id
    )
    # Security: only sender or recipient may view
    if root.sender != request.user and root.recipient != request.user:
        messages.error(request, 'You do not have access to this message.')
        return redirect('instructor:messages_inbox')

    # Mark as read if viewing as recipient
    if root.recipient == request.user and not root.is_read:
        root.mark_as_read()

    thread_messages = [root] + list(
        Message.objects.filter(parent=root).order_by('created_at')
    )
    other_user = root.recipient if root.sender == request.user else root.sender

    return render(request, 'instructor/message_thread.html', {
        'root_message':    root,
        'thread_messages': thread_messages,
        'thread_subject':  root.subject,
        'other_user':      other_user,
        'compose':         False,
    })


# ============================================================
# INSTRUCTOR NOTIFICATIONS
# ============================================================

@login_required(login_url='eduweb:auth_page')
@instructor_required
def instructor_notifications(request):
    """Show all notifications for the logged-in instructor."""

    # Mark all as read if requested
    if request.GET.get('mark_all') == '1':
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        messages.success(request, 'All notifications marked as read.')
        return redirect('instructor:notifications')

    notifs_qs = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    unread_count = notifs_qs.filter(is_read=False).count()

    paginator = Paginator(notifs_qs, 20)
    page = request.GET.get('page')
    notifications = paginator.get_page(page)

    return render(request, 'instructor/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'page_title': 'Notifications',
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def instructor_notification_read(request, notif_id):
    """Mark a single instructor notification as read (AJAX)."""
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
    return JsonResponse({'success': True})


@login_required(login_url='eduweb:auth_page')
@instructor_required
def message_compose(request):
    """Compose and send a new message."""
    from .forms import MessageForm
    initial = {}

    # Pre-fill if coming from a student profile link: ?recipient=<id>&subject=...
    recipient_id = request.GET.get('recipient')
    subject      = request.GET.get('subject', '')
    if recipient_id:
        from django.contrib.auth.models import User as AuthUser
        try:
            initial['recipient'] = AuthUser.objects.get(pk=recipient_id)
        except AuthUser.DoesNotExist:
            pass
    if subject:
        initial['subject'] = subject

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.save()
            messages.success(request, f'Message sent to {msg.recipient.get_full_name()}!')
            _notify_instructor(
                instructor=msg.recipient,
                title=f'New Message from {request.user.get_full_name() or request.user.username}',
                message=f'Subject: {msg.subject}',
                notif_type='message',
                link='/instructor/messages/',
            )
            from eduweb.emailservices import send_new_message_email
            send_new_message_email(msg.recipient, request.user, msg)
            return redirect('instructor:messages_inbox')
    else:
        form = MessageForm(initial=initial)

    # Build recipients list for the searchable UI (all active users except self)
    from django.contrib.auth.models import User as AuthUser
    recipients = AuthUser.objects.filter(
        is_active=True
    ).exclude(
        id=request.user.id
    ).select_related('profile').order_by('first_name', 'last_name')

    return render(request, 'instructor/message_thread.html', {
        'form':       form,
        'compose':    True,
        'recipients': recipients,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def message_reply(request, message_id):
    """Post a reply to an existing thread (POST only)."""
    root = get_object_or_404(Message, id=message_id)
    if root.sender != request.user and root.recipient != request.user:
        messages.error(request, 'Access denied.')
        return redirect('instructor:messages_inbox')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            other = root.recipient if root.sender == request.user else root.sender
            reply_msg = Message.objects.create(
                sender    = request.user,
                recipient = other,
                subject   = f'Re: {root.subject}',
                body      = body,
                parent    = root,
            )
            messages.success(request, 'Reply sent.')
            _notify_instructor(
                instructor=other,
                title=f'New Reply from {request.user.get_full_name() or request.user.username}',
                message=f'Re: {root.subject}',
                notif_type='message',
                link=f'/instructor/messages/{root.id}/',
            )
            from eduweb.emailservices import send_new_message_email
            send_new_message_email(other, request.user, root)
        else:
            messages.error(request, 'Reply cannot be empty.')

    return redirect('instructor:message_thread', message_id=root.id)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def messages_mark_all_read(request):
    """Mark all inbox messages as read."""
    Message.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    messages.success(request, 'All messages marked as read.')
    return redirect('instructor:messages_inbox')


# ============================================================
# 4.  DISCUSSIONS — List / Detail / Reply / Pin / Lock / Delete
# ============================================================

@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussions(request, course_slug):
    """List all discussion threads for a course."""
    course = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussions_qs = Discussion.objects.filter(course=course).select_related(
        'author'
    ).prefetch_related('replies').order_by('-is_pinned', '-created_at')

    return render(request, 'instructor/discussions.html', {
        'course':      course,
        'discussions': discussions_qs,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussion_detail(request, course_slug, discussion_slug):
    """View a single discussion thread and its replies."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)

    # Increment views
    discussion.views_count += 1
    discussion.save(update_fields=['views_count'])

    replies = discussion.replies.select_related('author').order_by('created_at')

    return render(request, 'instructor/discussion_detail.html', {
        'course':     course,
        'discussion': discussion,
        'replies':    replies,
    })


@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussion_reply(request, course_slug, discussion_slug):
    """Instructor posts a reply to a discussion (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)

    if request.method == 'POST' and not discussion.is_locked:
        content = request.POST.get('content', '').strip()
        if content:
            DiscussionReply.objects.create(
                discussion=discussion,
                author=request.user,
                content=content,
            )
            messages.success(request, 'Reply posted.')
            # Notify discussion author if they are not the instructor
            if discussion.author != request.user:
                _notify_instructor(
                    instructor=discussion.author,
                    title='Instructor Replied to Your Discussion',
                    message=f'Your instructor replied to "{discussion.title}" in "{course.title}".',
                    notif_type='announcement',
                    link=f'/student/community/thread/{discussion.id}/',
                )
        else:
            messages.error(request, 'Reply cannot be empty.')

    return redirect('instructor:discussion_detail',
                    course_slug=course.slug, discussion_slug=discussion.slug)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussion_toggle_pin(request, course_slug, discussion_slug):
    """Toggle pinned status (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)

    if request.method == 'POST':
        discussion.is_pinned = not discussion.is_pinned
        discussion.save(update_fields=['is_pinned'])
        state = 'pinned' if discussion.is_pinned else 'unpinned'
        messages.success(request, f'Discussion {state}.')

    return redirect('instructor:discussions', course_slug=course.slug)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussion_toggle_lock(request, course_slug, discussion_slug):
    """Toggle locked status (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)

    if request.method == 'POST':
        discussion.is_locked = not discussion.is_locked
        discussion.save(update_fields=['is_locked'])
        state = 'locked' if discussion.is_locked else 'unlocked'
        messages.success(request, f'Discussion {state}.')

    return redirect('instructor:discussions', course_slug=course.slug)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def discussion_delete(request, course_slug, discussion_slug):
    """Delete a discussion and all replies (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)

    if request.method == 'POST':
        discussion.delete()
        messages.success(request, 'Discussion deleted.')

    return redirect('instructor:discussions', course_slug=course.slug)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def reply_toggle_solution(request, course_slug, discussion_slug, reply_id):
    """Mark / unmark a reply as the solution (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)
    reply      = get_object_or_404(DiscussionReply, id=reply_id, discussion=discussion)

    if request.method == 'POST':
        reply.is_solution = not reply.is_solution
        reply.save(update_fields=['is_solution'])
        state = 'marked as solution' if reply.is_solution else 'unmarked'
        messages.success(request, f'Reply {state}.')
        if reply.is_solution and reply.author != request.user:
            _notify_instructor(
                instructor=reply.author,
                title='Your Reply Was Marked as Solution',
                message=f'Your reply in "{discussion.title}" was marked as the solution by the instructor.',
                notif_type='announcement',
                link=f'/student/community/thread/{discussion.id}/',
            )

    return redirect('instructor:discussion_detail',
                    course_slug=course.slug, discussion_slug=discussion.slug)


@login_required(login_url='eduweb:auth_page')
@instructor_required
def reply_delete(request, course_slug, discussion_slug, reply_id):
    """Delete a specific reply (POST only)."""
    course     = get_object_or_404(LMSCourse, slug=course_slug, instructor=request.user)
    discussion = get_object_or_404(Discussion, slug=discussion_slug, course=course)
    reply      = get_object_or_404(DiscussionReply, id=reply_id, discussion=discussion)

    if request.method == 'POST':
        reply.delete()
        messages.success(request, 'Reply deleted.')

    return redirect('instructor:discussion_detail',
                    course_slug=course.slug, discussion_slug=discussion.slug)

# ── JSON helper ───────────────────────────────────────────────────────────────
from django.http import JsonResponse
 
 
# ─────────────────────────────────────────────────────────────────────────────
# AJAX: return course details (code, academic session) for a given course pk
# Used by the Create Assessment page to auto-populate locked fields.
# ─────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def ajax_course_details(request):
    """
    GET /instructor/assessments/course-details/?course_id=<pk>
    Returns JSON {code, academic_session_id, academic_session_name}
    for the instructor's own course only.
    """
    course_id = request.GET.get('course_id')
    if not course_id:
        return JsonResponse({'error': 'No course_id provided'}, status=400)
 
    course = get_object_or_404(
        LMSCourse, pk=course_id, instructor=request.user
    )
 
    session_id   = None
    session_name = '—'
    # LMSCourse has an optional FK to AcademicSession via academic_course → Course → session
    # Try to get the session through the chain that exists in your model
    try:
        # If LMSCourse has a direct academic_session FK:
        if hasattr(course, 'academic_session') and course.academic_session:
            session_id   = course.academic_session.pk
            session_name = str(course.academic_session)
        # Fallback: through academic_course (the Course model)
        elif hasattr(course, 'academic_course') and course.academic_course:
            ac = course.academic_course
            if hasattr(ac, 'academic_session') and ac.academic_session:
                session_id   = ac.academic_session.pk
                session_name = str(ac.academic_session)
    except Exception:
        pass
 
    return JsonResponse({
        'code':                  course.code or '',
        'title':                 course.title,
        'academic_session_id':   session_id,
        'academic_session_name': session_name,
        # Always True — ALL LMS courses (standalone or academic-linked) can create exams.
        'is_linked':             True,
        'has_academic_course':   bool(getattr(course, 'academic_course', None)),
        # Explicit flag: exam creation is ALWAYS allowed regardless of academic linkage
        'exam_allowed':          True,
    })
 
# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED CREATE ASSESSMENT  (quiz / assignment / exam — all on one page)
# ─────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def create_assessment(request):
    """
    Unified page that lets an instructor create a Quiz, Assignment, or Exam.
 
    Flow:
      1. Instructor picks assessment type (quiz | assignment | exam).
      2. Instructor picks one of their LMS courses — AJAX fills code + session.
      3. The right form panel slides in.
         • Quiz    → QuizForm  + repeating QuizQuestion+QuizAnswer blocks (JS)
         • Assignment → AssignmentForm
         • Exam    → ExamForm  (submitted DRAFT, goes to admin for approval)
      4. On POST the view creates the right objects and redirects.
 
    For Quiz, the questions are submitted as a formset-like JSON payload in
    hidden fields (questions_data) so the instructor can add/remove them
    dynamically without a page reload, leveraging the existing jQuery on the page.
    """
    instructor_courses = LMSCourse.objects.filter(
        instructor=request.user
    ).select_related('academic_course').order_by('title')
 
    # ── POST handling ─────────────────────────────────────────────────────────
    if request.method == 'POST':
        assessment_type = request.POST.get('assessment_type', '')
        course_id       = request.POST.get('course_id', '')
        course          = get_object_or_404(
            LMSCourse, pk=course_id, instructor=request.user
        )
 
        # ── QUIZ ──────────────────────────────────────────────────────────────
        if assessment_type == 'quiz':
            lesson_id = request.POST.get('lesson_id', '')
            lesson    = get_object_or_404(Lesson, pk=lesson_id, course=course)

            quiz_form = QuizForm(request.POST)
            if quiz_form.is_valid():
                quiz        = quiz_form.save(commit=False)
                quiz.lesson = lesson
                quiz.save()

                import json as _json
                questions_raw = request.POST.get('questions_data', '[]')
                try:
                    questions_list = _json.loads(questions_raw)
                except ValueError:
                    questions_list = []

                for q_data in questions_list:
                    q = QuizQuestion.objects.create(
                        quiz          = quiz,
                        question_type = q_data.get('question_type', 'mcq'),
                        question_text = q_data.get('question_text', ''),
                        explanation   = q_data.get('explanation', ''),
                        points        = q_data.get('points', 1),
                        display_order = q_data.get('display_order', 0),
                    )
                    for a_data in q_data.get('answers', []):
                        QuizAnswer.objects.create(
                            question      = q,
                            answer_text   = a_data.get('answer_text', ''),
                            is_correct    = a_data.get('is_correct', False),
                            display_order = a_data.get('display_order', 0),
                        )

                messages.success(request, f'Quiz "{quiz.title}" created successfully!')
                return redirect('instructor:quiz_questions', course.slug, lesson.slug, quiz.slug)
            else:
                # Surface field-level errors in the message
                error_detail = '; '.join(
                    f"{field}: {', '.join(errs)}"
                    for field, errs in quiz_form.errors.items()
                )
                messages.error(request, f'Please fix the quiz form errors: {error_detail}')
                context = {
                    'instructor_courses': instructor_courses,
                    'quiz_form':          quiz_form,           # bound — shows errors
                    'assign_form':        AssignmentForm(),
                    'exam_form':          ExamForm(),
                    'question_form':      QuizQuestionForm(),
                    'answer_form':        QuizAnswerForm(),
                    'active_tab':         'quiz',
                    'post_course_id':     course_id,
                    'post_lesson_id':     lesson_id,
                }
                return render(request, 'instructor/create_assessment.html', context)

        # ── ASSIGNMENT ────────────────────────────────────────────────────────
        elif assessment_type == 'assignment':
            lesson_id  = request.POST.get('lesson_id', '')
            lesson     = get_object_or_404(Lesson, pk=lesson_id, course=course)

            assign_form = AssignmentForm(request.POST, request.FILES)
            if assign_form.is_valid():
                assignment        = assign_form.save(commit=False)
                assignment.lesson = lesson
                assignment.save()
                messages.success(request, f'Assignment "{assignment.title}" created successfully!')
                return redirect('instructor:assignment_list', course.slug, lesson.slug)
            else:
                error_detail = '; '.join(
                    f"{field}: {', '.join(errs)}"
                    for field, errs in assign_form.errors.items()
                )
                messages.error(request, f'Please fix the assignment form errors: {error_detail}')
                context = {
                    'instructor_courses': instructor_courses,
                    'quiz_form':          QuizForm(),
                    'assign_form':        assign_form,         # bound — shows errors
                    'exam_form':          ExamForm(),
                    'question_form':      QuizQuestionForm(),
                    'answer_form':        QuizAnswerForm(),
                    'active_tab':         'assignment',
                    'post_course_id':     course_id,
                    'post_lesson_id':     lesson_id,
                }
                return render(request, 'instructor/create_assessment.html', context)

        # ── EXAM ──────────────────────────────────────────────────────────────
        elif assessment_type == 'exam':
            exam_form = ExamForm(request.POST, request.FILES)
            if exam_form.is_valid():
                exam            = exam_form.save(commit=False)
                exam.instructor = request.user
                if hasattr(exam, 'created_by'):
                    exam.created_by = request.user
                exam.status     = 'draft'

                # Always assign the LMSCourse instance (what the FK expects)
                lms_course      = course  # LMSCourse instance
                academic_course = getattr(lms_course, 'academic_course', None)
                exam.course     = lms_course  # ← always LMSCourse, never Course

                # Denorm department from the academic course if available
                try:
                    if academic_course and hasattr(academic_course, 'department') and academic_course.department:
                        exam.department = academic_course.department
                except Exception:
                    pass

                # Resolve academic_session through the academic course
                try:
                    if academic_course and getattr(academic_course, 'academic_session', None):
                        exam.academic_session = academic_course.academic_session
                except Exception:
                    pass

                exam.save()

                # ── Save manually entered exam questions from JSON ─────────────
                import json as _json
                from eduweb.models import ExamQuestion
                eq_raw = request.POST.get('exam_questions_data', '[]')
                try:
                    eq_list = _json.loads(eq_raw)
                except (ValueError, TypeError):
                    eq_list = []

                for idx, eq_data in enumerate(eq_list):
                    q_text = (eq_data.get('question_text') or '').strip()
                    if not q_text:
                        continue
                    import uuid as _uuid
                    raw_options = eq_data.get('options', [])
                    options_with_ids = []
                    for opt in raw_options:
                        options_with_ids.append({
                            'id':         f'opt-{_uuid.uuid4().hex[:8]}',
                            'text':       opt.get('text', ''),
                            'is_correct': bool(opt.get('is_correct', False)),
                        })
                    ExamQuestion.objects.create(
                        exam          = exam,
                        question_text = q_text,
                        question_type = eq_data.get('question_type', 'mcq'),
                        marks         = eq_data.get('marks', 1),
                        options       = options_with_ids,
                        explanation   = eq_data.get('explanation', ''),
                        created_by    = request.user,
                    )

                # ── Parse uploaded question file (docx / xlsx) ────────────────
                import_file = request.FILES.get('question_import_file')
                if import_file:
                    _parse_exam_questions_from_file(import_file, exam, request.user)

                messages.success(
                    request,
                    f'Exam "{exam.title}" saved as DRAFT and submitted for admin approval.'
                )
                return redirect('instructor:dashboard')
            else:
                error_detail = '; '.join(
                    f"{field}: {', '.join(errs)}"
                    for field, errs in exam_form.errors.items()
                )
                messages.error(request, f'Please fix the exam form errors: {error_detail}')
                context = {
                    'instructor_courses': instructor_courses,
                    'quiz_form':          QuizForm(),
                    'assign_form':        AssignmentForm(),
                    'exam_form':          exam_form,           # bound — shows errors
                    'question_form':      QuizQuestionForm(),
                    'answer_form':        QuizAnswerForm(),
                    'active_tab':         'exam',
                    'post_course_id':     course_id,
                }
                return render(request, 'instructor/create_assessment.html', context)

    # ── GET ───────────────────────────────────────────────────────────────────
    # Support ?type=quiz|assignment|exam from dashboard quick-action buttons
    active_tab = request.GET.get('type', '')
    if active_tab not in ('quiz', 'assignment', 'exam'):
        active_tab = ''

    context = {
        'instructor_courses': instructor_courses,
        'quiz_form':          QuizForm(),
        'assign_form':        AssignmentForm(),
        'exam_form':          ExamForm(),
        'question_form':      QuizQuestionForm(),
        'answer_form':        QuizAnswerForm(),
        'active_tab':         active_tab,
    }
    return render(request, 'instructor/create_assessment.html', context)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# AJAX: lessons for a given course (needed to pick lesson on quiz/assignment)
# ─────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def ajax_course_lessons(request):
    """
    GET /instructor/assessments/course-lessons/?course_id=<pk>
    Returns JSON list of lessons for the instructor's course.
    """
    course_id = request.GET.get('course_id')
    if not course_id:
        return JsonResponse({'lessons': []})
 
    course  = get_object_or_404(LMSCourse, pk=course_id, instructor=request.user)
    lessons = list(
        Lesson.objects.filter(course=course)
        .values('id', 'title')
        .order_by('display_order', 'title')
    )
    return JsonResponse({'lessons': lessons})

import json as _json
import uuid as _uuid
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM LIST
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_list(request):
    """List all exams created by this instructor with filtering & search."""
    qs = Exam.objects.filter(instructor=request.user).order_by('-created_at')
 
    active_status = request.GET.get('status', 'all')
    search        = request.GET.get('q', '').strip()
 
    if active_status and active_status != 'all':
        qs = qs.filter(status=active_status)
    if search:
        qs = qs.filter(title__icontains=search)
 
    # Counts for stat cards
    base_qs        = Exam.objects.filter(instructor=request.user)
    stat_total     = base_qs.count()
    stat_draft     = base_qs.filter(status=Exam.DRAFT).count()
    stat_submitted = base_qs.filter(status=Exam.SUBMITTED).count()
    stat_approved  = base_qs.filter(status=Exam.APPROVED).count()
    stat_rejected  = base_qs.filter(status=Exam.REJECTED).count()
    stat_published = base_qs.filter(status=Exam.PUBLISHED).count()
 
    paginator = Paginator(qs, 12)
    exams     = paginator.get_page(request.GET.get('page'))
 
    return render(request, 'instructor/exam_list.html', {
        'exams':         exams,
        'active_status': active_status,
        'search':        search,
        'stat_total':    stat_total,
        'stat_draft':    stat_draft,
        'stat_submitted': stat_submitted,
        'stat_approved': stat_approved,
        'stat_rejected': stat_rejected,
        'stat_published': stat_published,
    })
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM DETAIL  (overview / edit / questions / results tabs)
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_detail(request, slug):
    """Single exam — tabbed view: overview, edit, questions, results."""
    exam = get_object_or_404(Exam, slug=slug, instructor=request.user)
 
    questions    = exam.questions.filter(is_active=True).order_by('created_at')
    status_logs  = exam.status_logs.all().order_by('-created_at')[:10]
 
    # Results stats (only meaningful when published)
    responses        = exam.student_responses.all()
    submitted_resp   = responses.filter(status__in=['submitted', 'graded'])
    graded_resp      = responses.filter(status='graded')
    avg_score        = graded_resp.aggregate(avg=Avg('score_percentage'))['avg']
    avg_score_str    = f"{avg_score:.1f}" if avg_score is not None else None
 
    response_stats = {
        'total':     responses.count(),
        'submitted': submitted_resp.count(),
        'graded':    graded_resp.count(),
        'avg_score': avg_score_str,
    }
    student_responses = responses.select_related('student').order_by('-submitted_at')[:50]
 
    return render(request, 'instructor/exam_detail.html', {
        'exam':              exam,
        'questions':         questions,
        'status_logs':       status_logs,
        'response_stats':    response_stats,
        'student_responses': student_responses,
    })
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM UPDATE  (POST from the Edit Details tab)
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_update(request, slug):
    """Handle POST from the Edit Details tab on exam_detail."""
    exam = get_object_or_404(Exam, slug=slug, instructor=request.user)
 
    if request.method != 'POST':
        return redirect('instructor:exam_detail', slug=exam.slug)
 
    if exam.status == Exam.PUBLISHED:
        messages.error(request, 'A published exam can no longer be edited.')
        return redirect('instructor:exam_detail', slug=exam.slug)

    # If submitted or approved, revert to draft
    if exam.status in (Exam.SUBMITTED, Exam.APPROVED):
        old_status   = exam.status
        exam.status  = Exam.DRAFT
        _write_exam_log(exam, from_status=old_status, to_status=Exam.DRAFT,
                        changed_by=request.user,
                        note="Reverted to draft by instructor edit.")
 
    # Update fields from POST
    exam.title                   = request.POST.get('title', exam.title).strip()
    exam.exam_type               = request.POST.get('exam_type', exam.exam_type)
    exam.description             = request.POST.get('description', exam.description)
    exam.instructions            = request.POST.get('instructions', exam.instructions)
    exam.special_instructions    = request.POST.get('special_instructions', exam.special_instructions)
    exam.internal_notes          = request.POST.get('internal_notes', exam.internal_notes)
    exam.shuffle_questions       = 'shuffle_questions' in request.POST
    exam.shuffle_options         = 'shuffle_options' in request.POST
    exam.show_result_immediately = 'show_result_immediately' in request.POST
 
    # REMOVED: exam.mode  — always online, no longer a field
    # REMOVED: exam.venue — no physical location
 
    # Numeric fields
    # REMOVED: 'instruction_window_minutes' — fixed class constant, never written from POST
    for attr, field in (
        ('questions_per_student', 'questions_per_student'),
        ('pass_mark',             'pass_mark'),
    ):
        raw = request.POST.get(field, '').strip()
        if raw:
            try:
                setattr(exam, attr, int(raw) if attr != 'pass_mark' else float(raw))
            except ValueError:
                pass
        else:
            setattr(exam, attr, None)
 
    # Combined datetime fields — replace the old exam_date / start_time / end_time split
    # REMOVED: separate 'exam_date', 'start_time', 'end_time' parsing
    from django.utils.dateparse import parse_datetime
    raw_start = request.POST.get('start_datetime', '').strip()
    raw_end   = request.POST.get('end_datetime',   '').strip()
    if raw_start:
        parsed = parse_datetime(raw_start)
        if parsed:
            exam.start_datetime = parsed
    if raw_end:
        parsed = parse_datetime(raw_end)
        if parsed:
            exam.end_datetime = parsed
 
    # show_answers_after
    raw_saa = request.POST.get('show_answers_after', '').strip()
    if raw_saa:
        from django.utils.dateparse import parse_datetime as _pd
        parsed_saa = _pd(raw_saa)
        if parsed_saa:
            exam.show_answers_after = parsed_saa
    elif 'show_answers_after' in request.POST and not raw_saa:
        exam.show_answers_after = None

    # REMOVED: visible_from_override / visible_until_override parsing
    # — visibility is now a fully computed @property, no overrides stored
 
    try:
        exam.save()
        messages.success(request, f'Exam "{exam.title}" updated successfully.')
    except Exception as e:
        messages.error(request, f'Could not save changes: {e}')
 
    from django.urls import reverse
    return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=edit')
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM SUBMIT  (draft / rejected → submitted)
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def exam_submit(request, slug):
    """Submit an exam for admin approval."""
    exam = get_object_or_404(Exam, slug=slug, instructor=request.user)
 
    if exam.status not in (Exam.DRAFT, Exam.REJECTED):
        messages.error(request, 'Only draft or rejected exams can be submitted.')
        return redirect('instructor:exam_detail', slug=exam.slug)
 
    if exam.active_question_count == 0:
        messages.error(request, 'Please add at least one question before submitting.')
        from django.urls import reverse
        return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
 
    old_status           = exam.status
    exam.status          = Exam.SUBMITTED
    exam.submitted_by    = request.user
    exam.submitted_at    = timezone.now()
    exam.submission_count += 1
    exam.save(update_fields=['status', 'submitted_by', 'submitted_at', 'submission_count'])
 
    _write_exam_log(exam, from_status=old_status, to_status=Exam.SUBMITTED,
                    changed_by=request.user)
 
    messages.success(request, f'"{exam.title}" submitted for admin approval.')
    return redirect('instructor:exam_detail', slug=exam.slug)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM PUBLISH  (approved → published)
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def exam_publish(request, slug):
    """Publish an approved exam so students can see it."""
    exam = get_object_or_404(Exam, slug=slug, instructor=request.user)
 
    if exam.status != Exam.APPROVED:
        messages.error(request, 'Only approved exams can be published.')
        return redirect('instructor:exam_detail', slug=exam.slug)
 
    exam.status       = Exam.PUBLISHED
    exam.published_by = request.user
    exam.published_at = timezone.now()
    exam.save(update_fields=['status', 'published_by', 'published_at'])
 
    _write_exam_log(exam, from_status=Exam.APPROVED, to_status=Exam.PUBLISHED,
                    changed_by=request.user)
 
    messages.success(request, f'"{exam.title}" is now published and visible to students.')
    return redirect('instructor:exam_detail', slug=exam.slug)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM QUESTION: CREATE
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_question_create(request, slug):
    """Add a new question to the exam question pool."""
    exam = get_object_or_404(Exam, slug=slug, instructor=request.user)

    if exam.status == Exam.PUBLISHED:
        messages.error(request, 'Cannot modify questions for a published exam.')
        return redirect('instructor:exam_detail', slug=exam.slug)
 
    if request.method == 'POST':
        error = _save_exam_question(request, exam, question=None)
        if error:
            messages.error(request, error)
            return render(request, 'instructor/exam_question_form.html', {'exam': exam, 'question': None})
        messages.success(request, 'Question added successfully.')
        from django.urls import reverse
        if request.POST.get('_save_back'):
            return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
        return redirect(reverse('instructor:exam_question_create', kwargs={'slug': exam.slug}))
 
    return render(request, 'instructor/exam_question_form.html', {'exam': exam, 'question': None})
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM QUESTION: EDIT
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_question_edit(request, slug, question_id):
    """Edit an existing exam question."""
    exam     = get_object_or_404(Exam, slug=slug, instructor=request.user)
    question = get_object_or_404(ExamQuestion, pk=question_id, exam=exam)

    if exam.status == Exam.PUBLISHED:
        messages.error(request, 'Cannot modify questions for a published exam.')
        return redirect('instructor:exam_detail', slug=exam.slug)
 
    if request.method == 'POST':
        error = _save_exam_question(request, exam, question=question)
        if error:
            messages.error(request, error)
            return render(request, 'instructor/exam_question_form.html', {'exam': exam, 'question': question})
        messages.success(request, 'Question updated successfully.')
        from django.urls import reverse
        return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
 
    return render(request, 'instructor/exam_question_form.html', {'exam': exam, 'question': question})
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM QUESTION: DELETE
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def exam_question_delete(request, slug, question_id):
    """Soft-delete (deactivate) an exam question."""
    exam     = get_object_or_404(Exam, slug=slug, instructor=request.user)

    if exam.status == Exam.PUBLISHED:
        messages.error(request, 'Cannot modify questions for a published exam.')
        return redirect('instructor:exam_detail', slug=exam.slug)

    question = get_object_or_404(ExamQuestion, pk=question_id, exam=exam)
    question.is_active = False
    question.save(update_fields=['is_active'])
    messages.success(request, 'Question removed from the active pool.')
    from django.urls import reverse
    return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
 
 
# ──────────────────────────────────────────────────────────────────────────────
# EXAM QUESTION IMPORT  (docx / xlsx → ExamQuestion rows)
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
@require_POST
def exam_import_questions(request, slug):
    """Accept a .docx or .xlsx upload and parse questions into the DB."""
    exam        = get_object_or_404(Exam, slug=slug, instructor=request.user)

    if exam.status == Exam.PUBLISHED:
        messages.error(request, 'Cannot import questions for a published exam.')
        return redirect('instructor:exam_detail', slug=exam.slug)

    import_file = request.FILES.get('question_import_file')
 
    if not import_file:
        messages.error(request, 'Please select a file to upload.')
        from django.urls import reverse
        return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
 
    try:
        _parse_exam_questions_from_file(import_file, exam, request.user)
        messages.success(request, 'Questions imported successfully.')
    except Exception as e:
        exam.import_status    = Exam.IMPORT_FAILED
        exam.import_error_log = str(e)
        exam.save(update_fields=['import_status', 'import_error_log'])
        messages.error(request, f'Import failed: {e}')
 
    from django.urls import reverse
    return redirect(reverse('instructor:exam_detail', kwargs={'slug': exam.slug}) + '?tab=questions')
 
 
# ──────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ──────────────────────────────────────────────────────────────────────────────
 
def _write_exam_log(exam, from_status, to_status, changed_by, note=''):
    """Write an immutable ExamStatusLog entry."""
    from eduweb.models import ExamStatusLog
    try:
        ExamStatusLog.objects.create(
            exam        = exam,
            from_status = from_status,
            to_status   = to_status,
            changed_by  = changed_by,
            note        = note,
        )
    except Exception:
        pass  # Never crash the main action
 
 
def _save_exam_question(request, exam, question=None):
    """
    Parse POST data and create or update an ExamQuestion.
    Returns an error string on failure, or None on success.
    """
    q_type   = request.POST.get('question_type', 'mcq')
    q_text   = (request.POST.get('question_text') or '').strip()
    if not q_text:
        return 'Question text is required.'
 
    marks_raw        = request.POST.get('marks', '1').strip()
    explanation      = request.POST.get('explanation', '').strip()
    source_reference = request.POST.get('source_reference', '').strip()
    is_active        = 'is_active' in request.POST
    tags_raw         = request.POST.get('tags_input', '').strip()
    tags             = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
 
    try:
        marks = float(marks_raw)
    except ValueError:
        marks = 1.0
 
    # Build options list
    options = []
    if q_type == 'true_false':
        correct_val = request.POST.get('tf_correct', 'true')
        options = [
            {'id': f'opt-{_uuid.uuid4().hex[:8]}', 'text': 'True',  'is_correct': correct_val == 'true'},
            {'id': f'opt-{_uuid.uuid4().hex[:8]}', 'text': 'False', 'is_correct': correct_val == 'false'},
        ]
    elif q_type in ('mcq', 'multi_select'):
        options_count_raw = request.POST.get('options_count', '0').strip()
        try:
            options_count = int(options_count_raw)
        except ValueError:
            options_count = 0
 
        correct_option_idx = request.POST.get('correct_option', '')  # single for mcq
 
        for i in range(options_count):
            text = (request.POST.get(f'option_text_{i}') or '').strip()
            if not text:
                continue
            # Try to keep existing option IDs intact
            opt_id = (request.POST.get(f'option_id_{i}') or '').strip()
            if not opt_id:
                opt_id = f'opt-{_uuid.uuid4().hex[:8]}'
 
            if q_type == 'multi_select':
                is_correct = f'option_correct_{i}' in request.POST
            else:
                is_correct = str(i) == correct_option_idx
 
            options.append({'id': opt_id, 'text': text, 'is_correct': is_correct})
 
        if not options:
            return 'Please add at least 2 answer options.'
 
    # Accepted answers for short_answer
    accepted_answers = []
    if q_type == 'short_answer':
        raw_accepted = request.POST.get('accepted_answers', '').strip()
        if raw_accepted:
            accepted_answers = [ln.strip() for ln in raw_accepted.splitlines() if ln.strip()]
 
    # Year first used
    yr_raw = request.POST.get('year_first_used', '').strip()
    year_first_used = None
    if yr_raw:
        try:
            year_first_used = int(yr_raw)
        except ValueError:
            pass
 
    # Handle image
    image_file  = request.FILES.get('image')
    clear_image = 'clear_image' in request.POST
 
    if question is None:
        # Create
        q = ExamQuestion(
            exam             = exam,
            question_text    = q_text,
            question_type    = q_type,
            marks            = marks,
            options          = options,
            accepted_answers = accepted_answers,
            explanation      = explanation,
            source_reference = source_reference,
            year_first_used  = year_first_used,
            tags             = tags,
            is_active        = is_active,
            created_by       = request.user,
        )
        if image_file:
            q.image = image_file
        q.save()
    else:
        # Update
        question.question_text   = q_text
        question.question_type   = q_type
        question.marks           = marks
        question.options         = options
        question.accepted_answers = accepted_answers
        question.explanation     = explanation
        question.source_reference = source_reference
        question.year_first_used  = year_first_used
        question.tags            = tags
        question.is_active       = is_active
        if clear_image and question.image:
            question.image.delete(save=False)
            question.image = None
        if image_file:
            question.image = image_file
        question.save()
 
    return None  # success
 
 
def _parse_exam_questions_from_file(import_file, exam, user):
    """
    Parse uploaded .docx or .xlsx file into ExamQuestion rows.
    This is a minimal implementation — extend as needed.
    """
    import os
    name = import_file.name.lower()
 
    exam.import_status    = Exam.IMPORT_PROCESSING
    exam.import_error_log = ''
    exam.save(update_fields=['import_status', 'import_error_log'])
 
    errors = []
    created = 0
 
    try:
        if name.endswith('.xlsx'):
            try:
                import openpyxl
            except ImportError:
                raise RuntimeError('openpyxl is not installed. Run: pip install openpyxl')
            wb = openpyxl.load_workbook(import_file, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            for idx, row in enumerate(rows, start=2):
                if not row or not row[0]:
                    continue
                q_text = str(row[0]).strip()
                if not q_text:
                    continue
                q_type = str(row[1]).strip().lower() if len(row) > 1 and row[1] else 'mcq'
                marks  = float(row[2]) if len(row) > 2 and row[2] else 1.0
                diff   = str(row[3]).strip().lower() if len(row) > 3 and row[3] else 'medium'
                # Options in columns E–J (index 4–9), correct answer column K (index 10)
                raw_opts = [str(row[i]).strip() for i in range(4, 9) if i < len(row) and row[i]]
                correct_idx_raw = str(row[9]).strip() if len(row) > 9 and row[9] else '1'
                try:
                    correct_idx = int(correct_idx_raw) - 1  # 1-based → 0-based
                except ValueError:
                    correct_idx = 0
                options = [
                    {
                        'id': f'opt-{_uuid.uuid4().hex[:8]}',
                        'text': opt,
                        'is_correct': i == correct_idx,
                    }
                    for i, opt in enumerate(raw_opts)
                ]
                ExamQuestion.objects.create(
                    exam=exam, question_text=q_text, question_type=q_type,
                    difficulty=diff, marks=marks, options=options,
                    order=idx, created_by=user, imported_from_file=import_file.name,
                    import_row_number=idx,
                )
                created += 1
 
        elif name.endswith('.docx'):
            try:
                import docx as python_docx
            except ImportError:
                raise RuntimeError('python-docx is not installed. Run: pip install python-docx')
            from io import BytesIO
            doc = python_docx.Document(BytesIO(import_file.read()))
            order = 0
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                ExamQuestion.objects.create(
                    exam=exam, question_text=text, question_type='essay',
                    difficulty='medium', marks=1, options=[],
                    order=order, created_by=user, imported_from_file=import_file.name,
                    import_row_number=order,
                )
                order += 1
                created += 1
        else:
            raise RuntimeError(f'Unsupported file type: {name}')
 
    except Exception as e:
        exam.import_status    = Exam.IMPORT_FAILED
        exam.import_error_log = str(e)
        exam.save(update_fields=['import_status', 'import_error_log'])
        raise
 
    exam.import_status = Exam.IMPORT_DONE
    exam.save(update_fields=['import_status', 'import_error_log'])

# ──────────────────────────────────────────────────────────────────────────────
# EXAM GRADE RESPONSE  — instructor manually grades pending-manual questions
# ──────────────────────────────────────────────────────────────────────────────
@login_required(login_url='eduweb:auth_page')
@instructor_required
def exam_grade_response(request, slug, response_id):
    from eduweb.models import StudentExamResponse
    exam     = get_object_or_404(Exam, slug=slug, instructor=request.user)
    response = get_object_or_404(StudentExamResponse, pk=response_id, exam=exam)

    assigned_ids = response.assigned_question_ids or []
    questions    = {q.id: q for q in exam.questions.filter(id__in=assigned_ids)}

    if request.method == 'POST':
        question_scores = response.question_scores or {}

        for qid_str, entry in question_scores.items():
            if not entry.get('pending_manual'):
                continue
            raw = request.POST.get(f'marks_{qid_str}', '').strip()
            if raw == '':
                continue
            try:
                awarded = float(raw)
            except ValueError:
                continue
            max_marks = entry['max_marks']
            awarded   = max(0.0, min(awarded, float(max_marks)))
            question_scores[qid_str] = {
                'marks_awarded':  awarded,
                'max_marks':      max_marks,
                'is_correct':     awarded == float(max_marks),
                'pending_manual': False,
            }

        pending_manual = sum(1 for e in question_scores.values() if e.get('pending_manual'))
        total_score    = sum(float(e['marks_awarded']) for e in question_scores.values() if e.get('marks_awarded') is not None)
        total_marks    = sum(float(e['max_marks']) for e in question_scores.values())
        score_pct      = round((total_score / total_marks) * 100, 2) if total_marks > 0 else 0.0

        response.question_scores      = question_scores
        response.total_score          = total_score
        response.score_percentage     = score_pct
        response.pending_manual_count = pending_manual

        now = timezone.now()
        if pending_manual == 0:
            response.status    = StudentExamResponse.GRADED
            response.passed    = score_pct >= float(exam.pass_mark)
            response.graded_at = now
            response.graded_by = request.user
        else:
            response.passed = None

        response.save(update_fields=[
            'question_scores', 'total_score', 'score_percentage',
            'pending_manual_count', 'status', 'passed', 'graded_at', 'graded_by',
        ])

        if pending_manual == 0:
            messages.success(request, f"Fully graded — {response.student.get_full_name() or response.student.username} scored {score_pct}%.")
        else:
            messages.success(request, f"Saved. {pending_manual} question(s) still awaiting marks.")

        return redirect('instructor:exam_grade_response', slug=slug, response_id=response_id)

    # GET
    question_scores = response.question_scores or {}
    rows = []
    for qid in assigned_ids:
        q = questions.get(qid)
        if not q:
            continue
        entry = question_scores.get(str(qid), {})
        rows.append({
            'question':       q,
            'student_answer': response.answers.get(str(qid)),
            'entry':          entry,
            'is_pending':     entry.get('pending_manual', False),
            'marks_awarded':  entry.get('marks_awarded'),
            'max_marks':      entry.get('max_marks', float(q.marks)),
        })

    return render(request, 'instructor/exam_grade_response.html', {
        'exam':     exam,
        'response': response,
        'rows':     rows,
    })