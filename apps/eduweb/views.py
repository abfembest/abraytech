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
from functools import lru_cache

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
from django.templatetags.static import static as static_asset_url
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
    send_otp_email,
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
    AuditLog,
    BlogCategory,
    BlogPost,
    Certificate,
    ContactMessage,
    Course,
    CourseApplication,
    CourseIntake,
    DEGREE_LEVEL_CHOICES,
    Department,
    Faculty,
    FeePayment,
    ListOfCountry,
    AllRequiredPayments,
    PaymentGateway,
    Program,
    SystemConfiguration,
    UserProfile,
    decrypt_secret,
)

# ─── Location libs ────────────────────────────────────────────────────────────
import pycountry
import phonenumbers
try:
    import geonamescache
    _gc = geonamescache.GeonamesCache()
    GEONAMES_AVAILABLE = True
except ImportError:
    GEONAMES_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Module-level logger & Stripe key resolution
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


def _get_client_ip(request):
    """Extract real client IP from request, respecting a reverse proxy's
    X-Forwarded-For header when present. Used for security-critical audit
    log entries (login/logout/password changes)."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')



def _active_stripe_gateway() -> "PaymentGateway | None":
    return PaymentGateway.objects.filter(gateway_type='stripe', is_active=True).first()


def get_stripe_secret_key() -> str:
    gw = _active_stripe_gateway()
    decrypted = decrypt_secret(gw.api_secret) if gw else ''
    return decrypted or settings.STRIPE_SECRET_KEY


def get_stripe_public_key() -> str:
    gw = _active_stripe_gateway()
    return (gw.api_key if gw and gw.api_key else settings.STRIPE_PUBLIC_KEY)


def get_stripe_webhook_secret() -> str:
    gw = _active_stripe_gateway()
    decrypted = decrypt_secret(gw.webhook_secret) if gw else ''
    return decrypted or settings.STRIPE_WEBHOOK_SECRET


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


def generate_captcha():
    """Return a (question_str, answer_int) math captcha pair."""
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    op   = random.choice(['+', '-', '*'])
    if op == '+':
        answer = num1 + num2
    elif op == '-':
        # Keep the result non-negative — a negative answer needs a minus-sign
        # key that many mobile numeric keypads don't expose, locking those
        # users out of the captcha entirely.
        if num2 > num1:
            num1, num2 = num2, num1
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
        profile = UserProfile.objects.select_related('user').get(verification_token=token)
    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('eduweb:auth_page')

    user = profile.user

    if user.is_active:
        messages.info(request, 'Your email is already verified.')
        return redirect('eduweb:auth_page')

    if not profile.is_verification_token_valid():
        messages.error(
            request,
            'This verification link has expired. Please request a new one below.',
        )
        return redirect('eduweb:auth_page')

    user.is_active = True
    user.save(update_fields=['is_active'])
    profile.email_verified = True
    profile.save(update_fields=['email_verified'])
    messages.success(request, 'Your email has been verified! You can now log in.')
    send_verification_success_email(user)

    return redirect('eduweb:auth_page')

@login_required(login_url='eduweb:auth_page')
def force_change_password(request):
    """
    AJAX POST — submitted by the force-password modal (force_password_modal.html).
    Uses PasswordChangeForm so the user must supply their temporary password
    before setting a new one. Clears must_change_password flag on success.
    Returns JSON { success, message }.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)

    from django.contrib.auth.forms import PasswordChangeForm

    form = PasswordChangeForm(request.user, request.POST)

    if form.is_valid():
        form.save()
        # Keep the user logged in after password change
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, form.user)

        profile = request.user.profile
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])

        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='User',
            object_id=str(request.user.pk),
            description=f'{request.user.username} changed their password.',
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # Non-fatal — send confirmation email
        try:
            from apps.eduweb.emailservices import send_password_changed_email
            send_password_changed_email(request.user)
        except Exception:
            pass

        return JsonResponse({'success': True, 'message': 'Password updated successfully.'})

    errors = ' '.join(
        str(e)
        for field_errors in form.errors.values()
        for e in field_errors
    )
    return JsonResponse({'success': False, 'message': errors}, status=400)


def _get_first_permitted_url(user):
    """
    Return the first management URL the user has can_view on.
    Only called for admin role and superusers.
    Falls back to management:dashboard for superusers (full access).
    Falls back to eduweb:apply if no module is permitted (misconfigured role).
    """
    from apps.eduweb.models import StaffPermissionsMatrix as _SPM

    if user.is_superuser:
        return reverse('management:dashboard')

    role = getattr(getattr(user, 'profile', None), 'role', None)
    if not role:
        return reverse('eduweb:apply')

    # finance has its own portal — always send there
    if role == 'finance':
        return reverse('finance:dashboard')

    _MODULE_URL_MAP = [
        ('dashboard',       'management:dashboard'),
        ('applications',    'management:applications_list'),
        ('user_management', 'management:users_list'),
        ('academics',       'management:faculties_list'),
        ('lms_courses',     'management:lms_courses_list'),
        ('exams',           'management:admin_exam_list'),
        ('enrollments',     'management:enrollments_list'),
        ('finance',         'management:transactions_list'),
        ('communications',  'management:broadcast_center'),
        ('blog',            'management:blog_posts_list'),
        ('library',         'management:library_items_list'),
        ('site_content',    'management:site_config_general'),
        ('security_audit',  'management:audit_logs_list'),
        ('ticket_management', 'management:ticket_list'),
    ]

    # Role-level defaults
    permitted = set(
        _SPM.objects.filter(role=role, user__isnull=True, can_view=True)
        .values_list('module', flat=True)
    )
    # User-level overrides (can grant or revoke individually)
    for row in _SPM.objects.filter(user=user):
        if row.can_view:
            permitted.add(row.module)
        else:
            permitted.discard(row.module)

    for module, url_name in _MODULE_URL_MAP:
        if module in permitted:
            return reverse(url_name)

    # No permitted module found — role misconfigured in StaffPermissionsMatrix
    return reverse('eduweb:apply')


