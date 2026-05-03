"""
eduweb/views.py

All imports are consolidated at the top.
Dead / commented-out code blocks removed.
Duplicate payment_data definition resolved (kept the correct str(fee) version).
Inline email HTML blocks replaced with emailservices calls.
logging import moved to module level; logger defined once.
"""

# ─── Standard library ────────────────────────────────────────────────────────
import json
import logging
import random
from datetime import datetime
from decimal import Decimal
from threading import Thread

# ─── Third-party ─────────────────────────────────────────────────────────────
import stripe

# ─── Django ──────────────────────────────────────────────────────────────────
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.contrib.sites.shortcuts import get_current_site
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, IntegrityError
from django.db.models import Prefetch, Q
from django.http import (
    HttpResponse, HttpResponseForbidden, JsonResponse, Http404,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST

# ─── Local ───────────────────────────────────────────────────────────────────
from .decorators import applicant_required, check_for_auth, smart_redirect_applicant
from .emailservices import (
    send_admin_email,
    send_application_confirmation_email,
    send_application_admin_notification,
    send_application_submitted_email,
    send_admission_offer_accepted_email,
    send_document_upload_confirmation,
    send_document_upload_admin_notification,
    send_password_reset_email,
    send_user_confirmation_email,
    send_verification_email,
    send_verification_success_email,
    send_certificate_ready_email,
    send_transcript_generated_email,
    send_overdue_payment_reminder_email,
    send_payroll_payment_notification_email,
)
from .forms import (
    ContactForm,
    CourseApplicationForm,
    LoginForm,
    PasswordResetRequestForm,
    SetNewPasswordForm,
    SignUpForm,
)
from .models import (
    ApplicationDocument,
    ApplicationPayment,
    BlogCategory,
    BlogPost,
    Certificate,
    ContactMessage,
    Course,
    CourseApplication,
    CourseIntake,
    Department,
    Faculty,
    FeePayment,
    ListOfCountry,
    AllRequiredPayments,
    Program,
    UserProfile,
)

# ─────────────────────────────────────────────────────────────────────────────
# Module-level logger & Stripe initialisation
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


# =============================================================================
# HELPERS
# =============================================================================

def get_application_secure(application_id, user):
    try:
        return CourseApplication.objects.get(
            application_id=application_id,
            user=user,
        )
    except CourseApplication.DoesNotExist:
        logger.warning(
            "Unauthorized access attempt — user: %s, application_id: %s",
            user.email, application_id,
        )
        return None
    except Exception:
        logger.exception("Unexpected error in get_application_secure")
        return None


def application_status_context(request):
    """Context processor — adds has_pending_application to every template."""
    has_pending = False
    if request.user.is_authenticated:
        has_pending = CourseApplication.objects.filter(
            user=request.user,
            status__in=[
                'draft', 'pending_payment', 'payment_complete',
                'documents_uploaded', 'under_review',
            ],
        ).exists()
    return {'has_pending_application': has_pending}


def redirect_after_login(user):
    """Return the correct redirect response based on the user's role/status."""
    if user.is_staff or user.is_superuser:
        return redirect('management:dashboard')

    accepted = CourseApplication.objects.filter(
        user=user,
        status='approved',
        admission_accepted=True,
        admission_number__isnull=False,
        department_approved=True,
    ).first()
    if accepted:
        return redirect('student:dashboard')

    if CourseApplication.objects.filter(user=user).exists():
        return redirect('eduweb:application_status')

    return redirect('eduweb:index')


def generate_captcha():
    """Return a (question_str, answer_int) math captcha pair."""
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    op   = random.choice(['+', '-', '*'])
    if op == '+':
        answer = num1 + num2
    elif op == '-':
        answer = num1 - num2
    else:
        answer = num1 * num2
    return f"{num1} {op} {num2}", answer


# =============================================================================
# AUTHENTICATION
# =============================================================================

def verify_email(request, token):
    """Verify a user's email address via the one-time token link."""
    try:
        profile = UserProfile.objects.get(verification_token=token)
        user = profile.user

        if not user.is_active:
            user.is_active = True
            user.save()
            profile.email_verified = True
            profile.save()
            messages.success(request, 'Your email has been verified! You can now log in.')
            send_verification_success_email(user)
        else:
            messages.info(request, 'Your email is already verified.')

        return redirect('eduweb:auth_page')

    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('eduweb:auth_page')


def auth_page(request):
    """Combined login / signup page."""

    # ── Already authenticated ─────────────────────────────────────────────────
    if request.user.is_authenticated:
        if not request.user.is_active:
            logout(request)
            messages.warning(request, 'Your account is inactive. Please verify your email.')
        elif not request.user.profile.email_verified:
            logout(request)
            messages.warning(
                request,
                'Please verify your email to continue. '
                'Check your inbox for the verification link.',
            )
        else:
            messages.info(request, 'You are already logged in.')
            role = request.user.profile.role
            if role == 'admin' or request.user.is_superuser:
                return redirect('management:dashboard')
            elif role == 'instructor':
                return redirect('instructor:dashboard')
            elif role == 'finance':
                return redirect('finance:dashboard')
            else:
                return redirect('eduweb:apply')

    # ── CAPTCHA setup ─────────────────────────────────────────────────────────
    if request.method == 'GET':
        captcha_question, captcha_answer = generate_captcha()
        request.session['captcha_answer'] = captcha_answer
    else:
        captcha_answer = request.session.get('captcha_answer')
        if captcha_answer is None:
            captcha_question, captcha_answer = generate_captcha()
            request.session['captcha_answer'] = captcha_answer
            return JsonResponse({
                'success': False,
                'errors': {'captcha': ['Session expired. Please try again.']},
                'captcha_question': captcha_question,
            }, status=400)
        else:
            captcha_question = None

    # ── POST ──────────────────────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action')

        # ── SIGNUP ────────────────────────────────────────────────────────────
        if action == 'signup':
            signup_form = SignUpForm(
                request.POST,
                captcha_answer=request.session.get('captcha_answer'),
            )
            if signup_form.is_valid():
                request.session.pop('captcha_answer', None)
                user = signup_form.save(commit=False)
                user.is_active = False
                user.save()
                send_verification_email(request, user)
                return JsonResponse({
                    'success': True,
                    'message': (
                        'Account created! Check your email '
                        'to verify your account before logging in.'
                    ),
                    'email': user.email,
                })
            else:
                new_question, new_answer = generate_captcha()
                request.session['captcha_answer'] = new_answer
                return JsonResponse({
                    'success': False,
                    'errors': {f: [str(e) for e in errs]
                               for f, errs in signup_form.errors.items()},
                    'captcha_question': new_question,
                }, status=400)

        # ── LOGIN ─────────────────────────────────────────────────────────────
        elif action == 'login':
            username_or_email = request.POST.get('username', '').strip()
            password          = request.POST.get('password', '')
            captcha           = request.POST.get('captcha', '').strip()

            def _fresh_captcha_error(field, msg):
                q, a = generate_captcha()
                request.session['captcha_answer'] = a
                return JsonResponse({
                    'success': False,
                    'errors': {field: [msg]},
                    'captcha_question': q,
                }, status=400)

            if not username_or_email or not password:
                return _fresh_captcha_error('username', 'Username/email and password required.')

            # Verify captcha
            session_answer = request.session.get('captcha_answer')
            try:
                if int(captcha) != int(session_answer):
                    return _fresh_captcha_error('captcha', 'Incorrect answer. Try again.')
            except (ValueError, TypeError):
                return _fresh_captcha_error('captcha', 'Invalid answer. Enter a number.')

            # Allow login by email
            if '@' in username_or_email:
                try:
                    username_or_email = User.objects.get(
                        email=username_or_email
                    ).username
                except User.DoesNotExist:
                    pass

            user = authenticate(request, username=username_or_email, password=password)

            if user is None:
                return _fresh_captcha_error('username', 'Invalid username/email or password.')

            if not user.is_active:
                return _fresh_captcha_error(
                    'username', 'Account inactive. Please verify your email first.'
                )

            if not user.profile.email_verified:
                return _fresh_captcha_error(
                    'username', 'Email not verified. Check your inbox for verification link.'
                )

            # ── Single-device enforcement ─────────────────────────────────────────────────
            profile = user.profile
            if profile.is_logged_in and profile.active_session_key:
                # Check if that session still physically exists in the DB
                still_alive = Session.objects.filter(
                    session_key=profile.active_session_key,
                    expire_date__gte=timezone.now(),
                ).exists()
                if still_alive:
                    return JsonResponse({
                        'success': False,
                        'errors': {
                            'username': [
                                'This account is already logged in on another terminal.'
                            ]
                        },
                    }, status=403)
                else:
                    # Stale flag — previous session expired/browser closed; clear it
                    profile.is_logged_in = False
                    profile.active_session_key = ''
                    profile.save(update_fields=['is_logged_in', 'active_session_key'])

            login(request, user)

            if request.POST.get('remember_me') == 'on':
                request.session.set_expiry(1209600)  # 14 days
            else:
                request.session.set_expiry(900)      # 15 min — inactivity middleware handles logout

            request.session.pop('captcha_answer', None)

            # Mark user as logged in with this session key
            profile.is_logged_in = True
            profile.active_session_key = request.session.session_key
            profile.save(update_fields=['is_logged_in', 'active_session_key'])

            role = user.profile.role
            if role == 'admin' or user.is_superuser:
                redirect_url = 'management:dashboard'
            elif role == 'instructor':
                redirect_url = 'instructor:dashboard'
            elif role == 'finance':
                redirect_url = 'finance:dashboard'
            else:
                redirect_url = 'eduweb:apply'

            return JsonResponse({
                'success': True,
                'message': 'Login successful!',
                'redirect_url': reverse(redirect_url),
            })

    # ── GET — render page ─────────────────────────────────────────────────────
    return render(request, 'auth.html', {
        'signup_form':      SignUpForm(),
        'login_form':       LoginForm(),
        'captcha_question': captcha_question,
    })


def user_logout(request):
    user = request.user
    if user.is_authenticated:
        try:
            profile = user.profile
            profile.is_logged_in = False
            profile.active_session_key = ''
            profile.save(update_fields=['is_logged_in', 'active_session_key'])
        except Exception:
            pass

    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('eduweb:auth_page')

@login_required
def resend_verification(request):
    """Resend the email-verification link."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    user = request.user
    if not user.profile.email_verified:
        user.profile.generate_verification_token()
        send_verification_email(request, user)
        return JsonResponse({
            'success': True,
            'message': 'Verification email has been resent. Please check your inbox.',
        })
    return JsonResponse({'success': False, 'message': 'Your email is already verified.'})


# ─── Password reset ───────────────────────────────────────────────────────────

def forgot_password(request):
    """Display forgot-password form and dispatch reset email."""
    if request.user.is_authenticated:
        return redirect('eduweb:index')

    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email, is_active=True)
                if not send_password_reset_email(request, user):
                    logger.error("Password reset email failed silently for %s", email)
            except User.DoesNotExist:
                pass  # Silent — do not reveal whether the account exists

            # Always show the same success screen to prevent email enumeration
            return render(request, 'forgot_password.html', {
                'form': form,
                'email_sent': True,
                'submitted_email': request.POST.get('email', ''),
            })
        return render(request, 'forgot_password.html', {'form': form})

    return render(request, 'forgot_password.html', {'form': PasswordResetRequestForm()})


def reset_password(request, token):
    """Validate reset token and let the user set a new password."""
    try:
        profile = UserProfile.objects.get(password_reset_token=token)
    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('eduweb:forgot_password')

    if not profile.is_reset_token_valid():
        profile.clear_reset_token()
        messages.error(request, 'This reset link has expired. Please request a new one.')
        return redirect('eduweb:forgot_password')

    user = profile.user

    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.save()
            profile.clear_reset_token()
            messages.success(
                request,
                'Your password has been reset successfully. You can now log in.',
            )
            return redirect('eduweb:auth_page')
        return render(request, 'reset_password.html', {'form': form, 'token': token})

    return render(request, 'reset_password.html', {
        'form': SetNewPasswordForm(), 'token': token,
    })

@check_for_auth
def products(request):
    # Replace Project with your actual model name when ready
    # projects = Project.objects.filter(is_active=True).order_by('order')
    return render(request, 'products.html', {
        'projects': [],  # swap [] for the queryset above when the model exists
    })


# =============================================================================
# PUBLIC PAGES
# =============================================================================

@check_for_auth
def index(request):
    from .models import Testimonial
    captcha_question, captcha_answer = generate_captcha()
    request.session['contact_captcha_answer'] = captcha_answer
    return render(request, 'index.html', {
        'featured_programs': (
            Program.objects
            .filter(is_active=True, is_featured=True)
            .select_related('department__faculty')
            .order_by('name')[:6]
        ),
        'faculties': (
            Faculty.objects
            .filter(is_active=True)
            .prefetch_related('departments')
            .order_by('name')[:6]
        ),
        'testimonials': Testimonial.objects.filter(is_active=True).order_by('order'),
        'recent_posts': (
            BlogPost.objects
            .filter(status='published')
            .order_by('-publish_date')[:6]
        ),
        'captcha_question': captcha_question,
    })


@check_for_auth
def about(request):
    from .models import InstitutionMember, SiteConfig, SiteHistoryMilestone, InstitutionPartner
    partners_qs = InstitutionPartner.objects.filter(is_active=True)
    return render(request, 'about.html', {
        'faculties': Faculty.objects.filter(is_active=True).order_by('name'),
        'admin_board_members': (
            InstitutionMember.objects.filter(member_type='admin_board', is_active=True)
            .order_by('name')
        ),
        'academic_board_members': (
            InstitutionMember.objects.filter(member_type='academic_board', is_active=True)
            .order_by('name')
        ),
        'advisorate_board_members': (
            InstitutionMember.objects.filter(member_type='advisorate_board', is_active=True)
            .order_by('name')
        ),
        'staff_members': (
            InstitutionMember.objects.filter(member_type='staff', is_active=True)
            .order_by('name')
        ),
        'history_milestones': (
            SiteHistoryMilestone.objects.filter(is_active=True)
            .order_by('year')
        ),
        'partners_list':      partners_qs.filter(category='partner'),
        'affiliations_list':  partners_qs.filter(category='affiliation'),
        'accreditations_list': partners_qs.filter(category='accreditation'),
    })

@check_for_auth
def all_programs(request):
    faculties = (
        Faculty.objects
        .filter(is_active=True)
        .prefetch_related(
            Prefetch(
                'departments',
                queryset=Department.objects.filter(is_active=True).prefetch_related(
                    Prefetch(
                        'programs',
                        queryset=Program.objects.filter(is_active=True)
                                        .order_by('name'),
                    )
                ).order_by('name'),
            )
        )
        .order_by('name')
    )
    return render(request, 'all_programs.html', {'faculties': faculties})

@check_for_auth
def contact(request):
    captcha_question, captcha_answer = generate_captcha()
    request.session['contact_captcha_answer'] = captcha_answer
    return render(request, 'contact.html', {
        'captcha_question': captcha_question,
    })

@check_for_auth
def activities(request):
    return render(request, 'activities.html')


@check_for_auth
def research(request):
    return render(request, 'research.html')


@check_for_auth
def campus_life(request):
    return render(request, 'campus_life.html')


@check_for_auth
def detail(request):
    return render(request, 'detail.html')


@check_for_auth
def admission_course(request):
    return render(request, 'course.html')


@check_for_auth
def admission_requirement(request):
    return render(request, 'admission_requirement.html')


@check_for_auth
def blank_page(request):
    return render(request, 'blank_page.html')


# =============================================================================
# BLOG
# =============================================================================

@check_for_auth
def blog(request):
    """Blog listing with category filter, search, and pagination."""
    posts = (
        BlogPost.objects
        .filter(status='published')
        .select_related('category', 'author')
    )

    category_slug = request.GET.get('category', '')
    if category_slug:
        posts = posts.filter(category__slug=category_slug)

    search_query = request.GET.get('search', '')
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query)    |
            Q(excerpt__icontains=search_query)  |
            Q(content__icontains=search_query)
        )

    posts = posts.order_by('-publish_date')

    featured_post = (
        BlogPost.objects
        .filter(status='published', is_featured=True)
        .order_by('-publish_date')
        .first()
    )

    paginator = Paginator(posts, 9)
    page_obj  = paginator.get_page(request.GET.get('page', 1))
    categories = BlogCategory.objects.filter(is_active=True).order_by('name')

    return render(request, 'blog/blog_list.html', {
        'posts':            page_obj,
        'featured_post':    featured_post,
        'categories':       categories,
        'current_category': category_slug,
        'search_query':     search_query,
    })


@check_for_auth
def blog_detail(request, slug):
    post = get_object_or_404(
        BlogPost.objects.select_related('category', 'author'),
        slug=slug,
        status='published',
    )
    post.increment_views()
    return render(request, 'blog/blog_detail.html', {
        'post':          post,
        'related_posts': post.get_related_posts(limit=3),
        'categories':    BlogCategory.objects.filter(is_active=True).order_by('name'),
    })


@check_for_auth
def blog_category(request, slug):
    category = get_object_or_404(BlogCategory, slug=slug, is_active=True)
    posts = (
        BlogPost.objects
        .filter(status='published', category=category)
        .select_related('author')
        .order_by('-publish_date')
    )
    paginator = Paginator(posts, 9)
    return render(request, 'blog/blog_category.html', {
        'posts':            paginator.get_page(request.GET.get('page', 1)),
        'categories':       BlogCategory.objects.filter(is_active=True).order_by('name'),
        'current_category': category,
    })


# =============================================================================
# CONTACT FORM
# =============================================================================

@check_for_auth
def contact_submit(request):
    if request.method != 'POST':
        return redirect('index')

    # ── CAPTCHA verification ──────────────────────────────────────────────────
    session_answer = request.session.get('contact_captcha_answer')
    user_answer    = request.POST.get('captcha', '').strip()

    def _captcha_fail(msg):
        new_question, new_answer = generate_captcha()
        request.session['contact_captcha_answer'] = new_answer
        messages.error(request, msg)
        return render(request, 'contact.html', {
            'form': ContactForm(request.POST),
            'captcha_question': new_question,
        })

    try:
        if int(user_answer) != int(session_answer):
            return _captcha_fail('Incorrect answer. Please try the bot check again.')
    except (ValueError, TypeError):
        return _captcha_fail('Invalid answer. Please enter a number.')

    # Clear used captcha
    request.session.pop('contact_captcha_answer', None)
    # ─────────────────────────────────────────────────────────────────────────

    form = ContactForm(request.POST)
    if form.is_valid():
        contact_message = form.save()
        admin_sent = send_admin_email(contact_message)
        user_sent  = send_user_confirmation_email(contact_message)

        if admin_sent and user_sent:
            messages.success(
                request,
                'Thank you for contacting us! A confirmation email has been sent to your inbox.',
            )
        else:
            messages.success(
                request,
                'Thank you for contacting us! We have received your message and will get back to you soon.',
            )
        return redirect('eduweb:contact')

    # Re-generate captcha on form validation failure too
    new_question, new_answer = generate_captcha()
    request.session['contact_captcha_answer'] = new_answer
    messages.error(request, 'Please correct the errors below.')
    return render(request, 'contact.html', {'form': form, 'captcha_question': new_question})


# =============================================================================
# FACULTY & PROGRAM PAGES
# =============================================================================
@check_for_auth
def faculty_detail(request, slug):
    """
    Faculty detail: Faculty → Departments → Programs → Courses
    """
    faculty = get_object_or_404(Faculty, slug=slug, is_active=True)
    departments = (
        faculty.departments
        .filter(is_active=True)
        .prefetch_related(
            Prefetch(
                'programs',
                queryset=Program.objects.filter(is_active=True).prefetch_related(
                    Prefetch(
                        'courses',
                        queryset=Course.objects.filter(is_active=True)
                                        .order_by('year_of_study', 'semester'),
                        to_attr='active_courses',
                    )
                ).order_by('name'),
                to_attr='active_programs',
            )
        )
        .order_by('name')
    )
    return render(request, 'faculty_detail.html', {
        'faculty':     faculty,
        'departments': departments,
    })


@check_for_auth
def program_detail(request, slug):
    """Program detail: program info, courses grouped by year/semester, intakes."""
    program = get_object_or_404(
        Program.objects.select_related('department', 'department__faculty'),
        slug=slug,
        is_active=True,
    )
    return render(request, 'program_detail.html', {
        'program':        program,
        'courses': (
            program.courses
            .filter(is_active=True)
            # .select_related('lecturer')
            .order_by('year_of_study', 'semester', 'name')
        ),
        'active_intakes': (
            program.intakes
            .filter(is_active=True)
            .order_by('-year', 'intake_period')
        ),
        'department': program.department,
        'faculty':    program.department.faculty,
    })


# =============================================================================
# APPLICATION — FORM
# =============================================================================

@login_required
@smart_redirect_applicant
def apply(request):
    """Multi-step course application form."""

    if not request.user.profile.email_verified:
        messages.warning(request, 'Please verify your email before applying.')
        return redirect('eduweb:auth_page')

    existing = CourseApplication.objects.filter(
        user=request.user,
        status__in=[
            'draft', 'pending_payment', 'payment_complete',
            'documents_uploaded', 'under_review',
        ],
    ).first()
    if existing:
        messages.info(request, 'You already have an application in progress.')
        return redirect('eduweb:application_status')

    programs  = (
        Program.objects
        .filter(is_active=True)
        .select_related('department__faculty')
        .order_by('department__faculty__name', 'name')
    )
    faculties = Faculty.objects.filter(is_active=True)
    countries = ListOfCountry.objects.order_by('country')

    # Build JSON for JS-driven dynamic dropdowns
    courses_by_faculty = {}
    for prog in programs:
        faculty_name = prog.department.faculty.name
        courses_by_faculty.setdefault(faculty_name, [])
        courses_by_faculty[faculty_name].append({
            'id':                    prog.id,
            'name':                  prog.name,
            'code':                  prog.code,
            'degree_level':          prog.degree_level,
            'available_study_modes': prog.available_study_modes,
            'application_fee':       str(prog.application_fee),
            'tuition_fee':           str(prog.tuition_fee),
        })
    courses_json = json.dumps(courses_by_faculty, cls=DjangoJSONEncoder)

    if request.method == 'POST':
        form = CourseApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                application = form.save(commit=False)
                application.user = request.user

                # Build academic history from dynamic POST fields
                academic_history = []
                entry_count = 1
                while True:
                    education_level = request.POST.get(f'education_level_{entry_count}')
                    if not education_level:
                        break
                    academic_history.append({
                        'degree':          education_level,
                        'institution':     request.POST.get(f'institution_{entry_count}', '').strip(),
                        'field_of_study':  request.POST.get(f'field_of_study_{entry_count}', '').strip(),
                        'graduation_year': request.POST.get(f'graduation_year_{entry_count}', '').strip(),
                        'gpa':             request.POST.get(f'gpa_{entry_count}', '').strip(),
                    })
                    entry_count += 1

                application.status = 'draft'
                application.save()

                # Optional document uploads
                file_field_mapping = {
                    'transcript_file':      'transcript',
                    'certificate_file':     'certificate',
                    'english_test_file':    'other',
                    'id_document_file':     'id_document',
                    'cv_file':              'cv',
                    'recommendation_file':  'recommendation',
                }
                for field_name, file_type in file_field_mapping.items():
                    if field_name in request.FILES:
                        f = request.FILES[field_name]
                        ApplicationDocument.objects.create(
                            application=application,
                            file=f,
                            file_type=file_type,
                            original_filename=f.name,
                            file_size=f.size,
                        )

                # Send confirmation emails in a background thread
                def _send_emails():
                    send_application_confirmation_email(application)
                    send_application_admin_notification(application)
                Thread(target=_send_emails, daemon=True).start()

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success':        True,
                        'application_id': application.application_id,
                        'redirect_url':   reverse('eduweb:application_status'),
                    })

                messages.success(
                    request,
                    f'Application saved! Your reference: {application.application_id}',
                )
                return redirect('eduweb:application_status')

            except Exception as exc:
                logger.exception("apply view — error saving application")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': str(exc)}, status=500)
                messages.error(request, f'An error occurred: {exc}')

        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, 'Please correct the errors highlighted in the form.')

    else:
        form = CourseApplicationForm(
            initial={'email': request.user.email} if request.user.is_authenticated else {}
        )

    from eduweb.models import AcademicSession
    academic_sessions = AcademicSession.objects.filter(
        status__in=['active', 'upcoming']
    ).order_by('-name')

    return render(request, 'form.html', {
        'form':              form,
        'courses':           programs,
        'faculties':         faculties,
        'courses_json':      courses_json,
        'countries':         countries,
        'academic_sessions': academic_sessions,
    })


# =============================================================================
# APPLICATION — STATUS, LETTER, SUBMIT, ACCEPT
# =============================================================================

@smart_redirect_applicant
@login_required(login_url='eduweb:auth_page')
def application_status(request):
    """Show the most recent application for the logged-in user."""
    application = (
        CourseApplication.objects
        .filter(Q(email=request.user.email) | Q(user=request.user))  # fallback if email drifted
        .order_by('-created_at')
        .first()
    )
    return render(request, 'applications/application_status.html', {
        'application': application,
    })


@login_required(login_url='eduweb:auth_page')
def admission_letter(request, application_id):
    """
    Display the admission letter.
    Accessible by the application owner and admin/staff.
    Only available when the application status is 'approved'.
    """
    application = get_object_or_404(CourseApplication, application_id=application_id)

    user     = request.user
    is_owner = application.user == user or application.email == user.email
    is_admin = user.is_staff or user.is_superuser

    if not (is_owner or is_admin):
        return HttpResponseForbidden("You don't have permission to view this letter.")

    if application.status != 'approved':
        messages.warning(request, 'Admission letter is only available for approved applications.')
        if is_admin:
            return redirect('management:application_detail', application.application_id)
        return redirect('eduweb:application_status')

    return render(request, 'applications/admission_letter.html', {'application': application})


@login_required(login_url='eduweb:auth_page')
def submit_application(request, application_id):
    """
    Formally submit an application for admissions review.
    Requires at least one uploaded document.
    """
    if request.method != 'POST':
        return redirect('eduweb:application_status')

    application = get_application_secure(application_id, request.user)
    if not application:
        messages.error(request, 'Application not found or you do not have permission to access it.')
        return redirect('eduweb:application_status')

    if not application.documents.exists():
        messages.error(request, 'Please upload required documents before submission.')
        return redirect('eduweb:application_status')

    if application.status not in ['draft', 'payment_complete', 'documents_uploaded']:
        messages.warning(
            request,
            f'Application cannot be submitted from status: {application.get_status_display()}',
        )
        return redirect('eduweb:application_status')

    if application.mark_as_submitted():
        send_application_submitted_email(application)
        messages.success(
            request,
            'Application submitted successfully! You will receive a decision within 4–6 weeks. '
            'Check your email for confirmation.',
        )
    else:
        messages.error(request, 'Unable to submit application. Please ensure all requirements are met.')

    return redirect('eduweb:application_status')


@login_required(login_url='eduweb:auth_page')
def accept_admission(request, application_id):
    """Student accepts an approved admission offer."""
    if request.method != 'POST':
        return redirect('eduweb:application_status')

    application = get_application_secure(application_id, request.user)
    if not application:
        messages.error(request, 'Application not found or you do not have permission to access it.')
        return redirect('eduweb:application_status')

    if application.status != 'approved':
        messages.error(request, 'Only approved applications can be accepted.')
        return redirect('eduweb:application_status')

    if application.admission_accepted:
        messages.info(request, 'You have already accepted this admission offer.')
        return redirect('eduweb:application_status')

    if application.accept_admission():
        application.issue_admission_number()

        # Sync academic session and entry level to the student's UserProfile
        try:
            profile = application.user.profile
            if application.academic_session:
                profile.admission_session = application.academic_session
            if application.entry_level:
                # entry_level is e.g. 100, 200 ... convert to year_of_study (1, 2 ...)
                profile.year_of_study = application.entry_level // 100
            if application.program:
                profile.program    = application.program
                profile.department = application.program.department
                profile.faculty    = application.program.department.faculty
            profile.save(update_fields=[
                'admission_session', 'year_of_study',
                'program', 'department', 'faculty',
            ])
        except Exception:
            logger.exception("accept_admission — failed to sync profile fields")

        send_admission_offer_accepted_email(application)
        messages.success(
            request,
            f'Admission accepted successfully! Your admission number is {application.admission_number}. '
            'Awaiting department approval to access the student portal.',
        )
    else:
        messages.error(request, 'Unable to accept admission at this time. Please contact support.')

    return redirect('eduweb:application_status')


# =============================================================================
# APPLICATION — DRAFT SAVE (AJAX)
# =============================================================================

@login_required
def save_application_draft(request):
    """
    Save or update a CourseApplication draft via FormData (AJAX POST).
    Called by the multi-step form on the final Save & Continue step.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        data = request.POST

        # Guard: reject if user already has an in-processing application
        if CourseApplication.objects.filter(user=request.user, in_processing=True).exists():
            return redirect('eduweb:application_status')

        # Get or create the draft
        application_id = data.get('application_id', '').strip()
        application = None
        if application_id:
            application = CourseApplication.objects.filter(
                application_id=application_id,
                user=request.user,
                status='draft',
            ).first()

        if not application:
            application = CourseApplication(user=request.user)

        # 1. Course & Intake
        program_id = data.get('program')
        if program_id:
            try:
                application.program = Program.objects.get(id=program_id, is_active=True)
            except Program.DoesNotExist:
                pass

        session_id = data.get('academic_session')
        if session_id:
            try:
                from eduweb.models import AcademicSession
                application.academic_session = AcademicSession.objects.get(id=session_id)
            except AcademicSession.DoesNotExist:
                pass

        entry_level = data.get('entry_level')
        if entry_level:
            try:
                application.entry_level = int(entry_level)
            except (ValueError, TypeError):
                pass

        application.study_mode = data.get('study_mode', '')

        # 2. Personal Information
        application.first_name  = data.get('first_name', '').strip()
        application.last_name   = data.get('last_name', '').strip()
        application.email       = data.get('email', '').strip().lower()
        application.phone       = data.get('phone', '').strip()
        application.gender      = data.get('gender', '')
        application.nationality = data.get('nationality', '')

        dob = data.get('date_of_birth', '')
        if dob:
            try:
                application.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError:
                pass

        # 3. Address
        application.address_line1 = data.get('address_line1', '').strip()
        application.address_line2 = data.get('address_line2', '').strip()
        application.city          = data.get('city', '').strip()
        application.state         = data.get('state', '').strip()
        application.postal_code   = data.get('postal_code', '').strip()
        application.country       = data.get('country', '')

        # 4. Academic Background
        application.highest_qualification = (
            data.get('highest_qualification', '').strip()
            or data.get('education_level_1', '').strip()
        )
        application.institution_name = (
            data.get('institution_name', '').strip()
            or data.get('institution_1', '').strip()
        )
        application.graduation_year = (
            data.get('graduation_year', '').strip()
            or data.get('graduation_year_1', '').strip()
        )
        application.gpa_or_grade = (
            data.get('gpa_or_grade', '').strip()
            or data.get('gpa_1', '').strip()
        )

        # 5. Language Proficiency
        application.language_skill = data.get('language_skill', '') or None
        lang_score_raw = data.get('language_score', '').strip()
        if lang_score_raw:
            try:
                application.language_score = float(lang_score_raw)
            except ValueError:
                pass
        else:
            application.language_score = None

        # 6. Academic History JSON (from JS serialisation)
        academic_history_raw = data.get('academic_history', '')
        if academic_history_raw:
            try:
                application.academic_history_json = json.loads(academic_history_raw)
            except (json.JSONDecodeError, ValueError):
                pass

        # 7. Additional Information
        work_exp = data.get('work_experience_years', '0').strip()
        try:
            application.work_experience_years = int(work_exp) if work_exp else 0
        except ValueError:
            application.work_experience_years = 0

        application.personal_statement     = data.get('personal_statement', '').strip()
        application.how_did_you_hear        = data.get('how_did_you_hear', '')
        application.how_did_you_hear_other  = data.get('how_did_you_hear_other', '').strip()

        # 8. Privacy & Consent
        def _bool(val):
            return val in ('true', 'on', '1', 'True')

        application.accept_privacy_policy   = _bool(data.get('accept_privacy_policy'))
        application.accept_terms_conditions = _bool(data.get('accept_terms_conditions'))
        application.marketing_consent       = _bool(data.get('marketing_consent'))
        application.scholarship             = _bool(data.get('scholarship'))

        # 9. Emergency Contact
        application.emergency_contact_name         = data.get('emergency_contact_name', '').strip()
        application.emergency_contact_phone        = data.get('emergency_contact_phone', '').strip()
        application.emergency_contact_relationship = data.get('emergency_contact_relationship', '').strip()
        application.emergency_contact_email        = data.get('emergency_contact_email', '').strip()
        application.emergency_contact_address      = data.get('emergency_contact_address', '').strip()

        # 10. Save
        application.status = 'draft'
        application.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success':        True,
                'application_id': application.application_id,
                'redirect_url':   reverse('eduweb:application_status'),
            })

        return redirect('eduweb:application_status')

    except Exception as exc:
        logger.exception("save_application_draft failed")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        messages.error(request, f'Could not save your application: {exc}')
        return redirect('eduweb:apply')


