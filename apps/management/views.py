# =============================================================================
# IMPORTS
# =============================================================================

# Standard library
import csv
import json
import logging
import secrets
import string
import zoneinfo
from datetime import date, datetime, timedelta
from functools import wraps

# Django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.exceptions import SuspiciousOperation
from django.core.mail import EmailMultiAlternatives, send_mail, send_mass_mail
from django.core.paginator import Paginator
from django.db import transaction, connection, IntegrityError
from django.db.models import F, Q, Count, Sum, Avg, Value, DecimalField, Max
from django.db.models.functions import Coalesce, TruncMonth, TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_POST

# Models
from apps.eduweb.models import (
    Announcement,
    ApplicationPayment,
    AuditLog,
    Badge,
    BlogCategory,
    BlogPost,
    BroadcastMessage,
    Certificate,
    ContactMessage,
    Course,
    CourseApplication,
    CourseCategory,
    CourseGrade,
    CourseIntake,
    CourseRegistration,
    Department,
    Enrollment,
    Faculty,
    FeePayment,
    InstitutionMember,
    InstitutionPartner,
    LMSCourse,
    LibraryItem,
    Notification,
    PaymentGateway,
    Program,
    Review,
    SiteConfig,
    SiteHistoryMilestone,
    SocialPost,
    StaffPayroll,
    StudentBadge,
    SystemConfiguration,
    encrypt_secret,
    Testimonial,
    Invoice,
    Transaction,
    UserProfile,
    Message,
    Exam,
    ExamQuestion,
    StudentExamResponse,
    ExamStatusLog,
    StaffPermissionsMatrix,
)
from apps.store import services as store_services
from apps.store.emailservices import send_order_refunded_email, send_refund_request_rejected_email
from apps.store.models import Product, ProductCategory, ProductSpecification, MediaAsset, ProductImage, Order, OrderItem

# Forms
from apps.management.forms import (
    AdminMessageComposeForm,
    AnnouncementForm,
    AuditLogFilterForm,
    BadgeForm,
    BlogCategoryForm,
    BlogPostForm,
    BrandingConfigForm,
    BroadcastMessageForm,
    CertificateForm,
    CourseCategoryForm,
    CourseForm,
    CourseIntakeForm,
    DepartmentForm,
    EmailAccountForm,
    EmailServerForm,
    EnrollmentForm,
    FacultyForm,
    InstitutionMemberForm,
    InstitutionPartnerForm,
    LMSCourseForm,
    LibraryItemForm,
    MediaAssetForm,
    NotificationConfigForm,
    PaymentGatewayForm,
    ProductCategoryForm,
    ProductForm,
    ProductSpecificationFormSet,
    ProductVariantFormSet,
    ProgramForm,
    QuickRoleChangeForm,
    ReviewForm,
    SiteConfigAboutForm,
    SiteConfigGeneralForm,
    SiteConfigIndexForm,
    SiteHistoryMilestoneForm,
    SocialPostForm,
    StaffPayrollForm,
    StudentBadgeForm,
    SystemConfigurationForm,
    TestimonialForm,
    UserCreateForm,
    UserEditForm,
    UserProfileForm,
    UserSearchForm,
)

# Email Services
from apps.eduweb.emailservices import (
    send_transcript_generated_email,
    send_payroll_payment_notification_email,
    send_admin_created_user_email,
    send_new_message_email,
    _resolve_sender,
    send_test_email,
)

logger = logging.getLogger('melbac')


def _notify(user, title, message, notif_type='system', link=''):
    """Create a Notification for any user and prune beyond 100."""
    Notification.objects.create(
        user=user, notification_type=notif_type,
        title=title, message=message, link=link,
    )
    old_ids = (
        Notification.objects.filter(user=user)
        .order_by('-created_at').values_list('id', flat=True)[100:]
    )
    if old_ids:
        Notification.objects.filter(id__in=list(old_ids)).delete()


def _permission_modules_for_role(role):
    """
    All modules + action fields, for any given staff role. Deliberately NOT
    filtered down to the role's own defaults — the permissions modal and
    role-assignment page show every module for every user, so an admin can
    grant a user access outside their nominal role's usual scope (e.g. give
    a support agent a finance module) rather than being limited to it.
    """
    role_defaults = StaffPermissionsMatrix.ROLE_DEFAULT_PERMISSIONS.get(role, {})
    modules = [m[0] for m in StaffPermissionsMatrix.MODULE_CHOICES]
    return modules, StaffPermissionsMatrix.ALL_ACTION_FIELDS, role_defaults


def _effective_permissions_for_user(user):
    """
    Effective StaffPermissionsMatrix snapshot for a user — user-level
    override row, else role-level default row, else hardcoded
    ROLE_DEFAULT_PERMISSIONS — covers every module, not just the ones
    nominally tied to this user's role, so the permissions modal always
    shows and can edit the full matrix for any user.
    """
    role = user.profile.role
    modules, actions, role_defaults = _permission_modules_for_role(role)

    user_rows = {r.module: r for r in StaffPermissionsMatrix.objects.filter(user=user, role=None)}
    role_rows = {r.module: r for r in StaffPermissionsMatrix.objects.filter(role=role, user=None)}

    result = {}
    for module in modules:
        row = user_rows.get(module) or role_rows.get(module)
        if row:
            result[module] = {f: getattr(row, f) for f in actions}
        else:
            result[module] = {f: role_defaults.get(module, {}).get(f, False) for f in actions}
    return modules, actions, result


def _has_permission(request, module, action):
    """
    True if the acting user may perform `action` on `module`. Superuser
    always bypasses; otherwise reads the StaffPermissionsMatrix snapshot
    SessionSecurityMiddleware attaches to the request as `request.permissions`.
    """
    if request.user.is_superuser:
        return True
    return getattr(request, 'permissions', {}).get(module, {}).get(action, False)


def _is_superuser_protected(request, target_user):
    """
    True if `target_user` is a superuser and the acting request.user is not —
    i.e. this action must be blocked. A superuser account may only be edited,
    deactivated, or have its role changed by another superuser (including
    itself). Ordinary admins/staff — even with full user_management
    permissions — can never touch a superuser's account through these views.
    Deletion of any user is already disallowed everywhere, so no separate
    check is needed for that.
    """
    return bool(getattr(target_user, 'is_superuser', False)) and not request.user.is_superuser


def _clear_stale_permission_overrides(user):
    """
    Delete every StaffPermissionsMatrix user-level override row for this
    user. Call this whenever a user's role actually changes.

    Those rows aren't scoped to the role they were created under —
    eduweb.security_middleware._load_permissions applies
    StaffPermissionsMatrix.objects.filter(user=user) unconditionally, with
    no role filter — so a row saved while someone was e.g. 'support' would
    silently keep suppressing/altering modules after they're switched to
    'admin' or any other role, with no indication anything is wrong. Wiping
    them on role change gives the user a clean slate of the new role's
    defaults; an admin can re-customize via the permissions modal from there.
    """
    StaffPermissionsMatrix.objects.filter(user=user).delete()


def require_permission(module, action, redirect_to='management:users_list', skip_get=True):
    """
    Decorator for management views that mutate state or export data — denies
    the request unless _has_permission(request, module, action) is True, so
    the server-side check can't be skipped just because the corresponding
    template button happens to be hidden. AJAX requests get a 403 JSON
    response; everything else gets an error message and a redirect.

    `skip_get` (default True) leaves GET requests unguarded, matching the
    common convention in this file of gating only the POST/mutation branch
    while GET just renders the page/form. Pass `skip_get=False` for views
    that perform the privileged action itself on GET (e.g. a CSV/PDF export
    triggered by a plain link, with no separate POST step to gate).

    `redirect_to` is either a URL name with no required args (e.g.
    'management:users_list'), or a callable `(request, *args, **kwargs) ->
    HttpResponse` for views whose redirect target needs the same URL kwargs
    the view itself received (e.g. a detail page keyed by slug/pk).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            guarded = not skip_get or request.method != 'GET'
            if guarded and not _has_permission(request, module, action):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
                messages.error(request, 'You do not have permission to perform this action.')
                if callable(redirect_to):
                    return redirect_to(request, *args, **kwargs)
                return redirect(redirect_to)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


# Internal back-office roles that share the /management/ inbox + notifications
# pages. Students and instructors each have their own dedicated inbox/notification
# pages (students:notifications_view, instructor:messages_inbox etc.) and don't
# need — or use — these; everyone else lands here per the navbar's role routing.
_STAFF_ROLES = {'admin', 'support', 'finance'}


def is_staff_member(user):
    """Any authenticated internal staff user — broader than is_admin(), used for
    pages shared across the whole back office (inbox, notifications)."""
    return (
        user.is_authenticated and user.is_active and (
            user.is_staff or
            user.is_superuser or
            (hasattr(user, 'profile') and user.profile.role in _STAFF_ROLES)
        )
    )


def is_admin(user):
    """
    The one admin gate for this app. is_staff and is_superuser each act as
    a full bypass on their own (equivalent to role='admin'); is_superuser
    additionally bypasses every StaffPermissionsMatrix check downstream.
    Also lets in a non-admin (support/finance/instructor) user who's been
    granted can_view on at least one admin-portal module via
    /management/role-assign/ — otherwise the sidebar link that permission
    unlocks would 404/redirect the moment they click it.
    """
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if hasattr(user, 'profile') and user.profile.role == 'admin':
        return True
    return StaffPermissionsMatrix.user_can_view_any(user, StaffPermissionsMatrix.ADMIN_PORTAL_MODULES)


def is_superuser_only(user):
    """
    Stricter gate for pages that must stay off-limits even to staff granted
    narrow StaffPermissionsMatrix access to unrelated admin modules (SMTP
    credentials, raw config key/value store, branding, notifications).
    Add `or user.is_staff` here to extend access to any is_staff account.
    """
    return user.is_authenticated and user.is_active and user.is_superuser


# ===========================================================================
# ADMIN INBOX / MESSAGING
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_staff_member)
def admin_inbox(request):
    """
    Admin/staff inbox — shows all received and sent messages.
    Marks all unread received messages as read on open.
    """
    user = request.user

    received = (
        Message.objects
        .filter(recipient=user, parent__isnull=True)
        .select_related('sender', 'sender__profile')
        .order_by('-created_at')
    )
    sent = (
        Message.objects
        .filter(sender=user, parent__isnull=True)
        .select_related('recipient', 'recipient__profile')
        .order_by('-created_at')
    )

    unread_count = received.filter(is_read=False).count()

    Message.objects.filter(
        recipient=user, is_read=False, parent__isnull=True
    ).update(is_read=True, read_at=timezone.now())

    tab = request.GET.get('tab', 'received')
    paginator_received = Paginator(received, 20)
    paginator_sent = Paginator(sent, 20)
    page = request.GET.get('page', 1)

    return render(request, 'management/inbox.html', {
        'page_title': 'Inbox',
        'received': paginator_received.get_page(page),
        'sent': paginator_sent.get_page(page),
        'unread_count': unread_count,
        'tab': tab,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_staff_member)
def admin_compose_message(request):
    """
    Admin compose — send a new message to any user.
    Supports ?to=<user_id> query param to pre-fill recipient.
    """
    if request.method == 'POST':
        form = AdminMessageComposeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    msg = form.save(commit=False)
                    msg.sender = request.user
                    msg.save()
            except Exception:
                logger.exception('admin_compose_message: unexpected error saving message')
                messages.error(request, 'Something went wrong while sending this message. Please try again.')
            else:
                # In-app notification to recipient
                _notify(
                    user=msg.recipient,
                    title=f'New Message from {request.user.get_full_name() or request.user.username}',
                    message=f'You have a new message: "{msg.subject}"',
                    notif_type='message',
                    link=f'/management/inbox/{msg.id}/',
                )
                try:
                    send_new_message_email(msg.recipient, request.user, msg)
                except Exception:
                    logger.exception('Failed to send new-message email to %s', msg.recipient)
                messages.success(request, 'Message sent successfully!')
                return redirect('management:admin_inbox')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        initial = {}
        to_id = request.GET.get('to')
        if to_id:
            try:
                initial['recipient'] = User.objects.get(pk=to_id)
            except (User.DoesNotExist, ValueError):
                pass
        form = AdminMessageComposeForm(initial=initial)

    return render(request, 'management/compose_message.html', {
        'page_title': 'Compose Message',
        'form': form,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_staff_member)
def admin_message_thread(request, message_id):
    """
    View a full message thread and reply.
    Only sender or recipient may access.
    """
    msg = get_object_or_404(
        Message.objects.select_related(
            'sender', 'sender__profile',
            'recipient', 'recipient__profile'
        ),
        pk=message_id,
    )

    if msg.sender != request.user and msg.recipient != request.user:
        messages.error(request, 'You do not have permission to view this message.')
        return redirect('management:admin_inbox')

    if msg.recipient == request.user and not msg.is_read:
        msg.mark_as_read()

    thread_replies = (
        Message.objects
        .filter(parent=msg)
        .select_related('sender', 'sender__profile', 'recipient', 'recipient__profile')
        .order_by('created_at')
    )

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if len(body) >= 5:
            reply_to = msg.sender if msg.recipient == request.user else msg.recipient
            try:
                with transaction.atomic():
                    Message.objects.create(
                        sender=request.user,
                        recipient=reply_to,
                        subject=f'Re: {msg.subject}',
                        body=body,
                        parent=msg,
                    )
            except Exception:
                logger.exception('admin_message_thread: unexpected error saving reply for message_id=%s', message_id)
                messages.error(request, 'Something went wrong while sending your reply. Please try again.')
            else:
                _notify(
                    user=reply_to,
                    title=f'Reply from {request.user.get_full_name() or request.user.username}',
                    message=f'New reply on: "{msg.subject}"',
                    notif_type='message',
                    link=f'/management/inbox/{msg.id}/',
                )
                try:
                    send_new_message_email(reply_to, request.user, msg)
                except Exception:
                    logger.exception('Failed to send reply-notification email to %s', reply_to)
                messages.success(request, 'Reply sent!')
                return redirect('management:admin_message_thread', message_id=message_id)
        messages.error(request, 'Reply must be at least 5 characters.')

    return render(request, 'management/message_thread.html', {
        'page_title': msg.subject,
        'message': msg,
        'thread_replies': thread_replies,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_staff_member)
def notifications_view(request):
    """
    Notifications page for admin and staff roles.
    Marks all as read if ?mark_all=1. Paginated at 15 per page.
    """
    if request.GET.get('mark_all') == '1':
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return redirect('management:notifications_view')

    notifs = (
        Notification.objects
        .filter(user=request.user)
        .order_by('-created_at')
    )
    unread_count = notifs.filter(is_read=False).count()
    page_obj = Paginator(notifs, 15).get_page(request.GET.get('page', 1))

    return render(request, 'management/notifications.html', {
        'page_title': 'Notifications',
        'notifications': page_obj,
        'unread_count': unread_count,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_staff_member)
def mark_notification_read(request, notification_id):
    """Mark a single notification as read — AJAX GET."""
    notif = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    notif.mark_as_read()
    return JsonResponse({'success': True})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def dashboard(request):
    """Admin dashboard with statistics and recent applications"""
    
    # Get statistics
    total_applications = CourseApplication.objects.count()
    pending_applications = CourseApplication.objects.filter(status__in=['payment_complete', 'under_review', 'documents_uploaded']).count()
    approved_applications = CourseApplication.objects.filter(status='approved').count()
    total_students = User.objects.filter(is_staff=False, is_active=True).count()
    
    # Get recent applications (last 10)
    recent_applications = CourseApplication.objects.select_related('user').order_by('-created_at')[:10]
    
    # Prepare chart data for applications over time (last 7 days) — one
    # bucketed query instead of 7 separate .count() calls in a loop (same
    # N+1 shape already fixed for the student 28-day heatmap in Phase 1).
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)

    daily_counts = dict(
        CourseApplication.objects.filter(created_at__date__gte=week_ago, created_at__date__lte=today)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .values_list('day', 'count')
    )

    applications_by_day = []
    labels = []

    for i in range(7):
        date = week_ago + timedelta(days=i)
        applications_by_day.append(daily_counts.get(date, 0))
        labels.append(date.strftime('%a'))

    applications_chart_data = json.dumps({
        'labels': labels,
        'data': applications_by_day
    })
    
    program_distribution = CourseApplication.objects.values(
        'program__name', 'program__department__faculty__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    program_labels = [
        f"{item['program__name']} ({item['program__department__faculty__name'] or 'N/A'})"
        for item in program_distribution
    ]
    program_data = [item['count'] for item in program_distribution]
    
    program_chart_data = json.dumps({
        'labels': program_labels,
        'data': program_data
    })
    
    context = {
        'total_applications': total_applications,
        'pending_applications': pending_applications,
        'approved_applications': approved_applications,
        'total_students': total_students,
        'recent_applications': recent_applications,
        'applications_chart_data': applications_chart_data,
        'program_chart_data': program_chart_data,
        'pending_count': pending_applications,
    }
    
    return render(request, 'management/dashboard.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def applications_list(request):
    """List all applications with filtering and pagination"""

    if not _has_permission(request, 'applications', 'can_view'):
        messages.error(request, 'You do not have permission to view applications.')
        return redirect('management:dashboard')

    applications = CourseApplication.objects.select_related('user', 'program').order_by('-created_at')
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    program_filter = request.GET.get('program', '')
    
    # Apply search filter
    if search_query:
        applications = applications.filter(
            Q(application_id__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Apply status filter
    if status_filter:
        applications = applications.filter(status=status_filter)
    
    # Apply program filter
    if program_filter:
        applications = applications.filter(program__id=program_filter)
    
    # Pagination
    paginator = Paginator(applications, 15)  # 15 applications per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get pending count for sidebar
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    

    context = {
        'applications': page_obj,
        'programs': [
            (str(p.id), f"{p.name} ({p.department.faculty.name})")
            for p in Program.objects.filter(is_active=True).select_related('department__faculty')
        ],
        'pending_count': pending_count,
    }
    
    return render(request, 'management/applications.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def application_detail(request, application_id):
    """View detailed information about a specific application"""

    if not _has_permission(request, 'applications', 'can_view'):
        messages.error(request, 'You do not have permission to view applications.')
        return redirect('management:dashboard')

    application = get_object_or_404(
        CourseApplication.objects.prefetch_related('documents'),  # ✅ Correct related name
        application_id=application_id
    )
    
    # Mark as under review when admin opens it (only if status is 'documents_uploaded')
    if application.status == 'documents_uploaded':
        application.status = 'under_review'
        application.save(update_fields=['status'])
    
    # Get pending count for sidebar
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded']).count()

    context = {
        'application': application,
        'pending_count': pending_count,
    }
    
    return render(request, 'management/application_detail.html', context)

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def make_decision(request, pk):
    """Make admission decision on an application"""

    if request.method == 'POST':
        application = get_object_or_404(CourseApplication, pk=pk)

        if not _has_permission(request, 'applications', 'can_edit'):
            messages.error(request, 'You do not have permission to make admission decisions.')
            return redirect('management:application_detail', application_id=application.application_id)

        decision = request.POST.get('decision')
        decision_notes = request.POST.get('decision_notes', '')
        
        VALID_DECISIONS = ['approved', 'rejected']
        if decision not in VALID_DECISIONS:
            messages.error(request, 'Invalid decision. Choose Approved or Rejected.')
            return redirect('management:application_detail', application_id=application.application_id)

        # Update application status
        if decision == 'approved':
            application.status = 'approved'
        elif decision == 'rejected':
            application.status = 'rejected'

        application.review_notes = decision_notes
        application.reviewer = request.user
        application.reviewed_at = timezone.now()
        try:
            application.save()
        except Exception:
            logger.exception('make_decision: unexpected error saving decision for application pk=%s', pk)
            messages.error(request, 'Something went wrong while recording this decision. Please try again.')
            return redirect('management:application_detail', application_id=application.application_id)

        # On approval: sync program / dept / faculty to UserProfile
        if decision == 'approved' and application.user:
            try:
                profile = application.user.profile
                if application.program:
                    profile.program    = application.program
                    profile.department = application.program.department
                    profile.faculty    = application.program.department.faculty
                profile.save(update_fields=['program', 'department', 'faculty'])
            except Exception:
                logger.exception(
                    "make_decision — failed to sync profile for application %s",
                    application.application_id,
                )
        
        # Send decision email
        send_decision_email(application)
        
        messages.success(
            request,
            f'Decision "{decision.capitalize()}" has been recorded and email sent to applicant.'
        )
        # In-app notification to applicant if they have a user account
        if application.user:
            if decision == 'approved':
                _notify(
                    user=application.user,
                    title='Application Approved',
                    message=f'Congratulations! Your application ({application.application_id}) has been approved.',
                    notif_type='enrollment',
                    link='/dashboard/',
                )
            else:
                _notify(
                    user=application.user,
                    title='Application Decision',
                    message=f'A decision has been made on your application ({application.application_id}). Please log in for details.',
                    notif_type='system',
                    link='/dashboard/',
                )

        return redirect('management:application_detail', application_id=application.application_id)
    
    return redirect('management:applications_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def issue_transcript(request, pk):
    """Issue a transcript for an approved application"""

    if request.method != 'POST':
        return redirect('management:applications_list')

    application = get_object_or_404(CourseApplication, pk=pk)

    if not _has_permission(request, 'applications', 'can_edit'):
        messages.error(request, 'You do not have permission to issue transcripts.')
        return redirect('management:application_detail', application_id=application.application_id)

    # Only issue transcripts for approved applications
    if application.status != 'approved':
        messages.error(request, 'Can only issue transcripts for approved applications.')
        return redirect('management:application_detail', application_id=application.application_id)
    
    # Check if transcript already issued
    if application.transcript_issued:
        messages.info(request, 'Transcript has already been issued for this application.')
        return redirect('management:application_detail', application_id=application.application_id)

    # The student must request their transcript first — that's the moment the
    # grade snapshot gets locked (see CourseGrade.build_transcript_snapshot).
    # Issuing without a request would show "Official Transcript Issued" next
    # to a page that's still rendering live, unlocked grades.
    if not application.transcript_requested:
        messages.error(
            request,
            'This student has not requested their transcript yet — it cannot be issued until they do.'
        )
        return redirect('management:application_detail', application_id=application.application_id)

    try:
        # Mark transcript as issued
        application.transcript_issued = True
        application.transcript_issued_at = timezone.now()
        application.transcript_issued_by = request.user
        if not application.transcript_snapshot and application.user:
            # Defensive fallback — should already exist from the request step.
            application.transcript_snapshot = CourseGrade.build_transcript_snapshot(application.user)
            application.save(update_fields=[
                'transcript_issued', 'transcript_issued_at', 'transcript_issued_by', 'transcript_snapshot'
            ])
        else:
            application.save(update_fields=['transcript_issued', 'transcript_issued_at', 'transcript_issued_by'])

        # Send notification email to student
        if application.user:
            send_transcript_generated_email(application.user, application)
            _notify(
                user=application.user,
                title='Transcript Generated',
                message=f'Your transcript has been generated. You can download it from your dashboard.',
                notif_type='academic',
                link='/dashboard/',
            )
        
        messages.success(request, f'Transcript issued for {application.application_id}. Email sent to applicant.')
    except Exception as e:
        logger.error(f'Failed to issue transcript for {application.application_id}: {str(e)}')
        messages.error(request, 'Failed to issue transcript. Please try again.')
    
    return redirect('management:application_detail', application_id=application.application_id)


def send_decision_email(application):
    """Send admission decision email to applicant"""
    try:
        decision = application.status
        
        if decision == 'approved':
            subject = f'Congratulations! Admission Offer - {application.application_id}'
            decision_text = 'Congratulations! We are pleased to offer you admission to'
            color = '#10b981'  # green
            icon = '🎉'
        else:
            subject = f'Application Decision - {application.application_id}'
            decision_text = 'Thank you for your interest in'
            color = '#ef4444'  # red
            icon = '📧'
        
        # Get program name from the related Course model
        program_name = f"{application.course.name} ({application.course.get_degree_level_display()})"
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg, #0F2A44 0%, #1D4ED8 100%); padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">{icon} Application Decision</h1>
                    </div>
                    <div style="background-color: white; padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">Dear <strong>{application.first_name} {application.last_name}</strong>,</p>
                        <div style="background-color: {color}15; padding: 20px; border-radius: 8px; margin: 25px 0; border-left: 4px solid {color};">
                            <h3 style="color: {color}; margin-top: 0;">Admission Decision</h3>
                            <p style="font-size: 16px;"><strong>{decision_text} {program_name}</strong></p>
                            <p><strong>Application ID:</strong> {application.application_id}</p>
                            <p><strong>Decision Date:</strong> {application.reviewed_at.strftime('%B %d, %Y') if application.reviewed_at else timezone.now().strftime('%B %d, %Y')}</p>
                        </div>
        """
        
        if decision == 'approved':
            html_content += f"""
                        <p>We are excited to welcome you to Melchisedec International University!</p>
                        <h4>Next Steps:</h4>
                        <ol>
                            <li>Review your admission offer letter (attached)</li>
                            <li>Complete enrollment within 2 weeks</li>
                            <li>Submit your acceptance confirmation</li>
                            <li>Pay the enrollment deposit</li>
                        </ol>
                        <p>If you have any questions, please contact our admissions office.</p>
            """
        else:
            html_content += f"""
                        <p>After careful review of your application, we regret to inform you that we are unable to offer you admission at this time.</p>
                        <p>We encourage you to apply again in the future. We wish you the best in your academic pursuits.</p>
            """
        
        if application.review_notes:
            html_content += f"""
                        <div style="background-color: #f9f9f9; padding: 15px; margin-top: 20px; border-radius: 5px;">
                            <p style="margin: 0;"><strong>Additional Notes:</strong></p>
                            <p style="margin: 10px 0 0 0;">{application.review_notes}</p>
                        </div>
            """
        
        html_content += f"""
                        <p style="margin-top: 30px;">Best regards,<br><strong style="color: #0F2A44;">The Abraytech Admissions Team</strong></p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        connection, from_email = _resolve_sender('admissions')
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Application Decision for {application.application_id}",
            from_email=from_email,
            to=[application.email],
            connection=connection,
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Error sending decision email for application %s', application.application_id)
        return False
    


def _faculty_ctx(form=None, edit_pk=None):
    """Shared context for all faculty list views."""
    qs = Faculty.objects.prefetch_related('departments').order_by('name')
    return {
        'faculties':         qs,
        'form':              form or FacultyForm(),
        'edit_pk':           edit_pk,
        'active_count':      qs.filter(is_active=True).count(),
        'total_departments': Department.objects.count(),
        'total_programs':    Program.objects.count(),
    }
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def faculties_list(request):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view academic structure.')
        return redirect('management:dashboard')
    return render(request, 'management/faculties_list.html', _faculty_ctx())
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def faculty_create(request):
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_create'):
            messages.error(request, 'You do not have permission to create faculties.')
            return redirect('management:faculties_list')

        form = FacultyForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    faculty = form.save()
            except IntegrityError:
                logger.exception('faculty_create: IntegrityError saving faculty')
                messages.error(request, 'Could not save this faculty — that code may already be in use.')
                return render(request, 'management/faculties_list.html', _faculty_ctx(form=form))
            except Exception:
                logger.exception('faculty_create: unexpected error saving faculty')
                messages.error(request, 'Something went wrong while saving this faculty. Please try again.')
                return render(request, 'management/faculties_list.html', _faculty_ctx(form=form))
            messages.success(request, f'Faculty "{faculty.name}" created successfully!')
            return redirect('management:faculties_list')
        messages.error(request, 'Please correct the errors below.')
        return render(request, 'management/faculties_list.html', _faculty_ctx(form=form))
    return redirect('management:faculties_list')
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def faculty_edit(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_edit'):
            messages.error(request, 'You do not have permission to edit faculties.')
            return redirect('management:faculties_list')

        form = FacultyForm(request.POST, request.FILES, instance=faculty)
        if form.is_valid():
            try:
                with transaction.atomic():
                    faculty = form.save()
            except IntegrityError:
                logger.exception('faculty_edit: IntegrityError saving faculty pk=%s', pk)
                messages.error(request, 'Could not save this faculty — that code may already be in use.')
                return render(request, 'management/faculties_list.html', _faculty_ctx(form=form, edit_pk=pk))
            except Exception:
                logger.exception('faculty_edit: unexpected error saving faculty pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this faculty. Please try again.')
                return render(request, 'management/faculties_list.html', _faculty_ctx(form=form, edit_pk=pk))
            messages.success(request, f'Faculty "{faculty.name}" updated successfully!')
            return redirect('management:faculties_list')
        messages.error(request, 'Please correct the errors below.')
        return render(request, 'management/faculties_list.html', _faculty_ctx(form=form, edit_pk=pk))
    return redirect('management:faculties_list')
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def faculty_delete(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_delete'):
            messages.error(request, 'You do not have permission to delete faculties.')
            return redirect('management:faculties_list')

        dept_count = faculty.departments.count()
        if dept_count:
            messages.error(
                request,
                f'Cannot delete "{faculty.name}" — it still has {dept_count} '
                f'department(s). Delete or reassign them first.'
            )
            return redirect('management:faculties_list')

        name = faculty.name
        try:
            faculty.delete()
            messages.success(request, f'Faculty "{name}" deleted successfully!')
        except Exception:
            logger.exception('faculty_delete: unexpected error deleting faculty pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this faculty. Please try again.')
    return redirect('management:faculties_list')




@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_posts_list(request):
    """List all blog posts"""
    if not _has_permission(request, 'blog', 'can_view'):
        messages.error(request, 'You do not have permission to view blog posts.')
        return redirect('management:dashboard')

    posts = BlogPost.objects.select_related('category', 'author').all().order_by('-publish_date')
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    # Filter by status if provided
    status_filter = request.GET.get('status', '')
    if status_filter:
        posts = posts.filter(status=status_filter)
    
    context = {
        'posts': posts,
        'pending_count': pending_count,
    }
    
    return render(request, 'management/blog/blog_posts_list.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_post_create(request):
    """Create a new blog post"""
    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_create'):
            messages.error(request, 'You do not have permission to create blog posts.')
            return redirect('management:blog_posts_list')

        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    post = form.save(commit=False)
                    post.author = request.user
                    post.save()
            except IntegrityError:
                logger.exception('blog_post_create: IntegrityError saving post')
                messages.error(request, 'Could not save this post — please check the details and try again.')
            except Exception:
                logger.exception('blog_post_create: unexpected error saving post')
                messages.error(request, 'Something went wrong while saving this post. Please try again.')
            else:
                messages.success(request, f'Blog post "{post.title}" created successfully!')
                return redirect('management:blog_posts_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BlogPostForm()
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'pending_count': pending_count,
        'action': 'Create',
    }
    
    return render(request, 'management/blog/blog_post_form.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_post_edit(request, pk):
    """Edit an existing blog post"""
    post = get_object_or_404(BlogPost, pk=pk)

    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_edit'):
            messages.error(request, 'You do not have permission to edit blog posts.')
            return redirect('management:blog_posts_list')

        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            try:
                with transaction.atomic():
                    post = form.save()
            except IntegrityError:
                logger.exception('blog_post_edit: IntegrityError saving post pk=%s', pk)
                messages.error(request, 'Could not save this post — please check the details and try again.')
            except Exception:
                logger.exception('blog_post_edit: unexpected error saving post pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this post. Please try again.')
            else:
                messages.success(request, f'Blog post "{post.title}" updated successfully!')
                return redirect('management:blog_posts_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BlogPostForm(instance=post)
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'post': post,
        'pending_count': pending_count,
        'action': 'Edit',
    }
    
    return render(request, 'management/blog/blog_post_form.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_post_delete(request, pk):
    """Delete a blog post"""
    post = get_object_or_404(BlogPost, pk=pk)

    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_delete'):
            messages.error(request, 'You do not have permission to delete blog posts.')
            return redirect('management:blog_posts_list')

        post_title = post.title
        try:
            post.delete()
            messages.success(request, f'Blog post "{post_title}" deleted successfully!')
        except Exception:
            logger.exception('blog_post_delete: unexpected error deleting post pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this post. Please try again.')
        return redirect('management:blog_posts_list')

    return redirect('management:blog_posts_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_categories_list(request):
    """List all blog categories"""
    if not _has_permission(request, 'blog', 'can_view'):
        messages.error(request, 'You do not have permission to view blog categories.')
        return redirect('management:dashboard')

    categories = BlogCategory.objects.all().order_by('name')
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'categories': categories,
        'pending_count': pending_count,
    }
    
    return render(request, 'management/blog/blog_categories_list.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_category_create(request):
    """Create a new blog category"""
    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_create'):
            messages.error(request, 'You do not have permission to create blog categories.')
            return redirect('management:blog_categories_list')

        form = BlogCategoryForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    category = form.save()
            except IntegrityError:
                logger.exception('blog_category_create: IntegrityError saving category')
                messages.error(request, 'Could not save this category — that name may already be in use.')
            except Exception:
                logger.exception('blog_category_create: unexpected error saving category')
                messages.error(request, 'Something went wrong while saving this category. Please try again.')
            else:
                messages.success(request, f'Category "{category.name}" created successfully!')
                return redirect('management:blog_categories_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BlogCategoryForm()
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'pending_count': pending_count,
        'action': 'Create',
    }
    
    return render(request, 'management/blog/blog_category_form.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_category_edit(request, pk):
    """Edit an existing blog category"""
    category = get_object_or_404(BlogCategory, pk=pk)

    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_edit'):
            messages.error(request, 'You do not have permission to edit blog categories.')
            return redirect('management:blog_categories_list')

        form = BlogCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                with transaction.atomic():
                    category = form.save()
            except IntegrityError:
                logger.exception('blog_category_edit: IntegrityError saving category pk=%s', pk)
                messages.error(request, 'Could not save this category — that name may already be in use.')
            except Exception:
                logger.exception('blog_category_edit: unexpected error saving category pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this category. Please try again.')
            else:
                messages.success(request, f'Category "{category.name}" updated successfully!')
                return redirect('management:blog_categories_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BlogCategoryForm(instance=category)
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'category': category,
        'pending_count': pending_count,
        'action': 'Edit',
    }
    
    return render(request, 'management/blog/blog_category_form.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_category_delete(request, pk):
    """Delete a blog category"""
    category = get_object_or_404(BlogCategory, pk=pk)

    if request.method == 'POST':
        if not _has_permission(request, 'blog', 'can_delete'):
            messages.error(request, 'You do not have permission to delete blog categories.')
            return redirect('management:blog_categories_list')

        post_count = category.blog_posts.count()
        if post_count:
            messages.error(
                request,
                f'Cannot delete "{category.name}" — {post_count} blog post(s) are still linked to it.'
            )
            return redirect('management:blog_categories_list')

        category_name = category.name
        try:
            category.delete()
            messages.success(request, f'Category "{category_name}" deleted successfully!')
        except Exception:
            logger.exception('blog_category_delete: unexpected error deleting category pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this category. Please try again.')
        return redirect('management:blog_categories_list')

    return redirect('management:blog_categories_list')


def _generate_password(length=12):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each required character class
        if (any(c.islower() for c in pwd)
                and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)):
            return pwd
 
 
# _send_new_user_credentials removed — logic moved to
# eduweb.emailservices.send_admin_created_user_email


# ---------------------------------------------------------------------------
# VIEW 1 — users_list  (GET: list + stats; POST bulk actions handled here)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('user_management', 'can_edit')
def users_list(request):
    """
    Main user management page.
    Serves the single unified template with all modals embedded.
    Handles bulk activate/deactivate via POST.
    """
    # ── Bulk action (POST from modal-less bulk bar) ──────────────────────────
    if request.method == 'POST':
        return _handle_bulk_action(request)

    if not _has_permission(request, 'user_management', 'can_view'):
        messages.error(request, 'You do not have permission to view user management.')
        return redirect('management:dashboard')

    # ── Queryset + filters ───────────────────────────────────────────────────
    search_form = UserSearchForm(request.GET or None)
    qs = User.objects.select_related('profile').all()
 
    if search_form.is_valid():
        search = search_form.cleaned_data.get('search')
        role   = search_form.cleaned_data.get('role')
        active = search_form.cleaned_data.get('is_active')
 
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        if role:
            qs = qs.filter(profile__role=role)
        if active:
            qs = qs.filter(is_active=(active == 'true'))
 
    qs = qs.order_by('-date_joined')
 
    # ── Stats ────────────────────────────────────────────────────────────────
    stats = {
        'total_users':  User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'staff_users':  User.objects.filter(is_staff=True).count(),
        'students':     UserProfile.objects.filter(role='student').count(),
        'instructors':  UserProfile.objects.filter(role='instructor').count(),
    }
 
    # ── Pagination ───────────────────────────────────────────────────────────
    paginator = Paginator(qs, 25)
    users_page = paginator.get_page(request.GET.get('page'))
 
    return render(request, 'management/user_management.html', {
        'users':        users_page,
        'search_form':  search_form,
        'stats':        stats,
        'create_form':  UserCreateForm(),
        'profile_form': UserProfileForm(),
    })
 
 
def _handle_bulk_action(request):
    """Internal handler for bulk activate/deactivate."""
    action   = request.POST.get('action')
    user_ids = request.POST.get('user_ids', '')
 
    try:
        ids = [int(uid) for uid in user_ids.split(',') if uid.strip()]
    except ValueError:
        messages.error(request, 'Invalid user selection.')
        return redirect('management:users_list')
 
    # Never allow self-modification
    ids = [i for i in ids if i != request.user.id]

    if not ids:
        messages.warning(request, 'No valid users selected.')
        return redirect('management:users_list')

    affected = User.objects.filter(id__in=ids)

    # Superuser accounts are never touched by a bulk action run by a
    # non-superuser — silently drop them from the batch rather than failing
    # the whole request, so the rest of the selection still goes through.
    if not request.user.is_superuser:
        affected = affected.filter(is_superuser=False)
 
    if action == 'activate':
        affected.update(is_active=True)
        messages.success(request, f'{affected.count()} user(s) activated.')
    elif action == 'deactivate':
        affected.update(is_active=False)
        messages.success(request, f'{affected.count()} user(s) deactivated.')
    else:
        messages.error(request, 'Unknown action.')
 
    return redirect('management:users_list')
 
 
# ---------------------------------------------------------------------------
# VIEW 2 — user_create  (GET stub / POST AJAX)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def user_create(request):
    """
    AJAX POST — creates a user, generates a secure password, marks account as
    inactive until email is verified, then sends a single email containing:
      • login credentials (username + temporary password)
      • email verification link
      • instruction to verify BEFORE logging in

    Returns JSON { success, user_id, email_sent, message }.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not _has_permission(request, 'user_management', 'can_create'):
        return JsonResponse({'success': False, 'message': 'You do not have permission to create users.'}, status=403)

    raw_password = _generate_password()
    post_data = request.POST.copy()
    post_data['password1'] = raw_password
    post_data['password2'] = raw_password

    form = UserCreateForm(post_data)

    if not form.is_valid():
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    try:
        with transaction.atomic():
            user = form.save(commit=False)
            role = form.cleaned_data.get('role', 'student')

            # is_staff (full admin-portal bypass) may only be granted by a true
            # superuser — user_management.can_create alone isn't enough to hand
            # out that tier to someone else.
            if not request.user.is_superuser:
                user.is_staff = False

            # Enforce capitalization on names
            user.first_name = user.first_name.strip().title()
            user.last_name = user.last_name.strip().title()

            # Set the password correctly so it is hashed in the database
            user.set_password(raw_password)

            # Account starts inactive — activated automatically after email verification
            user.is_active = False
            user.save()

            # Sync role onto the auto-created profile
            user.profile.role = role
            user.profile.email_verified = False
            user.profile.must_change_password = True
            user.profile.save(update_fields=['role', 'email_verified', 'must_change_password'])

            AuditLog.objects.create(
                user=request.user,
                action='create',
                model_name='User',
                object_id=str(user.pk),
                description=(
                    f'{request.user.username} created user {user.username} with role "{role}"'
                    + (' and staff (admin-portal) access' if user.is_staff else '') + '.'
                ),
            )
    except IntegrityError:
        logger.exception('user_create: IntegrityError creating user')
        return JsonResponse({'success': False, 'message': 'Could not create this user — that username or email may already be in use.'}, status=400)
    except Exception:
        logger.exception('user_create: unexpected error creating user')
        return JsonResponse({'success': False, 'message': 'Something went wrong while creating this user. Please try again.'}, status=500)

    # Delegate email entirely to the service module (non-fatal if it fails)
    email_sent = send_admin_created_user_email(request, user, raw_password)

    status_note = 'sent' if email_sent else 'could not be sent (check email config)'
    return JsonResponse({
        'success': True,
        'user_id': user.id,
        'email_sent': email_sent,
        'message': (
            f'User {user.username} created. '
            f'Verification + credentials email {status_note}. '
            f'Account will activate after email verification.'
        ),
    })
 
 