def _redirect_authenticated_user(request):
    """
    Bounce an already-authenticated visitor away from a public auth page
    (sign-in or sign-up) to wherever their role belongs. Shared by
    auth_page() and signup_page() so both land a logged-in user in the same
    place instead of showing them an auth form.
    """
    if not request.user.is_active:
        logout(request)
        messages.warning(request, 'Your account is inactive. Please verify your email.')
        return None
    if not request.user.profile.email_verified:
        logout(request)
        messages.warning(
            request,
            'Please verify your email to continue. '
            'Check your inbox for the verification link.',
        )
        return None

    messages.info(request, 'You are already logged in.')
    role = request.user.profile.role
    if role == 'admin' or request.user.is_superuser:
        return redirect(_get_first_permitted_url(request.user))
    elif role == 'instructor':
        return redirect('instructor:dashboard')
    elif role == 'finance':
        return redirect('finance:dashboard')
    elif role == 'support':
        return redirect('support:dashboard')
    else:
        return redirect('eduweb:apply')


def auth_page(request):
    """Sign-in page. Sign-up now lives at eduweb:signup_page (program-gated)."""

    # ── Already authenticated ─────────────────────────────────────────────────
    if request.user.is_authenticated:
        redirect_response = _redirect_authenticated_user(request)
        if redirect_response is not None:
            return redirect_response

    # ── CAPTCHA setup ─────────────────────────────────────────────────────────
    if request.method == 'GET':
        captcha_question, captcha_answer = generate_captcha()
        request.session['signin_captcha_answer'] = captcha_answer
    else:
        captcha_answer = request.session.get('signin_captcha_answer')
        if captcha_answer is None:
            captcha_question, captcha_answer = generate_captcha()
            request.session['signin_captcha_answer'] = captcha_answer
            return JsonResponse({
                'success': False,
                'errors': {'captcha': ['Session expired. Please try again.']},
                'captcha_question': captcha_question,
            }, status=400)
        else:
            captcha_question = None

    # ── POST — LOGIN ──────────────────────────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'login':
        # auth.html's login form submits via fetch() with this header so the
        # page can redirect/show errors without a full reload. If that JS
        # doesn't run for any reason (blocked, errored, JS disabled), the
        # browser falls back to a plain form POST — in that case we must not
        # hand back raw JSON as the page body, so success paths below redirect
        # for real instead. Error paths still return JSON status=400, which
        # is an acceptable (if inelegant) fallback since the user can just
        # retry from the page they're already on.
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        username_or_email = request.POST.get('username', '').strip()
        password          = request.POST.get('password', '')
        captcha           = request.POST.get('captcha', '').strip()

        def _fresh_captcha_error(field, msg):
            q, a = generate_captcha()
            request.session['signin_captcha_answer'] = a
            return JsonResponse({
                'success': False,
                'errors': {field: [msg]},
                'captcha_question': q,
            }, status=400)

        if not username_or_email or not password:
            return _fresh_captcha_error('username', 'Username/email and password required.')

        # Verify captcha
        session_answer = request.session.get('signin_captcha_answer')
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

        # ── OTP: generate, email, then hold login until verified ──────────
        otp = str(random.randint(100000, 999999))
        profile.otp_code       = otp      # encrypted via setter
        profile.otp_created_at = timezone.now()
        profile.otp_attempts   = 0
        profile.save(update_fields=['_otp_code', 'otp_created_at', 'otp_attempts'])

        if not send_otp_email(user, otp):
            # Don't claim success and strand the user on a page waiting for
            # a code that was never sent — send_otp_email already logged
            # the underlying SMTP error. Sent synchronously (not
            # backgrounded) so we know for certain before responding —
            # EMAIL_TIMEOUT bounds the worst case instead of hanging.
            return _fresh_captcha_error(
                'username',
                'Could not send your verification code right now. Please try again shortly.',
            )

        # Store pending user in session — actual login() fires after OTP
        # Checkbox is named "remember" in auth.html (not "remember_me") —
        # this was reading the wrong POST key, so "Remember me" silently
        # never took effect; every login got the short 15-minute session.
        request.session['otp_user_id']     = user.pk
        request.session['otp_remember_me'] = request.POST.get('remember') == 'on'
        request.session.pop('signin_captcha_answer', None)

        if not is_ajax:
            messages.success(request, f'A 6-digit code has been sent to {user.email}')
            return redirect('eduweb:otp_verify')

        return JsonResponse({
            'success': True,
            'message': f'A 6-digit code has been sent to {user.email}',
            'redirect_url': reverse('eduweb:otp_verify'),
        })

    # ── GET — render page ─────────────────────────────────────────────────────
    return render(request, 'auth.html', {
        'login_form':       LoginForm(),
        'captcha_question': captcha_question,
    })