# =============================================================================
# APPLICATION — DOCUMENT UPLOAD (AJAX)
# =============================================================================

@login_required(login_url='eduweb:auth_page')
def upload_application_file(request, application_id):
    """Upload a document for an application via AJAX POST."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    application = get_application_secure(application_id, request.user)
    if not application:
        return JsonResponse({'success': False, 'error': 'Application not found or access denied'})

    if application.status not in ['draft', 'payment_complete', 'documents_uploaded', 'under_review']:
        return JsonResponse({
            'success': False,
            'error':   'Document upload is not available for this application status.',
        })

    file_type   = request.POST.get('file_type')
    file        = request.FILES.get('file')
    auto_submit = request.POST.get('auto_submit') == 'true'

    if not file_type or not file:
        return JsonResponse({'success': False, 'error': 'Both file type and file are required'})

    # Size check: 5 MB
    if file.size > 5 * 1024 * 1024:
        return JsonResponse({
            'success': False,
            'error':   f'File size exceeds 5 MB limit. Your file is {file.size / 1024 / 1024:.2f} MB.',
        })

    # Extension check
    allowed = ['.pdf', '.jpg', '.jpeg', '.png']
    if not any(file.name.lower().endswith(ext) for ext in allowed):
        return JsonResponse({
            'success': False,
            'error':   'Invalid file type. Only PDF, JPG, and PNG files are allowed.',
        })

    try:
        document = ApplicationDocument.objects.create(
            application=application,
            file_type=file_type,
            file=file,
            original_filename=file.name,
            file_size=file.size,
        )

        if application.status in ['draft', 'payment_complete']:
            application.status = 'documents_uploaded'
            application.save(update_fields=['status'])

        send_document_upload_confirmation(application, document)
        send_document_upload_admin_notification(application, document)

        if auto_submit:
            application.mark_as_submitted()

        return JsonResponse({
            'success':     True,
            'message':     'Document uploaded successfully',
            'document_id': document.id,
            'filename':    document.original_filename,
            'file_size':   document.get_file_size_display(),
        })

    except Exception as e:
        logger.exception("upload_application_file failed")
        return JsonResponse({'success': False, 'error': f'Upload failed: {e}'})


# =============================================================================
# PAYMENTS
# =============================================================================

@login_required
def payments(request):
    return render(request, 'payments.html')


@login_required
def stddebt_by_id(request):
    """Display payment details for all outstanding payments."""
    return render(request, 'students/allpayments/paymentdetails.html')


@require_GET
@login_required
def get_payment_summary(request, application_id=None, student_fee_id=None):
    """Return payment summary JSON for either a student fee or an application."""
    try:
        if student_fee_id:
            fee = get_object_or_404(
                AllRequiredPayments.objects.select_related(
                    'program', 'program__department__faculty'
                ),
                id=student_fee_id,
                is_active=True,
            )
            data = {
                'full_name':        request.user.get_full_name() or 'Student',
                'amount':           float(fee.amount),
                'currency':         'USD',
                'purpose':          fee.purpose,
                'description':      fee.purpose,
                'student_fee_id':   fee.id,
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
            }

        elif application_id:
            application = CourseApplication.objects.select_related(
                'program', 'program__department__faculty'
            ).get(application_id__iexact=application_id)
            data = {
                'full_name':        f"{application.first_name} {application.last_name}",
                'application_id':   application.application_id,
                'amount':           float(application.program.application_fee) if application.program else 0,
                'currency':         'USD',
                'description':      'Application Processing Fee',
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
            }

        else:
            return JsonResponse({'success': False, 'error': 'No valid identifier provided.'})

        return JsonResponse({'success': True, 'data': data})

    except CourseApplication.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Application not found.'})
    except Exception as e:
        logger.exception("get_payment_summary failed")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def get_student_fee_summary(request, fee_pk):
    """Return JSON summary for a single student fee (used by the payment modal)."""
    try:
        fee = AllRequiredPayments.objects.select_related(
            'faculty', 'department'
        ).get(pk=fee_pk, is_active=True)
    except AllRequiredPayments.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)

    return JsonResponse({
        'success': True,
        'data': {
            'full_name':         request.user.get_full_name() or request.user.username,
            'purpose':           fee.purpose,
            'amount':            float(fee.amount),
            'currency':          'NGN',
            'stripe_public_key': settings.STRIPE_PUBLISHABLE_KEY,
        },
    })


@require_POST
@login_required
def create_payment_intent(request):
    """Create a Stripe PaymentIntent for either a student fee or an application."""
    try:
        payload = request.body.decode('utf-8')
        if not payload:
            return JsonResponse({'success': False, 'error': 'Empty request body'}, status=400)

        data            = json.loads(payload)
        application_id  = data.get('application_id')
        student_fee_id  = data.get('student_fee_id')

        if not application_id and not student_fee_id:
            return JsonResponse(
                {'success': False, 'error': 'Provide application_id or student_fee_id'},
                status=400,
            )

        with transaction.atomic():

            # ── Student fee ───────────────────────────────────────────────────
            if student_fee_id:
                fee           = get_object_or_404(AllRequiredPayments, id=student_fee_id, is_active=True)
                amount_pence  = int(fee.amount * Decimal('100'))

                existing = FeePayment.objects.filter(
                    fee=fee, user=request.user
                ).select_for_update().first()

                if existing:
                    if existing.status == 'success':
                        return JsonResponse({'success': False, 'error': 'Payment already made'}, status=400)
                    if existing.status == 'pending':
                        intent = stripe.PaymentIntent.retrieve(existing.gateway_payment_id)
                        return JsonResponse({'success': True, 'clientSecret': intent.client_secret})

                intent = stripe.PaymentIntent.create(
                    amount=amount_pence,
                    currency='usd',
                    metadata={
                        'type':           'student_fee',
                        'student_fee_id': str(fee.id),
                        'purpose':        fee.purpose,
                        'user_id':        request.user.id,
                    },
                    automatic_payment_methods={'enabled': True},
                )
                FeePayment.objects.create(
                    fee=fee,
                    user=request.user,
                    gateway_payment_id=intent.id,
                    amount=fee.amount,
                    currency='USD',
                    status='pending',
                    payment_metadata={
                        'type':           'student_fee',
                        'student_fee_id': str(fee.id),
                        'purpose':        fee.purpose,
                    },
                )
                return JsonResponse({'success': True, 'clientSecret': intent.client_secret})

            # ── Application payment ───────────────────────────────────────────
            if application_id:
                application  = get_object_or_404(
                    CourseApplication,
                    application_id__iexact=application_id,
                    user=request.user,
                )
                if application.is_paid:
                    return JsonResponse({'success': False, 'error': 'Application already paid'}, status=400)

                amount_pence = int(application.program.application_fee * Decimal('100'))

                existing = ApplicationPayment.objects.filter(
                    application=application
                ).select_for_update().first()

                if existing:
                    if existing.status == 'success':
                        return JsonResponse({'success': False, 'error': 'Payment already made'}, status=400)
                    if existing.status == 'pending':
                        intent = stripe.PaymentIntent.retrieve(existing.gateway_payment_id)
                        return JsonResponse({'success': True, 'clientSecret': intent.client_secret})

                intent = stripe.PaymentIntent.create(
                    amount=amount_pence,
                    currency='gbp',
                    metadata={
                        'application_id': application.application_id,
                        'user_id':        request.user.id,
                    },
                    automatic_payment_methods={'enabled': True},
                )
                ApplicationPayment.objects.create(
                    application=application,
                    gateway_payment_id=intent.id,
                    amount=application.program.application_fee,
                    currency='USD',
                    status='pending',
                )
                return JsonResponse({'success': True, 'clientSecret': intent.client_secret})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except stripe.error.StripeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception:
        logger.exception("create_payment_intent failed")
        return JsonResponse({'success': False, 'error': 'Unable to create payment'}, status=500)


@require_POST
@login_required
def confirm_payment(request):
    """
    Confirm a Stripe payment after the client-side flow completes.
    Handles both student-fee and application payment types.
    Always returns JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    payment_intent_id = data.get('payment_intent_id')
    if not payment_intent_id:
        return JsonResponse({'success': False, 'error': 'Missing payment_intent_id'}, status=400)

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    if intent.status != 'succeeded':
        return JsonResponse({'success': False, 'error': 'Payment not successful'}, status=400)

    metadata     = intent.metadata or {}
    payment_type = metadata.get('type')

    # ── Student fee ───────────────────────────────────────────────────────────
    if payment_type == 'student_fee':
        student_fee_id = metadata.get('student_fee_id')
        if not student_fee_id:
            return JsonResponse(
                {'success': False, 'error': 'student_fee_id missing in payment intent'},
                status=400,
            )
        try:
            fee = AllRequiredPayments.objects.get(id=student_fee_id)
        except AllRequiredPayments.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)

        with transaction.atomic():
            payment, created = FeePayment.objects.select_for_update().get_or_create(
                gateway_payment_id=intent.id,
                defaults={
                    'fee':              fee,
                    'user':             request.user,
                    'amount':           Decimal(intent.amount) / Decimal(100),
                    'currency':         intent.currency.upper(),
                    'status':           'success',
                    'paid_at':          timezone.now(),
                    'payment_metadata': metadata,
                },
            )
            if not created and payment.status != 'success':
                payment.status  = 'success'
                payment.paid_at = timezone.now()
                payment.save(update_fields=['status', 'paid_at'])
            
            # ── EMAIL: Certificate fee paid ──────────────────────────────────
            if created and 'certificate' in fee.purpose.lower():
                # Check if there are any pending-payment certificates for this user
                try:
                    pending_cert = Certificate.objects.filter(
                        student=request.user,
                        payment_status='unpaid'
                    ).first()
                    if pending_cert:
                        pending_cert.mark_paid(payment_reference=payment.payment_reference)
                        send_certificate_ready_email(request.user, pending_cert)
                except Exception as e:
                    logger.error("Certificate ready email failed: %s", e)

        return JsonResponse({
            'success':      True,
            'payment_id':   payment.id,
            'redirect_url': '/student/payments/',
            'fee':          fee.id,
            'show_receipt': True,
        })

    # ── Application payment ───────────────────────────────────────────────────
    application_id = metadata.get('application_id')
    if not application_id:
        return JsonResponse(
            {'success': False, 'error': 'Application ID missing in payment intent'},
            status=400,
        )

    try:
        application = CourseApplication.objects.get(
            application_id=application_id, user=request.user
        )
    except CourseApplication.DoesNotExist:
        return JsonResponse(
            {'success': False, 'error': 'Application not found or access denied'},
            status=404,
        )

    # Idempotency: handle duplicate confirm calls (e.g. webhook raced us)
    payment = ApplicationPayment.objects.filter(gateway_payment_id=intent.id).first()
    if payment:
        if not payment.paid_at:
            payment.paid_at = timezone.now()
            payment.save(update_fields=['paid_at'])
        if application.status in ['draft', 'pending_payment']:
            application.status         = 'payment_complete'
            application.payment_status = 'success'
            application.save(update_fields=['status', 'payment_status'])
        return JsonResponse({
            'success':      True,
            'payment_id':   payment.id,
            'redirect_url': reverse('eduweb:application_status'),
        })

    with transaction.atomic():
        payment, created = ApplicationPayment.objects.select_for_update().get_or_create(
            gateway_payment_id=intent.id,
            defaults={
                'application':      application,
                'amount':           Decimal(intent.amount) / Decimal(100),
                'currency':         intent.currency.upper(),
                'status':           'success',
                'paid_at':          timezone.now(),
                'payment_metadata': metadata,
            },
        )
        if not created and payment.status != 'success':
            payment.status  = 'success'
            payment.paid_at = timezone.now()
            payment.save(update_fields=['status', 'paid_at'])

        application.status         = 'payment_complete'
        application.payment_status = 'success'
        application.save(update_fields=['status', 'payment_status'])

    return JsonResponse({
        'success':      True,
        'payment_id':   payment.id,
        'redirect_url': reverse('eduweb:application_status'),
    })