# ---------------------------------------------------------------------------
# VIEW 3 — user_edit  (GET redirects to list; POST AJAX; also handles delete)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def user_edit(request, pk):
    """
    AJAX POST — updates User + UserProfile in one atomic transaction.
    Returns JSON { success, errors }.
    User deletion is not permitted.
    """
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)

    if request.method == 'GET':
        return redirect('management:users_list')

    if not _has_permission(request, 'user_management', 'can_edit'):
        return JsonResponse({'success': False, 'message': 'You do not have permission to edit users.'}, status=403)

    # Deletion is disabled — reject any attempt explicitly
    if request.POST.get('action') == 'delete':
        return JsonResponse({'success': False, 'message': 'User deletion is not permitted.'}, status=403)

    # Superuser accounts may only be edited by another superuser
    if _is_superuser_protected(request, user):
        return JsonResponse({'success': False, 'message': 'Superuser accounts cannot be edited by non-superuser staff.'}, status=403)

    original_is_staff = user.is_staff
    original_role = user.profile.role

    # ── Edit action ──────────────────────────────────────────────────────────
    user_form    = UserEditForm(request.POST, instance=user)
    profile_form = UserProfileForm(request.POST, request.FILES, instance=user.profile)

    if not (user_form.is_valid() and profile_form.is_valid()):
        errors = {**user_form.errors, **profile_form.errors}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        messages.error(request, 'Please fix the errors below.')
        return redirect('management:users_list')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        with transaction.atomic():
            updated_user    = user_form.save(commit=False)
            updated_profile = profile_form.save(commit=False)

            # is_staff (full admin-portal bypass) may only be granted/revoked by
            # a true superuser — user_management.can_edit alone isn't enough,
            # and this also blocks a non-superuser admin from unlocking
            # themselves via their own user_edit request.
            if not request.user.is_superuser:
                updated_user.is_staff = original_is_staff

            updated_user.save()
            updated_profile.save()

            if updated_user.is_staff != original_is_staff:
                AuditLog.objects.create(
                    user=request.user,
                    action='permission_change',
                    model_name='User',
                    object_id=str(updated_user.pk),
                    description=(
                        f'{request.user.username} '
                        f'{"granted" if updated_user.is_staff else "revoked"} admin-portal (is_staff) '
                        f'access for {updated_user.username}.'
                    ),
                )

            # Role can also change from this form's role dropdown, not just via
            # user_change_role — clear stale overrides here too so the user
            # starts clean on whatever role they were just switched to.
            if updated_profile.role != original_role:
                _clear_stale_permission_overrides(updated_user)
                AuditLog.objects.create(
                    user=request.user,
                    action='permission_change',
                    model_name='UserProfile',
                    object_id=str(updated_user.pk),
                    description=(
                        f'Changed role for {updated_user.username} from "{original_role}" '
                        f'to "{updated_profile.role}" via user edit. Prior permission overrides were cleared.'
                    ),
                )
    except IntegrityError:
        logger.exception('user_edit: IntegrityError updating user pk=%s', pk)
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Could not save — that username or email may already be in use.'}, status=400)
        messages.error(request, 'Could not save — that username or email may already be in use.')
        return redirect('management:users_list')
    except Exception:
        logger.exception('user_edit: unexpected error updating user pk=%s', pk)
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Something went wrong while saving. Please try again.'}, status=500)
        messages.error(request, 'Something went wrong while saving. Please try again.')
        return redirect('management:users_list')

    if is_ajax:
        return JsonResponse({'success': True, 'message': f'User {user.username} updated.'})

    messages.success(request, f'User {user.username} updated successfully.')
    return redirect('management:users_list')
 
 