def _resolve_intake_eligibility(program, intake):
    """
    Return the reason applying to `program` via `intake` is blocked right
    now ('no_intake' / 'closed' / 'not_open_yet' / 'deadline_passed' /
    'full'), or None if applications are open. signup.html turns the
    reason into user-facing copy. Shared by signup_page()'s GET and POST
    handling so a forged POST is always re-checked against current state,
    never trusted from an earlier GET.
    """
    if intake is None:
        return 'no_intake'
    if not intake.is_active:
        return 'closed'
    today = timezone.now().date()
    if intake.application_start_date and today < intake.application_start_date:
        return 'not_open_yet'
    if today > intake.application_deadline:
        return 'deadline_passed'
    if intake.is_full:
        return 'full'
    return None


def signup_page(request):
    """
    Program-gated sign-up. Only reachable via an Apply/Start-Application
    link carrying ?program=<slug>[&intake=<id>] — a bare visit with no
    ?program bounces to the program catalog, since sign-up with no
    application intent isn't meant to be a directly-linkable page. Renders
    either the real sign-up form or a read-only "not eligible" message
    depending on the resolved intake's status, re-validated on every
    request (GET and POST alike).
    """
    if request.user.is_authenticated:
        redirect_response = _redirect_authenticated_user(request)
        if redirect_response is not None:
            return redirect_response

    program_slug = request.GET.get('program') or request.POST.get('program')
    if not program_slug:
        return redirect('eduweb:all_programs')
    program = get_object_or_404(Program, slug=program_slug, is_active=True)

    intake_id = request.GET.get('intake') or request.POST.get('intake')
    if intake_id and intake_id.isdigit():
        intake = get_object_or_404(CourseIntake, pk=intake_id, program=program)
    else:
        intake = program.get_current_intake()

    blocked_reason = _resolve_intake_eligibility(program, intake)
    if blocked_reason:
        return render(request, 'signup.html', {
            'program': program,
            'intake': intake,
            'blocked_reason': blocked_reason,
        })

    # ── CAPTCHA setup — same convention as auth_page, own session key so a
    #    sign-in tab and a sign-up tab open at once never stomp each other's
    #    displayed number. ────────────────────────────────────────────────
    if request.method == 'GET':
        captcha_question, captcha_answer = generate_captcha()
        request.session['signup_captcha_answer'] = captcha_answer
    else:
        captcha_answer = request.session.get('signup_captcha_answer')
        if captcha_answer is None:
            captcha_question, captcha_answer = generate_captcha()
            request.session['signup_captcha_answer'] = captcha_answer
            return JsonResponse({
                'success': False,
                'errors': {'captcha': ['Session expired. Please try again.']},
                'captcha_question': captcha_question,
            }, status=400)
        else:
            captcha_question = None

    if request.method == 'POST' and request.POST.get('action') == 'signup':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        signup_form = SignUpForm(
            request.POST,
            captcha_answer=request.session.get('signup_captcha_answer'),
        )
        if signup_form.is_valid():
            request.session.pop('signup_captcha_answer', None)
            user = signup_form.save(commit=False)
            user.is_active = False
            user.save()
            AuditLog.objects.create(
                user=user,
                action='create',
                model_name='User',
                object_id=str(user.pk),
                description=f'New account created for {user.username} ({user.email}), pending email verification.',
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            send_verification_email(request, user)
            request.session['apply_program_id'] = program.id
            message = (
                'Account created! Check your email to verify your account '
                'before logging in.'
            )
            if not is_ajax:
                messages.success(request, message)
                return redirect('eduweb:auth_page')
            return JsonResponse({
                'success': True,
                'message': message,
                'email': user.email,
                'redirect_url': reverse('eduweb:auth_page'),
            })
        else:
            new_question, new_answer = generate_captcha()
            request.session['signup_captcha_answer'] = new_answer
            return JsonResponse({
                'success': False,
                'errors': {f: [str(e) for e in errs]
                           for f, errs in signup_form.errors.items()},
                'captcha_question': new_question,
            }, status=400)

    # ── GET, eligible ─────────────────────────────────────────────────────────
    return render(request, 'signup.html', {
        'program':          program,
        'intake':           intake,
        'blocked_reason':   None,
        'signup_form':      SignUpForm(),
        'captcha_question': captcha_question,
    })

from django.http import JsonResponse as jsonresponse

def otp_verify(request):
    """
    intermediate otp verification step.
    session must contain 'otp_user_id' set by the login flow.
    """
    user_id = request.session.get('otp_user_id')
    if not user_id:
        return redirect('eduweb:auth_page')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return redirect('eduweb:auth_page')

    # ── resend (GET ?resend=1) ────────────────────────────────────────────────
    if request.method == 'GET' and request.GET.get('resend') == '1':
        otp = str(random.randint(100000, 999999))
        profile = user.profile
        previous_code, previous_created_at = profile.otp_code, profile.otp_created_at
        profile.otp_code       = otp      # encrypted via setter
        profile.otp_created_at = timezone.now()
        profile.otp_attempts   = 0
        profile.save(update_fields=['_otp_code', 'otp_created_at', 'otp_attempts'])

        if not send_otp_email(user, otp):
            # Roll back to the previous code rather than leaving the DB
            # pointing at one the user was never actually sent.
            profile.otp_code       = previous_code
            profile.otp_created_at = previous_created_at
            profile.save(update_fields=['_otp_code', 'otp_created_at'])
            return JsonResponse({
                'success': False,
                'message': 'Could not send a new code right now. Please try again shortly.',
            }, status=502)

        return JsonResponse({
            'success': True,
            'message': 'new code sent to your email.'
        })

    # ── POST: validate submitted otp ──────────────────────────────────────────
    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        profile = user.profile

        # rate-limit: max 5 attempts
        if profile.otp_attempts >= 5:
            request.session.pop('otp_user_id', None)
            return JsonResponse({
                'success': False,
                'errors': {
                    'otp': ['too many failed attempts. please log in again.']
                },
                'redirect_login': True,
            }, status=429)

        # expiry: 10 minutes
        if not profile.otp_created_at or (
            timezone.now() - profile.otp_created_at
        ).total_seconds() > 600:
            request.session.pop('otp_user_id', None)
            return JsonResponse({
                'success': False,
                'errors': {
                    'otp': ['your code has expired. please log in again.']
                },
                'redirect_login': True,
            }, status=400)

        # wrong code  (profile.otp_code decrypts automatically)
        if entered_otp != profile.otp_code:
            profile.otp_attempts += 1
            profile.save(update_fields=['otp_attempts'])

            remaining = 5 - profile.otp_attempts

            return JsonResponse({
                'success': False,
                'errors': {
                    'otp': [
                        f'incorrect code. {remaining} attempt(s) remaining.'
                    ]
                },
            }, status=400)

        # ── correct — complete login ──────────────────────────────────────────
        profile.otp_code = ''             # setter encrypts empty string
        profile.otp_created_at = None
        profile.otp_attempts = 0

        login(request, user)

        remember_me = request.session.pop('otp_remember_me', False)
        request.session.pop('otp_user_id', None)

        if remember_me:
            request.session.set_expiry(1209600)
        else:
            request.session.set_expiry(900)

        profile.is_logged_in = True
        profile.active_session_key = request.session.session_key

        profile.save(update_fields=[
            '_otp_code',
            'otp_created_at',
            'otp_attempts',
            'is_logged_in',
            'active_session_key',
        ])

        AuditLog.objects.create(
            user=user,
            action='login',
            model_name='User',
            object_id=str(user.pk),
            description=f'{user.username} logged in (OTP verified).',
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        role = user.profile.role

        if role == 'admin' or user.is_superuser:
            redirect_url = _get_first_permitted_url(user)
        elif role == 'instructor':
            redirect_url = reverse('instructor:dashboard')
        elif role == 'finance':
            redirect_url = reverse('finance:dashboard')
        elif role == 'support':
            redirect_url = reverse('support:dashboard')
        else:
            redirect_url = reverse('eduweb:apply')

        return JsonResponse({
            'success': True,
            'message': 'Verification Successful!',
            'redirect_url': redirect_url,
        })

    # ── GET: render otp page ──────────────────────────────────────────────────
    email = user.email or ''

    if '@' in email:
        masked = email[:3] + '****' + email[email.index('@'):]
    else:
        masked = email

    return render(request, 'otp_verify.html', {
        'masked_email': masked,
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

        AuditLog.objects.create(
            user=user,
            action='logout',
            model_name='User',
            object_id=str(user.pk),
            description=f'{user.username} logged out.',
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

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
            AuditLog.objects.create(
                user=user,
                action='update',
                model_name='User',
                object_id=str(user.pk),
                description=f'{user.username} reset their password via the forgot-password link.',
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(
                request,
                'Your password has been reset successfully. You can now log in.',
            )
            return redirect('eduweb:auth_page')
        return render(request, 'reset_password.html', {'form': form, 'token': token})

    return render(request, 'reset_password.html', {
        'form': SetNewPasswordForm(), 'token': token,
    })


# =============================================================================
# ERROR HANDLERS
# =============================================================================

def custom_404(request, exception=None):
    """
    handler404 — registered in config/urls.py, used for any request
    path that doesn't match a URL pattern.

    A logged-in user hitting a stray/broken link (internal or external) is
    far more likely to want their own dashboard than the public 404 page —
    so they're redirected straight there, using the same role → dashboard
    mapping already used by the portal sidebar/breadcrumb's "Home" link
    (management/base.html). Anonymous visitors still get the normal
    templates/404.html page.
    """
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        role = getattr(profile, 'role', None)

        if role == 'student':
            return redirect('students:dashboard')
        if role == 'instructor':
            return redirect('instructor:dashboard')
        if role == 'finance':
            return redirect('finance:dashboard')
        if role == 'support':
            return redirect('support:dashboard')
        # admin role, is_staff, is_superuser, or any other/unrecognised
        # role — same fallback the sidebar's own "Home" link uses.
        return redirect('management:dashboard')

    return render(request, '404.html', status=404)


# =============================================================================
# PUBLIC PAGES
# =============================================================================

THEOLOGY_SCHOOL_HOST = 'theology.miuedu.com'


@check_for_auth
def index(request):
    from .models import Testimonial
    captcha_question, captcha_answer = generate_captcha()
    request.session['contact_captcha_answer'] = captcha_answer
    current_host = request.get_host().split(':')[0].lower()
    return render(request, 'index.html', {
        'show_theology_ad': current_host != THEOLOGY_SCHOOL_HOST,
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
        'testimonials': Testimonial.objects.filter(is_active=True).order_by('author_name'),
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
    admin_board_members = (
        InstitutionMember.objects.filter(member_type='admin_board', is_active=True)
        .order_by('name')
    )
    who_we_are_member = (
        InstitutionMember.objects.filter(is_who_we_are=True, is_active=True).first()
        or admin_board_members.first()
    )
    return render(request, 'about.html', {
        'default_core_values': [
            'Sound Biblical Foundation',
            'Personal Relationship with the Lord Jesus',
            'Non-Denominational Service to the Christian Family',
            'Free & Accessible Ministerial Training',
            'End-time Readiness & Gospel Excellence',
        ],
        'faculties': Faculty.objects.filter(is_active=True).order_by('name'),
        'admin_board_members': admin_board_members,
        'who_we_are_member': who_we_are_member,
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


@login_required
def profile(request):
    """
    Central 'My Profile' page shared by every role (student, instructor,
    finance, admin, support) — one page, one URL, instead of a per-app copy.
    """
    from apps.student.forms import ProfileUpdateForm

    user = request.user
    user_profile = user.profile

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            old_email = user.email
            user.first_name = form.cleaned_data.get('first_name', '')
            user.last_name = form.cleaned_data.get('last_name', '')
            user.email = form.cleaned_data.get('email', '')
            user.save()
            form.save()
            if old_email != user.email:
                AuditLog.objects.create(
                    user=user,
                    action='update',
                    model_name='User',
                    object_id=str(user.pk),
                    description=f'{user.username} changed their account email from "{old_email}" to "{user.email}".',
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
            messages.success(request, 'Profile updated successfully!')
            return redirect('eduweb:profile')
    else:
        form = ProfileUpdateForm(
            instance=user_profile,
            initial={'first_name': user.first_name, 'last_name': user.last_name, 'email': user.email},
        )

    return render(request, 'account/profile.html', {'form': form, 'page_title': 'My Profile'})


@login_required
def account_settings(request):
    """
    Central 'Settings' page shared by every role — notification preferences
    and password change, one page instead of a per-app copy.

    Named account_settings, not settings — a view literally named `settings`
    shadows the `from django.conf import settings` import for the rest of
    this module (Python resolves module globals at call time, not def time,
    so every settings.SOMETHING reference anywhere else in this file —
    regardless of source position — silently broke once this function
    existed: Stripe key/webhook-secret lookups included). URL name stays
    'settings' (see eduweb/urls.py) so `{% url 'eduweb:settings' %}` is
    unaffected.
    """
    from django.contrib.auth import update_session_auth_hash
    from apps.student.forms import SettingsForm
    from apps.instructor.forms import PasswordChangeForm

    settings_form = SettingsForm(instance=request.user.profile)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST':
        if 'update_settings' in request.POST:
            settings_form = SettingsForm(request.POST, instance=request.user.profile)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, 'Settings updated successfully!')
                return redirect('eduweb:settings')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data['new_password'])
                request.user.save()
                update_session_auth_hash(request, request.user)
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='User',
                    object_id=str(request.user.pk),
                    description=f'{request.user.username} changed their password via Account Settings.',
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                messages.success(request, 'Your password has been changed successfully!')
                return redirect('eduweb:settings')

    return render(request, 'account/settings.html', {
        'settings_form': settings_form,
        'password_form': password_form,
        'page_title': 'Settings',
    })


@check_for_auth
def research(request):
    return render(request, 'research.html')


@check_for_auth
def campus_life(request):
    return render(request, 'campus_life.html')


@check_for_auth
def admission_requirement(request):
    degree_level_labels = dict(DEGREE_LEVEL_CHOICES)
    featured_intake = (
        CourseIntake.objects
        .filter(
            is_active=True,
            program__is_active=True,
            application_deadline__gte=timezone.now().date(),
        )
        .select_related('program')
        .order_by('application_deadline')
        .first()
    )
    active_degree_levels = [
        degree_level_labels.get(level, level)
        for level in (
            Program.objects
            .filter(is_active=True)
            .exclude(degree_level='')
            .order_by('degree_level')
            .values_list('degree_level', flat=True)
            .distinct()
        )
    ]

    spots_percent = None
    if featured_intake and featured_intake.available_slots:
        spots_percent = min(
            100,
            round(featured_intake.accepted_count / featured_intake.available_slots * 100),
        )

    return render(request, 'admission_requirement.html', {
        'featured_intake': featured_intake,
        'active_degree_levels': active_degree_levels,
        'spots_percent': spots_percent,
        'scholarship_deadline': SystemConfiguration.get_value('admissions_scholarship_deadline'),
    })


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
        return redirect('eduweb:index')

    referer = request.POST.get('next') or request.META.get('HTTP_REFERER', '/')
    # ── CAPTCHA verification ──────────────────────────────────────────────────
    session_answer = request.session.get('contact_captcha_answer')
    user_answer    = request.POST.get('captcha', '').strip()

    def _captcha_fail(msg):
        new_question, new_answer = generate_captcha()
        request.session['contact_captcha_answer'] = new_answer
        messages.error(request, msg)
        return redirect(referer)

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
        return redirect(referer)

    # Re-generate captcha on form validation failure too
    new_question, new_answer = generate_captcha()
    request.session['contact_captcha_answer'] = new_answer
    messages.error(request, 'Please correct the errors below.')
    return redirect(referer)


# =============================================================================
# FACULTY & PROGRAM PAGES
# =============================================================================

# Used only when a Faculty/Program has no gallery_video/gallery_image_*
# uploaded — keeps the carousel section a genuine 2-slide carousel (with
# working prev/next + indicators) instead of a single static placeholder.
# Distinct from the hero's own fallback (images/hero.webp) so the two
# sections don't show the exact same photo back-to-back.
FALLBACK_GALLERY_IMAGES = ['images/hero2.webp', 'images/hero3.webp']


def _build_gallery_items(obj, max_items=4):
    """
    Shared by faculty_detail/program_detail: builds an ordered list of media
    items (video first if present, then images) from an object's
    gallery_video/gallery_image_1/2/3 fields, capped at max_items. If the
    object has none of these fields set, falls back to two static campus
    photos (FALLBACK_GALLERY_IMAGES) so the carousel section always has
    something to show instead of disappearing entirely.
    """
    items = []
    video = getattr(obj, 'gallery_video', None)
    if video:
        items.append({'type': 'video', 'url': video.url})
    for field_name in ('gallery_image_1', 'gallery_image_2', 'gallery_image_3'):
        image = getattr(obj, field_name, None)
        if image:
            items.append({'type': 'image', 'url': image.url})
    if not items:
        items = [
            {'type': 'image', 'url': static_asset_url(path), 'is_fallback': True}
            for path in FALLBACK_GALLERY_IMAGES
        ]
    return items[:max_items]


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
        'gallery_items': _build_gallery_items(faculty),
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
        'gallery_items': _build_gallery_items(program),
        'today':      timezone.now().date(),
    })


# =============================================================================
# APPLICATION — FORM
# =============================================================================

# =============================================================================
# LOCATION HELPERS  (used only by the apply view)
# =============================================================================

# Territories/dependencies to EXCLUDE from country list (not independent countries)
# This prevents duplicate phone codes and confusion in selection (e.g., Guernsey vs UK)
EXCLUDED_TERRITORIES = {
    'AX', 'AI', 'AS', 'AW', 'BQ', 'BV', 'CC', 'CW', 'CX', 'FK', 'FO', 'GF',
    'GG', 'GI', 'GP', 'GS', 'GU', 'HK', 'HM', 'IO', 'JE', 'KY', 'MF', 'MO',
    'MP', 'MQ', 'MS', 'PM', 'PR', 'RE', 'SJ', 'SX', 'TC', 'TF', 'TW', 'UM',
    'VG', 'VI', 'WF', 'IM', 'BL',  # IM=Isle of Man, BL=Saint Barthélemy
}

@lru_cache(maxsize=1)
def _build_countries_list():
    """
    Returns a list of dicts: {code, name, phone_code, nationality}
    Sorted by name. pycountry → country list; phonenumbers → dial code.

    Cached (pure function, no arguments, static reference data — safe to
    compute once per process) since the `apply` page was rebuilding this
    ~200-entry list, phone codes included, from scratch on every single GET.
    
    FILTERS OUT: Territories and dependencies (GG, JE, IM, etc.) to prevent
    duplicate phone codes. Only returns independent sovereign countries.
    """
    countries = []
    for c in pycountry.countries:
        # SKIP territories/dependencies to avoid duplicate phone codes
        if c.alpha_2 in EXCLUDED_TERRITORIES:
            continue
            
        try:
            phone_code = ""
            # phonenumbers uses alpha-2 codes
            codes = phonenumbers.country_code_for_region(c.alpha_2)
            if codes:
                phone_code = f"+{codes}"
        except Exception:
            phone_code = ""

        # Derive nationality from pycountry common_name / name
        name = getattr(c, "common_name", None) or c.name
        # Simple heuristic: strip trailing qualifiers like ", Republic of"
        short = name.split(",")[0].strip()
        nationality = short  # fallback; override known irregular forms below

        countries.append({
            "code":        c.alpha_2,
            "name":        name,
            "phone_code":  phone_code,
            "nationality": nationality,
        })

    countries.sort(key=lambda x: x["name"])
    return countries


def _get_states(country_code):
    """
    Return list of {code, name} for a given alpha-2 country code.
    Uses geonamescache if available, otherwise pycountry subdivisions.
    """
    states = []

    if GEONAMES_AVAILABLE:
        try:
            all_countries = _gc.get_countries()
            # geonamescache doesn't directly map alpha-2 → states;
            # use pycountry subdivisions as primary with gc as fallback
            pass  # fall through to pycountry below
        except Exception:
            pass

    # pycountry subdivisions (works for all countries)
    try:
        subdivisions = pycountry.subdivisions.get(country_code=country_code)
        if subdivisions:
            # Only include top-level (no parent)
            top_level = [s for s in subdivisions if s.parent_code is None]
            if not top_level:
                top_level = list(subdivisions)
            for s in sorted(top_level, key=lambda x: x.name):
                states.append({
                    "code": s.code,          # e.g. "US-CA"
                    "name": s.name,
                })
    except Exception:
        pass

    return states


# =============================================================================
# APPLICATION — FORM
# =============================================================================

@login_required
@smart_redirect_applicant
def apply(request):
    """Multi-step course application form.

    Handles three request types in one view:
    1. GET  → render initial page with countries from pycountry
    2. AJAX POST action=location_data → return states/cities/phone/nationality JSON
    3. Normal POST → save application (existing logic unchanged)
    """

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

    # ── AJAX location requests ────────────────────────────────────────────────
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.POST.get('x_requested_with') == 'XMLHttpRequest'
    )

    if request.method == 'POST' and is_ajax:
        action = request.POST.get('action')

        # ── Country selected: return phone_code + nationality + states ────────
        if action == 'get_location_data':
            country_code = request.POST.get('country_code', '').strip().upper()
            if not country_code:
                return JsonResponse({'error': 'country_code required'}, status=400)
            
            # Security check: reject territories/dependencies
            if country_code in EXCLUDED_TERRITORIES:
                return JsonResponse({
                    'error': f'Territory code {country_code} not allowed. Use the main country.',
                }, status=400)

            phone_code   = ""
            nationality  = ""
            states       = []

            try:
                country_obj = pycountry.countries.get(alpha_2=country_code)
                if country_obj:
                    name = getattr(country_obj, 'common_name', None) or country_obj.name
                    nationality = name.split(',')[0].strip()

                dial = phonenumbers.country_code_for_region(country_code)
                if dial:
                    phone_code = f"+{dial}"
            except Exception as e:
                logger.warning("Location data error for %s: %s", country_code, e)

            states = _get_states(country_code)

            return JsonResponse({
                'phone_code':  phone_code,
                'nationality': nationality,
                'states':      states,
            })

        # get_cities and get_postal_code removed — city/postal are now plain text inputs

    # ── Build data for initial page render ────────────────────────────────────
    programs  = (
        Program.objects
        .filter(is_active=True)
        .select_related('department__faculty')
        .order_by('department__faculty__name', 'name')
    )
    faculties = Faculty.objects.filter(is_active=True)

    # Countries from pycountry (NOT from ListOfCountry model)
    pycountry_countries = _build_countries_list()

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
            'tuition_fee':           str(prog.tuition_fee),
        })
    courses_json = json.dumps(courses_by_faculty, cls=DjangoJSONEncoder)

    if request.method == 'POST':
        form = CourseApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                application = form.save(commit=False)
                application.user = request.user
                application.resolve_intake()

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

                # Was backgrounded via a daemon Thread — matches the same
                # failure mode already hit in production for other emails on
                # Passenger/shared hosting (the worker process can be
                # recycled before a detached thread finishes sending, so the
                # email silently never goes out). Sent synchronously instead,
                # same as every other email in this file; EMAIL_TIMEOUT (see
                # settings.py) bounds the worst-case wait to 15s.
                send_application_confirmation_email(application)
                send_application_admin_notification(application)

                if is_ajax:
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

            except Exception:
                # Log the real exception server-side; never echo it back —
                # it can leak internal details (field/table names, file
                # paths) and previously showed up verbatim in the UI.
                logger.exception("apply view — error saving application")
                generic_message = 'Something went wrong while saving your application. Please try again.'
                if is_ajax:
                    return JsonResponse({'success': False, 'error': generic_message}, status=500)
                messages.error(request, generic_message)

        else:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, 'Please correct the errors highlighted in the form.')

    else:
        initial = {'email': request.user.email} if request.user.is_authenticated else {}
        # One-time carry-over from the program-gated signup flow (see
        # eduweb.views.signup_page) — popped so it doesn't leak into a
        # later, unrelated application.
        apply_program_id = request.session.pop('apply_program_id', None)
        if apply_program_id:
            initial['program'] = apply_program_id
        form = CourseApplicationForm(initial=initial)

    from apps.eduweb.models import AcademicSession
    academic_sessions = AcademicSession.objects.filter(
        status__in=['active', 'upcoming']
    ).order_by('-name')

    return render(request, 'form.html', {
        'form':                 form,
        'courses':              programs,
        'faculties':            faculties,
        'courses_json':         courses_json,
        'countries':            pycountry_countries,   # replaces ListOfCountry queryset
        'academic_sessions':    academic_sessions,
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

    # Re-check under a row lock inside the transaction — the plain checks
    # above are just a fast-path for the common case; without this, two
    # near-simultaneous submits (double-click, double tab) could both pass
    # the admission_accepted check above and both issue an admission number.
    with transaction.atomic():
        application = CourseApplication.objects.select_for_update().get(pk=application.pk)

        if application.status != 'approved':
            messages.error(request, 'Only approved applications can be accepted.')
            return redirect('eduweb:application_status')

        if application.admission_accepted:
            messages.info(request, 'You have already accepted this admission offer.')
            return redirect('eduweb:application_status')

        accepted = application.accept_admission()
        if accepted:
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

    if accepted:
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
                new_program = Program.objects.get(id=program_id, is_active=True)
                if new_program.pk != application.program_id:
                    application.program = new_program
                    application.intake = None  # re-resolve for the newly chosen program
                application.resolve_intake()
            except Program.DoesNotExist:
                pass

        session_id = data.get('academic_session')
        if session_id:
            try:
                from apps.eduweb.models import AcademicSession
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

    except Exception:
        logger.exception("save_application_draft failed")
        generic_message = 'Could not save your application right now. Please try again.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': generic_message}, status=400)
        messages.error(request, generic_message)
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
                'stripe_public_key': get_stripe_public_key(),
            }

        elif application_id:
            application = CourseApplication.objects.select_related(
                'program', 'program__department__faculty'
            ).get(application_id__iexact=application_id)
            data = {
                'full_name':        f"{application.first_name} {application.last_name}",
                'application_id':   application.application_id,
                'amount':           float(application.application_fee),
                'currency':         'USD',
                'description':      'Application Processing Fee',
                'stripe_public_key': get_stripe_public_key(),
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
            'program__department__faculty'
        ).get(pk=fee_pk, is_active=True)
    except AllRequiredPayments.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)

    return JsonResponse({
        'success': True,
        'data': {
            'full_name':         request.user.get_full_name() or request.user.username,
            'purpose':           fee.purpose,
            'amount':            float(fee.amount),
            'currency':          fee.currency,
            'stripe_public_key': get_stripe_public_key(),
        },
    })


@require_POST
@login_required
def create_payment_intent(request):
    """Create a Stripe PaymentIntent for either a student fee or an application."""
    try:
        stripe.api_key = get_stripe_secret_key()
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

                if not application.intake_id and application.resolve_intake():
                    application.save(update_fields=['intake'])
                fee = application.application_fee
                amount_pence = int(fee * Decimal('100'))

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
                    # Was 'gbp' while the ApplicationPayment row below always
                    # recorded currency='USD' — a real mismatch between what
                    # Stripe actually charged and what got recorded, which
                    # would corrupt any future refund/reporting math. Aligned
                    # to 'usd' to match both the recorded currency and the
                    # student-fee branch above.
                    currency='usd',
                    metadata={
                        # Required for the Stripe webhook (stripe_webhook
                        # below) to recognize this as an application payment —
                        # without it, 'type' is never set and the webhook's
                        # `elif payment_type == 'application':` branch can
                        # never match, so a payment confirmed by Stripe but
                        # never confirmed by confirm_payment (e.g. the user
                        # closes the tab right after paying) has no fallback.
                        'type':           'application',
                        'application_id': application.application_id,
                        'user_id':        request.user.id,
                    },
                    automatic_payment_methods={'enabled': True},
                )
                ApplicationPayment.objects.create(
                    application=application,
                    gateway_payment_id=intent.id,
                    amount=fee,
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
        stripe.api_key = get_stripe_secret_key()
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

            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='FeePayment',
                object_id=str(payment.id),
                description=(
                    f'{request.user.username} paid {payment.currency} {payment.amount} '
                    f'for "{fee.purpose}" (Stripe payment {intent.id}).'
                ),
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )

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
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='ApplicationPayment',
                object_id=str(payment.id),
                description=(
                    f'{request.user.username} paid {payment.currency} {payment.amount} '
                    f'application fee for {application.application_id} (Stripe payment {intent.id}).'
                ),
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
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

        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='ApplicationPayment',
            object_id=str(payment.id),
            description=(
                f'{request.user.username} paid {payment.currency} {payment.amount} '
                f'application fee for {application.application_id} (Stripe payment {intent.id}).'
            ),
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

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
            payload, sig_header, get_stripe_webhook_secret()
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

                AuditLog.objects.create(
                    user_id=metadata.get('user_id'),
                    action='update',
                    model_name='FeePayment',
                    object_id=str(payment.id),
                    description=(
                        f'Stripe webhook confirmed payment of {payment.currency} {payment.amount} '
                        f'for "{fee.purpose}" (Stripe payment {intent["id"]}).'
                    ),
                )

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

                AuditLog.objects.create(
                    user=application.user,
                    action='update',
                    model_name='ApplicationPayment',
                    object_id=str(payment.id),
                    description=(
                        f'Stripe webhook confirmed payment of {payment.currency} {payment.amount} '
                        f'application fee for {application.application_id} (Stripe payment {intent["id"]}).'
                    ),
                )

    return HttpResponse(status=200)