@login_required
def payment_data(request, payment_id):
    """Return JSON data for a specific student fee payment (for receipts)."""
    try:
        payment = FeePayment.objects.get(id=payment_id, user=request.user)
    except FeePayment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Payment not found'})

    fee = payment.fee
    return JsonResponse({
        'success': True,
        'payment': {
            'id':                 payment.id,
            'amount':             float(payment.amount),
            'currency':           payment.currency,
            'paid_at':            payment.paid_at.isoformat(),
            'gateway_payment_id': payment.gateway_payment_id,
        },
        'fee': {
            'id':   fee.id,
            'name': str(fee),
        },
    })


# =============================================================================
# STRIPE WEBHOOK
# =============================================================================

@csrf_exempt
def stripe_webhook(request):
    """
    Stripe webhook endpoint.
    Handles payment_intent.succeeded for both student-fee and application payments.
    Uses select_for_update + get_or_create for idempotency.
    """
    payload    = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.warning("Stripe webhook verification failed: %s", e)
        return HttpResponse(status=400)

    if event['type'] == 'payment_intent.succeeded':
        intent       = event['data']['object']
        metadata     = intent.get('metadata', {})
        payment_type = metadata.get('type')

        # ── Student fee ───────────────────────────────────────────────────────
        if payment_type == 'student_fee':
            student_fee_id = metadata.get('student_fee_id')
            if not student_fee_id:
                return HttpResponse(status=200)
            try:
                fee = AllRequiredPayments.objects.get(id=student_fee_id)
            except AllRequiredPayments.DoesNotExist:
                return HttpResponse(status=200)

            with transaction.atomic():
                payment, created = FeePayment.objects.select_for_update().get_or_create(
                    gateway_payment_id=intent['id'],
                    defaults={
                        'fee':              fee,
                        'user_id':          metadata.get('user_id'),
                        'amount':           Decimal(intent['amount']) / Decimal(100),
                        'currency':         intent['currency'].upper(),
                        'status':           'success',
                        'paid_at':          timezone.now(),
                        'payment_metadata': metadata,
                    },
                )
                if not created and payment.status == 'success':
                    return HttpResponse(status=200)
                payment.status  = 'success'
                payment.paid_at = timezone.now()
                payment.save()

        # ── Application payment ───────────────────────────────────────────────
        elif payment_type == 'application':
            application_id = metadata.get('application_id')
            if not application_id:
                return HttpResponse(status=200)
            try:
                application = CourseApplication.objects.get(application_id=application_id)
            except CourseApplication.DoesNotExist:
                return HttpResponse(status=200)

            with transaction.atomic():
                payment, created = ApplicationPayment.objects.select_for_update().get_or_create(
                    gateway_payment_id=intent['id'],
                    defaults={
                        'application':      application,
                        'amount':           Decimal(intent['amount']) / Decimal(100),
                        'currency':         intent['currency'].upper(),
                        'status':           'success',
                        'paid_at':          timezone.now(),
                        'payment_metadata': metadata,
                    },
                )
                if not created and payment.status == 'success':
                    return HttpResponse(status=200)
                payment.status  = 'success'
                payment.paid_at = timezone.now()
                payment.save()

                application.status         = 'payment_complete'
                application.payment_status = 'success'
                application.save(update_fields=['status', 'payment_status'])

    return HttpResponse(status=200)