# ---------------------------------------------------------------------------
# UNCHANGED small endpoints (kept as-is; included for completeness)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('user_management', 'can_edit')
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)

    if user.id == request.user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Cannot deactivate your own account.'}, status=400)
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('management:users_list')

    if _is_superuser_protected(request, user):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Superuser accounts cannot be activated or deactivated by non-superuser staff.'}, status=403)
        messages.error(request, 'Superuser accounts cannot be activated or deactivated by non-superuser staff.')
        return redirect('management:users_list')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])

    AuditLog.objects.create(
        user=request.user,
        action='update',
        model_name='User',
        object_id=str(user.pk),
        description=(
            f'{request.user.username} {"activated" if user.is_active else "deactivated"} '
            f'user {user.username}.'
        ),
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'is_active': user.is_active})

    messages.success(request, f'User {user.username} {"activated" if user.is_active else "deactivated"}.')
    return redirect('management:users_list')
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def user_change_role(request, pk):
    if not _has_permission(request, 'user_management', 'can_edit'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        messages.error(request, 'You do not have permission to change user roles.')
        return redirect('management:users_list')

    if int(pk) == request.user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'You cannot change your own role.'}, status=403)
        messages.error(request, 'You cannot change your own role.')
        return redirect('management:users_list')

    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)

    if _is_superuser_protected(request, user):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Superuser accounts cannot have their role changed by non-superuser staff.'}, status=403)
        messages.error(request, 'Superuser accounts cannot have their role changed by non-superuser staff.')
        return redirect('management:users_list')

    form = QuickRoleChangeForm(request.POST)

    if form.is_valid():
        old_role = user.profile.role
        role = form.cleaned_data['role']
        with transaction.atomic():
            user.profile.role = role
            user.profile.save(update_fields=['role'])
            if old_role != role:
                _clear_stale_permission_overrides(user)
                AuditLog.objects.create(
                    user=request.user,
                    action='permission_change',
                    model_name='UserProfile',
                    object_id=str(user.pk),
                    description=(
                        f'Changed role for {user.username} from "{old_role}" to "{role}". '
                        f'Prior permission overrides were cleared.'
                    ),
                )
        if old_role != role:
            _notify(
                user=user,
                title='Your account role has changed',
                message=f'Your role was changed from {old_role} to {user.profile.get_role_display()} by an administrator.',
                notif_type='system',
            )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'role': user.profile.role,
                'role_display': user.profile.get_role_display(),
            })
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    # Non-AJAX fallback — the only real caller (role_assign.html) always sends
    # the AJAX header, so this path is dead in practice today, but it should
    # still surface *something* rather than silently redirecting on a
    # rejected role change if some future caller ever hits it without XHR.
    first_error = next((e for errs in form.errors.values() for e in errs), 'Invalid role selection.')
    messages.error(request, first_error)
    return redirect('management:users_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('user_management', 'can_view', redirect_to='management:users_list', skip_get=False)
def user_quick_info(request, pk):
    """AJAX GET — returns JSON snapshot for view/edit modals."""
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    profile = user.profile

    # Permissions snapshot — scoped to this user's actual role, matching
    # the permissions modal and the role-assignment page exactly.
    _, _, permissions_data = _effective_permissions_for_user(user)

    return JsonResponse({
        'id':          user.id,
        'username':    user.username,
        'full_name':   user.get_full_name() or user.username,
        'email':       user.email,
        'role':        profile.get_role_display(),
        'role_value':  profile.role,
        'is_active':   user.is_active,
        'is_staff':    user.is_staff,
        'date_joined': user.date_joined.strftime('%B %d, %Y'),
        'last_login':  user.last_login.strftime('%B %d, %Y') if user.last_login else 'Never',
        'avatar_url':  profile.avatar.url if profile.avatar else None,
        'phone':               profile.phone,
        'date_of_birth':       str(profile.date_of_birth) if profile.date_of_birth else '',
        'bio':                 profile.bio,
        'address':             profile.address,
        'city':                profile.city,
        'country':             profile.country,
        'website':             profile.website,
        'linkedin':            profile.linkedin,
        'twitter':             profile.twitter,
        'email_notifications': profile.email_notifications,
        'marketing_emails':    profile.marketing_emails,
        'permissions':         permissions_data,
    })

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def role_assign(request):
    """
    Standalone role-assign + permissions page.
    GET  → render page (optionally pre-select user via ?user_id=<pk>)
    POST → handled via AJAX to existing user_change_role / user_permissions endpoints.
    """
    if not _has_permission(request, 'role_permissions', 'can_view'):
        messages.error(request, 'You do not have permission to view role/permission assignment.')
        return redirect('management:dashboard')

    selected_user = None
    user_id = request.GET.get('user_id')
    if user_id:
        try:
            candidate = User.objects.select_related('profile').get(pk=int(user_id))
            if candidate.pk != request.user.pk and not _is_superuser_protected(request, candidate):
                selected_user = candidate
        except (User.DoesNotExist, ValueError):
            pass

    # All roles/users display here now — no role-based filtering. The
    # logged-in user is still excluded: this page is for assigning roles/
    # permissions to *other* accounts; letting an admin select themselves
    # here is exactly the self-escalation path user_change_role/
    # user_permissions guard against server-side, so it stays out of the
    # picker regardless of role.
    users = (
        User.objects.select_related('profile')
        .exclude(pk=request.user.pk)
        .order_by('first_name', 'last_name', 'username')
    )

    # Superuser accounts are completely off-limits to this page for anyone
    # who isn't a superuser themselves — they shouldn't even appear in the
    # picker, let alone be reachable via ?user_id=. The write endpoints
    # (user_change_role / user_permissions) already reject this server-side
    # too, so this is belt-and-braces, not the only line of defense.
    if not request.user.is_superuser:
        users = users.exclude(is_superuser=True)

    return render(request, 'management/role_assign.html', {
        'users': users,
        'selected_user': selected_user,
        'role_choices': list(UserProfile.ROLE_CHOICES),
    })
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def user_permissions(request, pk):
    """
    GET  → JSON: current effective permissions for this user (user override or role default).
    POST → save/upsert user-level overrides for all modules..
    """
    target = get_object_or_404(User.objects.select_related('profile'), pk=pk)

    if request.method == 'GET':
        if not _has_permission(request, 'user_management', 'can_view'):
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        modules, actions, result = _effective_permissions_for_user(target)
        return JsonResponse({'success': True, 'permissions': result, 'modules': modules, 'actions': actions})

    # POST — upsert user-level rows for every submitted module
    if not _has_permission(request, 'user_management', 'can_edit'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        messages.error(request, 'You do not have permission to edit user permissions.')
        return redirect('management:users_list')

    if target.pk == request.user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'You cannot edit your own permissions.'}, status=403)
        messages.error(request, 'You cannot edit your own permissions.')
        return redirect('management:users_list')

    if _is_superuser_protected(request, target):
        error = 'Superuser accounts cannot have their permissions edited by non-superuser staff.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': error}, status=403)
        messages.error(request, error)
        return redirect('management:users_list')

    if target.profile.role == 'student':
        # StaffPermissionsMatrix.user_can_view_any() already refuses to honor
        # any override row for a student account (see its docstring), so a
        # saved grant here would just be permanently inert — reject outright
        # instead of letting an admin believe it took effect.
        error = 'Permission overrides don\'t apply to student accounts — change their role first if they need staff access.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': error}, status=400)
        messages.error(request, error)
        return redirect('management:users_list')

    MODULES, ACTION_FIELDS, _ = _permission_modules_for_role(target.profile.role)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        with transaction.atomic():
            for module in MODULES:
                prefix = f'perm_{module}_'
                row_data = {
                    f: bool(request.POST.get(f'{prefix}{f}'))
                    for f in ACTION_FIELDS
                }
                StaffPermissionsMatrix.objects.update_or_create(
                    user=target, module=module, role=None,
                    defaults={**row_data, 'updated_by': request.user},
                )
            AuditLog.objects.create(
                user=request.user,
                action='permission_change',
                model_name='StaffPermissionsMatrix',
                object_id=str(target.pk),
                description=f'Updated user-level permission overrides for {target.username}.',
            )
    except Exception:
        logger.exception('user_permissions: unexpected error saving overrides for user pk=%s', pk)
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Something went wrong while saving permissions. Please try again.'}, status=500)
        messages.error(request, 'Something went wrong while saving permissions. Please try again.')
        return redirect('management:users_list')

    _notify(
        user=target,
        title='Your permissions have changed',
        message='An administrator updated your account permissions.',
        notif_type='system',
    )

    if is_ajax:
        return JsonResponse({'success': True, 'message': f'Permissions updated for {target.username}.'})

    messages.success(request, f'Permissions updated for {target.username}.')
    return redirect('management:users_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('user_management', 'can_edit')
def bulk_user_action(request):
    """Standalone bulk action endpoint (also handled in users_list POST)."""
    action   = request.POST.get('action')
    user_ids = request.POST.get('user_ids', '')
 
    try:
        ids = [int(uid) for uid in user_ids.split(',') if uid.strip()]
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid user IDs.'}, status=400)
 
    ids = [i for i in ids if i != request.user.id]
 
    if not ids:
        return JsonResponse({'success': False, 'message': 'No valid users selected.'}, status=400)
 
    affected = User.objects.filter(id__in=ids)
 
    if action == 'activate':
        affected.update(is_active=True)
        msg = f'{affected.count()} user(s) activated.'
    elif action == 'deactivate':
        affected.update(is_active=False)
        msg = f'{affected.count()} user(s) deactivated.'
    else:
        return JsonResponse({'success': False, 'message': 'Unknown action.'}, status=400)
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': msg})
 
    messages.success(request, msg)
    return redirect('management:users_list')


# ==================== SYSTEM CONFIGURATION VIEWS ====================
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def system_config_list(request):
    """List all system configurations"""
    configs = SystemConfiguration.objects.all().order_by('key')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        configs = configs.filter(
            Q(key__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(configs, 20)
    page = request.GET.get('page', 1)
    configs_page = paginator.get_page(page)
    
    context = {
        'configs': configs_page,
        'search_query': search_query,
        'total_configs': configs.count()
    }
    return render(request, 'management/system_config/list.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def system_config_create(request):
    """Create new system configuration"""
    if request.method == 'POST':
        form = SystemConfigurationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    config = form.save(commit=False)
                    config.updated_by = request.user
                    config.save()

                    AuditLog.objects.create(
                        user=request.user,
                        action='create',
                        model_name='SystemConfiguration',
                        object_id=config.id,
                        description=f'Created configuration: {config.key}'
                    )
            except IntegrityError:
                logger.exception('system_config_create: IntegrityError saving config')
                messages.error(request, 'Could not save — that configuration key may already be in use.')
            except Exception:
                logger.exception('system_config_create: unexpected error saving config')
                messages.error(request, 'Something went wrong while saving this configuration. Please try again.')
            else:
                messages.success(request, f'Configuration "{config.key}" created successfully.')
                return redirect('management:system_config_list')
    else:
        form = SystemConfigurationForm()
    
    return render(request, 'management/system_config/create.html', {'form': form})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def system_config_edit(request, pk):
    """Edit system configuration"""
    config = get_object_or_404(SystemConfiguration, pk=pk)
    
    if request.method == 'POST':
        form = SystemConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            try:
                with transaction.atomic():
                    config = form.save(commit=False)
                    config.updated_by = request.user
                    config.save()

                    AuditLog.objects.create(
                        user=request.user,
                        action='update',
                        model_name='SystemConfiguration',
                        object_id=config.id,
                        description=f'Updated configuration: {config.key}'
                    )
            except IntegrityError:
                logger.exception('system_config_edit: IntegrityError saving config pk=%s', pk)
                messages.error(request, 'Could not save — that configuration key may already be in use.')
            except Exception:
                logger.exception('system_config_edit: unexpected error saving config pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this configuration. Please try again.')
            else:
                messages.success(request, f'Configuration "{config.key}" updated successfully.')
                return redirect('management:system_config_list')
    else:
        form = SystemConfigurationForm(instance=config)
    
    return render(request, 'management/system_config/edit.html', {
        'form': form,
        'config': config
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def system_config_delete(request, pk):
    """Delete system configuration"""
    config = get_object_or_404(SystemConfiguration, pk=pk)
    
    if request.method == 'POST':
        config_key = config.key
        try:
            with transaction.atomic():
                # Create audit log before deletion
                AuditLog.objects.create(
                    user=request.user,
                    action='delete',
                    model_name='SystemConfiguration',
                    object_id=config.id,
                    description=f'Deleted configuration: {config_key}'
                )
                config.delete()
        except Exception:
            logger.exception('system_config_delete: unexpected error deleting config pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this configuration. Please try again.')
            return redirect('management:system_config_list')
        messages.success(request, f'Configuration "{config_key}" deleted successfully.')
        return redirect('management:system_config_list')
    
    return render(request, 'management/system_config/delete.html', {'config': config})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def branding_config(request):
    """Manage branding configuration"""
    if request.method == 'POST':
        try:
            form = BrandingConfigForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        # Save each configuration
                        for key, value in form.cleaned_data.items():
                            if value:
                                config, created = SystemConfiguration.objects.get_or_create(
                                    key=f'branding_{key}',
                                    defaults={
                                        'setting_type': 'text',
                                        'is_public': True,
                                        'updated_by': request.user
                                    }
                                )
                                config.value = str(value)
                                config.updated_by = request.user
                                config.save()

                        AuditLog.objects.create(
                            user=request.user,
                            action='update',
                            model_name='SystemConfiguration',
                            description='Updated branding configuration'
                        )
                except Exception:
                    logger.exception('branding_config: unexpected error saving branding settings')
                    messages.error(request, 'Something went wrong while saving these settings. Please try again.')
                else:
                    messages.success(request, 'Branding settings updated successfully.')
                    return redirect('management:branding_config')
        except SuspiciousOperation:
            logger.warning('branding_config: oversized/suspicious upload')
            messages.error(request, 'Your changes could not be saved — the file you uploaded was too large. Please use a smaller file and try again.')
            form = BrandingConfigForm()
    else:
        # Load existing values
        initial_data = {}
        for key in ['site_name', 'site_tagline', 'primary_color']:
            try:
                config = SystemConfiguration.objects.get(key=f'branding_{key}')
                initial_data[key] = config.value
            except SystemConfiguration.DoesNotExist:
                pass
        
        form = BrandingConfigForm(initial=initial_data)
    
    return render(request, 'management/system_config/branding.html', {'form': form})


# account name -> SystemConfiguration key prefix for that account's credentials/sender identity.
# SMTP host/port are shared between accounts and stored under the bare 'email_' prefix.
_EMAIL_ACCOUNTS = {'default': 'email_', 'admissions': 'email_admissions_', 'store': 'email_store_'}
_SERVER_FIELDS = ['smtp_host', 'smtp_port']
_ACCOUNT_FIELDS = ['smtp_username', 'smtp_password', 'from_email', 'from_name']


def _load_server_form():
    initial = {}
    for key in _SERVER_FIELDS:
        val = SystemConfiguration.get_value(f'email_{key}')
        if val:
            initial[key] = val
    return EmailServerForm(initial=initial)


def _load_account_form(account):
    db_prefix = _EMAIL_ACCOUNTS[account]
    initial = {}
    # smtp_password is intentionally never loaded back — it never round-trips to the browser.
    for key in ['smtp_username', 'from_email', 'from_name']:
        val = SystemConfiguration.get_value(f'{db_prefix}{key}')
        if val:
            initial[key] = val
    return EmailAccountForm(initial=initial, prefix=account)


def _save_config_keys(request, db_prefix, cleaned_data, encrypt_fields=()):
    """Persists a group of SystemConfiguration rows as one unit — wrapped in a
    transaction so a mid-loop failure can't leave some keys updated and others stale."""
    with transaction.atomic():
        for key, value in cleaned_data.items():
            stored_value = encrypt_secret(value) if key in encrypt_fields else str(value)
            config, created = SystemConfiguration.objects.get_or_create(
                key=f'{db_prefix}{key}',
                defaults={
                    'setting_type': 'text',
                    'is_public': False,
                    'updated_by': request.user
                }
            )
            config.value = stored_value
            config.updated_by = request.user
            config.save()

        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='SystemConfiguration',
            description=f'Updated {db_prefix}* email configuration'
        )


def _clear_config_keys(request, db_prefix, fields, description):
    """Deletes a group of SystemConfiguration rows — used by the 'Clear' actions to
    actually remove an account/server override so it falls back to .env again."""
    SystemConfiguration.objects.filter(key__in=[f'{db_prefix}{f}' for f in fields]).delete()
    AuditLog.objects.create(
        user=request.user,
        action='update',
        model_name='SystemConfiguration',
        description=description,
    )


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def email_config(request):
    """Manage the shared SMTP server plus every outbound-email account
    (default/admissions/store — see _EMAIL_ACCOUNTS) on one page.
    Independent forms, saved independently, each with its own Clear action
    to remove the override and fall back to .env (or the default account)
    again."""
    target = request.POST.get('save') if request.method == 'POST' else None

    def _all_account_forms(overrides=None):
        overrides = overrides or {}
        return {
            account: overrides.get(account) or _load_account_form(account)
            for account in _EMAIL_ACCOUNTS
        }

    if target and target.startswith('test_') and target[len('test_'):] in _EMAIL_ACCOUNTS:
        account = target[len('test_'):]
        account_label = account.title()
        to_email = request.user.email
        if not to_email:
            messages.error(request, 'Your account has no email address on file to send the test to.')
            return redirect('management:email_config')

        ok, detail, used_fallback, diagnostics = send_test_email(account, to_email)
        auth_user = diagnostics.get('username') if diagnostics else None
        auth_note = f' Authenticated SMTP user: {auth_user}.' if auth_user else ''
        if ok:
            note = (f' — note: the {account_label.lower()} account has no override configured, '
                     'so this actually went out via the default account.'
                     ) if used_fallback else ''
            messages.success(
                request,
                f'{account_label} account test succeeded — sent to {to_email} from {detail}.{note}{auth_note}'
            )
        else:
            messages.error(request, f'{account_label} account test failed: {detail}.{auth_note}')
        return redirect('management:email_config')

    if target == 'clear_server':
        _clear_config_keys(request, 'email_', _SERVER_FIELDS, 'Cleared shared SMTP server settings')
        messages.success(request, 'SMTP server settings cleared. All accounts will fall back to .env until a server is configured again.')
        return redirect('management:email_config')

    if target and target.startswith('clear_') and target[len('clear_'):] in _EMAIL_ACCOUNTS:
        account = target[len('clear_'):]
        db_prefix = _EMAIL_ACCOUNTS[account]
        _clear_config_keys(request, db_prefix, _ACCOUNT_FIELDS, f'Cleared {db_prefix}* email configuration')
        account_label = account.title()
        fallback = 'the default account' if account != 'default' else '.env'
        messages.success(request, f'{account_label} account cleared. It will fall back to {fallback} until reconfigured.')
        return redirect('management:email_config')

    if target == 'server':
        submitted = EmailServerForm(request.POST)
        if submitted.is_valid():
            _save_config_keys(request, 'email_', submitted.cleaned_data)
            messages.success(request, 'SMTP server settings updated successfully.')
            return redirect('management:email_config')
        messages.error(request, 'SMTP server settings were not saved — please fix the errors below.')
        server_form = submitted
        account_forms = _all_account_forms()

    elif target in _EMAIL_ACCOUNTS:
        db_prefix = _EMAIL_ACCOUNTS[target]
        submitted = EmailAccountForm(request.POST, prefix=target)
        account_label = target.title()
        if submitted.is_valid():
            # Blank password means "keep the existing one" — never overwrite a real
            # password with an empty value just because the admin didn't retype it.
            to_save = dict(submitted.cleaned_data)
            if not to_save.get('smtp_password'):
                to_save.pop('smtp_password', None)
            _save_config_keys(request, db_prefix, to_save, encrypt_fields={'smtp_password'})
            messages.success(request, f'{account_label} account settings updated successfully.')
            return redirect('management:email_config')
        messages.error(request, f'{account_label} account settings were not saved — please fix the errors below.')
        server_form = _load_server_form()
        account_forms = _all_account_forms({target: submitted})

    else:
        server_form = _load_server_form()
        account_forms = _all_account_forms()

    return render(request, 'management/system_config/email.html', {
        'server_form': server_form,
        'default_form': account_forms['default'],
        'admissions_form': account_forms['admissions'],
        'store_form': account_forms['store'],
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def notification_config(request):
    """Manage notification settings"""
    if request.method == 'POST':
        form = NotificationConfigForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save notification configuration
                    for key, value in form.cleaned_data.items():
                        config, created = SystemConfiguration.objects.get_or_create(
                            key=f'notification_{key}',
                            defaults={
                                'setting_type': 'boolean' if isinstance(value, bool) else 'text',
                                'is_public': False,
                                'updated_by': request.user
                            }
                        )
                        config.value = str(value)
                        config.updated_by = request.user
                        config.save()

                    AuditLog.objects.create(
                        user=request.user,
                        action='update',
                        model_name='SystemConfiguration',
                        description='Updated notification configuration'
                    )
            except Exception:
                logger.exception('notification_config: unexpected error saving notification settings')
                messages.error(request, 'Something went wrong while saving these settings. Please try again.')
            else:
                messages.success(request, 'Notification settings updated successfully.')
                return redirect('management:notification_config')
    else:
        # Load existing values
        initial_data = {}
        form = NotificationConfigForm(initial=initial_data)
    
    return render(request, 'management/system_config/notifications.html', {'form': form})



# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS  (unchanged — keep as-is)
# ─────────────────────────────────────────────────────────────────────────────
 
def _pluralise(count, singular, plural=None):
    """Return '1 lesson' / '2 lessons' etc."""
    label = plural if (plural and count != 1) else (singular + ('' if count == 1 else 's'))
    return f"{count} {label}"
 
 
def _notify_instructor(course, requesting_user):
    """Notify an assigned instructor they have been given a course."""
    if course.instructor and course.instructor != requesting_user:
        Notification.objects.create(
            user=course.instructor,
            notification_type='system',
            title=f'Course Assigned: {course.title}',
            message=(
                f'You have been assigned as instructor for "{course.title}". '
                f'You can now add content, lessons, and assessments.'
            ),
            link=f'/instructor/courses/{course.slug}/manage/',
        )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# VIEW 1 — LIST  (GET: render page | POST: create via modal)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def lms_courses_list(request):
    """
    Single-page hub: course table + create modal + edit modal (inline form).
    POST here is no longer used for creates (lms_course_save handles both
    create and update), but the create_form is still rendered for the modal.
    """
    if not _has_permission(request, 'lms_courses', 'can_view'):
        messages.error(request, 'You do not have permission to view LMS courses.')
        return redirect('management:dashboard')

    # ── Base queryset ─────────────────────────────────────────────────────────
    courses = (
        LMSCourse.objects
        .select_related('instructor', 'academic_course__program__department')
        .prefetch_related('enrollments')
        .annotate(lesson_count=Count('lessons', distinct=True))
        .order_by('-created_at')
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    program_id = request.GET.get('program', '').strip()
    if program_id.isdigit():
        courses = courses.filter(academic_course__program_id=program_id)

    published_filter = request.GET.get('published', '').strip()
    if published_filter == 'published':
        courses = courses.filter(is_published=True)
    elif published_filter == 'draft':
        courses = courses.filter(is_published=False)
 
    # ── Stats (always from the full, unfiltered table) ────────────────────────
    _s = LMSCourse.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(is_published=True)),
        draft=Count('id', filter=Q(is_published=False)),
        featured=Count('id', filter=Q(is_featured=True)),
    )
 
    context = {
        'courses':      courses,
        'create_form':  LMSCourseForm(),               # create modal
        'edit_form':    LMSCourseForm(),               # edit modal (values filled by JS)
        'programs':     Program.objects.only('id', 'name').order_by('name'),
        'stats': {
            'total':     _s['total'],
            'published': _s['published'],
            'draft':     _s['draft'],
            'featured':  _s['featured'],
        },
    }
    return render(request, 'management/lms_course/list.html', context)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# AJAX HELPER — academic-course data for auto-fill (create modal only)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('lms_courses', 'can_view', redirect_to='management:lms_courses_list', skip_get=False)
def lms_academic_course_data(request, pk):
    """
    AJAX — returns basic info for a given academic Course pk.
    Used by the create modal to auto-fill fields when academic_course changes.
    NOT called on edit (edit shows saved values only).
    """
    try:
        course = Course.objects.select_related('program').get(pk=pk, is_active=True)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    return JsonResponse({
        'code': course.code,
        'name': course.name,
    })
 
 
# ─────────────────────────────────────────────────────────────────────────────
# VIEW 2 — SAVE  (create + update in one endpoint)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def lms_course_save(request):
    """
    Unified create / update endpoint.
 
    POST body must include:
        _mode      = 'create' | 'edit'
        course_id  = <pk>  (required when _mode == 'edit')
 
    On success → redirect to list with a success message.
    On failure → redirect to list with an error message (modal re-open is
                 not needed because inline Select2 forms don't need re-population
                 from the server on validation failure in this design).
    """
    mode = request.POST.get('_mode', 'create')
    required_action = 'can_create' if mode == 'create' else 'can_edit'
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if not _has_permission(request, 'lms_courses', required_action):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to save LMS courses.'}]}}, status=403)
        messages.error(request, 'You do not have permission to save LMS courses.')
        return redirect('management:lms_courses_list')
    course_id = request.POST.get('course_id', '').strip()

    if mode == 'edit' and course_id.isdigit():
        # ── UPDATE ────────────────────────────────────────────────────────────
        course = get_object_or_404(LMSCourse, pk=int(course_id))
        form   = LMSCourseForm(request.POST, request.FILES, instance=course)

        if form.is_valid():
            was_published = course.is_published
            course = form.save()
 
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='LMSCourse',
                object_id=course.id,
                description=f'Updated LMS course: {course.title}',
            )
            messages.success(request, f'LMS course "{course.title}" updated successfully.')
 
            # Notify enrolled students when a draft course is first published
            if not was_published and course.is_published:
                enrolled_students = (
                    User.objects
                    .filter(
                        enrollments__course=course,
                        enrollments__status='active',
                        is_active=True,
                    )
                    .only('id')
                    .distinct()
                )
                for student in enrolled_students:
                    _notify(
                        user=student,
                        title=f'Course Now Available: {course.title}',
                        message=(
                            f'The course "{course.title}" you are enrolled in '
                            f'has been published and is now accessible.'
                        ),
                        notif_type='enrollment',
                        link=f'/courses/{course.slug}/',
                    )
            if is_ajax:
                return JsonResponse({'success': True})
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
            messages.error(request, 'Could not save — please check the form and try again.')

    else:
        # ── CREATE ────────────────────────────────────────────────────────────
        form = LMSCourseForm(request.POST, request.FILES)

        if form.is_valid():
            course = form.save()
            AuditLog.objects.create(
                user=request.user,
                action='create',
                model_name='LMSCourse',
                object_id=course.id,
                description=f'Created LMS course: {course.title}',
            )
            _notify_instructor(course, request.user)
            if is_ajax:
                return JsonResponse({'success': True})
            messages.success(request, f'LMS course "{course.title}" created successfully.')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
            messages.error(request, 'Please correct the errors in the form.')

    return redirect('management:lms_courses_list')
 
 
# ─────────────────────────────────────────────────────────────────────────────
# VIEW 3 — DETAIL  (JSON for modals, full-page fallback)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('lms_courses', 'can_view', redirect_to='management:lms_courses_list', skip_get=False)
def lms_course_detail(request, pk):
    """
    GET ?_modal=1 or XHR → JsonResponse (used by both detail AND edit modals).
    GET (normal)          → redirect to list (no standalone detail page needed).
 
    Extra fields returned for the edit modal:
        instructor_id, thumbnail_url
    """
    course = get_object_or_404(
        LMSCourse.objects.select_related(
            'instructor', 'academic_course__program__department',
        ),
        pk=pk,
    )
 
    enrollments_count = course.enrollments.count()
    lessons_count     = course.lessons.count()
 
    if (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.GET.get('_modal')
    ):
        ac = course.academic_course
        ac_program_str = ''
        if ac and ac.program:
            ac_program_str = ac.program.name
            if ac.program.department:
                ac_program_str += f' — {ac.program.department.name}'
 
        instructor_display = 'Unassigned'
        if course.instructor:
            instructor_display = course.instructor.get_full_name().strip() or course.instructor.username
 
        return JsonResponse({
            # ── Identity
            'pk':    course.pk,
            'title': course.title,
            'code':  course.code or '',
 
            # ── Descriptions
            'short_description': course.short_description or '',
            'description':       course.description or '',
 
            # ── Structured content
            'learning_objectives': (
                course.learning_objectives if isinstance(course.learning_objectives, list) else []
            ),
            'prerequisites': (
                course.prerequisites if isinstance(course.prerequisites, list) else []
            ),
 
            # ── Status
            'is_published': course.is_published,
            'is_featured':  course.is_featured,
 
            # ── Instructor
            'instructor_name': instructor_display,
            'instructor_id':   course.instructor_id or '',
 
            # ── Media
            'promo_video_url': course.promo_video_url or '',
            'thumbnail_url':   course.thumbnail.url if course.thumbnail else '',
 
            # ── SEO
            'meta_description': course.meta_description or '',
            'meta_keywords':    course.meta_keywords or '',
 
            # ── Counts
            'enrollments': enrollments_count,
            'lessons':     lessons_count,
 
            # ── Timestamps
            'created_at': course.created_at.strftime('%b %d, %Y %H:%M'),
 
            # ── Linked academic course
            'academic_course':         ac.pk   if ac else None,
            'academic_course_code':    ac.code if ac else '',
            'academic_course_name':    ac.name if ac else '',
            'academic_course_program': ac_program_str,
        })
 
    # Full-page fallback — redirect to list (edit page is gone)
    return redirect('management:lms_courses_list')
 
 
# ─────────────────────────────────────────────────────────────────────────────
# VIEW 4 — DELETE  (POST only, modal form)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('lms_courses', 'can_delete', redirect_to='management:lms_courses_list')
def lms_course_delete(request, pk):
    """
    POST → validate safety guards, then delete and redirect to list.
    GET  → redirect to list (delete only via modal POST).
 
    Safety guards:
      1. Course has lessons or sections → HARD BLOCK
      2. Course has active enrollments  → soft, cascade-deleted (allowed with confirm)
    """
    course = get_object_or_404(LMSCourse, pk=pk)
 
    if request.method == 'POST':
        lessons_count     = course.lessons.count()
        sections_count    = course.sections.count()
        enrollments_count = course.enrollments.count()
 
        if lessons_count > 0 or sections_count > 0:
            blocking = []
            if lessons_count:  blocking.append(_pluralise(lessons_count,  'lesson'))
            if sections_count: blocking.append(_pluralise(sections_count, 'section'))
            messages.error(
                request,
                f'Cannot delete "{course.title}" — it still contains '
                f'{" and ".join(blocking)}. Remove all content first.',
            )
            return redirect('management:lms_courses_list')
 
        if not request.POST.get('confirm'):
            messages.warning(request, 'Please tick the confirmation box before deleting.')
            return redirect('management:lms_courses_list')
 
        course_title = course.title
        try:
            with transaction.atomic():
                AuditLog.objects.create(
                    user=request.user,
                    action='delete',
                    model_name='LMSCourse',
                    object_id=course.id,
                    description=(
                        f'Deleted LMS course: {course_title}'
                        + (f' (had {_pluralise(enrollments_count, "enrollment")})' if enrollments_count else '')
                    ),
                )
                course.delete()
        except Exception:
            logger.exception('lms_course_delete: unexpected error deleting course pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this course. Please try again.')
            return redirect('management:lms_courses_list')
        messages.success(request, f'LMS course "{course_title}" deleted successfully.')
 
    return redirect('management:lms_courses_list')


# ==================== AUDIT LOG VIEWS ====================
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def audit_logs_list(request):
    """List all audit logs with filtering"""
    if not _has_permission(request, 'security_audit', 'can_view'):
        messages.error(request, 'You do not have permission to view audit logs.')
        return redirect('management:dashboard')

    logs = AuditLog.objects.select_related('user').order_by('-timestamp')
    
    # Apply filters
    form = AuditLogFilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get('user'):
            logs = logs.filter(user=form.cleaned_data['user'])
        if form.cleaned_data.get('action'):
            logs = logs.filter(action=form.cleaned_data['action'])
        if form.cleaned_data.get('date_from'):
            logs = logs.filter(timestamp__date__gte=form.cleaned_data['date_from'])
        if form.cleaned_data.get('date_to'):
            logs = logs.filter(timestamp__date__lte=form.cleaned_data['date_to'])
        if form.cleaned_data.get('search'):
            logs = logs.filter(
                Q(description__icontains=form.cleaned_data['search']) |
                Q(model_name__icontains=form.cleaned_data['search'])
            )
    
    # Pagination
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)
    
    # Statistics
    stats = {
        'total_logs': logs.count(),
        'today_logs': AuditLog.objects.filter(timestamp__date=timezone.now().date()).count(),
        'week_logs': AuditLog.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'action_breakdown': AuditLog.objects.values('action').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
    }
    
    context = {
        'logs': logs_page,
        'form': form,
        'stats': stats,
        'total_logs': logs.count()
    }
    return render(request, 'management/audit_logs/list.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def audit_log_detail(request, pk):
    """View detailed audit log entry"""
    if not _has_permission(request, 'security_audit', 'can_view'):
        messages.error(request, 'You do not have permission to view audit logs.')
        return redirect('management:dashboard')

    log = get_object_or_404(AuditLog, pk=pk)
    
    # Get related logs (same object)
    related_logs = []
    if log.model_name and log.object_id:
        related_logs = AuditLog.objects.filter(
            model_name=log.model_name,
            object_id=log.object_id
        ).exclude(pk=log.pk).order_by('-timestamp')[:10]
    
    context = {
        'log': log,
        'related_logs': related_logs
    }
    return render(request, 'management/audit_logs/detail.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('security_audit', 'can_export', redirect_to='management:audit_logs_list', skip_get=False)
def audit_logs_export(request):
    """Export audit logs to CSV"""
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')
    
    # Apply same filters as list view
    form = AuditLogFilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get('user'):
            logs = logs.filter(user=form.cleaned_data['user'])
        if form.cleaned_data.get('action'):
            logs = logs.filter(action=form.cleaned_data['action'])
        if form.cleaned_data.get('date_from'):
            logs = logs.filter(timestamp__date__gte=form.cleaned_data['date_from'])
        if form.cleaned_data.get('date_to'):
            logs = logs.filter(timestamp__date__lte=form.cleaned_data['date_to'])
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Action', 'Model', 'Object ID', 'Description', 'IP Address'])
    
    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user.username if log.user else 'System',
            log.action,
            log.model_name or '',
            log.object_id or '',
            log.description,
            log.ip_address or ''
        ])

    AuditLog.objects.create(
        user=request.user,
        action='export',
        model_name='AuditLog',
        description=f'{request.user.username} exported audit logs to CSV ({logs.count()} record(s)).',
    )

    return response


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def security_dashboard(request):
    """Security overview dashboard"""
    if not _has_permission(request, 'security_audit', 'can_view'):
        messages.error(request, 'You do not have permission to view the security dashboard.')
        return redirect('management:dashboard')

    # Recent security events
    security_logs = AuditLog.objects.filter(
        action__in=['login', 'logout', 'password_reset', 'permission_change']
    ).select_related('user').order_by('-timestamp')[:20]
    
    # Failed login attempts (would need additional tracking)
    failed_logins = []
    
    # Active sessions count
    active_users = User.objects.filter(
        is_active=True,
        last_login__gte=timezone.now() - timedelta(hours=24)
    ).count()
    
    # Permission changes in last 30 days
    recent_permission_changes = AuditLog.objects.filter(
        action='permission_change',
        timestamp__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    context = {
        'security_logs': security_logs,
        'failed_logins': failed_logins,
        'active_users': active_users,
        'recent_permission_changes': recent_permission_changes
    }
    return render(request, 'management/security/dashboard.html', context)

# ==================== BROADCAST CENTER ====================
@login_required
@user_passes_test(
    lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin'
)
def broadcast_center(request):
    """List all broadcasts with status counts"""
    if not _has_permission(request, 'communications', 'can_view'):
        messages.error(request, 'You do not have permission to view broadcasts.')
        return redirect('management:dashboard')

    broadcasts = BroadcastMessage.objects.select_related('created_by').all()
    
    # Calculate status counts
    sent_count = broadcasts.filter(status='sent').count()
    draft_count = broadcasts.filter(status='draft').count()
    failed_count = broadcasts.filter(status='failed').count()
    
    context = {
        'broadcasts': broadcasts,
        'sent_count': sent_count,
        'draft_count': draft_count,
        'failed_count': failed_count,
        'page_title': 'Broadcast Center',
    }
    return render(
        request, 
        'management/broadcast/list.html', 
        context
    )


@login_required
@user_passes_test(
    lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin'
)
@require_permission('communications', 'can_create', redirect_to='management:broadcast_center')
def broadcast_create(request):
    """Create new broadcast"""
    if request.method == 'POST':
        form = BroadcastMessageForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    broadcast = form.save(commit=False)
                    broadcast.created_by = request.user

                    # Collect filter values
                    filter_values = {}
                    filter_type = form.cleaned_data['filter_type']

                    if filter_type == 'faculty':
                        filter_values['faculties'] = list(
                            form.cleaned_data['faculties']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'course':
                        filter_values['courses'] = list(
                            form.cleaned_data['courses']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'lms_course':
                        filter_values['lms_courses'] = list(
                            form.cleaned_data['lms_courses']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'role':
                        filter_values['roles'] = form.cleaned_data['roles']
                    elif filter_type == 'application_status':
                        filter_values['application_statuses'] = (
                            form.cleaned_data['application_statuses']
                        )
                    elif filter_type == 'enrollment_status':
                        filter_values['enrollment_statuses'] = (
                            form.cleaned_data['enrollment_statuses']
                        )

                    broadcast.filter_values = filter_values

                    # Get recipient emails
                    emails = get_recipient_emails(filter_type, filter_values)
                    broadcast.recipient_emails = emails
                    broadcast.recipient_count = len(emails)

                    broadcast.save()
            except Exception:
                logger.exception('broadcast_create: unexpected error saving broadcast')
                messages.error(request, 'Something went wrong while saving this broadcast. Please try again.')
            else:
                messages.success(
                    request,
                    f'Broadcast created! {len(emails)} recipients identified.'
                )
                return redirect('management:broadcast_center')
    else:
        form = BroadcastMessageForm()
    
    context = {
        'form': form,
        'page_title': 'Create Broadcast',
    }
    return render(
        request, 
        'management/broadcast/form.html', 
        context
    )

@login_required
@user_passes_test(
    lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin'
)
@require_permission('communications', 'can_edit', redirect_to='management:broadcast_center')
def broadcast_edit(request, slug):
    """Edit draft broadcast"""
    if not _has_permission(request, 'communications', 'can_view'):
        messages.error(request, 'You do not have permission to view broadcasts.')
        return redirect('management:broadcast_center')

    broadcast = get_object_or_404(BroadcastMessage, slug=slug)

    # Only allow editing drafts
    if broadcast.status != 'draft':
        messages.error(
            request,
            'Only draft broadcasts can be edited.'
        )
        return redirect('management:broadcast_center')

    if request.method == 'POST':
        form = BroadcastMessageForm(request.POST, instance=broadcast)
        if form.is_valid():
            try:
                with transaction.atomic():
                    broadcast = form.save(commit=False)

                    # Update filter values
                    filter_values = {}
                    filter_type = form.cleaned_data['filter_type']

                    if filter_type == 'faculty':
                        filter_values['faculties'] = list(
                            form.cleaned_data['faculties']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'course':
                        filter_values['courses'] = list(
                            form.cleaned_data['courses']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'lms_course':
                        filter_values['lms_courses'] = list(
                            form.cleaned_data['lms_courses']
                            .values_list('id', flat=True)
                        )
                    elif filter_type == 'role':
                        filter_values['roles'] = form.cleaned_data['roles']
                    elif filter_type == 'application_status':
                        filter_values['application_statuses'] = (
                            form.cleaned_data['application_statuses']
                        )
                    elif filter_type == 'enrollment_status':
                        filter_values['enrollment_statuses'] = (
                            form.cleaned_data['enrollment_statuses']
                        )

                    broadcast.filter_values = filter_values

                    # Recalculate recipient emails
                    emails = get_recipient_emails(filter_type, filter_values)
                    broadcast.recipient_emails = emails
                    broadcast.recipient_count = len(emails)

                    broadcast.save()
            except Exception:
                logger.exception('broadcast_edit: unexpected error saving broadcast slug=%s', slug)
                messages.error(request, 'Something went wrong while saving this broadcast. Please try again.')
            else:
                messages.success(
                    request,
                    f'Broadcast updated! {len(emails)} recipients identified.'
                )
                return redirect('management:broadcast_center')
    else:
        # Pre-populate form with existing data
        initial_data = {
            'subject': broadcast.subject,
            'message': broadcast.message,
            'filter_type': broadcast.filter_type,
        }
        
        # Pre-populate filter selections
        filter_type = broadcast.filter_type
        filter_values = broadcast.filter_values
        
        if filter_type == 'faculty' and 'faculties' in filter_values:
            initial_data['faculties'] = Faculty.objects.filter(
                id__in=filter_values['faculties']
            )
        elif filter_type == 'course' and 'courses' in filter_values:
            initial_data['courses'] = Course.objects.filter(
                id__in=filter_values['courses']
            )
        elif filter_type == 'lms_course' and 'lms_courses' in filter_values:
            initial_data['lms_courses'] = LMSCourse.objects.filter(
                id__in=filter_values['lms_courses']
            )
        elif filter_type == 'role' and 'roles' in filter_values:
            initial_data['roles'] = filter_values['roles']
        elif (filter_type == 'application_status' and 
              'application_statuses' in filter_values):
            initial_data['application_statuses'] = (
                filter_values['application_statuses']
            )
        elif (filter_type == 'enrollment_status' and 
              'enrollment_statuses' in filter_values):
            initial_data['enrollment_statuses'] = (
                filter_values['enrollment_statuses']
            )
        
        form = BroadcastMessageForm(instance=broadcast, initial=initial_data)
    
    context = {
        'form': form,
        'broadcast': broadcast,
        'is_edit': True,
        'page_title': f'Edit Broadcast: {broadcast.subject}',
    }
    return render(
        request, 
        'management/broadcast/form.html', 
        context
    )

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin')
@require_permission('communications', 'can_edit', redirect_to='management:broadcast_center')
def broadcast_send(request, slug):
    """Send broadcast email - POST only"""
    if request.method != 'POST':
        return redirect('management:broadcast_center')

    # Atomically claim the send: lock the row and flip draft/failed -> sending
    # in one transaction, so a double-click/retry racing this same request
    # sees status already 'sending' (or 'sent') and bails out instead of
    # spawning a second background thread that re-emails everyone.
    try:
        with transaction.atomic():
            broadcast = get_object_or_404(
                BroadcastMessage.objects.select_for_update(), slug=slug
            )
            if broadcast.status in ('sent', 'sending'):
                messages.warning(request, 'This broadcast is already sent or in progress.')
                return redirect('management:broadcast_center')

            broadcast.status = 'sending'
            broadcast.save(update_fields=['status'])
    except Http404:
        raise
    except Exception:
        logger.exception('broadcast_send: unexpected error claiming broadcast slug=%s', slug)
        messages.error(request, 'Something went wrong while starting this broadcast. Please try again.')
        return redirect('management:broadcast_center')

    # Synchronous, not backgrounded — on Passenger/shared hosting a daemon
    # thread can be killed mid-send when the worker process is recycled,
    # silently dropping whatever recipients hadn't been reached yet, and
    # leaving `status='sending'` permanently stuck with no retry path (the
    # guard above treats 'sending' as already-in-progress forever). Every
    # other email send in this codebase was already made synchronous for
    # this exact reason (see AUDIT.md Phase 6/7) — this was the one gap.
    # Bounded by settings.EMAIL_TIMEOUT (15s) per connection, same as
    # everywhere else.
    batch_size = 50
    email_list = broadcast.recipient_emails
    failed_batches = []

    for i in range(0, len(email_list), batch_size):
        batch = email_list[i:i + batch_size]
        email_messages = [
            (
                broadcast.subject,
                broadcast.message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
            )
            for email in batch
        ]
        try:
            send_mass_mail(email_messages, fail_silently=False)
        except Exception as e:
            # One bad batch doesn't abort the rest — keep sending, and
            # report which batches failed instead of losing everything
            # already delivered.
            logger.exception('Broadcast %s: batch starting at %d failed', broadcast.slug, i)
            failed_batches.append(f'recipients {i}-{i + len(batch) - 1}: {e}')

    broadcast.sent_at = timezone.now()
    if failed_batches:
        broadcast.status = 'failed' if len(failed_batches) * batch_size >= len(email_list) else 'sent'
        broadcast.error_message = 'Some batches failed:\n' + '\n'.join(failed_batches)
        messages.warning(
            request,
            f'Broadcast sent with some failures — {len(failed_batches)} batch(es) '
            f'out of {(len(email_list) + batch_size - 1) // batch_size} did not go through.'
        )
    else:
        broadcast.status = 'sent'
        broadcast.error_message = ''
        messages.success(
            request,
            f'Broadcast sent to {broadcast.recipient_count} recipients.'
        )
    try:
        broadcast.save(update_fields=['status', 'sent_at', 'error_message'])
    except Exception:
        logger.exception('broadcast_send: unexpected error saving final status for broadcast slug=%s', slug)
        messages.error(request, 'The broadcast was sent, but its status could not be saved. Please contact support.')

    return redirect('management:broadcast_center')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin')
@require_permission('communications', 'can_delete', redirect_to='management:broadcast_center')
def broadcast_delete(request, slug):
    """Delete broadcast - POST only"""
    broadcast = get_object_or_404(BroadcastMessage, slug=slug)

    if request.method == 'POST':
        try:
            broadcast.delete()
            messages.success(request, 'Broadcast deleted successfully.')
        except Exception:
            logger.exception('broadcast_delete: unexpected error deleting broadcast slug=%s', slug)
            messages.error(request, 'Something went wrong while deleting this broadcast. Please try again.')

    return redirect('management:broadcast_center')


# ==================== HELPER FUNCTIONS ====================
def get_recipient_emails(filter_type, filter_values):
    """Get recipient emails based on filter"""
    emails = set()
    
    if filter_type == 'all_users':
        # All active users
        emails = set(
            User.objects.filter(is_active=True)
            .values_list('email', flat=True)
        )
    
    elif filter_type == 'faculty':
        # Users who applied to courses in selected faculties
        faculty_ids = filter_values.get('faculties', [])
        emails = set(
            CourseApplication.objects.filter(
                program__department__faculty_id__in=faculty_ids
            ).values_list('email', flat=True)
        )
    
    elif filter_type == 'course':
        # Users who applied to selected programs
        program_ids = filter_values.get('courses', [])
        emails = set(
            CourseApplication.objects.filter(
                program_id__in=program_ids
            ).values_list('email', flat=True)
        )
    
    elif filter_type == 'lms_course':
        # Users enrolled in selected LMS courses
        lms_course_ids = filter_values.get('lms_courses', [])
        user_emails = User.objects.filter(
            enrollments__course_id__in=lms_course_ids
        ).values_list('email', flat=True)
        emails = set(user_emails)
    
    elif filter_type == 'role':
        # Users with selected roles
        roles = filter_values.get('roles', [])
        user_emails = User.objects.filter(
            profile__role__in=roles
        ).values_list('email', flat=True)
        emails = set(user_emails)
    
    elif filter_type == 'application_status':
        # Users with specific application statuses
        statuses = filter_values.get('application_statuses', [])
        emails = set(
            CourseApplication.objects.filter(
                status__in=statuses
            ).values_list('email', flat=True)
        )
    
    elif filter_type == 'enrollment_status':
        # Users with specific enrollment statuses
        statuses = filter_values.get('enrollment_statuses', [])
        user_emails = User.objects.filter(
            enrollments__status__in=statuses
        ).values_list('email', flat=True)
        emails = set(user_emails)
    
    # Remove empty emails
    emails = {e for e in emails if e}
    
    return list(emails)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def approve_department(request, pk):
    """Department head approves admission"""
    
    if request.method == 'POST':
        application = get_object_or_404(CourseApplication, pk=pk)
        
        if not application.admission_accepted:
            messages.error(
                request, 
                'Student must accept admission first.'
            )
            return redirect('management:application_detail', application_id=application.application_id)
        
        try:
            application.department_approved = True
            application.department_approved_at = timezone.now()
            application.department_approved_by = request.user
            application.save()

            # Send notification to student
            send_department_approval_email(application)

            if application.user:
                _notify(
                    user=application.user,
                    title='Department Approval Granted',
                    message=f'Your admission ({application.admission_number}) has received department approval. You now have full portal access.',
                    notif_type='enrollment',
                    link='/dashboard/',
                )
        except Exception:
            logger.exception('approve_department: unexpected error approving application pk=%s', pk)
            messages.error(request, 'Something went wrong while granting approval. Please try again.')
        else:
            messages.success(
                request,
                f'Department approval granted for {application.admission_number}'
            )

        return redirect('management:application_detail', application_id=application.application_id)
    
    return redirect('management:applications_list')


def send_department_approval_email(application):
    """Send email when department approves admission"""
    try:
        subject = f'Portal Access Granted - {application.admission_number}'
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; 
                         line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; 
                            padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg, 
                                #0F2A44 0%, #1D4ED8 100%); 
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">
                            🎉 Welcome to the Abraytech Student Portal!
                        </h1>
                    </div>
                    
                    <div style="background-color: white; 
                                padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">
                            Dear <strong>
                                {application.first_name} 
                                {application.last_name}
                            </strong>,
                        </p>
                        
                        <div style="background-color: #10b98115; 
                                    padding: 20px; border-radius: 8px; 
                                    margin: 25px 0; 
                                    border-left: 4px solid #10b981;">
                            <h3 style="color: #10b981; margin-top: 0;">
                                Department Approval Complete!
                            </h3>
                            <p>
                                Your admission has been approved by 
                                the department.
                            </p>
                            <p>
                                <strong>Admission Number:</strong> 
                                {application.admission_number}
                            </p>
                        </div>
                        
                        <h4>You can now access:</h4>
                        <ul>
                            <li>Student Dashboard</li>
                            <li>Course Materials</li>
                            <li>Academic Resources</li>
                            <li>Student Services</li>
                        </ul>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{settings.SITE_URL}/login/" 
                               style="background-color: #1D4ED8; 
                                      color: white; padding: 12px 30px; 
                                      text-decoration: none; 
                                      border-radius: 5px; 
                                      display: inline-block;">
                                Access Student Portal
                            </a>
                        </div>
                        
                        <p style="margin-top: 30px;">
                            Welcome to Abraytech!<br>
                            <strong style="color: #0F2A44;">
                                The Abraytech Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        connection, from_email = _resolve_sender('admissions')
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Portal Access Granted - {application.admission_number}",
            from_email=from_email,
            to=[application.email],
            connection=connection,
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True

    except Exception:
        logger.exception('Error sending approval email for application %s', application.application_id)
        return False


# ===========================================================================
# DEPARTMENTS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def departments_list(request):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view academic structure.')
        return redirect('management:dashboard')

    qs = Department.objects.select_related('faculty').prefetch_related('programs')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))

    faculty_id = request.GET.get('faculty', '')
    if faculty_id:
        qs = qs.filter(faculty_id=faculty_id)

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    
    # Order before pagination
    qs = qs.order_by('name')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'departments': page_obj,
        'faculties': Faculty.objects.all(),
        'total_departments': Department.objects.count(),
        'active_departments': Department.objects.filter(is_active=True).count(),
        'total_faculties': Faculty.objects.count(),
        'total_programs': Program.objects.count(),
        'create_form': DepartmentForm(),
    }
    return render(request, 'management/departments_list.html', context)


@login_required
@user_passes_test(is_admin)
def department_create(request):
    """
    "Add Department" is a modal on departments_list.html, not a standalone
    page — this view exists purely to handle that modal's POST. On success
    it redirects to departments_list as before; the modal's JS detects the
    redirect and reloads. On validation failure it re-renders just the
    fields partial (no page chrome), which the modal's JS swaps in without
    a full navigation. A direct GET (no modal, e.g. a stale bookmark) just
    bounces to the list — there's no dedicated create page to show.
    """
    if request.method != 'POST':
        return redirect('management:departments_list')

    if not _has_permission(request, 'academics', 'can_create'):
        messages.error(request, 'You do not have permission to create departments.')
        return redirect('management:departments_list')

    form = DepartmentForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            logger.exception('department_create: IntegrityError saving department')
            messages.error(request, 'Could not save — that department code may already be in use.')
        except Exception:
            logger.exception('department_create: unexpected error saving department')
            messages.error(request, 'Something went wrong while saving this department. Please try again.')
        else:
            messages.success(request, 'Department created successfully.')
            return redirect('management:departments_list')

    return render(request, 'management/_department_form_fields.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def department_edit(request, pk):
    """
    "Edit" is the same modal, populated by fetching this view's GET response
    (the fields partial, pre-filled from the instance) and swapping it into
    the modal body — mirroring department_create's POST-invalid partial
    re-render. POST behaves like the old standalone-page view.
    """
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_edit'):
            messages.error(request, 'You do not have permission to edit departments.')
            return redirect('management:departments_list')

        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('department_edit: IntegrityError saving department pk=%s', pk)
                messages.error(request, 'Could not save — that department code may already be in use.')
            except Exception:
                logger.exception('department_edit: unexpected error saving department pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this department. Please try again.')
            else:
                messages.success(request, 'Department updated.')
                return redirect('management:departments_list')
    else:
        form = DepartmentForm(instance=dept)
    return render(request, 'management/_department_form_fields.html', {'form': form, 'department': dept})


@login_required
@user_passes_test(is_admin)
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_delete'):
            messages.error(request, 'You do not have permission to delete departments.')
            return redirect('management:departments_list')

        program_count = dept.programs.count()
        if program_count:
            messages.error(
                request,
                f'Cannot delete "{dept.name}" — it still has {program_count} '
                f'program(s). Delete or reassign them first.'
            )
            return redirect('management:departments_list')

        dept_name = dept.name
        try:
            dept.delete()
            messages.success(request, f'Department "{dept_name}" deleted successfully.')
        except Exception:
            logger.exception('department_delete: unexpected error deleting department pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this department. Please try again.')
        return redirect('management:departments_list')

    # No dedicated confirm page any more — deletion is confirmed via the
    # SweetAlert dialog on departments_list.html, which POSTs directly here.
    return redirect('management:departments_list')


# ===========================================================================
# PROGRAMS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def programs_list(request):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view academic structure.')
        return redirect('management:dashboard')

    # Filtering/search/pagination all happen client-side in the DataTable now
    # (instant, no page reload) — the view just hands over every row.
    # The counts are annotated so the delete confirmation (a SweetAlert
    # on this page, not a standalone page any more) can warn about exactly
    # what will cascade-delete without an extra request per click.
    qs = (
        Program.objects
        .select_related('department__faculty')
        .annotate(
            application_count=Count('applications', distinct=True),
            student_count=Count('program_students', distinct=True),
        )
        .order_by('name')
    )

    context = {
        'programs': qs,
        'faculties': Faculty.objects.all(),
        'stats': [
            {'label': 'Total Programs', 'value': Program.objects.count(), 'color': 'text-primary-600'},
            {'label': 'Active', 'value': Program.objects.filter(is_active=True).count(), 'color': 'text-green-600'},
            {'label': 'Featured', 'value': Program.objects.filter(is_featured=True).count(), 'color': 'text-yellow-600'},
            {'label': 'Departments', 'value': Department.objects.count(), 'color': 'text-blue-600'},
        ],
        # The "New Program" modal on this page posts straight to program_create.
        'form': ProgramForm(),
    }
    return render(request, 'management/programs_list.html', context)


@login_required
@user_passes_test(is_admin)
def program_create(request):
    """
    "New Program" is a modal on programs_list.html now, not a standalone
    page — this view exists purely to handle that modal's POST. On success
    it redirects to programs_list as before; the modal's JS detects the
    redirect and reloads. On validation failure it re-renders just the
    fields partial (no page chrome), which the modal's JS swaps in without
    a full navigation. A direct GET (no modal, e.g. a stale bookmark) just
    bounces to the list — there's no dedicated create page to show.
    """
    if request.method != 'POST':
        return redirect('management:programs_list')

    if not _has_permission(request, 'academics', 'can_create'):
        messages.error(request, 'You do not have permission to create programs.')
        return redirect('management:programs_list')

    form = ProgramForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            program = form.save()
        except IntegrityError:
            logger.exception('program_create: IntegrityError saving program')
            messages.error(
                request,
                'Could not save this program — that program code may already be '
                'in use by another program. Please use a different code.'
            )
        except Exception:
            logger.exception('program_create: unexpected error saving program')
            messages.error(
                request,
                'Something went wrong while saving this program. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
        else:
            messages.success(request, 'Program created.')
            return redirect('management:programs_list')

    return render(request, 'management/_program_form_fields.html', {
        'form': form,
    })


@login_required
@user_passes_test(is_admin)
def program_edit(request, pk):
    """
    "Edit" is the same modal as "New Program" on programs_list.html,
    populated by fetching this view's GET response (the fields partial,
    pre-filled from the instance) and swapping it into the modal body —
    mirroring department_edit's pattern. POST-invalid re-renders the same
    partial with errors; POST-valid redirects.
    """
    program = get_object_or_404(Program, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_edit'):
            messages.error(request, 'You do not have permission to edit programs.')
            return redirect('management:programs_list')

        try:
            # Constructing the form is what triggers Django to actually
            # parse request.POST/request.FILES — if the submitted request
            # body is larger than Django's own DATA_UPLOAD_MAX_MEMORY_SIZE,
            # that parsing raises SuspiciousOperation right here instead of
            # letting it surface as an unhandled crash.
            form = ProgramForm(request.POST, request.FILES, instance=program)
            if form.is_valid():
                try:
                    form.save()
                except IntegrityError:
                    logger.exception(
                        'program_edit: IntegrityError saving program pk=%s', pk
                    )
                    messages.error(
                        request,
                        'Could not save changes — that program code may already be '
                        'in use by another program. Please use a different code.'
                    )
                else:
                    messages.success(request, 'Program updated.')
                    return redirect('management:programs_list')
        except SuspiciousOperation:
            # Most often an oversized upload (see ProgramForm.clean_gallery_video).
            # A request this large can also be rejected by the web server
            # itself before Django ever sees it, showing a raw host-level
            # "Forbidden"/"denied" page instead of this message — if that's
            # what's happening, the fix is a server-level upload limit
            # increase, not anything in this view.
            logger.warning('program_edit: oversized/suspicious upload for pk=%s', pk)
            messages.error(
                request,
                'Your changes could not be saved — the files you uploaded were too '
                'large for the server to accept. Please use a smaller image/video '
                'and try again.'
            )
            form = ProgramForm(instance=program)
        except Exception:
            # Last-resort net: never let an unexpected error surface as a
            # raw crash page — log it for diagnosis and show the admin a
            # clean, actionable message on the same form instead.
            logger.exception('program_edit: unexpected error saving program pk=%s', pk)
            messages.error(
                request,
                'Something went wrong while saving your changes. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
            form = ProgramForm(instance=program)
    else:
        form = ProgramForm(instance=program)
    return render(request, 'management/_program_form_fields.html', {
        'form': form,
        'program': program,
    })


@login_required
@user_passes_test(is_admin)
def program_detail(request, pk):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view academic structure.')
        return redirect('management:dashboard')

    program = get_object_or_404(Program.objects.select_related('department__faculty'), pk=pk)
    applications = program.applications.all()[:10]
    context = {'program': program, 'applications': applications}
    return render(request, 'management/program_detail.html', context)


@login_required
@user_passes_test(is_admin)
def program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_delete'):
            messages.error(request, 'You do not have permission to delete programs.')
            return redirect('management:programs_list')

        course_count = program.courses.count()
        student_count = program.program_students.count()
        if course_count or student_count:
            messages.error(
                request,
                f'Cannot delete "{program.name}" — it still has {course_count} '
                f'course(s) and {student_count} student(s) attached. '
                f'Reassign or archive them first.'
            )
            return redirect('management:programs_list')

        program_name = program.name
        try:
            program.delete()
            messages.success(request, f'Program "{program_name}" deleted successfully.')
        except Exception:
            logger.exception('program_delete: unexpected error deleting program pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this program. Please try again.')
        return redirect('management:programs_list')

    # No dedicated confirm page any more — deletion is confirmed via the
    # SweetAlert dialog on programs_list.html, which POSTs directly here.
    return redirect('management:programs_list')


# ===========================================================================
# COURSE INTAKES
# The on/off switch for program applications — see Program.get_current_intake()
# and eduweb.views._resolve_intake_eligibility(). Same permission category
# ('academics') and modal-create/edit pattern as Programs above.
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def intakes_list(request):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view course intakes.')
        return redirect('management:dashboard')

    qs = (
        CourseIntake.objects
        .select_related('program__department__faculty')
        .order_by('-year', 'intake_period')
    )

    context = {
        'intakes': qs,
        'today': timezone.now().date(),
        # The "New Intake" modal on this page posts straight to intake_create.
        'form': CourseIntakeForm(),
    }
    return render(request, 'management/intakes_list.html', context)


@login_required
@user_passes_test(is_admin)
def intake_create(request):
    """
    "New Intake" is a modal on intakes_list.html, not a standalone page —
    this view exists purely to handle that modal's POST. On success it
    redirects to intakes_list as before; the modal's JS detects the
    redirect and reloads. On validation failure it re-renders just the
    fields partial (no page chrome), which the modal's JS swaps in without
    a full navigation.
    """
    if request.method != 'POST':
        return redirect('management:intakes_list')

    if not _has_permission(request, 'academics', 'can_create'):
        messages.error(request, 'You do not have permission to create intakes.')
        return redirect('management:intakes_list')

    form = CourseIntakeForm(request.POST)
    if form.is_valid():
        try:
            form.save()
        except IntegrityError:
            logger.exception('intake_create: IntegrityError saving intake')
            messages.error(
                request,
                'Could not save — an intake for that program/period/year already exists.'
            )
        except Exception:
            logger.exception('intake_create: unexpected error saving intake')
            messages.error(
                request,
                'Something went wrong while saving this intake. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
        else:
            messages.success(request, 'Intake created.')
            return redirect('management:intakes_list')

    return render(request, 'management/_intake_form_fields.html', {
        'form': form,
    })


@login_required
@user_passes_test(is_admin)
def intake_edit(request, pk):
    """Same modal as "New Intake" on intakes_list.html, populated by
    fetching this view's GET response (the fields partial, pre-filled from
    the instance) and swapping it into the modal body — mirrors
    program_edit's pattern."""
    intake = get_object_or_404(CourseIntake, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_edit'):
            messages.error(request, 'You do not have permission to edit intakes.')
            return redirect('management:intakes_list')

        form = CourseIntakeForm(request.POST, instance=intake)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                logger.exception('intake_edit: IntegrityError saving intake pk=%s', pk)
                messages.error(
                    request,
                    'Could not save changes — an intake for that program/period/year already exists.'
                )
            else:
                messages.success(request, 'Intake updated.')
                return redirect('management:intakes_list')
    else:
        form = CourseIntakeForm(instance=intake)
    return render(request, 'management/_intake_form_fields.html', {
        'form': form,
        'intake': intake,
    })


@login_required
@user_passes_test(is_admin)
def intake_delete(request, pk):
    intake = get_object_or_404(CourseIntake, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'academics', 'can_delete'):
            messages.error(request, 'You do not have permission to delete intakes.')
            return redirect('management:intakes_list')

        app_count = intake.applications.count()
        if app_count:
            messages.error(
                request,
                f'Cannot delete "{intake}" — {app_count} application(s) reference it. '
                f'Close it instead by unchecking "Active".'
            )
            return redirect('management:intakes_list')

        intake_name = str(intake)
        try:
            intake.delete()
            messages.success(request, f'Intake "{intake_name}" deleted.')
        except Exception:
            logger.exception('intake_delete: unexpected error deleting intake pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this intake. Please try again.')
        return redirect('management:intakes_list')

    # No dedicated confirm page any more — deletion is confirmed via the
    # SweetAlert dialog on intakes_list.html, which POSTs directly here.
    return redirect('management:intakes_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def courses_list(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        # ── CREATE ──────────────────────────────────────────────────────────
        if action == 'create':
            if not _has_permission(request, 'academics', 'can_create'):
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to create courses.'}]}}, status=403)
                messages.error(request, 'You do not have permission to create courses.')
                return redirect('management:courses_list')

            form = CourseForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                except IntegrityError:
                    logger.exception('courses_list: IntegrityError creating course')
                    if is_ajax:
                        return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Could not save — that course code may already be in use.'}]}}, status=400)
                    messages.error(request, 'Could not save — that course code may already be in use.')
                    return redirect('management:courses_list')
                except Exception:
                    logger.exception('courses_list: unexpected error creating course')
                    if is_ajax:
                        return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong. Please try again.'}]}}, status=500)
                    messages.error(request, 'Something went wrong while saving this course. Please try again.')
                    return redirect('management:courses_list')
                if is_ajax:
                    return JsonResponse({'success': True})
                messages.success(request, 'Course created successfully.')
            elif is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
            else:
                # Surface first field error so the user knows what went wrong
                for field, errs in form.errors.items():
                    messages.error(request, f'{field.replace("_"," ").title()}: {errs[0]}')

        # ── EDIT ────────────────────────────────────────────────────────────
        elif action == 'edit':
            if not _has_permission(request, 'academics', 'can_edit'):
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to edit courses.'}]}}, status=403)
                messages.error(request, 'You do not have permission to edit courses.')
                return redirect('management:courses_list')

            course_id = request.POST.get('course_id')
            course    = get_object_or_404(Course, pk=course_id)
            form      = CourseForm(request.POST, instance=course)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                except IntegrityError:
                    logger.exception('courses_list: IntegrityError updating course_id=%s', course_id)
                    if is_ajax:
                        return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Could not save — that course code may already be in use.'}]}}, status=400)
                    messages.error(request, 'Could not save — that course code may already be in use.')
                    return redirect('management:courses_list')
                except Exception:
                    logger.exception('courses_list: unexpected error updating course_id=%s', course_id)
                    if is_ajax:
                        return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong. Please try again.'}]}}, status=500)
                    messages.error(request, 'Something went wrong while saving this course. Please try again.')
                    return redirect('management:courses_list')
                if is_ajax:
                    return JsonResponse({'success': True})
                messages.success(request, f'Course "{course.code}" updated successfully.')
            elif is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
            else:
                for field, errs in form.errors.items():
                    messages.error(request, f'{field.replace("_"," ").title()}: {errs[0]}')

        # ── DELETE ──────────────────────────────────────────────────────────
        elif action == 'delete':
            if not _has_permission(request, 'academics', 'can_delete'):
                messages.error(request, 'You do not have permission to delete courses.')
                return redirect('management:courses_list')

            course_id = request.POST.get('course_id')
            course    = get_object_or_404(Course, pk=course_id)

            dependents = (
                course.registrations.count()
                + course.student_grades.count()
            )
            if dependents:
                messages.error(
                    request,
                    f'Cannot delete "{course.code}" — it has {dependents} linked '
                    f'registration/grade record(s). Archive it instead.'
                )
                return redirect('management:courses_list')

            code = course.code
            try:
                course.delete()
            except Exception:
                logger.exception('courses_list: unexpected error deleting course_id=%s', course_id)
                messages.error(request, 'Something went wrong while deleting this course. Please try again.')
                return redirect('management:courses_list')
            messages.success(request, f'Course "{code}" deleted successfully.')
 
        return redirect('management:courses_list')

    # ── GET ─────────────────────────────────────────────────────────────────
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view courses.')
        return redirect('management:dashboard')

    courses = (
        Course.objects
        .select_related('program__department__faculty')
        .order_by('code')
    )
    form = CourseForm()
 
    return render(request, 'management/courses_list.html', {
        'courses':     courses,
        'departments': Department.objects.all().order_by('name'),
        'form':        form,
    })


# ===========================================================================
# COURSE CATEGORIES LIST (the missing page)
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def course_categories_list(request):
    if not _has_permission(request, 'academics', 'can_view'):
        messages.error(request, 'You do not have permission to view course categories.')
        return redirect('management:dashboard')

    categories = CourseCategory.objects.prefetch_related(
        'subcategories'
    ).select_related('parent').order_by('name')
    return render(request, 'management/course_categories_list.html', {'categories': categories})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('academics', 'can_create', redirect_to='management:course_categories_list')
def course_category_create(request):
    if request.method == 'POST':
        form = CourseCategoryForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    category = form.save()
                    AuditLog.objects.create(
                        user=request.user,
                        action='create',
                        model_name='CourseCategory',
                        object_id=category.id,
                        description=f'Created course category: {category.name}'
                    )
            except IntegrityError:
                logger.exception('course_category_create: IntegrityError saving category')
                messages.error(request, 'Could not save this category — that name may already be in use.')
            except Exception:
                logger.exception('course_category_create: unexpected error saving category')
                messages.error(request, 'Something went wrong while saving this category. Please try again.')
            else:
                messages.success(request, f'Category "{category.name}" created successfully.')
                return redirect('management:course_categories_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseCategoryForm()

    return render(request, 'management/course_category_form.html', {'form': form, 'action': 'Create'})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('academics', 'can_edit', redirect_to='management:course_categories_list')
def course_category_edit(request, pk):
    category = get_object_or_404(CourseCategory, pk=pk)

    if request.method == 'POST':
        form = CourseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                with transaction.atomic():
                    category = form.save()
                    AuditLog.objects.create(
                        user=request.user,
                        action='update',
                        model_name='CourseCategory',
                        object_id=category.id,
                        description=f'Updated course category: {category.name}'
                    )
            except IntegrityError:
                logger.exception('course_category_edit: IntegrityError saving category pk=%s', pk)
                messages.error(request, 'Could not save this category — that name may already be in use.')
            except Exception:
                logger.exception('course_category_edit: unexpected error saving category pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this category. Please try again.')
            else:
                messages.success(request, f'Category "{category.name}" updated successfully.')
                return redirect('management:course_categories_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseCategoryForm(instance=category)

    return render(request, 'management/course_category_form.html', {
        'form': form, 'category': category, 'action': 'Edit',
    })


@require_POST
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('academics', 'can_delete', redirect_to='management:course_categories_list')
def course_category_delete(request, pk):
    category = get_object_or_404(CourseCategory, pk=pk)

    dependent_count = category.subcategories.count()
    if dependent_count:
        messages.error(
            request,
            f'Cannot delete "{category.name}" — {dependent_count} subcategory(ies) are still linked to it.'
        )
        return redirect('management:course_categories_list')

    category_name = category.name
    AuditLog.objects.create(
        user=request.user,
        action='delete',
        model_name='CourseCategory',
        object_id=category.id,
        description=f'Deleted course category: {category_name}'
    )
    category.delete()
    messages.success(request, f'Category "{category_name}" deleted successfully.')
    return redirect('management:course_categories_list')


# ===========================================================================
# SUPPORT TICKETS
# NOTE: the full ticket console now lives in the `support` app
# (support:ticket_list / support:ticket_detail) — this used to duplicate it
# with a thinner, buggier copy (ticket.submitted_by didn't even exist on the
# model). Removed in favour of the one real implementation.
# ===========================================================================

# ===========================================================================
# CONTACT MESSAGES
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def contact_messages_list(request):
    if not _has_permission(request, 'communications', 'can_view'):
        messages.error(request, 'You do not have permission to view contact messages.')
        return redirect('management:dashboard')

    qs = ContactMessage.objects.select_related('user', 'responded_by').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(message__icontains=search)
        )

    subject = request.GET.get('subject', '')
    if subject:
        qs = qs.filter(subject=subject)

    read_status = request.GET.get('read_status', '')
    if read_status == 'unread':
        qs = qs.filter(is_read=False)
    elif read_status == 'read':
        qs = qs.filter(is_read=True)

    responded = request.GET.get('responded', '')
    if responded == 'yes':
        qs = qs.filter(responded=True)
    elif responded == 'no':
        qs = qs.filter(responded=False)

    unread_count = ContactMessage.objects.filter(is_read=False).count()
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/contact_messages_list.html', {
        'messages_list': page_obj,
        'unread_count': unread_count,
    })


@login_required
@user_passes_test(is_admin)
def contact_message_detail(request, pk):
    if not _has_permission(request, 'communications', 'can_view'):
        messages.error(request, 'You do not have permission to view contact messages.')
        return redirect('management:dashboard')

    msg = get_object_or_404(ContactMessage, pk=pk)
    # Auto-mark as read on open
    if not msg.is_read:
        msg.is_read = True
        msg.save(update_fields=['is_read'])
    return render(request, 'management/contact_message_detail.html', {'contact_message': msg})


@login_required
@user_passes_test(is_admin)
def contact_message_mark_read(request, pk):
    if request.method == 'POST':
        msg = get_object_or_404(ContactMessage, pk=pk)
        try:
            msg.is_read = True
            msg.save(update_fields=['is_read'])
            messages.success(request, 'Marked as read.')
        except Exception:
            logger.exception('contact_message_mark_read: unexpected error for pk=%s', pk)
            messages.error(request, 'Something went wrong. Please try again.')
    return redirect('management:contact_message_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
@require_permission('communications', 'can_create', redirect_to=lambda request, pk, **kw: redirect('management:contact_message_detail', pk=pk))
def contact_message_respond(request, pk):
    if request.method == 'POST':
        msg = get_object_or_404(ContactMessage, pk=pk)
        response_text = request.POST.get('response', '').strip()
        if response_text:
            try:
                connection, from_email = _resolve_sender('default')
                send_mail(
                    subject=f'Re: {msg.get_subject_display()} — Abraytech',
                    message=response_text,
                    from_email=from_email,
                    recipient_list=[msg.email],
                    fail_silently=False,
                    connection=connection,
                )
                email_sent = True
            except Exception:
                logger.exception('Failed to send contact-message response to %s (msg id=%s)', msg.email, msg.pk)
                email_sent = False

            try:
                msg.responded = True
                msg.responded_at = timezone.now()
                msg.responded_by = request.user
                msg.is_read = True
                msg.save(update_fields=['responded', 'responded_at', 'responded_by', 'is_read'])
            except Exception:
                logger.exception('contact_message_respond: unexpected error saving response for msg id=%s', msg.pk)
                messages.error(request, 'Something went wrong while saving your response. Please try again.')
                return redirect('management:contact_message_detail', pk=pk)

            if email_sent:
                messages.success(request, f'Response sent to {msg.email}.')
            else:
                messages.error(
                    request,
                    f'Response saved, but the email to {msg.email} failed to send. '
                    f'Please retry or contact them directly.'
                )
        else:
            messages.error(request, 'Response cannot be empty.')
    return redirect('management:contact_message_detail', pk=pk)


# ===========================================================================
# ANNOUNCEMENTS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def announcements_list(request):
    if not _has_permission(request, 'communications', 'can_view'):
        messages.error(request, 'You do not have permission to view announcements.')
        return redirect('management:dashboard')

    qs = Announcement.objects.select_related('course', 'category', 'created_by').order_by('-priority', '-publish_date')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

    ann_type = request.GET.get('type', '')
    if ann_type:
        qs = qs.filter(announcement_type=ann_type)

    priority = request.GET.get('priority', '')
    if priority:
        qs = qs.filter(priority=priority)

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/announcements_list.html', {'announcements': page_obj})


@login_required
@user_passes_test(is_admin)
@require_permission('communications', 'can_create', redirect_to='management:announcements_list')
def announcement_create(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    ann = form.save(commit=False)
                    ann.created_by = request.user
                    ann.save()
            except IntegrityError:
                logger.exception('announcement_create: IntegrityError saving announcement')
                messages.error(request, 'Could not save — please check the details and try again.')
                return render(request, 'management/announcement_form.html', {'form': form})
            except Exception:
                logger.exception('announcement_create: unexpected error saving announcement')
                messages.error(request, 'Something went wrong while saving this announcement. Please try again.')
                return render(request, 'management/announcement_form.html', {'form': form})
            messages.success(request, 'Announcement created.')
            # Notify users based on announcement type. Uses bulk_create instead of
            # one _notify() call per recipient (each of which is an INSERT + a
            # prune-query) — fan-out to "all active users" could otherwise be
            # thousands of queries in the request/response cycle. Non-fatal if
            # it fails: the announcement itself is already saved above.
            try:
                if ann.announcement_type == 'system':
                    recipients = User.objects.filter(is_active=True).exclude(id=request.user.id)
                    Notification.objects.bulk_create([
                        Notification(
                            user=u, notification_type='announcement',
                            title=f'Announcement: {ann.title}',
                            message=ann.content[:200], link='/',
                        )
                        for u in recipients
                    ])
                elif ann.announcement_type == 'course' and ann.course:
                    # Notify only students enrolled in this specific course
                    enrolled_users = User.objects.filter(
                        enrollments__course=ann.course,
                        enrollments__status='active',
                        is_active=True,
                    ).exclude(id=request.user.id).distinct()
                    Notification.objects.bulk_create([
                        Notification(
                            user=u, notification_type='announcement',
                            title=f'Course Announcement: {ann.title}',
                            message=ann.content[:200], link=f'/courses/{ann.course.slug}/',
                        )
                        for u in enrolled_users
                    ])
                elif ann.announcement_type == 'category' and ann.category:
                    # NOTE: LMSCourse has no live `category` FK (commented out in
                    # eduweb/models.py) — there is currently no way to resolve
                    # "students enrolled in a course under this category" at all.
                    # Filtering on it crashes with FieldError. Until that FK is
                    # wired up (flagged separately, see course_categories_list),
                    # skip the fan-out rather than 500 the whole announcement.
                    messages.warning(
                        request,
                        'Announcement saved, but category-targeted notifications were '
                        'not sent: courses aren\'t linked to categories yet.'
                    )
            except Exception:
                logger.exception('announcement_create: unexpected error notifying recipients for announcement pk=%s', ann.pk)
                messages.warning(request, 'Announcement saved, but notifications to recipients could not be sent.')
            return redirect('management:announcements_list')
    else:
        form = AnnouncementForm()
    return render(request, 'management/announcement_form.html', {'form': form})


@login_required
@user_passes_test(is_admin)
@require_permission('communications', 'can_edit', redirect_to='management:announcements_list')
def announcement_edit(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('announcement_edit: IntegrityError saving announcement pk=%s', pk)
                messages.error(request, 'Could not save — please check the details and try again.')
            except Exception:
                logger.exception('announcement_edit: unexpected error saving announcement pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this announcement. Please try again.')
            else:
                messages.success(request, 'Announcement updated.')
                return redirect('management:announcements_list')
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, 'management/announcement_form.html', {
        'form': form,
        'announcement': announcement,
    })


@login_required
@user_passes_test(is_admin)
@require_permission('communications', 'can_delete', redirect_to='management:announcements_list')
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        try:
            announcement.delete()
            messages.success(request, 'Announcement deleted.')
        except Exception:
            logger.exception('announcement_delete: unexpected error deleting announcement pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this announcement. Please try again.')
    return redirect('management:announcements_list')


# ===========================================================================
# ENROLLMENTS MANAGEMENT
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def enrollments_list(request):
    """List all student enrollments"""

    if not _has_permission(request, 'enrollments', 'can_view'):
        messages.error(request, 'You do not have permission to view enrollments.')
        return redirect('management:dashboard')

    qs = Enrollment.objects.select_related(
        'student', 'course'
    ).order_by('-enrolled_at')
    
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(student__username__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(course__title__icontains=search)
        )
    
    status = request.GET.get('status', '')
    if status and hasattr(Enrollment, 'STATUS_CHOICES'):
        qs = qs.filter(status=status)
    
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    return render(request, 'management/enrollments_list.html', {
        'enrollments': page_obj
    })


@login_required
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_create', redirect_to='management:enrollments_list')
def enrollment_create(request):
    """Create new enrollment"""

    if request.method == 'POST':
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save()
            except IntegrityError:
                logger.exception('enrollment_create: IntegrityError saving enrollment')
                messages.error(request, 'Could not save this enrollment — the student may already be enrolled.')
            except Exception:
                logger.exception('enrollment_create: unexpected error saving enrollment')
                messages.error(request, 'Something went wrong while saving this enrollment. Please try again.')
            else:
                messages.success(request, 'Enrollment created.')
                _notify(
                    user=enrollment.student,
                    title=f'Enrolled in {enrollment.course.title}',
                    message=f'You have been enrolled in "{enrollment.course.title}" by the administration.',
                    notif_type='enrollment',
                    link=f'/courses/{enrollment.course.slug}/',
                )
                # Notify course instructor
                if enrollment.course.instructor:
                    _notify(
                        user=enrollment.course.instructor,
                        title='New Student Enrolled',
                        message=f'{enrollment.student.get_full_name() or enrollment.student.username} was enrolled in "{enrollment.course.title}" by admin.',
                        notif_type='enrollment',
                        link=f'/instructor/courses/{enrollment.course.slug}/students/',
                    )
                return redirect('management:enrollments_list')
    else:
        form = EnrollmentForm()
    
    return render(request, 'management/enrollment_form.html', {
        'form': form,
        'students': User.objects.filter(is_active=True).order_by('last_name', 'first_name'),
        'courses': LMSCourse.objects.filter(is_published=True).order_by('title'),
    })


@login_required
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_edit', redirect_to='management:enrollments_list')
def enrollment_edit(request, pk):
    """Edit enrollment"""

    enrollment = get_object_or_404(Enrollment, pk=pk)
    if request.method == 'POST':
        old_status = enrollment.status
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated = form.save()
            except IntegrityError:
                logger.exception('enrollment_edit: IntegrityError saving enrollment pk=%s', pk)
                messages.error(request, 'Could not save this enrollment — please check the details and try again.')
            except Exception:
                logger.exception('enrollment_edit: unexpected error saving enrollment pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this enrollment. Please try again.')
            else:
                messages.success(request, 'Enrollment updated.')
                # Notify student only if their enrollment status changed
                if updated.status != old_status:
                    status_messages = {
                        'active':    'Your enrollment has been reactivated.',
                        'completed': 'Your enrollment has been marked as completed. Congratulations!',
                        'dropped':   'Your enrollment has been dropped. Contact support if this was unexpected.',
                        'suspended': 'Your enrollment has been suspended. Please contact the administration.',
                    }
                    _notify(
                        user=updated.student,
                        title=f'Enrollment Status Updated — {updated.course.title}',
                        message=status_messages.get(updated.status, f'Your enrollment status changed to "{updated.get_status_display()}".'),
                        notif_type='enrollment',
                        link='/dashboard/',
                    )
                return redirect('management:enrollments_list')
    else:
        form = EnrollmentForm(instance=enrollment)
    
    return render(request, 'management/enrollment_form.html', {
        'form': form,
        'enrollment': enrollment,
        'students': User.objects.filter(is_active=True).order_by('last_name', 'first_name'),
        'courses': LMSCourse.objects.filter(is_published=True).order_by('title'),
    })


@login_required
@user_passes_test(is_admin)
def enrollment_delete(request, pk):
    """Delete enrollment"""

    enrollment = get_object_or_404(Enrollment, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'enrollments', 'can_delete'):
            messages.error(request, 'You do not have permission to delete enrollments.')
            return redirect('management:enrollments_list')

        progress_count = enrollment.lesson_progress.count()
        if progress_count:
            messages.error(
                request,
                f'Cannot delete this enrollment — the student has {progress_count} '
                f'lesson-progress record(s) for "{enrollment.course.title}".'
            )
            return redirect('management:enrollments_list')

        try:
            _notify(
                user=enrollment.student,
                title=f'Enrollment Removed — {enrollment.course.title}',
                message=f'Your enrollment in "{enrollment.course.title}" has been removed by the administration. Please contact support if you believe this is an error.',
                notif_type='enrollment',
                link='/dashboard/',
            )
            enrollment.delete()
            messages.success(request, 'Enrollment deleted.')
        except Exception:
            logger.exception('enrollment_delete: unexpected error deleting enrollment pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this enrollment. Please try again.')
    return redirect('management:enrollments_list')

# ===========================================================================
# CERTIFICATES MANAGEMENT
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def certificates_list(request):
    """List all certificates with search + pagination."""
    if not _has_permission(request, 'enrollments', 'can_view'):
        messages.error(request, 'You do not have permission to view certificates.')
        return redirect('management:dashboard')

    qs = Certificate.objects.select_related('student', 'course').order_by('-issued_date')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(student__username__icontains=search) |
            Q(course__title__icontains=search) |
            Q(certificate_id__icontains=search)
        )
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'management/certificates.html', {
        'certificates': page_obj,
        'form': CertificateForm(),
        'students': User.objects.filter(
            is_active=True, profile__role='student'
        ).order_by('first_name', 'last_name'),
        'courses': LMSCourse.objects.filter(
            is_published=True
        ).order_by('title'),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_create', redirect_to='management:certificates_list')
def certificate_create(request):
    """Issue a new certificate (POST only from the combined page)."""
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    certificate = form.save()
            except IntegrityError:
                logger.exception('certificate_create: IntegrityError saving certificate')
                messages.error(request, 'Could not save this certificate — please check the details and try again.')
            except Exception:
                logger.exception('certificate_create: unexpected error saving certificate')
                messages.error(request, 'Something went wrong while saving this certificate. Please try again.')
            else:
                messages.success(request, 'Certificate issued successfully.')
                _notify(
                    user=certificate.student,
                    title='Certificate Issued',
                    message=f'Your certificate for "{certificate.course.title}" has been issued. Congratulations!',
                    notif_type='certificate',
                    link='/dashboard/',
                )
        else:
            # Surface the first meaningful error as a flash message
            first_error = next(
                (e for field_errors in form.errors.values() for e in field_errors),
                'Please correct the errors and try again.'
            )
            messages.error(request, first_error)
    return redirect('management:certificates_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_edit', redirect_to='management:certificates_list')
def certificate_edit(request, certificate_id):
    """Update an existing certificate (POST only from the combined page)."""
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES, instance=certificate)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('certificate_edit: IntegrityError saving certificate_id=%s', certificate_id)
                messages.error(request, 'Could not save this certificate — please check the details and try again.')
            except Exception:
                logger.exception('certificate_edit: unexpected error saving certificate_id=%s', certificate_id)
                messages.error(request, 'Something went wrong while saving this certificate. Please try again.')
            else:
                messages.success(request, 'Certificate updated successfully.')
        else:
            first_error = next(
                (e for field_errors in form.errors.values() for e in field_errors),
                'Please correct the errors and try again.'
            )
            messages.error(request, first_error)
    return redirect('management:certificates_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def certificate_delete(request, certificate_id):
    """Delete a certificate — POST only, guarded by confirm() on the client."""
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    if request.method == 'POST':
        if not _has_permission(request, 'enrollments', 'can_delete'):
            messages.error(request, 'You do not have permission to delete certificates.')
            return redirect('management:certificates_list')

        try:
            certificate.delete()
            messages.success(request, 'Certificate deleted.')
        except Exception:
            logger.exception('certificate_delete: unexpected error deleting certificate_id=%s', certificate_id)
            messages.error(request, 'Something went wrong while deleting this certificate. Please try again.')
    return redirect('management:certificates_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def reviews_list(request):

    if not _has_permission(request, 'enrollments', 'can_view'):
        messages.error(request, 'You do not have permission to view reviews.')
        return redirect('management:dashboard')

    qs = Review.objects.select_related('student', 'course').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(course__title__icontains=search) |
            Q(review_text__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(student__username__icontains=search)
        )

    rating = request.GET.get('rating', '').strip()
    if rating:
        try:
            qs = qs.filter(rating=int(rating))
        except ValueError:
            pass

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Only students for the datalist
    students = User.objects.filter(
        profile__role='student', is_active=True
    ).order_by('last_name', 'first_name', 'username')

    lms_courses = LMSCourse.objects.filter(
        is_published=True
    ).order_by('title')

    return render(request, 'management/reviews.html', {
        'reviews': page_obj,
        'form': ReviewForm(),
        'students': students,
        'lms_courses': lms_courses,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_create', redirect_to='management:reviews_list')
def review_create(request):

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('review_create: IntegrityError saving review')
                messages.error(request, 'Could not save this review — please check the details and try again.')
            except Exception:
                logger.exception('review_create: unexpected error saving review')
                messages.error(request, 'Something went wrong while saving this review. Please try again.')
            else:
                messages.success(request, 'Review created.')
        else:
            first_error = next(
                (e for errs in form.errors.values() for e in errs),
                'Please fix the errors below.'
            )
            messages.error(request, first_error)
    return redirect('management:reviews_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_edit', redirect_to='management:reviews_list')
def review_edit(request, pk):

    review = get_object_or_404(Review, pk=pk)
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('review_edit: IntegrityError saving review pk=%s', pk)
                messages.error(request, 'Could not save this review — please check the details and try again.')
            except Exception:
                logger.exception('review_edit: unexpected error saving review pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this review. Please try again.')
            else:
                messages.success(request, 'Review updated.')
        else:
            first_error = next(
                (e for errs in form.errors.values() for e in errs),
                'Please fix the errors below.'
            )
            messages.error(request, first_error)
    return redirect('management:reviews_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def review_delete(request, pk):

    review = get_object_or_404(Review, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'enrollments', 'can_delete'):
            messages.error(request, 'You do not have permission to delete reviews.')
            return redirect('management:reviews_list')

        try:
            review.delete()
            messages.success(request, 'Review deleted.')
        except Exception:
            logger.exception('review_delete: unexpected error deleting review pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this review. Please try again.')
    return redirect('management:reviews_list')


# ===========================================================================
# BADGES MANAGEMENT  —  no changes needed; included for completeness
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def badges_list(request):

    if not _has_permission(request, 'enrollments', 'can_view'):
        messages.error(request, 'You do not have permission to view badges.')
        return redirect('management:dashboard')

    qs = Badge.objects.order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(name__icontains=search)

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/badges.html', {
        'badges': page_obj,
        'form': BadgeForm(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_create', redirect_to='management:badges_list')
def badge_create(request):

    if request.method == 'POST':
        form = BadgeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('badge_create: IntegrityError saving badge')
                messages.error(request, 'Could not save this badge — that name may already be in use.')
            except Exception:
                logger.exception('badge_create: unexpected error saving badge')
                messages.error(request, 'Something went wrong while saving this badge. Please try again.')
            else:
                messages.success(request, 'Badge created.')
        else:
            first_error = next(
                (e for errs in form.errors.values() for e in errs),
                'Please fix the errors below.'
            )
            messages.error(request, first_error)
    return redirect('management:badges_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_edit', redirect_to='management:badges_list')
def badge_edit(request, slug):

    badge = get_object_or_404(Badge, slug=slug)
    if request.method == 'POST':
        form = BadgeForm(request.POST, instance=badge)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('badge_edit: IntegrityError saving badge slug=%s', slug)
                messages.error(request, 'Could not save this badge — that name may already be in use.')
            except Exception:
                logger.exception('badge_edit: unexpected error saving badge slug=%s', slug)
                messages.error(request, 'Something went wrong while saving this badge. Please try again.')
            else:
                messages.success(request, 'Badge updated.')
        else:
            first_error = next(
                (e for errs in form.errors.values() for e in errs),
                'Please fix the errors below.'
            )
            messages.error(request, first_error)
    return redirect('management:badges_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def badge_delete(request, slug):

    badge = get_object_or_404(Badge, slug=slug)
    if request.method == 'POST':
        if not _has_permission(request, 'enrollments', 'can_delete'):
            messages.error(request, 'You do not have permission to delete badges.')
            return redirect('management:badges_list')

        awarded_count = badge.awarded_to.count()
        if awarded_count:
            messages.error(
                request,
                f'Cannot delete "{badge.name}" — it has already been awarded to {awarded_count} student(s).'
            )
            return redirect('management:badges_list')

        try:
            badge.delete()
            messages.success(request, 'Badge deleted.')
        except Exception:
            logger.exception('badge_delete: unexpected error deleting badge slug=%s', slug)
            messages.error(request, 'Something went wrong while deleting this badge. Please try again.')
    return redirect('management:badges_list')


# ===========================================================================
# STUDENT BADGES (ASSIGNMENT)
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def student_badges_list(request):

    if not _has_permission(request, 'enrollments', 'can_view'):
        messages.error(request, 'You do not have permission to view student badges.')
        return redirect('management:dashboard')

    qs = StudentBadge.objects.select_related(
        'student', 'student__profile', 'badge', 'awarded_by'
    ).order_by('-awarded_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(student__username__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(badge__name__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Only students for the datalist
    students = User.objects.filter(
        profile__role='student', is_active=True
    ).order_by('last_name', 'first_name', 'username')

    badges = Badge.objects.filter(is_active=True).order_by('name')

    return render(request, 'management/student_badges.html', {
        'student_badges': page_obj,
        'form': StudentBadgeForm(),
        'students': students,
        'badges': badges,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('enrollments', 'can_create', redirect_to='management:student_badges_list')
def student_badge_assign(request):

    if request.method == 'POST':
        form = StudentBadgeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save(commit=False)
                    assignment.awarded_by = request.user
                    assignment.save()
            except IntegrityError:
                logger.exception('student_badge_assign: IntegrityError assigning badge')
                messages.error(request, 'Could not assign this badge — the student may already have it.')
            except Exception:
                logger.exception('student_badge_assign: unexpected error assigning badge')
                messages.error(request, 'Something went wrong while assigning this badge. Please try again.')
            else:
                messages.success(request, 'Badge assigned.')
                _notify(
                    user=assignment.student,
                    title=f'Badge Awarded: {assignment.badge.name}',
                    message=f'You have been awarded the "{assignment.badge.name}" badge!',
                    notif_type='system',
                    link='/dashboard/',
                )
        else:
            first_error = next(
                (e for errs in form.errors.values() for e in errs),
                'Please fix the errors below.'
            )
            messages.error(request, first_error)
    return redirect('management:student_badges_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def student_badge_delete(request, pk):

    student_badge = get_object_or_404(StudentBadge, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'enrollments', 'can_delete'):
            messages.error(request, 'You do not have permission to revoke badges.')
            return redirect('management:student_badges_list')

        try:
            student_badge.delete()
            messages.success(request, 'Badge revoked.')
        except Exception:
            logger.exception('student_badge_delete: unexpected error deleting student_badge pk=%s', pk)
            messages.error(request, 'Something went wrong while revoking this badge. Please try again.')
    return redirect('management:student_badges_list')

# ---------------------------------------------------------------------------
# PAYMENT GATEWAYS
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def payment_gateways_list(request):

    gateways = PaymentGateway.objects.order_by('name')
    form     = PaymentGatewayForm()
    return render(request, 'management/payment_gateways.html', {
        'gateways': gateways,
        'form':     form,
    })


def _deactivate_other_gateways(gw):
    """Ensures at most one active gateway per type. Locks that type's rows first
    where the backend supports it (Postgres; SQLite has no row locking and is
    skipped gracefully), so two concurrent activations can't interleave and
    both end up active."""
    same_type = PaymentGateway.objects.filter(gateway_type=gw.gateway_type)
    if connection.features.has_select_for_update:
        list(same_type.select_for_update())
    same_type.filter(is_active=True).exclude(pk=gw.pk).update(is_active=False)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def payment_gateway_create(request):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not _has_permission(request, 'finance', 'can_create'):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to add payment gateways.'}]}}, status=403)
        messages.error(request, 'You do not have permission to add payment gateways.')
        return redirect('management:payment_gateways_list')

    form = PaymentGatewayForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                gw = form.save(commit=False)
                gw.api_secret = encrypt_secret(form.cleaned_data.get('api_secret', ''))
                gw.webhook_secret = encrypt_secret(form.cleaned_data.get('webhook_secret', ''))
                if gw.is_active:
                    _deactivate_other_gateways(gw)
                gw.save()
                AuditLog.objects.create(
                    user=request.user,
                    action='create',
                    model_name='PaymentGateway',
                    object_id=str(gw.pk),
                    description=(
                        f'{request.user.username} added payment gateway "{gw.name}" '
                        f'({gw.gateway_type}, {"active" if gw.is_active else "inactive"}). '
                        f'API secrets not recorded.'
                    ),
                )
        except Exception:
            logger.exception('payment_gateway_create: unexpected error saving gateway')
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong while saving. Please try again.'}]}}, status=500)
            messages.error(request, 'Something went wrong while saving this gateway. Please try again.')
            return redirect('management:payment_gateways_list')
        if is_ajax:
            return JsonResponse({'success': True})
        messages.success(request, 'Gateway added.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:payment_gateways_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def payment_gateway_edit(request, slug):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not _has_permission(request, 'finance', 'can_edit'):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to edit payment gateways.'}]}}, status=403)
        messages.error(request, 'You do not have permission to edit payment gateways.')
        return redirect('management:payment_gateways_list')

    gateway = get_object_or_404(PaymentGateway, slug=slug)
    form    = PaymentGatewayForm(request.POST, instance=gateway)
    if form.is_valid():
        try:
            with transaction.atomic():
                # Preserve existing secrets when fields left blank; encrypt when submitted
                gw = form.save(commit=False)
                if not request.POST.get('api_key'):
                    gw.api_key = gateway.api_key
                if request.POST.get('api_secret'):
                    gw.api_secret = encrypt_secret(request.POST.get('api_secret'))
                else:
                    gw.api_secret = gateway.api_secret
                if request.POST.get('webhook_secret'):
                    gw.webhook_secret = encrypt_secret(request.POST.get('webhook_secret'))
                else:
                    gw.webhook_secret = gateway.webhook_secret
                if gw.is_active:
                    _deactivate_other_gateways(gw)
                gw.save()
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='PaymentGateway',
                    object_id=str(gw.pk),
                    description=(
                        f'{request.user.username} updated payment gateway "{gw.name}" '
                        f'({"active" if gw.is_active else "inactive"})'
                        + (' — API secret rotated.' if request.POST.get('api_secret') else '.')
                    ),
                )
        except Exception:
            logger.exception('payment_gateway_edit: unexpected error saving gateway slug=%s', slug)
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong while saving. Please try again.'}]}}, status=500)
            messages.error(request, 'Something went wrong while saving this gateway. Please try again.')
            return redirect('management:payment_gateways_list')
        if is_ajax:
            return JsonResponse({'success': True})
        messages.success(request, 'Gateway updated.')
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:payment_gateways_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_superuser_only)
def payment_gateway_delete(request, slug):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    if not _has_permission(request, 'finance', 'can_delete'):
        messages.error(request, 'You do not have permission to delete payment gateways.')
        return redirect('management:payment_gateways_list')

    gateway = get_object_or_404(PaymentGateway, slug=slug)
    txn_count = Transaction.objects.filter(gateway=gateway).count()
    if txn_count:
        messages.error(
            request,
            f'Cannot delete "{gateway.name}" — {txn_count} transaction(s) reference it.'
        )
        return redirect('management:payment_gateways_list')

    gateway_pk = gateway.pk
    gateway_name = gateway.name
    try:
        with transaction.atomic():
            gateway.delete()
            AuditLog.objects.create(
                user=request.user,
                action='delete',
                model_name='PaymentGateway',
                object_id=str(gateway_pk),
                description=f'{request.user.username} deleted payment gateway "{gateway_name}".',
            )
    except Exception:
        logger.exception('payment_gateway_delete: unexpected error deleting gateway slug=%s', slug)
        messages.error(request, 'Something went wrong while deleting this gateway. Please try again.')
        return redirect('management:payment_gateways_list')
    messages.success(request, 'Gateway deleted.')
    return redirect('management:payment_gateways_list')


# ---------------------------------------------------------------------------
# TRANSACTIONS  (read-only list + detail; no create/edit/delete)
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def transactions_list(request):
    if not _has_permission(request, 'finance', 'can_view'):
        messages.error(request, 'You do not have permission to view transactions.')
        return redirect('management:dashboard')

    qs = Transaction.objects.select_related('user', 'gateway').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    txn_type = request.GET.get('type', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search)  |
            Q(user__username__icontains=search)   |
            Q(transaction_id__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if txn_type:
        qs = qs.filter(transaction_type=txn_type)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Export CSV of filtered results
    if request.GET.get('export') == 'csv':
        if not _has_permission(request, 'finance', 'can_export'):
            messages.error(request, 'You do not have permission to export transactions.')
            return redirect('management:transactions_list')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
        writer = csv.writer(response)
        writer.writerow(['Transaction ID', 'User', 'Username', 'Gateway', 'Type', 'Amount', 'Currency', 'Status', 'Date'])
        for txn in qs:
            writer.writerow([
                txn.transaction_id,
                txn.user.get_full_name() or txn.user.username,
                txn.user.username,
                txn.gateway.name if txn.gateway else '',
                txn.get_transaction_type_display(),
                txn.amount,
                txn.currency,
                txn.get_status_display(),
                txn.created_at.strftime('%Y-%m-%d %H:%M'),
            ])
        return response

    all_txns = Transaction.objects
    summary = {
        'total':     all_txns.count(),
        'completed': all_txns.filter(status='completed').count(),
        'pending':   all_txns.filter(status='pending').count(),
        'failed':    all_txns.filter(status='failed').count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/transactions.html', {
        'transactions': page_obj,
        'summary': summary,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def transaction_detail(request, transaction_id):

    if not _has_permission(request, 'finance', 'can_view'):
        messages.error(request, 'You do not have permission to view transactions.')
        return redirect('management:dashboard')

    txn = get_object_or_404(
        Transaction.objects.select_related('user', 'gateway', 'course'),
        transaction_id=transaction_id
    )
    return render(request, 'management/transaction_detail.html', {
        'transaction': txn,
    })


# ---------------------------------------------------------------------------
# REQUIRED PAYMENTS
#
# This used to be a full, separate CRUD (list/create/edit/delete/reminders)
# duplicating the one in payment/views.py over the same AllRequiredPayments
# model — one for admin oversight, one for the finance portal. Collapsed
# into a single canonical surface (the finance-portal one, which has the
# fuller UI) per product decision; these just forward there now so any
# existing bookmark/link to the old management: URLs keeps working. The
# canonical view already grants admins/superusers access alongside finance
# staff (see payment/views.py's can_manage_required_payments).
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def required_payments_list(request):
    return redirect('payments:required_payments_list')


# ---------------------------------------------------------------------------
# FINANCIAL ANALYTICS DASHBOARD
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def financial_analytics(request):
    """Financial analytics — all student payment records."""

    if not _has_permission(request, 'finance', 'can_view'):
        messages.error(request, 'You do not have permission to view financial analytics.')
        return redirect('management:dashboard')

    _zero = Value(0, output_field=DecimalField())

    def _agg(qs, field='amount'):
        r = qs.aggregate(
            total=Coalesce(Sum(field), _zero, output_field=DecimalField()),
            count=Count('id'),
        )
        return float(r['total'] or 0), r['count']

    # ── Querysets ─────────────────────────────────────────────────────────────
    app_qs = ApplicationPayment.objects.select_related(
        'application', 'application__program'
    ).order_by('-created_at')

    # FeePayment → fee (AllRequiredPayments) → program
    fee_qs = FeePayment.objects.select_related(
        'user', 'fee', 'fee__program'
    ).order_by('-created_at')

    txn_qs = Transaction.objects.select_related(
        'user', 'course', 'gateway'
    ).order_by('-created_at')

    inv_qs = Invoice.objects.select_related(
        'student', 'course'
    ).order_by('-issue_date')

    # ── Revenue aggregates ────────────────────────────────────────────────────
    app_total, app_count = _agg(app_qs.filter(status='success'))
    fee_total, fee_count = _agg(fee_qs.filter(status='success'))
    txn_total, txn_count = _agg(txn_qs.filter(status='completed'))
    inv_total, inv_count = _agg(inv_qs, field='total_amount')

    total_revenue = app_total + fee_total

    revenue_by_source = {
        'application_fees': {
            'amount': app_total,
            'transactions': app_count,
            'percentage': round(app_total / total_revenue * 100, 1) if total_revenue else 0,
        },
        'student_fees': {
            'amount': fee_total,
            'transactions': fee_count,
            'percentage': round(fee_total / total_revenue * 100, 1) if total_revenue else 0,
        },
        'certificates': {
            'count': Certificate.objects.filter(payment_status='paid').count(),
        },
    }

    # ── Outstanding & refunds ─────────────────────────────────────────────────
    out_fee_total, out_fee_count = _agg(fee_qs.filter(status__in=['pending', 'failed']))
    out_app_total, out_app_count = _agg(app_qs.filter(status__in=['pending', 'failed']))
    ref_app_total, ref_app_count = _agg(app_qs.filter(status='refunded'))
    ref_fee_total, ref_fee_count = _agg(fee_qs.filter(status='refunded'))

    # ── Payment timing: values_list avoids .only() + select_related conflict ──
    # FeePayment direct fields: status, paid_at
    # Related field via FK fee → AllRequiredPayments.due_date (DateField)
    on_time = late = unpaid = 0
    for status, paid_at, due_date in FeePayment.objects.values_list('status', 'paid_at', 'fee__due_date'):
        if status == 'success':
            if paid_at and due_date and paid_at.date() > due_date:
                late += 1
            else:
                on_time += 1
        else:
            unpaid += 1

    total_fees = on_time + late + unpaid
    payment_rates = {
        'on_time':    {'count': on_time, 'percentage': round(on_time / total_fees * 100, 1) if total_fees else 0},
        'late':       {'count': late,    'percentage': round(late    / total_fees * 100, 1) if total_fees else 0},
        'unpaid':     {'count': unpaid,  'percentage': round(unpaid  / total_fees * 100, 1) if total_fees else 0},
        'total_fees': total_fees,
    }

    # ── Monthly revenue (last 6 months) ───────────────────────────────────────
    cutoff = timezone.now() - timedelta(days=365)

    def _monthly(qs, status='success'):
        return (
            qs.filter(status=status, paid_at__gte=cutoff)
            .annotate(month=TruncMonth('paid_at'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

    monthly_data = {}
    for r in _monthly(app_qs):
        k = r['month'].strftime('%Y-%m') if r['month'] else '?'
        monthly_data.setdefault(k, {'app_fees': 0.0, 'student_fees': 0.0})
        monthly_data[k]['app_fees'] += float(r['total'] or 0)
    for r in _monthly(fee_qs):
        k = r['month'].strftime('%Y-%m') if r['month'] else '?'
        monthly_data.setdefault(k, {'app_fees': 0.0, 'student_fees': 0.0})
        monthly_data[k]['student_fees'] += float(r['total'] or 0)
    for v in monthly_data.values():
        v['total'] = v['app_fees'] + v['student_fees']

    monthly_revenue = sorted(monthly_data.items())[-6:]
    current_mrr = monthly_revenue[-1][1]['total'] if monthly_revenue else 0.0

    # ── Instructor payouts ────────────────────────────────────────────────────
    payroll_rows = (
        StaffPayroll.objects
        .filter(payment_status='paid')
        .values('staff__id', 'staff__first_name', 'staff__last_name', 'staff__username')
        .annotate(
            total_paid=Coalesce(Sum('net_salary'),      _zero, output_field=DecimalField()),
            total_gross=Coalesce(Sum('gross_salary'),   _zero, output_field=DecimalField()),
            average_monthly=Coalesce(Avg('net_salary'), _zero, output_field=DecimalField()),
            payment_count=Count('id'),
        )
        .order_by('-total_paid')[:10]
    )

    instructor_payouts = []
    total_instructor_payouts = 0.0
    for p in payroll_rows:
        amt = float(p['total_paid'] or 0)
        total_instructor_payouts += amt
        name = f"{p['staff__first_name']} {p['staff__last_name']}".strip() or p['staff__username']
        instructor_payouts.append({
            'staff_name':      name,
            'count':           p['payment_count'],
            'total_paid':      amt,
            'total_gross':     float(p['total_gross'] or 0),
            'average_monthly': float(p['average_monthly'] or 0),
        })

    # ── Context ───────────────────────────────────────────────────────────────
    context = {
        'revenue_by_source':         revenue_by_source,
        'total_revenue':             total_revenue,
        'total_payment_count':       app_count + fee_count,
        'current_mrr':               current_mrr,
        'payment_rates':             payment_rates,
        'monthly_revenue':           monthly_revenue,
        'outstanding_amount':        out_fee_total + out_app_total,
        'outstanding_count':         out_fee_count + out_app_count,
        'total_refunded':            ref_app_total + ref_fee_total,
        'refund_count':              ref_app_count + ref_fee_count,
        'application_payments':      app_qs[:200],
        'fee_payments':              fee_qs[:200],
        'transactions':              txn_qs[:200],
        'invoices':                  inv_qs[:200],
        'invoices_count':            inv_count,
        'invoices_total':            inv_total,
        'transactions_total_count':  txn_count,
        'transactions_total_amount': txn_total,
        'instructor_payouts':        instructor_payouts,
        'total_instructor_payouts':  total_instructor_payouts,
    }

    return render(request, 'management/financial_analytics.html', context)


# ---------------------------------------------------------------------------
# STAFF PAYROLL
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def staff_payroll_list(request):

    if not _has_permission(request, 'finance_payroll', 'can_view'):
        messages.error(request, 'You do not have permission to view staff payroll.')
        return redirect('management:dashboard')

    STAFF_ROLES = ['instructor', 'support', 'admin', 'finance']

    qs = StaffPayroll.objects.select_related('staff').order_by('-year', '-month')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(staff__first_name__icontains=search)  |
            Q(staff__last_name__icontains=search)   |
            Q(staff__username__icontains=search)    |
            Q(payroll_reference__icontains=search)
        )

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(payment_status=status)

    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    staff_members = User.objects.filter(
        profile__role__in=STAFF_ROLES,
        is_active=True,
    ).order_by('last_name', 'first_name')

    form = StaffPayrollForm()

    # Pass status choices for the filter dropdown
    status_choices = StaffPayroll.STATUS_CHOICES

    return render(request, 'management/payroll.html', {
        'payroll_records': page_obj,
        'staff_members':   staff_members,
        'form':            form,
        'status_choices':  status_choices,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def staff_payroll_create(request):

    if request.method != 'POST':
        return redirect('management:staff_payroll_list')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not _has_permission(request, 'finance_payroll', 'can_create'):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to create payroll records.'}]}}, status=403)
        messages.error(request, 'You do not have permission to create payroll records.')
        return redirect('management:staff_payroll_list')

    form = StaffPayrollForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                payroll = form.save()
                AuditLog.objects.create(
                    user=request.user,
                    action='create',
                    model_name='StaffPayroll',
                    object_id=str(payroll.pk),
                    description=(
                        f'{request.user.username} created payroll record {payroll.payroll_reference} '
                        f'for {payroll.staff} ({payroll.month}/{payroll.year}).'
                    ),
                )
        except IntegrityError:
            logger.exception('staff_payroll_create: IntegrityError saving payroll')
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Could not save — this payroll record may already exist.'}]}}, status=400)
            messages.error(request, 'Could not save — this payroll record may already exist.')
            return redirect('management:staff_payroll_list')
        except Exception:
            logger.exception('staff_payroll_create: unexpected error saving payroll')
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong while saving. Please try again.'}]}}, status=500)
            messages.error(request, 'Something went wrong while saving this payroll record. Please try again.')
            return redirect('management:staff_payroll_list')
        messages.success(request, 'Payroll record created.')
        # Notify the staff member a payroll record has been created for them
        month_name = payroll.get_month_display()
        _notify(
            user=payroll.staff,
            title='Payroll Record Created',
            message=f'A payroll record for {month_name} {payroll.year} has been created. Net salary: {payroll.net_salary}.',
            notif_type='payroll',
            link='/dashboard/',
        )
        if is_ajax:
            return JsonResponse({'success': True})
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:staff_payroll_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def staff_payroll_edit(request, payroll_reference):

    if request.method != 'POST':
        return redirect('management:staff_payroll_list')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not _has_permission(request, 'finance_payroll', 'can_edit'):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'You do not have permission to edit payroll records.'}]}}, status=403)
        messages.error(request, 'You do not have permission to edit payroll records.')
        return redirect('management:staff_payroll_list')

    payroll = get_object_or_404(StaffPayroll, payroll_reference=payroll_reference)
    form    = StaffPayrollForm(request.POST, instance=payroll)
    if form.is_valid():
        # Track old status to detect changes
        old_status = payroll.payment_status

        try:
            with transaction.atomic():
                updated_payroll = form.save()
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='StaffPayroll',
                    object_id=str(updated_payroll.pk),
                    description=(
                        f'{request.user.username} updated payroll {updated_payroll.payroll_reference} '
                        f'for {updated_payroll.staff}, status "{old_status}" -> "{updated_payroll.payment_status}".'
                    ),
                )
        except IntegrityError:
            logger.exception('staff_payroll_edit: IntegrityError saving payroll_reference=%s', payroll_reference)
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Could not save — please check the details and try again.'}]}}, status=400)
            messages.error(request, 'Could not save — please check the details and try again.')
            return redirect('management:staff_payroll_list')
        except Exception:
            logger.exception('staff_payroll_edit: unexpected error saving payroll_reference=%s', payroll_reference)
            if is_ajax:
                return JsonResponse({'success': False, 'errors': {'__all__': [{'message': 'Something went wrong while saving. Please try again.'}]}}, status=500)
            messages.error(request, 'Something went wrong while saving this payroll record. Please try again.')
            return redirect('management:staff_payroll_list')
        messages.success(request, 'Payroll updated.')
        # Notify staff member their payroll record was updated
        month_name = updated_payroll.get_month_display()
        _notify(
            user=updated_payroll.staff,
            title='Payroll Record Updated',
            message=f'Your payroll record for {month_name} {updated_payroll.year} has been updated. Net salary: {updated_payroll.net_salary}.',
            notif_type='payroll',
            link='/dashboard/',
        )
        
        # Send payroll payment notification email if status changed to paid
        if old_status != 'paid' and updated_payroll.payment_status == 'paid':
            try:
                send_payroll_payment_notification_email(updated_payroll)
            except Exception as e:
                logger.error(f'Failed to send payroll notification email for {updated_payroll.payroll_reference}: {str(e)}')
        if is_ajax:
            return JsonResponse({'success': True})
    else:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:staff_payroll_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def staff_payroll_delete(request, payroll_reference):

    if request.method != 'POST':
        return redirect('management:staff_payroll_list')

    if not _has_permission(request, 'finance_payroll', 'can_delete'):
        messages.error(request, 'You do not have permission to delete payroll records.')
        return redirect('management:staff_payroll_list')

    payroll = get_object_or_404(StaffPayroll, payroll_reference=payroll_reference)
    payroll_pk = payroll.pk
    payroll_staff = str(payroll.staff)
    try:
        with transaction.atomic():
            payroll.delete()
            AuditLog.objects.create(
                user=request.user,
                action='delete',
                model_name='StaffPayroll',
                object_id=str(payroll_pk),
                description=f'{request.user.username} deleted payroll record {payroll_reference} for {payroll_staff}.',
            )
    except Exception:
        logger.exception('staff_payroll_delete: unexpected error deleting payroll_reference=%s', payroll_reference)
        messages.error(request, 'Something went wrong while deleting this payroll record. Please try again.')
        return redirect('management:staff_payroll_list')
    messages.success(request, 'Payroll deleted.')
    return redirect('management:staff_payroll_list')

# ── SITE CONFIG VIEWS ────────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:site_config_general')
def site_config_general(request):
    """Edit base.html / global fields: identity, logos, SEO, footer, social, contact."""
    if request.method == 'GET' and not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view site content settings.')
        return redirect('management:dashboard')

    site = SiteConfig.objects.first()
    if request.method == 'POST':
        try:
            form = SiteConfigGeneralForm(request.POST, request.FILES, instance=site)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='SiteConfig',
                            description='Updated general site configuration'
                        )
                except IntegrityError:
                    logger.exception('site_config_general: IntegrityError saving site config')
                    messages.error(request, 'Could not save these settings — please check the details and try again.')
                else:
                    messages.success(request, 'General site settings saved.')
                    return redirect('management:site_config_general')
        except SuspiciousOperation:
            logger.warning('site_config_general: oversized/suspicious upload')
            messages.error(request, 'Your changes could not be saved — one of the files you uploaded was too large. Please use a smaller file and try again.')
            form = SiteConfigGeneralForm(instance=site)
        except Exception:
            logger.exception('site_config_general: unexpected error saving site config')
            messages.error(request, 'Something went wrong while saving these settings. Nothing was saved. Please try again.')
            form = SiteConfigGeneralForm(instance=site)
    else:
        form = SiteConfigGeneralForm(instance=site)

    from apps.eduweb.paystack import _fetch_live_usd_to_ngn_rate
    return render(request, 'management/site_config/general.html', {
        'form': form,
        'site': site,
        'live_usd_to_ngn_rate': _fetch_live_usd_to_ngn_rate(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:site_config_index')
def site_config_index(request):
    """Edit index.html fields: hero slides, promo video, campus map."""
    if request.method == 'GET' and not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view site content settings.')
        return redirect('management:dashboard')

    site = SiteConfig.objects.first()
    if request.method == 'POST':
        try:
            form = SiteConfigIndexForm(request.POST, request.FILES, instance=site)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='SiteConfig',
                            description='Updated index page configuration'
                        )
                except IntegrityError:
                    logger.exception('site_config_index: IntegrityError saving site config')
                    messages.error(request, 'Could not save these settings — please check the details and try again.')
                else:
                    messages.success(request, 'Home page settings saved.')
                    return redirect('management:site_config_index')
        except SuspiciousOperation:
            logger.warning('site_config_index: oversized/suspicious upload')
            messages.error(request, 'Your changes could not be saved — one of the files you uploaded was too large. Please use a smaller file and try again.')
            form = SiteConfigIndexForm(instance=site)
        except Exception:
            logger.exception('site_config_index: unexpected error saving site config')
            messages.error(request, 'Something went wrong while saving these settings. Nothing was saved. Please try again.')
            form = SiteConfigIndexForm(instance=site)
    else:
        form = SiteConfigIndexForm(instance=site)
    return render(request, 'management/site_config/index_page.html', {'form': form, 'site': site})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:site_config_about')
def site_config_about(request):
    """Edit about.html fields: mission, vision, values, virtual tour."""
    if request.method == 'GET' and not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view site content settings.')
        return redirect('management:dashboard')

    site = SiteConfig.objects.first()
    if request.method == 'POST':
        try:
            form = SiteConfigAboutForm(request.POST, request.FILES, instance=site)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='SiteConfig',
                            description='Updated about page configuration'
                        )
                except IntegrityError:
                    logger.exception('site_config_about: IntegrityError saving site config')
                    messages.error(request, 'Could not save these settings — please check the details and try again.')
                else:
                    messages.success(request, 'About page settings saved.')
                    return redirect('management:site_config_about')
        except SuspiciousOperation:
            logger.warning('site_config_about: oversized/suspicious upload')
            messages.error(request, 'Your changes could not be saved — one of the files you uploaded was too large. Please use a smaller file and try again.')
            form = SiteConfigAboutForm(instance=site)
        except Exception:
            logger.exception('site_config_about: unexpected error saving site config')
            messages.error(request, 'Something went wrong while saving these settings. Nothing was saved. Please try again.')
            form = SiteConfigAboutForm(instance=site)
    else:
        form = SiteConfigAboutForm(instance=site)
    return render(request, 'management/site_config/about_page.html', {'form': form, 'site': site})

# ── SITE HISTORY MILESTONES ───────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_milestones_list(request):
    if not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view site history milestones.')
        return redirect('management:dashboard')

    milestones = SiteHistoryMilestone.objects.all().order_by('year')
    return render(request, 'management/site_config/milestones_list.html', {
        'milestones': milestones,
        'active_count': milestones.filter(is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_create', redirect_to='management:site_milestones_list')
def site_milestone_create(request):
    if request.method == 'POST':
        form = SiteHistoryMilestoneForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    milestone = form.save(commit=False)
                    milestone.site = SiteConfig.objects.first()
                    milestone.save()
                    AuditLog.objects.create(
                        user=request.user, action='create',
                        model_name='SiteHistoryMilestone',
                        description=f'Created milestone: {milestone}'
                    )
            except IntegrityError:
                logger.exception('site_milestone_create: IntegrityError saving milestone')
                messages.error(request, 'Could not save this milestone — please check the details and try again.')
            except Exception:
                logger.exception('site_milestone_create: unexpected error saving milestone')
                messages.error(request, 'Something went wrong while saving this milestone. Please try again.')
            else:
                messages.success(request, 'Milestone created.')
                return redirect('management:site_milestones_list')
    else:
        form = SiteHistoryMilestoneForm()
    return render(request, 'management/site_config/milestone_form.html', {
        'form': form, 'milestone': None,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:site_milestones_list')
def site_milestone_edit(request, pk):
    milestone = get_object_or_404(SiteHistoryMilestone, pk=pk)
    if request.method == 'POST':
        form = SiteHistoryMilestoneForm(request.POST, instance=milestone)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    AuditLog.objects.create(
                        user=request.user, action='update',
                        model_name='SiteHistoryMilestone',
                        description=f'Updated milestone: {milestone}'
                    )
            except IntegrityError:
                logger.exception('site_milestone_edit: IntegrityError saving milestone pk=%s', pk)
                messages.error(request, 'Could not save this milestone — please check the details and try again.')
            except Exception:
                logger.exception('site_milestone_edit: unexpected error saving milestone pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this milestone. Please try again.')
            else:
                messages.success(request, 'Milestone updated.')
                return redirect('management:site_milestones_list')
    else:
        form = SiteHistoryMilestoneForm(instance=milestone)
    return render(request, 'management/site_config/milestone_form.html', {
        'form': form, 'milestone': milestone,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_delete', redirect_to='management:site_milestones_list')
def site_milestone_delete(request, pk):
    milestone = get_object_or_404(SiteHistoryMilestone, pk=pk)
    if request.method == 'POST':
        try:
            milestone.delete()
            messages.success(request, 'Milestone deleted.')
        except Exception:
            logger.exception('site_milestone_delete: unexpected error deleting milestone pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this milestone. Please try again.')
    return redirect('management:site_milestones_list')


# ── TESTIMONIALS ──────────────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def testimonials_list(request):
    if not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view testimonials.')
        return redirect('management:dashboard')

    testimonials = Testimonial.objects.all().order_by('author_name')
    return render(request, 'management/site_config/testimonials_list.html', {
        'testimonials': testimonials,
        'active_count': testimonials.filter(is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_create', redirect_to='management:testimonials_list')
def testimonial_create(request):
    if request.method == 'POST':
        form = TestimonialForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    t = form.save()
                    AuditLog.objects.create(
                        user=request.user, action='create',
                        model_name='Testimonial',
                        description=f'Created testimonial: {t}'
                    )
            except IntegrityError:
                logger.exception('testimonial_create: IntegrityError saving testimonial')
                messages.error(request, 'Could not save this testimonial — please check the details and try again.')
            except Exception:
                logger.exception('testimonial_create: unexpected error saving testimonial')
                messages.error(request, 'Something went wrong while saving this testimonial. Please try again.')
            else:
                messages.success(request, 'Testimonial created.')
                return redirect('management:testimonials_list')
    else:
        form = TestimonialForm()
    return render(request, 'management/site_config/testimonial_form.html', {
        'form': form, 'testimonial': None,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:testimonials_list')
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        form = TestimonialForm(request.POST, request.FILES, instance=testimonial)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    AuditLog.objects.create(
                        user=request.user, action='update',
                        model_name='Testimonial',
                        description=f'Updated testimonial: {testimonial}'
                    )
            except IntegrityError:
                logger.exception('testimonial_edit: IntegrityError saving testimonial pk=%s', pk)
                messages.error(request, 'Could not save this testimonial — please check the details and try again.')
            except Exception:
                logger.exception('testimonial_edit: unexpected error saving testimonial pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this testimonial. Please try again.')
            else:
                messages.success(request, 'Testimonial updated.')
                return redirect('management:testimonials_list')
    else:
        form = TestimonialForm(instance=testimonial)
    return render(request, 'management/site_config/testimonial_form.html', {
        'form': form, 'testimonial': testimonial,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_delete', redirect_to='management:testimonials_list')
def testimonial_delete(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        try:
            testimonial.delete()
            messages.success(request, 'Testimonial deleted.')
        except Exception:
            logger.exception('testimonial_delete: unexpected error deleting testimonial pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this testimonial. Please try again.')
    return redirect('management:testimonials_list')


# ── SOCIAL POSTS (homepage "From Our Socials" carousel) ───────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def social_posts_list(request):
    if not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view social posts.')
        return redirect('management:dashboard')

    social_posts = SocialPost.objects.all().order_by('order', '-created_at')
    return render(request, 'management/site_config/social_posts_list.html', {
        'social_posts': social_posts,
        'active_count': social_posts.filter(is_active=True).count(),
        # The "New Social Post" modal on this page posts straight to
        # social_post_create — needs a blank bound form to render its
        # fields from (see programs_list/intakes_list for the same pattern).
        'form': SocialPostForm(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def social_post_create(request):
    """"New Social Post" is a modal on social_posts_list.html, not a
    standalone page — this view exists purely to handle that modal's POST,
    mirroring intake_create's pattern. On success it redirects to
    social_posts_list; the modal's JS detects the redirect and reloads. On
    validation failure it re-renders just the fields partial."""
    if request.method != 'POST':
        return redirect('management:social_posts_list')

    if not _has_permission(request, 'site_content', 'can_create'):
        messages.error(request, 'You do not have permission to create social posts.')
        return redirect('management:social_posts_list')

    form = SocialPostForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                post = form.save()
                AuditLog.objects.create(
                    user=request.user, action='create',
                    model_name='SocialPost',
                    description=f'Created social post: {post}'
                )
        except IntegrityError:
            logger.exception('social_post_create: IntegrityError saving social post')
            messages.error(request, 'Could not save this social post — please check the details and try again.')
        except Exception:
            logger.exception('social_post_create: unexpected error saving social post')
            messages.error(request, 'Something went wrong while saving this social post. Please try again.')
        else:
            messages.success(request, 'Social post created.')
            return redirect('management:social_posts_list')

    return render(request, 'management/site_config/_social_post_form_fields.html', {
        'form': form,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def social_post_edit(request, pk):
    """Same modal as "New Social Post" on social_posts_list.html, populated
    by fetching this view's GET response (the fields partial, pre-filled
    from the instance) and swapping it into the modal body — mirrors
    intake_edit's pattern."""
    social_post = get_object_or_404(SocialPost, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'site_content', 'can_edit'):
            messages.error(request, 'You do not have permission to edit social posts.')
            return redirect('management:social_posts_list')

        form = SocialPostForm(request.POST, instance=social_post)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    AuditLog.objects.create(
                        user=request.user, action='update',
                        model_name='SocialPost',
                        description=f'Updated social post: {social_post}'
                    )
            except IntegrityError:
                logger.exception('social_post_edit: IntegrityError saving social post pk=%s', pk)
                messages.error(request, 'Could not save this social post — please check the details and try again.')
            else:
                messages.success(request, 'Social post updated.')
                return redirect('management:social_posts_list')
    else:
        form = SocialPostForm(instance=social_post)
    return render(request, 'management/site_config/_social_post_form_fields.html', {
        'form': form, 'social_post': social_post,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_delete', redirect_to='management:social_posts_list')
def social_post_delete(request, pk):
    social_post = get_object_or_404(SocialPost, pk=pk)
    if request.method == 'POST':
        try:
            social_post.delete()
            messages.success(request, 'Social post deleted.')
        except Exception:
            logger.exception('social_post_delete: unexpected error deleting social post pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this social post. Please try again.')
    return redirect('management:social_posts_list')


# ── STORE PRODUCTS ────────────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def products_list(request):
    if not _has_permission(request, 'store_products', 'can_view'):
        messages.error(request, 'You do not have permission to view store products.')
        return redirect('management:dashboard')

    products = Product.objects.select_related('category').all()

    category_id = request.GET.get('category', '').strip()
    condition = request.GET.get('condition', '').strip()
    stock = request.GET.get('stock', '').strip()
    featured = request.GET.get('featured', '').strip()

    if category_id:
        products = products.filter(category_id=category_id)
    if condition:
        products = products.filter(condition=condition)
    if stock == 'in':
        products = products.filter(Q(track_inventory=False) | Q(stock_quantity__gt=0))
    elif stock == 'out':
        products = products.filter(track_inventory=True, stock_quantity=0)
    if featured == '1':
        products = products.filter(is_featured=True)

    return render(request, 'management/site_config/products_list.html', {
        'products': products,
        'categories': ProductCategory.objects.all(),
        'active_count': Product.objects.filter(is_active=True).count(),
        'featured_count': Product.objects.filter(is_featured=True).count(),
        'out_of_stock_count': Product.objects.filter(track_inventory=True, stock_quantity=0).count(),
        'form': ProductForm(),
        'specs_formset': ProductSpecificationFormSet(prefix='specs'),
        'variants_formset': ProductVariantFormSet(prefix='variants'),
    })


def _auto_number_sort_order(formset):
    """A row left with 'Order' blank gets its position in the formset as
    its sort_order (0, 1, 2, ...) instead of failing validation — staff
    reordering only a couple of rows shouldn't have to number every row."""
    for i, f in enumerate(formset.forms):
        if f.cleaned_data.get('DELETE'):
            continue
        if f.cleaned_data.get('sort_order') in (None, ''):
            f.instance.sort_order = i


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def product_create(request):
    """"New Product" is a modal on products_list.html, not a standalone
    page — mirrors social_post_create's pattern. The specifications repeater
    is an inline formset bound to an as-yet-unsaved Product() so validation
    errors on either the product or its specs re-render together; the real
    parent link is only written once both halves are valid (see Django's
    documented "formset bound to an unsaved instance" idiom)."""
    if request.method != 'POST':
        return redirect('management:products_list')

    if not _has_permission(request, 'store_products', 'can_create'):
        messages.error(request, 'You do not have permission to create store products.')
        return redirect('management:products_list')

    form = ProductForm(request.POST)
    if form.is_valid():
        product = form.save(commit=False)
        specs_formset = ProductSpecificationFormSet(request.POST, instance=product, prefix='specs')
        variants_formset = ProductVariantFormSet(request.POST, instance=product, prefix='variants')
        if specs_formset.is_valid() and variants_formset.is_valid():
            _auto_number_sort_order(specs_formset)
            _auto_number_sort_order(variants_formset)
            try:
                with transaction.atomic():
                    product.save()
                    specs_formset.save()
                    variants_formset.save()
                    AuditLog.objects.create(
                        user=request.user, action='create',
                        model_name='Product', object_id=str(product.pk),
                        description=f'Created store product: {product}'
                    )
            except IntegrityError:
                logger.exception('product_create: IntegrityError saving product')
                messages.error(request, 'Could not save this product — please check the details and try again.')
            except Exception:
                logger.exception('product_create: unexpected error saving product')
                messages.error(request, 'Something went wrong while saving this product. Please try again.')
            else:
                messages.success(request, 'Product created. Add images from the Edit screen.')
                return redirect('management:products_list')
    else:
        specs_formset = ProductSpecificationFormSet(request.POST, instance=Product(), prefix='specs')
        variants_formset = ProductVariantFormSet(request.POST, instance=Product(), prefix='variants')

    return render(request, 'management/site_config/_product_form_fields.html', {
        'form': form,
        'specs_formset': specs_formset,
        'variants_formset': variants_formset,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def product_edit(request, pk):
    """Same modal as "New Product" on products_list.html, populated by
    fetching this view's GET response — mirrors social_post_edit's pattern.
    Also carries the image-gallery manager (existing ProductImages + the
    upload-new/choose-from-library "Add Image" controls), since images can
    only be attached once the product itself has a pk."""
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'store_products', 'can_edit'):
            messages.error(request, 'You do not have permission to edit store products.')
            return redirect('management:products_list')

        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            specs_formset = ProductSpecificationFormSet(request.POST, instance=product, prefix='specs')
            variants_formset = ProductVariantFormSet(request.POST, instance=product, prefix='variants')
            if specs_formset.is_valid() and variants_formset.is_valid():
                _auto_number_sort_order(specs_formset)
                _auto_number_sort_order(variants_formset)
                try:
                    with transaction.atomic():
                        form.save()
                        specs_formset.save()
                        variants_formset.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='Product', object_id=str(product.pk),
                            description=f'Updated store product: {product}'
                        )
                except IntegrityError:
                    logger.exception('product_edit: IntegrityError saving product pk=%s', pk)
                    messages.error(request, 'Could not save this product — please check the details and try again.')
                else:
                    messages.success(request, 'Product updated.')
                    return redirect('management:products_list')
        else:
            specs_formset = ProductSpecificationFormSet(request.POST, instance=product, prefix='specs')
            variants_formset = ProductVariantFormSet(request.POST, instance=product, prefix='variants')
    else:
        form = ProductForm(instance=product)
        specs_formset = ProductSpecificationFormSet(instance=product, prefix='specs')
        variants_formset = ProductVariantFormSet(instance=product, prefix='variants')

    existing_images = product.images.select_related('asset').all()
    return render(request, 'management/site_config/_product_form_fields.html', {
        'form': form, 'product': product, 'specs_formset': specs_formset, 'variants_formset': variants_formset,
        'existing_images': existing_images,
        'library_assets': MediaAsset.objects.all()[:60],
        'attached_asset_ids': set(existing_images.values_list('asset_id', flat=True)),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('store_products', 'can_delete', redirect_to='management:products_list')
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        try:
            product_repr = str(product)
            product_pk = product.pk
            product.delete()
            AuditLog.objects.create(
                user=request.user, action='delete',
                model_name='Product', object_id=str(product_pk),
                description=f'Deleted store product: {product_repr}'
            )
            messages.success(request, 'Product deleted.')
        except Exception:
            logger.exception('product_delete: unexpected error deleting product pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this product. Please try again.')
    return redirect('management:products_list')


# ── PRODUCT IMAGES (AJAX, called from inside the product edit modal) ──────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def product_image_add(request, pk):
    """Handles both "Add Image" paths from the gallery manager: uploading a
    brand-new file (creates a MediaAsset then a ProductImage) or picking an
    existing MediaAsset from the shared library (creates only the
    ProductImage, so the same file can back more than one product)."""
    product = get_object_or_404(Product, pk=pk)
    if not _has_permission(request, 'store_products', 'can_edit'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    source = request.POST.get('source', 'upload')

    try:
        with transaction.atomic():
            if source == 'library':
                asset = MediaAsset.objects.filter(pk=request.POST.get('asset_id')).first()
                if not asset:
                    return JsonResponse({'success': False, 'error': 'Selected image could not be found.'}, status=404)
                if product.images.filter(asset=asset).exists():
                    return JsonResponse({'success': False, 'error': 'This image is already in this product\'s gallery.'}, status=400)
            else:
                asset_form = MediaAssetForm(request.POST, request.FILES)
                if not asset_form.is_valid():
                    errors = ' '.join(e for errs in asset_form.errors.values() for e in errs)
                    return JsonResponse({'success': False, 'error': errors or 'Invalid image file.'}, status=400)
                asset = asset_form.save(commit=False)
                asset.uploaded_by = request.user
                asset.save()

            is_first = not product.images.exists()
            next_order = (product.images.aggregate(Max('sort_order'))['sort_order__max'] or 0) + 1
            image = ProductImage.objects.create(
                product=product, asset=asset, sort_order=next_order, is_primary=is_first,
            )
    except Exception:
        logger.exception('product_image_add: unexpected error pk=%s', pk)
        return JsonResponse({'success': False, 'error': 'Something went wrong while adding this image.'}, status=500)

    AuditLog.objects.create(
        user=request.user, action='update', model_name='Product', object_id=str(product.pk),
        description=f'Added an image to store product: {product}'
    )
    return JsonResponse({
        'success': True,
        'image': {'id': image.id, 'url': image.asset.file.url, 'is_primary': image.is_primary},
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def product_image_delete(request, pk, image_id):
    product = get_object_or_404(Product, pk=pk)
    if not _has_permission(request, 'store_products', 'can_edit'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    was_primary = image.is_primary
    image.delete()

    if was_primary:
        next_image = product.images.first()
        if next_image:
            next_image.is_primary = True
            next_image.save(update_fields=['is_primary'])

    AuditLog.objects.create(
        user=request.user, action='update', model_name='Product', object_id=str(product.pk),
        description=f'Removed an image from store product: {product}'
    )
    return JsonResponse({'success': True})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def product_image_set_primary(request, pk, image_id):
    product = get_object_or_404(Product, pk=pk)
    if not _has_permission(request, 'store_products', 'can_edit'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    with transaction.atomic():
        product.images.exclude(pk=image.pk).update(is_primary=False)
        image.is_primary = True
        image.save(update_fields=['is_primary'])

    return JsonResponse({'success': True})


# ── PRODUCT CATEGORIES ─────────────────────────────────────────────────────────
# Gated on 'store_products' too — categories are part of product management,
# not a separate permission module (products need one to exist before they
# can be assigned to it).

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def product_categories_list(request):
    if not _has_permission(request, 'store_products', 'can_view'):
        messages.error(request, 'You do not have permission to view product categories.')
        return redirect('management:dashboard')

    categories = ProductCategory.objects.annotate(product_count=Count('products')).order_by('title')
    return render(request, 'management/site_config/product_categories_list.html', {
        'categories': categories,
        'form': ProductCategoryForm(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def product_category_create(request):
    if request.method != 'POST':
        return redirect('management:product_categories_list')

    if not _has_permission(request, 'store_products', 'can_create'):
        messages.error(request, 'You do not have permission to create product categories.')
        return redirect('management:product_categories_list')

    form = ProductCategoryForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                category = form.save()
                AuditLog.objects.create(
                    user=request.user, action='create',
                    model_name='ProductCategory', object_id=str(category.pk),
                    description=f'Created product category: {category}'
                )
        except IntegrityError:
            logger.exception('product_category_create: IntegrityError saving category')
            messages.error(request, 'Could not save this category — that title may already be in use.')
        except Exception:
            logger.exception('product_category_create: unexpected error saving category')
            messages.error(request, 'Something went wrong while saving this category. Please try again.')
        else:
            messages.success(request, 'Category created.')
            return redirect('management:product_categories_list')

    return render(request, 'management/site_config/_product_category_form_fields.html', {
        'form': form,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def product_category_edit(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'store_products', 'can_edit'):
            messages.error(request, 'You do not have permission to edit product categories.')
            return redirect('management:product_categories_list')

        form = ProductCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    AuditLog.objects.create(
                        user=request.user, action='update',
                        model_name='ProductCategory', object_id=str(category.pk),
                        description=f'Updated product category: {category}'
                    )
            except IntegrityError:
                logger.exception('product_category_edit: IntegrityError saving category pk=%s', pk)
                messages.error(request, 'Could not save this category — that title may already be in use.')
            else:
                messages.success(request, 'Category updated.')
                return redirect('management:product_categories_list')
    else:
        form = ProductCategoryForm(instance=category)

    return render(request, 'management/site_config/_product_category_form_fields.html', {
        'form': form, 'category': category,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('store_products', 'can_delete', redirect_to='management:product_categories_list')
def product_category_delete(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk)
    if request.method == 'POST':
        product_count = category.products.count()
        if product_count:
            messages.error(
                request,
                f'Cannot delete "{category}" — {product_count} product(s) are still assigned to it.'
            )
            return redirect('management:product_categories_list')
        try:
            category_repr = str(category)
            category_pk = category.pk
            category.delete()
            AuditLog.objects.create(
                user=request.user, action='delete',
                model_name='ProductCategory', object_id=str(category_pk),
                description=f'Deleted product category: {category_repr}'
            )
            messages.success(request, 'Category deleted.')
        except Exception:
            logger.exception('product_category_delete: unexpected error deleting category pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this category. Please try again.')
    return redirect('management:product_categories_list')


# ── STORE ORDERS (fulfillment queue) ───────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def orders_list(request):
    if not _has_permission(request, 'store_orders', 'can_view'):
        messages.error(request, 'You do not have permission to view store orders.')
        return redirect('management:dashboard')

    qs = Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    pending_count = Order.objects.filter(status__in=['paid', 'processing', 'shipped']).count()

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/site_config/orders_list.html', {
        'orders': page_obj,
        'pending_count': pending_count,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def order_detail(request, order_number):
    if not _has_permission(request, 'store_orders', 'can_view'):
        messages.error(request, 'You do not have permission to view store orders.')
        return redirect('management:orders_list')

    order = get_object_or_404(
        Order.objects.select_related('user').prefetch_related('items'),
        order_number=order_number
    )

    if request.method == 'POST' and request.POST.get('action') == 'advance_status':
        if not _has_permission(request, 'store_orders', 'can_edit'):
            messages.error(request, 'You do not have permission to update store orders.')
            return redirect('management:order_detail', order_number=order_number)

        target_status = request.POST.get('target_status', '').strip()
        staff_note = request.POST.get('staff_note', '').strip()
        try:
            if staff_note:
                order.staff_note = staff_note
                order.save(update_fields=['staff_note'])
            order.advance_status(target_status, request.user)
        except ValueError as e:
            messages.error(request, str(e))
        else:
            AuditLog.objects.create(
                user=request.user, action='update', model_name='Order', object_id=str(order.id),
                description=f'Marked order {order.order_number} as {order.get_status_display()}.'
            )
            messages.success(request, f'Order {order.order_number} marked as {order.get_status_display()}.')
        return redirect('management:order_detail', order_number=order_number)

    fulfillment_stages = None
    if order.status in Order.FULFILLMENT_SEQUENCE:
        current_index = Order.FULFILLMENT_SEQUENCE.index(order.status)
        stage_labels = {'paid': 'Paid', 'processing': 'Processing', 'shipped': 'Shipped', 'delivered': 'Delivered'}
        fulfillment_stages = [
            {'label': stage_labels[stage], 'done': i <= current_index}
            for i, stage in enumerate(Order.FULFILLMENT_SEQUENCE)
        ]

    return render(request, 'management/site_config/order_detail.html', {
        'order': order,
        'fulfillment_stages': fulfillment_stages,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def refund_requests_list(request):
    """Standalone review queue for customer-submitted cancel/refund
    requests (Order.request_refund in apps/store/views.py sets these —
    nothing here has touched Paystack or the order's status yet). Approving
    from this page is the only place that actually calls Paystack."""
    if not _has_permission(request, 'store_orders', 'can_view'):
        messages.error(request, 'You do not have permission to view store orders.')
        return redirect('management:dashboard')

    pending = (
        Order.objects.filter(refund_request_status='pending')
        .select_related('user').order_by('refund_requested_at')
    )
    decided = (
        Order.objects.filter(refund_request_status__in=['approved', 'rejected'])
        .select_related('user', 'refunded_by').order_by('-updated_at')[:25]
    )

    return render(request, 'management/site_config/refund_requests_list.html', {
        'pending_requests': pending,
        'decided_requests': decided,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
def refund_request_decide(request, order_number):
    if not _has_permission(request, 'store_orders', 'can_edit'):
        messages.error(request, 'You do not have permission to update store orders.')
        return redirect('management:refund_requests_list')

    order = get_object_or_404(Order, order_number=order_number)
    decision = request.POST.get('decision', '').strip()
    note = request.POST.get('note', '').strip()

    if order.refund_request_status != 'pending':
        messages.error(request, f'Order {order.order_number} has no pending refund request.')
        return redirect('management:refund_requests_list')

    if decision == 'reject':
        order.refund_request_status = 'rejected'
        order.refund_reason = note
        order.save(update_fields=['refund_request_status', 'refund_reason'])
        AuditLog.objects.create(
            user=request.user, action='update', model_name='Order', object_id=str(order.id),
            description=f'Rejected refund request for {order.order_number}.'
        )
        send_refund_request_rejected_email(order)
        messages.success(request, f'Refund request for {order.order_number} rejected.')
        return redirect('management:refund_requests_list')

    if decision != 'approve':
        messages.error(request, 'Unknown decision.')
        return redirect('management:refund_requests_list')

    if not order.can_be_refunded:
        messages.error(request, f'Order {order.order_number} is no longer eligible for a refund (status: {order.get_status_display()}).')
        return redirect('management:refund_requests_list')

    data = store_services.create_refund(order)
    if not data.get('status'):
        messages.error(request, f"Paystack refund failed: {data.get('message', 'Unknown error')}")
        return redirect('management:refund_requests_list')

    with transaction.atomic():
        for item in order.items.select_related('product').all():
            if item.product and item.product.track_inventory:
                Product.objects.filter(pk=item.product_id).update(
                    stock_quantity=F('stock_quantity') + item.quantity
                )
        order.status = 'refunded'
        order.refunded_at = timezone.now()
        order.refunded_by = request.user
        order.refund_reason = note
        order.refund_request_status = 'approved'
        order.save(update_fields=['status', 'refunded_at', 'refunded_by', 'refund_reason', 'refund_request_status', 'updated_at'])

    AuditLog.objects.create(
        user=request.user, action='update', model_name='Order', object_id=str(order.id),
        description=f'Approved and processed refund for {order.order_number}.'
    )
    send_order_refunded_email(order)
    messages.success(request, f'Order {order.order_number} refunded.')
    return redirect('management:refund_requests_list')


# ── INSTITUTION MEMBERS ───────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_members_list(request):
    if not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view institution members.')
        return redirect('management:dashboard')

    members = InstitutionMember.objects.all().order_by('member_type', 'name')
    return render(request, 'management/site_config/members_list.html', {
        'members': members,
        'admin_board_count':      members.filter(member_type='admin_board', is_active=True).count(),
        'academic_board_count':   members.filter(member_type='academic_board', is_active=True).count(),
        'advisorate_board_count': members.filter(member_type='advisorate_board', is_active=True).count(),
        'staff_count':            members.filter(member_type='staff', is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_create', redirect_to='management:institution_members_list')
def institution_member_create(request):
    if request.method == 'POST':
        try:
            # Constructing the form is what triggers Django to actually
            # parse request.POST/request.FILES — if the submitted request
            # body is larger than DATA_UPLOAD_MAX_MEMORY_SIZE, that parsing
            # raises SuspiciousOperation right here instead of letting it
            # surface as an unhandled crash.
            form = InstitutionMemberForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        m = form.save()
                        AuditLog.objects.create(
                            user=request.user, action='create',
                            model_name='InstitutionMember',
                            description=f'Created member: {m}'
                        )
                except IntegrityError:
                    logger.exception('institution_member_create: IntegrityError saving member')
                    messages.error(request, 'Could not save this member — please check the details and try again.')
                else:
                    messages.success(request, 'Member created.')
                    return redirect('management:institution_members_list')
        except SuspiciousOperation:
            logger.warning('institution_member_create: oversized/suspicious upload')
            messages.error(
                request,
                'This member could not be saved — the photo you uploaded was too '
                'large for the server to accept. Please use a smaller image and try again.'
            )
            form = InstitutionMemberForm()
        except Exception:
            # Last-resort net: never let an unexpected error surface as a
            # raw crash page — log it for diagnosis and show the admin a
            # clean, actionable message on the same form instead.
            logger.exception('institution_member_create: unexpected error saving member')
            messages.error(
                request,
                'Something went wrong while saving this member. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
            form = InstitutionMemberForm()
    else:
        form = InstitutionMemberForm()
    return render(request, 'management/site_config/member_form.html', {
        'form': form, 'member': None,
        'current_who_we_are': InstitutionMember.objects.filter(is_who_we_are=True).first(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:institution_members_list')
def institution_member_edit(request, pk):
    member = get_object_or_404(InstitutionMember, pk=pk)
    if request.method == 'POST':
        try:
            # Constructing the form is what triggers Django to actually
            # parse request.POST/request.FILES — if the submitted request
            # body is larger than DATA_UPLOAD_MAX_MEMORY_SIZE, that parsing
            # raises SuspiciousOperation right here instead of letting it
            # surface as an unhandled crash.
            form = InstitutionMemberForm(request.POST, request.FILES, instance=member)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='InstitutionMember',
                            description=f'Updated member: {member}'
                        )
                except IntegrityError:
                    logger.exception('institution_member_edit: IntegrityError saving member pk=%s', pk)
                    messages.error(request, 'Could not save changes — please check the details and try again.')
                else:
                    messages.success(request, 'Member updated.')
                    return redirect('management:institution_members_list')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        # Optional: make a nicer message for the photo field
                        if field == "photo":
                            messages.error(request, f"Photo upload error: {error}")
                        else:
                            messages.error(request, f"{field.capitalize()}: {error}")
        except SuspiciousOperation:
            logger.warning('institution_member_edit: oversized/suspicious upload for pk=%s', pk)
            messages.error(
                request,
                'Your changes could not be saved — the photo you uploaded was too '
                'large for the server to accept. Please use a smaller image and try again.'
            )
            form = InstitutionMemberForm(instance=member)
        except Exception:
            # Last-resort net: never let an unexpected error surface as a
            # raw crash page — log it for diagnosis and show the admin a
            # clean, actionable message on the same form instead.
            logger.exception('institution_member_edit: unexpected error saving member pk=%s', pk)
            messages.error(
                request,
                'Something went wrong while saving your changes. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
            form = InstitutionMemberForm(instance=member)
    else:
        form = InstitutionMemberForm(instance=member)
    return render(request, 'management/site_config/member_form.html', {
        'form': form, 'member': member,
        'current_who_we_are': InstitutionMember.objects.filter(is_who_we_are=True).exclude(pk=member.pk).first(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_delete', redirect_to='management:institution_members_list')
def institution_member_delete(request, pk):
    member = get_object_or_404(InstitutionMember, pk=pk)
    if request.method == 'POST':
        try:
            member.delete()
            messages.success(request, 'Member deleted.')
        except Exception:
            logger.exception('institution_member_delete: unexpected error deleting member pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this member. Please try again.')
    return redirect('management:institution_members_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_edit', redirect_to='management:institution_members_list')
def institution_member_set_who_we_are(request, pk):
    """Quick-toggle a member as the one featured in the About page 'Who We Are' section."""
    member = get_object_or_404(InstitutionMember, pk=pk)
    if request.method == 'POST':
        try:
            member.is_who_we_are = not member.is_who_we_are
            member.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='InstitutionMember',
                description=f'{"Featured" if member.is_who_we_are else "Unfeatured"} member in "Who We Are": {member}'
            )
        except Exception:
            logger.exception('institution_member_set_who_we_are: unexpected error toggling member pk=%s', pk)
            messages.error(request, 'Something went wrong. Please try again.')
        else:
            if member.is_who_we_are:
                messages.success(request, f'{member.name} is now featured in "Who We Are".')
            else:
                messages.success(request, f'{member.name} removed from "Who We Are".')
    return redirect('management:institution_members_list')


# ── ACCREDITATION / AFFILIATES / PARTNERS ─────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_partners_list(request):
    if not _has_permission(request, 'site_content', 'can_view'):
        messages.error(request, 'You do not have permission to view accreditation & partner records.')
        return redirect('management:dashboard')

    partners = InstitutionPartner.objects.all().order_by('category', 'name')
    return render(request, 'management/site_config/partners_list.html', {
        'form': InstitutionPartnerForm(),
        'accreditations': partners.filter(category='accreditation'),
        'affiliations':   partners.filter(category='affiliation'),
        'partners':       partners.filter(category='partner'),
        'accreditation_count': partners.filter(category='accreditation', is_active=True).count(),
        'affiliation_count':   partners.filter(category='affiliation', is_active=True).count(),
        'partner_count':       partners.filter(category='partner', is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_partner_create(request):
    """
    "Add" is a modal on partners_list.html, not a standalone page — this
    view exists purely to handle that modal's POST. On success it redirects
    to institution_partners_list (the modal's JS detects the redirect and
    reloads); on validation failure it re-renders just the fields partial,
    which the modal's JS swaps in without a full navigation.
    """
    if request.method != 'POST':
        return redirect('management:institution_partners_list')

    if not _has_permission(request, 'site_content', 'can_create'):
        messages.error(request, 'You do not have permission to create this record.')
        return redirect('management:institution_partners_list')

    try:
        # Constructing the form is what triggers Django to actually parse
        # request.POST/request.FILES — if the submitted request body is
        # larger than DATA_UPLOAD_MAX_MEMORY_SIZE, that parsing raises
        # SuspiciousOperation right here instead of letting it surface as
        # an unhandled crash.
        form = InstitutionPartnerForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    obj = form.save()
                    AuditLog.objects.create(
                        user=request.user, action='create',
                        model_name='InstitutionPartner',
                        description=f'Created {obj.get_category_display()}: {obj}'
                    )
            except IntegrityError:
                logger.exception('institution_partner_create: IntegrityError saving record')
                messages.error(request, 'Could not save this record — please check the details and try again.')
            else:
                messages.success(request, f'{obj.get_category_display()} record created.')
                return redirect('management:institution_partners_list')
    except SuspiciousOperation:
        logger.warning('institution_partner_create: oversized/suspicious upload')
        messages.error(
            request,
            'This record could not be saved — the logo you uploaded was too '
            'large for the server to accept. Please use a smaller image and try again.'
        )
        form = InstitutionPartnerForm()
    except Exception:
        # Last-resort net: never let an unexpected error surface as a raw
        # crash page — log it for diagnosis and show a clean message instead.
        logger.exception('institution_partner_create: unexpected error saving record')
        messages.error(
            request,
            'Something went wrong while saving this record. Nothing was saved. '
            'Please try again, and contact support if this keeps happening.'
        )
        form = InstitutionPartnerForm()

    return render(request, 'management/site_config/_partner_form_fields.html', {'form': form})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_partner_edit(request, pk):
    obj = get_object_or_404(InstitutionPartner, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'site_content', 'can_edit'):
            messages.error(request, 'You do not have permission to edit this record.')
            return redirect('management:institution_partners_list')

        try:
            # Constructing the form is what triggers Django to actually
            # parse request.POST/request.FILES — if the submitted request
            # body is larger than DATA_UPLOAD_MAX_MEMORY_SIZE, that parsing
            # raises SuspiciousOperation right here instead of letting it
            # surface as an unhandled crash.
            form = InstitutionPartnerForm(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        AuditLog.objects.create(
                            user=request.user, action='update',
                            model_name='InstitutionPartner',
                            description=f'Updated {obj.get_category_display()}: {obj}'
                        )
                except IntegrityError:
                    logger.exception('institution_partner_edit: IntegrityError saving record pk=%s', pk)
                    messages.error(request, 'Could not save changes — please check the details and try again.')
                else:
                    messages.success(request, f'{obj.get_category_display()} record updated.')
                    return redirect('management:institution_partners_list')
        except SuspiciousOperation:
            logger.warning('institution_partner_edit: oversized/suspicious upload for pk=%s', pk)
            messages.error(
                request,
                'Your changes could not be saved — the logo you uploaded was too '
                'large for the server to accept. Please use a smaller image and try again.'
            )
            form = InstitutionPartnerForm(instance=obj)
        except Exception:
            # Last-resort net: never let an unexpected error surface as a raw
            # crash page — log it for diagnosis and show a clean message instead.
            logger.exception('institution_partner_edit: unexpected error saving record pk=%s', pk)
            messages.error(
                request,
                'Something went wrong while saving your changes. Nothing was saved. '
                'Please try again, and contact support if this keeps happening.'
            )
            form = InstitutionPartnerForm(instance=obj)
    else:
        form = InstitutionPartnerForm(instance=obj)
    return render(request, 'management/site_config/_partner_form_fields.html', {'form': form, 'partner': obj})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('site_content', 'can_delete', redirect_to='management:institution_partners_list')
def institution_partner_delete(request, pk):
    obj = get_object_or_404(InstitutionPartner, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
            messages.success(request, 'Record deleted.')
        except Exception:
            logger.exception('institution_partner_delete: unexpected error deleting record pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this record. Please try again.')
    return redirect('management:institution_partners_list')

# ── Library: Item List ────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_items_list(request):
    """
    Paginated, filterable list of all LibraryItems.
    Filters: q (search), category, access, status (active/inactive).
    """
    if not _has_permission(request, 'library', 'can_view'):
        messages.error(request, 'You do not have permission to view library items.')
        return redirect('management:dashboard')

    qs = LibraryItem.objects.all().order_by('category', 'subcategory', 'order', 'title')
 
    q          = request.GET.get('q', '').strip()
    cat_filter = request.GET.get('category', '')
    access_f   = request.GET.get('access', '')
    status_f   = request.GET.get('status', '')   # 'active' | 'inactive'
 
    if q:
        qs = qs.filter(
            Q(title__icontains=q)       |
            Q(author__icontains=q)      |
            Q(subcategory__icontains=q) |
            Q(tags__icontains=q)        |
            Q(isbn__icontains=q)
        )
    if cat_filter:
        qs = qs.filter(category=cat_filter)
    if access_f:
        qs = qs.filter(access=access_f)
    if status_f == 'active':
        qs = qs.filter(is_active=True)
    elif status_f == 'inactive':
        qs = qs.filter(is_active=False)
 
    # Stats strip
    total_count    = LibraryItem.objects.count()
    active_count   = LibraryItem.objects.filter(is_active=True).count()
    public_count   = LibraryItem.objects.filter(access='public').count()
    featured_count = LibraryItem.objects.filter(featured=True).count()
 
    category_choices = LibraryItem.CATEGORY_CHOICES  # [('Books','Books'), ...]
 
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
 
    return render(request, 'management/library/items_list.html', {
        'page_obj':         page_obj,
        'query':            q,
        'cat_filter':       cat_filter,
        'access_filter':    access_f,
        'status_filter':    status_f,
        'total_count':      total_count,
        'active_count':     active_count,
        'public_count':     public_count,
        'featured_count':   featured_count,
        'category_choices': category_choices,
    })
 
 
# ── Library: Create ───────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_item_create(request):
    """Create a new LibraryItem. Records created_by from request.user."""
    if request.method == 'POST':
        if not _has_permission(request, 'library', 'can_create'):
            messages.error(request, 'You do not have permission to add library items.')
            return redirect('management:library_items_list')

        form = LibraryItemForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    item = form.save(commit=False)
                    item.created_by = request.user
                    item.save()
            except IntegrityError:
                logger.exception('library_item_create: IntegrityError saving item')
                messages.error(request, 'Could not save this item — please check the details and try again.')
            except Exception:
                logger.exception('library_item_create: unexpected error saving item')
                messages.error(request, 'Something went wrong while saving this item. Please try again.')
            else:
                messages.success(request, f'"{item.title}" added to the library.')
                if 'save_and_add' in request.POST:
                    return redirect('management:library_item_create')
                return redirect('management:library_items_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LibraryItemForm()
 
    return render(request, 'management/library/item_form.html', {
        'form':       form,
        'page_title': 'Add Library Item',
        'is_create':  True,
    })
 
 
# ── Library: Edit ─────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_item_edit(request, pk):
    """Edit an existing LibraryItem. pk is a UUID."""
    if request.method == 'GET' and not _has_permission(request, 'library', 'can_view'):
        messages.error(request, 'You do not have permission to view library items.')
        return redirect('management:library_items_list')

    item = get_object_or_404(LibraryItem, pk=pk)

    if request.method == 'POST':
        if not _has_permission(request, 'library', 'can_edit'):
            messages.error(request, 'You do not have permission to edit library items.')
            return redirect('management:library_items_list')

        form = LibraryItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                logger.exception('library_item_edit: IntegrityError saving item pk=%s', pk)
                messages.error(request, 'Could not save this item — please check the details and try again.')
            except Exception:
                logger.exception('library_item_edit: unexpected error saving item pk=%s', pk)
                messages.error(request, 'Something went wrong while saving this item. Please try again.')
            else:
                messages.success(request, f'"{item.title}" updated successfully.')
                return redirect('management:library_items_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LibraryItemForm(instance=item)
 
    return render(request, 'management/library/item_form.html', {
        'form':       form,
        'item':       item,
        'page_title': f'Edit — {item.title}',
        'is_create':  False,
    })
 
 
# ── Library: Delete ───────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_item_delete(request, pk):
    """Hard-delete a LibraryItem (POST only). pk is a UUID."""
    item = get_object_or_404(LibraryItem, pk=pk)
    if request.method == 'POST':
        if not _has_permission(request, 'library', 'can_delete'):
            messages.error(request, 'You do not have permission to delete library items.')
            return redirect('management:library_items_list')

        title = item.title
        try:
            item.delete()
            messages.success(request, f'"{title}" removed from the library.')
        except Exception:
            logger.exception('library_item_delete: unexpected error deleting item pk=%s', pk)
            messages.error(request, 'Something went wrong while deleting this item. Please try again.')
    return redirect('management:library_items_list')
 
 
# ── Library: Toggle Active ────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_permission('library', 'can_edit', redirect_to='management:library_items_list')
def library_item_toggle_active(request, pk):
    """
    Quick-toggle is_active on a LibraryItem.
    Supports both standard POST redirect and AJAX JSON response.
    pk is a UUID.
    """
    item = get_object_or_404(LibraryItem, pk=pk)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        try:
            item.is_active = not item.is_active
            item.save(update_fields=['is_active'])
        except Exception:
            logger.exception('library_item_toggle_active: unexpected error toggling item pk=%s', pk)
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Something went wrong. Please try again.'}, status=500)
            messages.error(request, 'Something went wrong. Please try again.')
            return redirect('management:library_items_list')

        state = 'published' if item.is_active else 'unpublished'

        if is_ajax:
            return JsonResponse({
                'success':   True,
                'is_active': item.is_active,
                'state':     state,
            })
        messages.success(request, f'"{item.title}" {state}.')
    return redirect('management:library_items_list')

# =============================================================================
# EXAM MANAGEMENT — SUPERADMIN VIEWS
# =============================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def admin_exam_list(request):
    if not _has_permission(request, 'exams', 'can_view'):
        messages.error(request, 'You do not have permission to view exams.')
        return redirect('management:dashboard')

    STATUS_CHOICES = Exam.STATUS_CHOICES
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')

    qs = Exam.objects.select_related('course', 'course__academic_course', 'instructor').order_by('-start_datetime')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(reference_code__icontains=search) |
            Q(course__title__icontains=search)
        )

    status_counts = {
        s: Exam.objects.filter(status=s).count()
        for s, _ in STATUS_CHOICES
    }

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'management/exam_list.html', {
        'page_obj': page_obj,
        'STATUS_CHOICES': STATUS_CHOICES,
        'status_filter': status_filter,
        'search': search,
        'status_counts': status_counts,
    })

def _redirect_to_exam_detail(request, slug, **kwargs):
    return redirect('management:admin_exam_detail', slug=slug)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('exams', 'can_edit', redirect_to='management:admin_exam_list')
def admin_exam_toggle_active(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    exam.is_active = not exam.is_active
    exam.save(update_fields=['is_active'])
    state = 'activated' if exam.is_active else 'deactivated'
    messages.success(request, f'Exam {exam.reference_code} has been {state}.')
    return redirect('management:admin_exam_list')

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def admin_exam_detail(request, slug):
    if not _has_permission(request, 'exams', 'can_view'):
        messages.error(request, 'You do not have permission to view exams.')
        return redirect('management:admin_exam_list')

    exam = get_object_or_404(
        Exam.objects.select_related('course', 'course__academic_course', 'instructor', 'submitted_by', 'approved_by', 'rejected_by', 'published_by'),
        slug=slug
    )
    status_logs = exam.status_logs.select_related('changed_by').order_by('-created_at')[:10]
    return render(request, 'management/exam_detail.html', {
        'exam': exam,
        'status_logs': status_logs,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('exams', 'can_approve', redirect_to=_redirect_to_exam_detail)
def admin_exam_approve(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    if exam.status != Exam.SUBMITTED:
        messages.error(request, 'Only submitted exams can be approved.')
        return redirect('management:admin_exam_detail', slug=slug)

    prev = exam.status
    with transaction.atomic():
        exam.status = Exam.APPROVED
        exam.approved_by = request.user
        exam.approved_at = timezone.now()
        exam.save(update_fields=['status', 'approved_by', 'approved_at'])

        ExamStatusLog.objects.create(
            exam=exam,
            from_status=prev,
            to_status=Exam.APPROVED,
            changed_by=request.user,
            note=request.POST.get('note', ''),
        )

    if exam.instructor:
        _notify(
            user=exam.instructor,
            title=f'Exam Approved: {exam.reference_code}',
            message=f'Your exam "{exam.title}" has been approved and is ready to publish.',
            notif_type='system',
        )

    messages.success(request, f'Exam {exam.reference_code} approved.')
    return redirect('management:admin_exam_detail', slug=slug)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('exams', 'can_approve', redirect_to=_redirect_to_exam_detail)
def admin_exam_reject(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    def fail(message):
        if is_ajax:
            return JsonResponse({'success': False, 'errors': {'reason': [{'message': message}]}}, status=400)
        messages.error(request, message)
        return redirect('management:admin_exam_detail', slug=slug)

    if exam.status != Exam.SUBMITTED:
        return fail('Only submitted exams can be rejected.')

    reason = request.POST.get('reason', '').strip()
    if not reason:
        return fail('A rejection reason is required.')

    prev = exam.status
    with transaction.atomic():
        exam.status = Exam.REJECTED
        exam.rejected_by = request.user
        exam.rejected_at = timezone.now()
        exam.rejection_reason = reason
        exam.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason'])

        ExamStatusLog.objects.create(
            exam=exam,
            from_status=prev,
            to_status=Exam.REJECTED,
            changed_by=request.user,
            note=reason,
        )

    if exam.instructor:
        _notify(
            user=exam.instructor,
            title=f'Exam Rejected: {exam.reference_code}',
            message=f'Your exam "{exam.title}" was rejected. Reason: {reason}',
            notif_type='system',
        )

    if is_ajax:
        return JsonResponse({'success': True})
    messages.warning(request, f'Exam {exam.reference_code} rejected.')
    return redirect('management:admin_exam_detail', slug=slug)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('exams', 'can_approve', redirect_to=_redirect_to_exam_detail)
def admin_exam_publish(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    if exam.status != Exam.APPROVED:
        messages.error(request, 'Only approved exams can be published.')
        return redirect('management:admin_exam_detail', slug=slug)

    prev = exam.status
    with transaction.atomic():
        exam.status = Exam.PUBLISHED
        exam.published_by = request.user
        exam.published_at = timezone.now()
        exam.save(update_fields=['status', 'published_by', 'published_at'])

        ExamStatusLog.objects.create(
            exam=exam,
            from_status=prev,
            to_status=Exam.PUBLISHED,
            changed_by=request.user,
            note=request.POST.get('note', ''),
        )

    if exam.instructor:
        _notify(
            user=exam.instructor,
            title=f'Exam Published: {exam.reference_code}',
            message=f'Your exam "{exam.title}" is now published and visible to students.',
            notif_type='system',
        )

    messages.success(request, f'Exam {exam.reference_code} published successfully.')
    return redirect('management:admin_exam_detail', slug=slug)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def admin_question_moderation(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    questions = exam.questions.order_by('created_at')

    if request.method == 'POST':
        if not _has_permission(request, 'exams', 'can_edit'):
            messages.error(request, 'You do not have permission to moderate exam questions.')
            return redirect('management:admin_question_moderation', slug=slug)

        q_id = request.POST.get('question_id')
        action = request.POST.get('action')
        question = get_object_or_404(ExamQuestion, pk=q_id, exam=exam)
        try:
            if action == 'activate':
                question.is_active = True
                question.save(update_fields=['is_active'])
                messages.success(request, 'Question activated.')
            elif action == 'deactivate':
                question.is_active = False
                question.save(update_fields=['is_active'])
                messages.warning(request, 'Question deactivated.')
        except Exception:
            logger.exception('admin_question_moderation: unexpected error updating question pk=%s', q_id)
            messages.error(request, 'Something went wrong while saving this change. Please try again.')
        return redirect('management:admin_question_moderation', slug=slug)

    if not _has_permission(request, 'exams', 'can_view'):
        messages.error(request, 'You do not have permission to view exam questions.')
        return redirect('management:admin_exam_list')

    return render(request, 'management/question_moderation.html', {
        'exam': exam,
        'questions': questions,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def admin_exam_timetable_update(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    if request.method == 'GET' and not _has_permission(request, 'exams', 'can_view'):
        messages.error(request, 'You do not have permission to view exam timetables.')
        return redirect('management:admin_exam_detail', slug=slug)

    if request.method == 'POST':
        if not _has_permission(request, 'exams', 'can_edit'):
            messages.error(request, 'You do not have permission to edit exam timetables.')
            return redirect('management:admin_exam_detail', slug=slug)

        exam_date = parse_date(request.POST.get('exam_date', ''))
        start_time = parse_time(request.POST.get('start_time', ''))
        end_time = parse_time(request.POST.get('end_time', ''))

        errors = []
        if not exam_date:
            errors.append('Invalid exam date.')
        if not start_time:
            errors.append('Invalid start time.')
        if not end_time:
            errors.append('Invalid end time.')
        if start_time and end_time and end_time <= start_time:
            errors.append('End time must be after start time.')

        if not errors:
            tz = zoneinfo.ZoneInfo('Africa/Lagos')
            start_datetime = timezone.make_aware(datetime.combine(exam_date, start_time), tz)
            end_datetime = timezone.make_aware(datetime.combine(exam_date, end_time), tz)

            # Clash detection: overlapping start_datetime/end_datetime window
            clash_qs = Exam.objects.filter(
                course=exam.course,
                status__in=[Exam.APPROVED, Exam.PUBLISHED],
            ).exclude(pk=exam.pk).filter(
                start_datetime__lt=end_datetime,
                end_datetime__gt=start_datetime,
            )
            if clash_qs.exists():
                clash = clash_qs.first()
                errors.append(
                    f'Schedule conflict with {clash.reference_code} '
                    f'({clash.start_datetime:%H:%M}–{clash.end_datetime:%H:%M}) on this date.'
                )

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                exam.start_datetime = start_datetime
                exam.end_datetime = end_datetime
                exam.clash_notes = ''
                exam.save(update_fields=['start_datetime', 'end_datetime', 'clash_notes'])
            except Exception:
                logger.exception('admin_exam_timetable_update: unexpected error saving exam slug=%s', slug)
                messages.error(request, 'Something went wrong while saving the timetable. Please try again.')
            else:
                messages.success(request, 'Timetable updated successfully.')
                return redirect('management:admin_exam_detail', slug=slug)

    return render(request, 'management/exam_timetable.html', {'exam': exam})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def admin_exam_responses(request, slug):
    if not _has_permission(request, 'exams', 'can_view'):
        messages.error(request, 'You do not have permission to view exam responses.')
        return redirect('management:admin_exam_list')

    exam = get_object_or_404(Exam, slug=slug)
    ATTEMPT_STATUS_CHOICES = StudentExamResponse.ATTEMPT_STATUS_CHOICES
    status_filter = request.GET.get('status', '')

    qs = exam.student_responses.select_related('student').order_by('-submitted_at', 'student__last_name')
    if status_filter:
        qs = qs.filter(status=status_filter)

    # Summary stats
    all_responses = exam.student_responses
    summary = {
        'total': all_responses.count(),
        'in_progress': all_responses.filter(status=StudentExamResponse.IN_PROGRESS).count(),
        'submitted': all_responses.filter(status=StudentExamResponse.SUBMITTED).count(),
        'graded': all_responses.filter(status=StudentExamResponse.GRADED).count(),
        'avg_score': all_responses.filter(score_percentage__isnull=False).aggregate(
            avg=Avg('score_percentage')
        )['avg'],
    }

    # Per-response correct/missed counts derived from question_scores JSON.
    # question_scores = {qid: {is_correct: bool|null, pending_manual: bool, ...}}
    # We compute per student: how many auto-graded correct, missed, and still pending.
    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    for r in page_obj:
        correct = missed = pending = 0
        for entry in (r.question_scores or {}).values():
            if entry.get('pending_manual'):
                pending += 1
            elif entry.get('is_correct') is True:
                correct += 1
            elif entry.get('is_correct') is False:
                missed += 1
        r.q_correct = correct
        r.q_missed  = missed
        r.q_pending = pending

    # Grading readiness — for the admin release banner
    all_submitted = all_responses.filter(
        status__in=[StudentExamResponse.SUBMITTED, StudentExamResponse.GRADED]
    )
    pending_any_manual = all_responses.filter(pending_manual_count__gt=0).exists()
    all_graded = (
        all_submitted.exists()
        and not all_responses.filter(status=StudentExamResponse.SUBMITTED).exists()
        and not pending_any_manual
    )

    return render(request, 'management/exam_responses.html', {
        'exam':                 exam,
        'page_obj':             page_obj,
        'summary':              summary,
        'status_filter':        status_filter,
        'ATTEMPT_STATUS_CHOICES': ATTEMPT_STATUS_CHOICES,
        'all_graded':           all_graded,
        'pending_any_manual':   pending_any_manual,
    })

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
@require_POST
@require_permission('exams', 'can_approve', redirect_to=lambda request, slug, **kw: redirect('management:admin_exam_responses', slug=slug))
def admin_exam_release_results(request, slug):
    """
    Toggle show_result_immediately on the Exam.
    ON  → results are visible to students on their dashboard/result page.
    OFF → results are hidden again (e.g. if a grading error is found).
    No new model field — reuses the existing BooleanField.
    """
    exam = get_object_or_404(Exam, slug=slug)
    action = request.POST.get('action', '')

    if action == 'release':
        exam.show_result_immediately = True
        exam.save(update_fields=['show_result_immediately'])
        # Notify instructor
        if exam.instructor:
            _notify(
                user=exam.instructor,
                title=f'Results Released: {exam.reference_code}',
                message=f'Results for "{exam.title}" are now visible to students.',
                notif_type='system',
            )
        messages.success(request, f'Results for {exam.reference_code} are now visible to students.')

    elif action == 'retract':
        exam.show_result_immediately = False
        exam.save(update_fields=['show_result_immediately'])
        messages.warning(request, f'Results for {exam.reference_code} have been hidden from students.')

    else:
        messages.error(request, 'Unknown action.')

    return redirect('management:admin_exam_responses', slug=slug)