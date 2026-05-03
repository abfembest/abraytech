# =============================================================================
# IMPORTS
# =============================================================================

# Standard library
import csv
import json
import threading
import uuid
from datetime import timedelta

# Django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, send_mail, send_mass_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Sum, Avg, F, Value, CharField, DecimalField
from django.db.models.functions import Coalesce, TruncMonth, Cast
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

# Models
from eduweb.models import (
    AcademicSession,
    AllRequiredPayments,
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
    CourseIntake,
    Department,
    Enrollment,
    Faculty,
    FeePayment,
    InstitutionMember,
    LMSCourse,
    LibraryItem,
    Notification,
    PaymentGateway,
    Program,
    Review,
    SiteConfig,
    SiteHistoryMilestone,
    StaffPayroll,
    StudentBadge,
    SupportTicket,
    SystemConfiguration,
    Testimonial,
    TicketReply,
    Invoice,
    Transaction,
    UserProfile,
    Message,
        Exam,
        ExamQuestion,
        StudentExamResponse,
        ExamStatusLog,
    )

# Forms
from management.forms import (
    AcademicSessionForm,
    AllRequiredPaymentsForm,
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
    EmailConfigForm,
    EnrollmentForm,
    FacultyForm,
    InstitutionMemberForm,
    LMSCourseForm,
    LibraryItemForm,
    NotificationConfigForm,
    PaymentGatewayForm,
    ProgramForm,
    QuickRoleChangeForm,
    ReviewForm,
    SiteConfigAboutForm,
    SiteConfigGeneralForm,
    SiteConfigIndexForm,
    SiteHistoryMilestoneForm,
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
from eduweb.emailservices import (
    send_certificate_ready_email,
    send_transcript_generated_email,
    send_overdue_payment_reminder_email,
    send_payroll_payment_notification_email,
    send_admin_created_user_email,
)


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


# ===========================================================================
# ADMIN INBOX / MESSAGING
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
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
def admin_compose_message(request):
    """
    Admin compose — send a new message to any user.
    Supports ?to=<user_id> query param to pre-fill recipient.
    """
    from .forms import AdminMessageComposeForm

    if request.method == 'POST':
        form = AdminMessageComposeForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.save()
            # In-app notification to recipient
            _notify(
                user=msg.recipient,
                title=f'New Message from {request.user.get_full_name() or request.user.username}',
                message=f'You have a new message: "{msg.subject}"',
                notif_type='message',
                link=f'/management/inbox/{msg.id}/',
            )
            try:
                from eduweb.emailservices import send_new_message_email
                send_new_message_email(msg.recipient, request.user, msg)
            except Exception:
                pass
            messages.success(request, 'Message sent successfully!')
            return redirect('management:admin_inbox')
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
        form = AdminMessageComposeForm(initial=initial)

    return render(request, 'management/compose_message.html', {
        'page_title': 'Compose Message',
        'form': form,
    })


@login_required(login_url='eduweb:auth_page')
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
            Message.objects.create(
                sender=request.user,
                recipient=reply_to,
                subject=f'Re: {msg.subject}',
                body=body,
                parent=msg,
            )
            _notify(
                user=reply_to,
                title=f'Reply from {request.user.get_full_name() or request.user.username}',
                message=f'New reply on: "{msg.subject}"',
                notif_type='message',
                link=f'/management/inbox/{msg.id}/',
            )
            try:
                from eduweb.emailservices import send_new_message_email
                send_new_message_email(reply_to, request.user, msg)
            except Exception:
                pass
            messages.success(request, 'Reply sent!')
            return redirect('management:admin_message_thread', message_id=message_id)
        messages.error(request, 'Reply must be at least 5 characters.')

    return render(request, 'management/message_thread.html', {
        'page_title': msg.subject,
        'message': msg,
        'thread_replies': thread_replies,
    })


@login_required(login_url='eduweb:auth_page')
def notifications_view(request):
    """
    Notifications page for admin and staff roles.
    Marks all as read if ?mark_all=1. Paginated at 15 per page.
    """
    if not request.user.is_authenticated:
        return redirect('eduweb:auth_page')

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
def mark_notification_read(request, notification_id):
    """Mark a single notification as read — AJAX GET."""
    notif = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    notif.mark_as_read()
    return JsonResponse({'success': True})


def is_admin(user):
    """Check if user is staff, superuser, or has admin role."""
    return (
        user.is_authenticated and (
            user.is_staff or
            user.is_superuser or
            (hasattr(user, 'profile') and user.profile.role == 'admin')
        )
    )


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
    
    # Prepare chart data for applications over time (last 7 days)
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)
    
    applications_by_day = []
    labels = []
    
    for i in range(7):
        date = week_ago + timedelta(days=i)
        count = CourseApplication.objects.filter(
            created_at__date=date
        ).count()
        applications_by_day.append(count)
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
    
    applications = CourseApplication.objects.select_related('user').order_by('-created_at')
    
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
    
    academic_sessions = AcademicSession.objects.filter(
        status__in=['active', 'upcoming']
    ).order_by('-name')

    context = {
        'application': application,
        'pending_count': pending_count,
        'academic_sessions': academic_sessions,
    }
    
    return render(request, 'management/application_detail.html', context)

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def make_decision(request, pk):
    """Make admission decision on an application"""
    
    if request.method == 'POST':
        application = get_object_or_404(CourseApplication, pk=pk)
        decision = request.POST.get('decision')
        decision_notes = request.POST.get('decision_notes', '')
        
        VALID_DECISIONS = ['approved', 'rejected']
        if decision not in VALID_DECISIONS:
            messages.error(request, 'Invalid decision. Choose Approved or Rejected.')
            return redirect('management:application_detail', application_id=application.application_id)

        # Update academic session and entry level if provided in decision form
        session_id = request.POST.get('academic_session')
        entry_level = request.POST.get('entry_level')
        if session_id:
            try:
                application.academic_session = AcademicSession.objects.get(id=session_id)
            except AcademicSession.DoesNotExist:
                pass
        if entry_level:
            try:
                application.entry_level = int(entry_level)
            except (ValueError, TypeError):
                pass

        # Update academic session and entry level if provided in decision form
        session_id = request.POST.get('academic_session')
        entry_level = request.POST.get('entry_level')
        if session_id:
            try:
                application.academic_session = AcademicSession.objects.get(id=session_id)
            except AcademicSession.DoesNotExist:
                pass
        if entry_level:
            try:
                application.entry_level = int(entry_level)
            except (ValueError, TypeError):
                pass

        # Update application status
        if decision == 'approved':
            application.status = 'approved'
        elif decision == 'rejected':
            application.status = 'rejected'

        application.review_notes = decision_notes
        application.reviewer = request.user
        application.reviewed_at = timezone.now()
        application.save()

        # On approval: sync program / dept / faculty / session / level to UserProfile
        if decision == 'approved' and application.user:
            try:
                profile = application.user.profile
                if application.program:
                    profile.program    = application.program
                    profile.department = application.program.department
                    profile.faculty    = application.program.department.faculty
                if application.academic_session:
                    profile.admission_session = application.academic_session
                if application.entry_level:
                    profile.year_of_study = application.entry_level // 100
                profile.save(update_fields=[
                    'program', 'department', 'faculty',
                    'admission_session', 'year_of_study',
                ])
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
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
    
    # Only issue transcripts for approved applications
    if application.status != 'approved':
        messages.error(request, 'Can only issue transcripts for approved applications.')
        return redirect('management:application_detail', application_id=application.application_id)
    
    # Check if transcript already issued
    if application.transcript_issued:
        messages.info(request, 'Transcript has already been issued for this application.')
        return redirect('management:application_detail', application_id=application.application_id)
    
    try:
        # Mark transcript as issued
        application.transcript_issued = True
        application.transcript_issued_at = timezone.now()
        application.transcript_issued_by = request.user
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
        import logging
        logger = logging.getLogger('melbac')
        logger.error(f'Failed to issue transcript for {application.application_id}: {str(e)}')
        messages.error(request, 'Failed to issue transcript. Please try again.')
    
    return redirect('management:application_detail', application_id=application.application_id)


def send_application_submission_email(application):
    """Send confirmation email when application is submitted"""
    try:
        subject = (
            f'Application Received - {application.application_id}'
        )
        
        program_name = (
            f"{application.course.name} "
            f"({application.course.get_degree_level_display()})"
        )
        
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
                            ✅ Application Submitted
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
                                Application Successfully Submitted!
                            </h3>
                            <p style="font-size: 16px;">
                                Your application for <strong>
                                    {program_name}
                                </strong> has been received.
                            </p>
                            <p>
                                <strong>Application ID:</strong> 
                                {application.application_id}
                            </p>
                            <p>
                                <strong>Submission Date:</strong> 
                                {timezone.now().strftime('%B %d, %Y')}
                            </p>
                        </div>
                        
                        <h4>What Happens Next?</h4>
                        <ol>
                            <li>
                                Our admissions team will review 
                                your application
                            </li>
                            <li>
                                You will receive an email with 
                                the decision within 5-7 business days
                            </li>
                            <li>
                                You can track your application status 
                                in your account
                            </li>
                        </ol>
                        
                        <p style="margin-top: 30px;">
                            Best regards,<br>
                            <strong style="color: #0F2A44;">
                                The MIU Admissions Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Application Submitted - {application.application_id}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
        
    except Exception as e:
        print(f"Error sending submission email: {str(e)}")
        return False

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
                        <p style="margin-top: 30px;">Best regards,<br><strong style="color: #0F2A44;">The MIU Admissions Team</strong></p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Application Decision for {application.application_id}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception as e:
        print(f"Error sending decision email: {str(e)}")
        return False
    


def _faculty_ctx(form=None, edit_pk=None):
    """Shared context for all faculty list views."""
    qs = Faculty.objects.prefetch_related('departments').order_by('display_order', 'name')
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
    return render(request, 'management/faculties_list.html', _faculty_ctx())
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def faculty_create(request):
    if request.method == 'POST':
        form = FacultyForm(request.POST, request.FILES)
        if form.is_valid():
            faculty = form.save()
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
        form = FacultyForm(request.POST, request.FILES, instance=faculty)
        if form.is_valid():
            faculty = form.save()
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
        name = faculty.name
        faculty.delete()
        messages.success(request, f'Faculty "{name}" deleted successfully!')
    return redirect('management:faculties_list')


# def courses(request):
#     """
#     Unified courses management page with tabs for programs and categories
#     """
    
#     # Get all programs with related data
#     programs = Program.objects.select_related(
#         'department',
#         'department__faculty'
#     ).order_by('display_order', 'name')
    
#     # Get all categories with course counts
#     categories = CourseCategory.objects.annotate(
#         course_count=Count('lms_courses')
#     ).order_by('display_order', 'name')
    
#     context = {
#         'courses': programs,  # Keep variable name as 'courses' for template compatibility
#         'categories': categories,
#     }
    
#     return render(request, 'management/course/courses.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def course_create(request):
    """Create a new course"""
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Course "{course.name}" created successfully!')
            return redirect('management:courses')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseForm()
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'pending_count': pending_count,
        'action': 'Create',
    }
    
    return render(request, 'management/course/course_form.html', context)

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def course_detail(request, pk):
    """
    Display detailed information about a specific course/program
    """
    course = get_object_or_404(
        Course.objects.select_related('faculty'),
        pk=pk
    )
    
    # Get statistics
    application_count = CourseApplication.objects.filter(
        course=course
    ).count()
    
    active_applications = CourseApplication.objects.filter(
        course=course,
        status__in=['payment_complete', 'documents_uploaded', 'under_review']
    ).count()
    
    accepted_applications = CourseApplication.objects.filter(
        course=course,
        status='accepted'
    ).count()
    
    # Get recent applications for this course
    recent_applications = CourseApplication.objects.filter(
        course=course
    ).select_related('user').order_by('-created_at')[:10]
    
    pending_count = CourseApplication.objects.filter(
        status__in=['payment_complete', 'documents_uploaded', 'under_review']
    ).count()
    
    context = {
        'course': course,
        'application_count': application_count,
        'active_applications': active_applications,
        'accepted_applications': accepted_applications,
        'recent_applications': recent_applications,
        'pending_count': pending_count,
    }
    
    return render(
        request, 
        'management/course/detail.html', 
        context
    )

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def course_edit(request, pk):
    """Edit an existing course"""
    course = get_object_or_404(Course, pk=pk)
    
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Course "{course.name}" updated successfully!')
            return redirect('management:courses')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseForm(instance=course)
    
    pending_count = CourseApplication.objects.filter(status__in=['payment_complete', 'documents_uploaded', 'under_review']).count()
    
    context = {
        'form': form,
        'course': course,
        'pending_count': pending_count,
        'action': 'Edit',
    }
    
    return render(request, 'management/course/course_form.html', context)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def course_delete(request, pk):
    """Delete a course"""
    course = get_object_or_404(Course, pk=pk)
    
    if request.method == 'POST':
        course_name = course.name
        course.delete()
        messages.success(request, f'Course "{course_name}" deleted successfully!')
        return redirect('management:courses')
    
    return redirect('management:courses')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_posts_list(request):
    """List all blog posts"""
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
        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
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
        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save()
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
        post_title = post.title
        post.delete()
        messages.success(request, f'Blog post "{post_title}" deleted successfully!')
        return redirect('management:blog_posts_list')
    
    return redirect('management:blog_posts_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def blog_categories_list(request):
    """List all blog categories"""
    categories = BlogCategory.objects.all().order_by('display_order', 'name')
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
        form = BlogCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
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
        form = BlogCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
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
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" deleted successfully!')
        return redirect('management:blog_categories_list')
    
    return redirect('management:blog_categories_list')

import secrets
import string
 
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
 
from eduweb.models import UserProfile
from management.forms import (
    QuickRoleChangeForm,
    UserCreateForm,
    UserEditForm,
    UserProfileForm,
    UserSearchForm,
)


def _is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)
 
 
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
 
 
def _apply_role_staff_rule(user_obj, role):
    """
    Enforce: only 'admin' role → is_staff=True. All others → False.
    Always call after saving role to UserProfile.
    """
    should_be_staff = (role == 'admin')
    if user_obj.is_staff != should_be_staff:
        user_obj.is_staff = should_be_staff
        user_obj.save(update_fields=['is_staff'])
 
 
# ---------------------------------------------------------------------------
# VIEW 1 — users_list  (GET: list + stats; POST bulk actions handled here)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_admin)
def users_list(request):
    """
    Main user management page.
    Serves the single unified template with all modals embedded.
    Handles bulk activate/deactivate via POST.
    """
    # ── Bulk action (POST from modal-less bulk bar) ──────────────────────────
    if request.method == 'POST':
        return _handle_bulk_action(request)
 
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
        'users':       users_page,
        'search_form': search_form,
        'stats':       stats,
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
@user_passes_test(_is_admin)
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

    raw_password = _generate_password()
    post_data = request.POST.copy()
    post_data['password1'] = raw_password
    post_data['password2'] = raw_password

    form = UserCreateForm(post_data)

    if not form.is_valid():
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    with transaction.atomic():
        user = form.save(commit=False)
        role = form.cleaned_data.get('role', 'student')

        # Role rule: only 'admin' → is_staff=True
        user.is_staff = (role == 'admin')

        # Set the password correctly so it is hashed in the database
        user.set_password(raw_password)

        # Account starts inactive — activated automatically after email verification
        user.is_active = False
        user.save()

        # Sync role onto the auto-created profile
        user.profile.role = role
        user.profile.email_verified = False
        user.profile.save(update_fields=['role', 'email_verified'])

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
@user_passes_test(_is_admin)
def user_edit(request, pk):
    """
    AJAX POST — updates User + UserProfile in one atomic transaction.
    Returns JSON { success, errors }.
    User deletion is not permitted.
    """
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)

    if request.method == 'GET':
        return redirect('management:users_list')

    # Deletion is disabled — reject any attempt explicitly
    if request.POST.get('action') == 'delete':
        return JsonResponse({'success': False, 'message': 'User deletion is not permitted.'}, status=403)

    # ── Edit action ──────────────────────────────────────────────────────────
    user_form    = UserEditForm(request.POST, instance=user)
    profile_form = UserProfileForm(request.POST, request.FILES, instance=user.profile)
 
    if not (user_form.is_valid() and profile_form.is_valid()):
        errors = {**user_form.errors, **profile_form.errors}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        messages.error(request, 'Please fix the errors below.')
        return redirect('management:users_list')
 
    with transaction.atomic():
        updated_user    = user_form.save(commit=False)
        updated_profile = profile_form.save(commit=False)
 
        role = updated_profile.role
 
        # Role rule: admin → staff, others → not staff
        updated_user.is_staff = (role == 'admin')
        updated_user.save()
        updated_profile.save()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f'User {user.username} updated.'})
 
    messages.success(request, f'User {user.username} updated successfully.')
    return redirect('management:users_list')
 
 
# ---------------------------------------------------------------------------
# UNCHANGED small endpoints (kept as-is; included for completeness)
# ---------------------------------------------------------------------------
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_admin)
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
 
    if user.id == request.user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Cannot deactivate your own account.'}, status=400)
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('management:users_list')
 
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'is_active': user.is_active})
 
    messages.success(request, f'User {user.username} {"activated" if user.is_active else "deactivated"}.')
    return redirect('management:users_list')
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_admin)
@require_POST
def user_change_role(request, pk):
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    form = QuickRoleChangeForm(request.POST)
 
    if form.is_valid():
        role = form.cleaned_data['role']
        user.profile.role = role
        user.profile.save(update_fields=['role'])
        _apply_role_staff_rule(user, role)
 
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'role': user.profile.role,
                'role_display': user.profile.get_role_display(),
            })
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
 
    return redirect('management:users_list')
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_admin)
def user_quick_info(request, pk):
    """AJAX GET — returns JSON snapshot for view/edit modals."""
    user = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    profile = user.profile
 
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
        # Extended profile fields
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
    })
 
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_admin)
@require_POST
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
@user_passes_test(is_admin)
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
@user_passes_test(is_admin)
def system_config_create(request):
    """Create new system configuration"""
    if request.method == 'POST':
        form = SystemConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='create',
                model_name='SystemConfiguration',
                object_id=config.id,
                description=f'Created configuration: {config.key}'
            )
            
            messages.success(request, f'Configuration "{config.key}" created successfully.')
            return redirect('management:system_config_list')
    else:
        form = SystemConfigurationForm()
    
    return render(request, 'management/system_config/create.html', {'form': form})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def system_config_edit(request, pk):
    """Edit system configuration"""
    config = get_object_or_404(SystemConfiguration, pk=pk)
    
    if request.method == 'POST':
        form = SystemConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='SystemConfiguration',
                object_id=config.id,
                description=f'Updated configuration: {config.key}'
            )
            
            messages.success(request, f'Configuration "{config.key}" updated successfully.')
            return redirect('management:system_config_list')
    else:
        form = SystemConfigurationForm(instance=config)
    
    return render(request, 'management/system_config/edit.html', {
        'form': form,
        'config': config
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def system_config_delete(request, pk):
    """Delete system configuration"""
    config = get_object_or_404(SystemConfiguration, pk=pk)
    
    if request.method == 'POST':
        config_key = config.key
        
        # Create audit log before deletion
        AuditLog.objects.create(
            user=request.user,
            action='delete',
            model_name='SystemConfiguration',
            object_id=config.id,
            description=f'Deleted configuration: {config_key}'
        )
        
        config.delete()
        messages.success(request, f'Configuration "{config_key}" deleted successfully.')
        return redirect('management:system_config_list')
    
    return render(request, 'management/system_config/delete.html', {'config': config})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def branding_config(request):
    """Manage branding configuration"""
    if request.method == 'POST':
        form = BrandingConfigForm(request.POST, request.FILES)
        if form.is_valid():
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
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='SystemConfiguration',
                description='Updated branding configuration'
            )
            
            messages.success(request, 'Branding settings updated successfully.')
            return redirect('management:branding_config')
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


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def email_config(request):
    """Manage email configuration"""
    if request.method == 'POST':
        form = EmailConfigForm(request.POST)
        if form.is_valid():
            # Save email configuration
            for key, value in form.cleaned_data.items():
                config, created = SystemConfiguration.objects.get_or_create(
                    key=f'email_{key}',
                    defaults={
                        'setting_type': 'text',
                        'is_public': False,
                        'updated_by': request.user
                    }
                )
                config.value = str(value)
                config.updated_by = request.user
                config.save()
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='SystemConfiguration',
                description='Updated email configuration'
            )
            
            messages.success(request, 'Email settings updated successfully.')
            return redirect('management:email_config')
    else:
        # Load existing values
        initial_data = {}
        for key in ['smtp_host', 'smtp_port', 'smtp_username', 'from_email', 'from_name']:
            try:
                config = SystemConfiguration.objects.get(key=f'email_{key}')
                initial_data[key] = config.value
            except SystemConfiguration.DoesNotExist:
                pass
        
        form = EmailConfigForm(initial=initial_data)
    
    return render(request, 'management/system_config/email.html', {'form': form})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def notification_config(request):
    """Manage notification settings"""
    if request.method == 'POST':
        form = NotificationConfigForm(request.POST)
        if form.is_valid():
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
            
            # Create audit log
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='SystemConfiguration',
                description='Updated notification configuration'
            )
            
            messages.success(request, 'Notification settings updated successfully.')
            return redirect('management:notification_config')
    else:
        # Load existing values
        initial_data = {}
        form = NotificationConfigForm(initial=initial_data)
    
    return render(request, 'management/system_config/notifications.html', {'form': form})


# @login_required(login_url='eduweb:auth_page')
# @user_passes_test(is_admin)
# def course_categories_list(request):
#     """List all course categories"""
#     # Add course counts to categories
#     categories = CourseCategory.objects.annotate(
#         course_count=Count('lms_courses')
#     ).order_by('display_order', 'name')
    
#     # Search functionality
#     search_query = request.GET.get('search', '')
#     if search_query:
#         categories = categories.filter(
#             Q(name__icontains=search_query) | 
#             Q(description__icontains=search_query)
#         )
    
#     # Status filter
#     status = request.GET.get('status', '')
#     if status == 'active':
#         categories = categories.filter(is_active=True)
#     elif status == 'inactive':
#         categories = categories.filter(is_active=False)
    
#     # Pagination
#     paginator = Paginator(categories, 15)
#     page = request.GET.get('page', 1)
#     categories_page = paginator.get_page(page)
    
#     context = {
#         'categories': categories_page,
#         'search_query': search_query,
#         'status': status,
#         'total_categories': categories.count()
#     }
#     return render(request, 'management/course/list.html', context)


# @login_required(login_url='eduweb:auth_page')
# @user_passes_test(is_admin)
# def course_category_create(request):
#     """Create new course category"""
#     if request.method == 'POST':
#         form = CourseCategoryForm(request.POST)
#         if form.is_valid():
#             category = form.save()
            
#             # Create audit log
#             AuditLog.objects.create(
#                 user=request.user,
#                 action='create',
#                 model_name='CourseCategory',
#                 object_id=category.id,
#                 description=f'Created course category: {category.name}'
#             )
            
#             messages.success(request, f'Category "{category.name}" created successfully.')
#             return redirect('management:course_categories_list')
#     else:
#         form = CourseCategoryForm()
    
#     return render(request, 'management/course/create.html', {'form': form})


# @login_required(login_url='eduweb:auth_page')
# @user_passes_test(is_admin)
# def course_category_edit(request, pk):
#     """Edit course category"""
#     category = get_object_or_404(CourseCategory, pk=pk)
    
#     if request.method == 'POST':
#         form = CourseCategoryForm(request.POST, instance=category)
#         if form.is_valid():
#             category = form.save()
            
#             # Create audit log
#             AuditLog.objects.create(
#                 user=request.user,
#                 action='update',
#                 model_name='CourseCategory',
#                 object_id=category.id,
#                 description=f'Updated course category: {category.name}'
#             )
            
#             messages.success(request, f'Category "{category.name}" updated successfully.')
#             return redirect('management:course_categories_list')
#     else:
#         form = CourseCategoryForm(instance=category)
    
#     return render(request, 'management/course/edit.html', {
#         'form': form,
#         'category': category
#     })


# @login_required(login_url='eduweb:auth_page')
# @user_passes_test(is_admin)
# def course_category_delete(request, pk):
#     """Delete course category"""
#     category = get_object_or_404(CourseCategory, pk=pk)
    
#     # Check if category has courses
#     course_count = category.lmscourse_set.count()
    
#     if request.method == 'POST':
#         category_name = category.name
        
#         # Create audit log before deletion
#         AuditLog.objects.create(
#             user=request.user,
#             action='delete',
#             model_name='CourseCategory',
#             object_id=category.id,
#             description=f'Deleted course category: {category_name}'
#         )
        
#         category.delete()
#         messages.success(request, f'Category "{category_name}" deleted successfully.')
#         return redirect('management:course_categories_list')
    
#     return render(request, 'management/course/delete.html', {
#         'category': category,
#         'course_count': course_count
#     })


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
    # ── Base queryset ─────────────────────────────────────────────────────────
    courses = (
        LMSCourse.objects
        .select_related('instructor', 'academic_course__program__department', 'session')
        .prefetch_related('enrollments')
        .annotate(lesson_count=Count('lessons', distinct=True))
        .order_by('-created_at')
    )
 
    # ── Filters ───────────────────────────────────────────────────────────────
    program_id = request.GET.get('program', '').strip()
    if program_id.isdigit():
        courses = courses.filter(academic_course__program_id=program_id)
 
    session_id = request.GET.get('session', '').strip()
    if session_id.isdigit():
        courses = courses.filter(session_id=session_id)
 
    term_filter = request.GET.get('term', '').strip()
    if term_filter:
        courses = courses.filter(term=term_filter)
 
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
        'sessions':     AcademicSession.objects.only('id', 'name').order_by('-name'),
        'term_choices': LMSCourse._meta.get_field('term').choices,
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
def lms_academic_course_data(request, pk):
    """
    AJAX — returns session, term, level for a given academic Course pk.
    Used by the create modal to auto-fill fields when academic_course changes.
    NOT called on edit (edit shows saved values only).
    """
    try:
        course = Course.objects.select_related('program').get(pk=pk, is_active=True)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
 
    active_session = AcademicSession.objects.filter(is_current=True).first()
    return JsonResponse({
        'session_id':   active_session.pk   if active_session else None,
        'session_name': str(active_session) if active_session else '',
        'term':         course.semester,
        'level':        course.year_of_study * 100,
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
    mode      = request.POST.get('_mode', 'create')
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
        else:
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
            messages.success(request, f'LMS course "{course.title}" created successfully.')
        else:
            messages.error(request, 'Please correct the errors in the form.')
 
    return redirect('management:lms_courses_list')
 
 
# ─────────────────────────────────────────────────────────────────────────────
# VIEW 3 — DETAIL  (JSON for modals, full-page fallback)
# ─────────────────────────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def lms_course_detail(request, pk):
    """
    GET ?_modal=1 or XHR → JsonResponse (used by both detail AND edit modals).
    GET (normal)          → redirect to list (no standalone detail page needed).
 
    Extra fields returned for the edit modal:
        session_id, term_value, difficulty_level_value, instructor_id, thumbnail_url
    """
    course = get_object_or_404(
        LMSCourse.objects.select_related(
            'instructor', 'academic_course__program__department', 'session',
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
 
            # ── Classification
            'difficulty_level_display': course.get_difficulty_level_display(),
            'difficulty_level_value':   course.difficulty_level or '',
 
            # ── Session & term (display values for detail modal)
            'session': course.session.name if course.session else '',
            'term':    course.get_term_display() if course.term else '',
 
            # ── Session & term (raw values for edit modal selects)
            'session_id':  course.session_id or '',
            'term_value':  course.term or '',
 
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
        messages.success(request, f'LMS course "{course_title}" deleted successfully.')
 
    return redirect('management:lms_courses_list')


# ==================== AUDIT LOG VIEWS ====================
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def audit_logs_list(request):
    """List all audit logs with filtering"""
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
    
    return response


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def security_dashboard(request):
    """Security overview dashboard"""
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
def broadcast_create(request):
    """Create new broadcast"""
    if request.method == 'POST':
        form = BroadcastMessageForm(request.POST)
        if form.is_valid():
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
def broadcast_edit(request, slug):
    """Edit draft broadcast"""
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
def broadcast_send(request, slug):
    """Send broadcast email - POST only"""
    broadcast = get_object_or_404(BroadcastMessage, slug=slug)
    
    if broadcast.status == 'sent':
        messages.warning(request, 'This broadcast has already been sent.')
        return redirect('management:broadcast_center')
    
    if request.method == 'POST':
        
        def send_emails_background():
            """Background thread to send emails"""
            try:
                # Send emails in smaller batches for better performance
                batch_size = 50
                email_list = broadcast.recipient_emails
                
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
                    send_mass_mail(email_messages, fail_silently=False)
                
                # Update status after all sent
                broadcast.status = 'sent'
                broadcast.sent_at = timezone.now()
                broadcast.save()
                
            except Exception as e:
                broadcast.status = 'failed'
                broadcast.error_message = str(e)
                broadcast.save()
        
        # Start background thread
        thread = threading.Thread(target=send_emails_background)
        thread.daemon = True
        thread.start()
        
        # Immediate response to user
        messages.success(
            request, 
            f'Sending broadcast to {broadcast.recipient_count} recipients...'
        )
    
    return redirect('management:broadcast_center')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser or u.profile.role == 'admin')
def broadcast_delete(request, slug):
    """Delete broadcast - POST only"""
    broadcast = get_object_or_404(BroadcastMessage, slug=slug)
    
    if request.method == 'POST':
        broadcast.delete()
        messages.success(request, 'Broadcast deleted successfully.')
    
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
        
        application.department_approved = True
        application.department_approved_at = timezone.now()
        application.department_approved_by = request.user
        application.save()
        
        # Send notification to student
        send_department_approval_email(application)
        
        messages.success(
            request,
            f'Department approval granted for {application.admission_number}'
        )
        if application.user:
            _notify(
                user=application.user,
                title='Department Approval Granted',
                message=f'Your admission ({application.admission_number}) has received department approval. You now have full portal access.',
                notif_type='enrollment',
                link='/dashboard/',
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
                            🎉 Welcome to MIU Student Portal!
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
                            Welcome to MIU!<br>
                            <strong style="color: #0F2A44;">
                                The MIU Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Portal Access Granted - {application.admission_number}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
        
    except Exception as e:
        print(f"Error sending approval email: {str(e)}")
        return False


    Department, Program, AcademicSession, CourseIntake,
    CourseCategory, SupportTicket, TicketReply,
    ContactMessage, Announcement, Faculty


# ── Helper: restrict to admin/staff ─────────────────────────────────────────


# ===========================================================================
# DEPARTMENTS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def departments_list(request):
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
    }
    return render(request, 'management/departments_list.html', context)


@login_required
@user_passes_test(is_admin)
def department_create(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department created successfully.')
            return redirect('management:departments_list')
    else:
        form = DepartmentForm()
    return render(request, 'management/department_form.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department updated.')
            return redirect('management:departments_list')
    else:
        form = DepartmentForm(instance=dept)
    return render(request, 'management/department_form.html', {'form': form, 'department': dept})


@login_required
@user_passes_test(is_admin)
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        dept_name = dept.name
        dept.delete()
        messages.success(request, f'Department "{dept_name}" deleted successfully.')
        return redirect('management:departments_list')
    
    return render(request, 'management/department_delete.html', {'department': dept})


# ===========================================================================
# PROGRAMS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def programs_list(request):
    qs = Program.objects.select_related('department__faculty').order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))

    faculty_id = request.GET.get('faculty', '')
    if faculty_id:
        qs = qs.filter(department__faculty_id=faculty_id)

    degree_level = request.GET.get('degree_level', '')
    if degree_level:
        qs = qs.filter(degree_level=degree_level)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'programs': page_obj,
        'faculties': Faculty.objects.all(),
        'stats': [
            {'label': 'Total Programs', 'value': Program.objects.count(), 'color': 'text-primary-600'},
            {'label': 'Active', 'value': Program.objects.filter(is_active=True).count(), 'color': 'text-green-600'},
            {'label': 'Featured', 'value': Program.objects.filter(is_featured=True).count(), 'color': 'text-yellow-600'},
            {'label': 'Departments', 'value': Department.objects.count(), 'color': 'text-blue-600'},
        ],
    }
    return render(request, 'management/programs_list.html', context)


@login_required
@user_passes_test(is_admin)
def program_create(request):
    if request.method == 'POST':
        form = ProgramForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Program created.')
            return redirect('management:programs_list')
    else:
        form = ProgramForm()
    return render(request, 'management/program_form.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def program_edit(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == 'POST':
        form = ProgramForm(request.POST, request.FILES, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, 'Program updated.')
            return redirect('management:programs_list')
    else:
        form = ProgramForm(instance=program)
    return render(request, 'management/program_form.html', {'form': form, 'program': program})


@login_required
@user_passes_test(is_admin)
def program_detail(request, pk):
    program = get_object_or_404(Program.objects.select_related('department__faculty'), pk=pk)
    intakes = program.intakes.all()
    applications = program.applications.all()[:10]
    context = {'program': program, 'intakes': intakes, 'applications': applications}
    return render(request, 'management/program_detail.html', context)


@login_required
@user_passes_test(is_admin)
def program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == 'POST':
        program_name = program.name
        program.delete()
        messages.success(request, f'Program "{program_name}" deleted successfully.')
        return redirect('management:programs_list')
    
    return render(request, 'management/program_delete.html', {'program': program})


# ===========================================================================
# ACADEMIC SESSIONS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def academic_sessions_list(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            form = AcademicSessionForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Academic session created successfully.')
            else:
                messages.error(request, 'Error creating session. Check form data.')
                
        elif action == 'edit':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AcademicSession, pk=session_id)
            form = AcademicSessionForm(request.POST, instance=session)
            if form.is_valid():
                form.save()
                messages.success(request, 'Academic session updated.')
            else:
                messages.error(request, 'Error updating session.')
        
        return redirect('management:academic_sessions_list')

    # GET logic
    sessions = AcademicSession.objects.all().order_by('-name')
    current_session = AcademicSession.get_current()
    form = AcademicSessionForm() # Empty form for the Modal
    
    return render(request, 'management/academic_sessions_list.html', {
        'sessions': sessions,
        'current_session': current_session,
        'form': form,
    })

@login_required
@user_passes_test(is_admin)
@require_POST
def academic_session_set_current(request, pk):
    from django.utils import timezone
    session = get_object_or_404(AcademicSession, pk=pk)

    today = timezone.now().date()

    # Set this session as current + active
    session.is_current = True
    session.status = 'active'
    session.save()  # AcademicSession.save() already flips is_current=False on all others

    # Now update statuses on the remaining sessions based on their dates
    other_sessions = AcademicSession.objects.exclude(pk=pk)
    for s in other_sessions:
        term_dates = s.term_dates or []
        if not term_dates:
            # No dates configured — leave as-is or mark closed
            if s.status == 'active':
                s.status = 'closed'
                s.save(update_fields=['status'])
            continue

        # Determine earliest start and latest end across all terms
        try:
            starts = [__import__('datetime').date.fromisoformat(t['start']) for t in term_dates if t.get('start')]
            ends   = [__import__('datetime').date.fromisoformat(t['end'])   for t in term_dates if t.get('end')]
        except (ValueError, KeyError):
            continue

        if not starts or not ends:
            continue

        session_start = min(starts)
        session_end   = max(ends)

        if today < session_start:
            new_status = 'upcoming'
        elif today > session_end:
            new_status = 'closed'
        else:
            new_status = 'closed'  # It's in range but we just made another session current

        if s.status != new_status:
            s.status = new_status
            s.save(update_fields=['status'])

    messages.success(request, f'✓ {session.name} is now the current active session.')
    return redirect('management:academic_sessions_list')

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def courses_list(request):
    if request.method == 'POST':
        action = request.POST.get('action')
 
        # ── CREATE ──────────────────────────────────────────────────────────
        if action == 'create':
            form = CourseForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Course created successfully.')
            else:
                # Surface first field error so the user knows what went wrong
                for field, errs in form.errors.items():
                    messages.error(request, f'{field.replace("_"," ").title()}: {errs[0]}')
 
        # ── EDIT ────────────────────────────────────────────────────────────
        elif action == 'edit':
            course_id = request.POST.get('course_id')
            course    = get_object_or_404(Course, pk=course_id)
            form      = CourseForm(request.POST, instance=course)
            if form.is_valid():
                form.save()
                messages.success(request, f'Course "{course.code}" updated successfully.')
            else:
                for field, errs in form.errors.items():
                    messages.error(request, f'{field.replace("_"," ").title()}: {errs[0]}')
 
        # ── DELETE ──────────────────────────────────────────────────────────
        elif action == 'delete':
            course_id = request.POST.get('course_id')
            course    = get_object_or_404(Course, pk=course_id)
            code      = course.code
            course.delete()
            messages.success(request, f'Course "{code}" deleted successfully.')
 
        return redirect('management:courses_list')
 
    # ── GET ─────────────────────────────────────────────────────────────────
    courses = (
        Course.objects
        .select_related('program__department__faculty')
        .order_by('year_of_study', 'semester', 'code')
    )
    form = CourseForm()
 
    return render(request, 'management/courses_list.html', {
        'courses':     courses,
        'departments': Department.objects.all().order_by('name'),
        'form':        form,
    })


# ===========================================================================
# COURSE INTAKES
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def intakes_list(request):
    qs = CourseIntake.objects.select_related('program__department__faculty').prefetch_related('applications')

    program_id = request.GET.get('program', '')
    if program_id:
        qs = qs.filter(program_id=program_id)

    year = request.GET.get('year', '')
    if year:
        qs = qs.filter(year=year)

    period = request.GET.get('period', '')
    if period:
        qs = qs.filter(intake_period=period)

    status = request.GET.get('status', '')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    
    # Order before pagination
    qs = qs.order_by('-year', 'intake_period')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    years = CourseIntake.objects.values_list('year', flat=True).distinct().order_by('-year')

    context = {
        'intakes': page_obj,
        'programs': Program.objects.filter(is_active=True).order_by('name'),
        'years': years,
        'today': timezone.now().date(),
    }
    return render(request, 'management/intakes_list.html', context)


@login_required
@user_passes_test(is_admin)
def intake_create(request):
    """AJAX-only: create a new intake, redirect back to list."""
    if request.method == 'POST':
        form = CourseIntakeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Intake created.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    return redirect('management:intakes_list')


@login_required
@user_passes_test(is_admin)
def intake_edit(request, pk):
    """AJAX GET returns JSON for the modal; POST saves changes."""
    intake = get_object_or_404(CourseIntake, pk=pk)
    if request.method == 'POST':
        form = CourseIntakeForm(request.POST, instance=intake)
        if form.is_valid():
            form.save()
            messages.success(request, 'Intake updated.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
        return redirect('management:intakes_list')

    # GET — return JSON so the modal can pre-fill fields
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'id': intake.pk,
            'program': intake.program_id,
            'intake_period': intake.intake_period,
            'year': intake.year,
            'start_date': str(intake.start_date),
            'application_deadline': str(intake.application_deadline),
            'available_slots': intake.available_slots,
            'is_active': intake.is_active,
        })
    return redirect('management:intakes_list')


@login_required
@user_passes_test(is_admin)
def intake_delete(request, pk):
    """POST-only delete; all confirmations happen client-side."""
    intake = get_object_or_404(CourseIntake, pk=pk)
    if request.method == 'POST':
        intake_name = str(intake)
        intake.delete()
        messages.success(request, f'Intake "{intake_name}" deleted.')
    return redirect('management:intakes_list')


# ===========================================================================
# COURSE CATEGORIES LIST (the missing page)
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def course_categories_list(request):
    categories = CourseCategory.objects.prefetch_related(
        'lms_courses', 'subcategories'
    ).select_related('parent').order_by('display_order', 'name')
    return render(request, 'management/course_categories_list.html', {'categories': categories})


# ===========================================================================
# SUPPORT TICKETS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def tickets_list(request):
    qs = SupportTicket.objects.select_related('user', 'assigned_to').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(ticket_id__icontains=search) |
            Q(subject__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    priority = request.GET.get('priority', '')
    if priority:
        qs = qs.filter(priority=priority)

    stats = {
        'total': SupportTicket.objects.count(),
        'open': SupportTicket.objects.filter(status='open').count(),
        'in_progress': SupportTicket.objects.filter(status='in_progress').count(),
        'resolved': SupportTicket.objects.filter(status='resolved').count(),
        'urgent': SupportTicket.objects.filter(priority='urgent', status__in=['open', 'in_progress']).count(),
    }

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/tickets_list.html', {'tickets': page_obj, 'stats': stats})


@login_required
@user_passes_test(is_admin)
def ticket_detail(request, pk):
    ticket = get_object_or_404(SupportTicket.objects.select_related('user', 'assigned_to'), pk=pk)
    replies = ticket.replies.select_related('author').order_by('created_at')
    staff_users = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).distinct()
    return render(request, 'management/ticket_detail.html', {
        'ticket': ticket,
        'replies': replies,
        'staff_users': staff_users,
    })


@login_required
@user_passes_test(is_admin)
def ticket_reply(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        is_internal = request.POST.get('is_internal_note') == 'on'
        if message:
            TicketReply.objects.create(
                ticket=ticket,
                author=request.user,
                message=message,
                is_internal_note=is_internal,
            )
            # Auto-set to in_progress if open
            if ticket.status == 'open':
                ticket.status = 'in_progress'
                ticket.save(update_fields=['status'])
            messages.success(request, 'Reply posted.')
            # Notify ticket owner if the reply is not an internal note
            if not is_internal and ticket.submitted_by != request.user:
                _notify(
                    user=ticket.submitted_by,
                    title='Support Ticket Reply',
                    message=f'Your support ticket "{ticket.subject}" has received a reply.',
                    notif_type='system',
                    link='/support/',
                )
    return redirect('management:ticket_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
def ticket_change_status(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(SupportTicket, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(SupportTicket.STATUS_CHOICES):
            ticket.status = new_status
            ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
            messages.success(request, f'Status changed to {ticket.get_status_display()}.')
            # Notify the ticket submitter about the status change
            if ticket.submitted_by:
                _notify(
                    user=ticket.submitted_by,
                    title=f'Support Ticket Status Updated',
                    message=f'Your support ticket "{ticket.subject}" status has been changed to "{ticket.get_status_display()}".',
                    notif_type='system',
                    link='/support/',
                )
    return redirect('management:ticket_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
def ticket_assign(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(SupportTicket, pk=pk)
        assigned_to_id = request.POST.get('assigned_to')
        if assigned_to_id:
            ticket.assigned_to = get_object_or_404(User, pk=assigned_to_id)
            ticket.save(update_fields=['assigned_to'])
            messages.success(request, 'Ticket assigned.')
            # Notify the staff member they have been assigned this ticket
            if ticket.assigned_to != request.user:
                _notify(
                    user=ticket.assigned_to,
                    title='Support Ticket Assigned to You',
                    message=f'You have been assigned support ticket "{ticket.subject}". Please review and respond.',
                    notif_type='system',
                    link=f'/management/tickets/{ticket.pk}/',
                )
        else:
            ticket.assigned_to = None
            ticket.save(update_fields=['assigned_to'])
            messages.success(request, 'Ticket unassigned.')
    return redirect('management:ticket_detail', pk=pk)


# ===========================================================================
# CONTACT MESSAGES
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def contact_messages_list(request):
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
        msg.is_read = True
        msg.save(update_fields=['is_read'])
        messages.success(request, 'Marked as read.')
    return redirect('management:contact_message_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
def contact_message_respond(request, pk):
    if request.method == 'POST':
        msg = get_object_or_404(ContactMessage, pk=pk)
        response_text = request.POST.get('response', '').strip()
        if response_text:
            try:
                send_mail(
                    subject=f'Re: {msg.get_subject_display()} — MIU',
                    message=response_text,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[msg.email],
                    fail_silently=False,
                )
            except Exception:
                pass  # Log in production
            msg.responded = True
            msg.responded_at = timezone.now()
            msg.responded_by = request.user
            msg.is_read = True
            msg.save(update_fields=['responded', 'responded_at', 'responded_by', 'is_read'])
            messages.success(request, f'Response sent to {msg.email}.')
        else:
            messages.error(request, 'Response cannot be empty.')
    return redirect('management:contact_message_detail', pk=pk)


# ===========================================================================
# ANNOUNCEMENTS
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def announcements_list(request):
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
def announcement_create(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.created_by = request.user
            ann.save()
            messages.success(request, 'Announcement created.')
            # Notify users based on announcement type
            if ann.announcement_type == 'system':
                # Notify all active users
                recipients = User.objects.filter(is_active=True).exclude(id=request.user.id)
                for u in recipients:
                    _notify(
                        user=u,
                        title=f'Announcement: {ann.title}',
                        message=ann.content[:200],
                        notif_type='announcement',
                        link='/',
                    )
            elif ann.announcement_type == 'course' and ann.course:
                # Notify only students enrolled in this specific course
                enrolled_users = User.objects.filter(
                    enrollments__course=ann.course,
                    enrollments__status='active',
                    is_active=True,
                ).exclude(id=request.user.id).distinct()
                for u in enrolled_users:
                    _notify(
                        user=u,
                        title=f'Course Announcement: {ann.title}',
                        message=ann.content[:200],
                        notif_type='announcement',
                        link=f'/courses/{ann.course.slug}/',
                    )
            elif ann.announcement_type == 'category' and ann.category:
                # Notify students enrolled in any course under this category
                enrolled_users = User.objects.filter(
                    enrollments__course__category=ann.category,
                    enrollments__status='active',
                    is_active=True,
                ).exclude(id=request.user.id).distinct()
                for u in enrolled_users:
                    _notify(
                        user=u,
                        title=f'Announcement: {ann.title}',
                        message=ann.content[:200],
                        notif_type='announcement',
                        link='/',
                    )
            return redirect('management:announcements_list')
    else:
        form = AnnouncementForm()
    return render(request, 'management/announcement_form.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def announcement_edit(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
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
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        announcement.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('management:announcements_list')


# ===========================================================================
# ENROLLMENTS MANAGEMENT
# ===========================================================================

@login_required
@user_passes_test(is_admin)
def enrollments_list(request):
    """List all student enrollments"""
    
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
def enrollment_create(request):
    """Create new enrollment"""
    
    if request.method == 'POST':
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            enrollment = form.save()
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
def enrollment_edit(request, pk):
    """Edit enrollment"""

    enrollment = get_object_or_404(Enrollment, pk=pk)
    if request.method == 'POST':
        old_status = enrollment.status
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            updated = form.save()
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
        _notify(
            user=enrollment.student,
            title=f'Enrollment Removed — {enrollment.course.title}',
            message=f'Your enrollment in "{enrollment.course.title}" has been removed by the administration. Please contact support if you believe this is an error.',
            notif_type='enrollment',
            link='/dashboard/',
        )
        enrollment.delete()
        messages.success(request, 'Enrollment deleted.')
    return redirect('management:enrollments_list')

# ===========================================================================
# CERTIFICATES MANAGEMENT
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def certificates_list(request):
    """List all certificates with search + pagination."""
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
def certificate_create(request):
    """Issue a new certificate (POST only from the combined page)."""
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES)
        if form.is_valid():
            certificate = form.save()
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
def certificate_edit(request, certificate_id):
    """Update an existing certificate (POST only from the combined page)."""
    certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
    if request.method == 'POST':
        form = CertificateForm(request.POST, request.FILES, instance=certificate)
        if form.is_valid():
            form.save()
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
        certificate.delete()
        messages.success(request, 'Certificate deleted.')
    return redirect('management:certificates_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def reviews_list(request):

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
def review_create(request):

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            form.save()
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
def review_edit(request, pk):

    review = get_object_or_404(Review, pk=pk)
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
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
        review.delete()
        messages.success(request, 'Review deleted.')
    return redirect('management:reviews_list')


# ===========================================================================
# BADGES MANAGEMENT  —  no changes needed; included for completeness
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def badges_list(request):

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
def badge_create(request):

    if request.method == 'POST':
        form = BadgeForm(request.POST)
        if form.is_valid():
            form.save()
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
def badge_edit(request, slug):

    badge = get_object_or_404(Badge, slug=slug)
    if request.method == 'POST':
        form = BadgeForm(request.POST, instance=badge)
        if form.is_valid():
            form.save()
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
        badge.delete()
        messages.success(request, 'Badge deleted.')
    return redirect('management:badges_list')


# ===========================================================================
# STUDENT BADGES (ASSIGNMENT)
# ===========================================================================

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def student_badges_list(request):

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
def student_badge_assign(request):

    if request.method == 'POST':
        form = StudentBadgeForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.awarded_by = request.user
            assignment.save()
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
        student_badge.delete()
        messages.success(request, 'Badge revoked.')
    return redirect('management:student_badges_list')

# ---------------------------------------------------------------------------
# PAYMENT GATEWAYS
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def payment_gateways_list(request):

    gateways = PaymentGateway.objects.order_by('name')
    form     = PaymentGatewayForm()
    return render(request, 'management/payment_gateways.html', {
        'gateways': gateways,
        'form':     form,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def payment_gateway_create(request):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    form = PaymentGatewayForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, 'Gateway added.')
    else:
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:payment_gateways_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def payment_gateway_edit(request, slug):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    gateway = get_object_or_404(PaymentGateway, slug=slug)
    form    = PaymentGatewayForm(request.POST, instance=gateway)
    if form.is_valid():
        # Preserve existing secrets when fields left blank
        gw = form.save(commit=False)
        if not request.POST.get('api_key'):
            gw.api_key = gateway.api_key
        if not request.POST.get('api_secret'):
            gw.api_secret = gateway.api_secret
        if not request.POST.get('webhook_secret'):
            gw.webhook_secret = gateway.webhook_secret
        gw.save()
        messages.success(request, 'Gateway updated.')
    else:
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:payment_gateways_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def payment_gateway_delete(request, slug):

    if request.method != 'POST':
        return redirect('management:payment_gateways_list')

    gateway = get_object_or_404(PaymentGateway, slug=slug)
    gateway.delete()
    messages.success(request, 'Gateway deleted.')
    return redirect('management:payment_gateways_list')


# ---------------------------------------------------------------------------
# TRANSACTIONS  (read-only list + detail; no create/edit/delete)
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def transactions_list(request):

    qs = Transaction.objects.select_related('user', 'gateway').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search)  |
            Q(user__last_name__icontains=search)   |
            Q(user__username__icontains=search)    |
            Q(transaction_id__icontains=search)
        )

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    # Summary counts on the full table (not the filtered qs)
    all_txns = Transaction.objects
    summary = {
        'total':     all_txns.count(),
        'completed': all_txns.filter(status='completed').count(),
        'pending':   all_txns.filter(status='pending').count(),
        'failed':    all_txns.filter(status='failed').count(),
    }

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'management/transactions.html', {
        'transactions': page_obj,
        'summary':      summary,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def transaction_detail(request, transaction_id):

    txn = get_object_or_404(
        Transaction.objects.select_related('user', 'gateway', 'course'),
        transaction_id=transaction_id
    )
    return render(request, 'management/transaction_detail.html', {
        'transaction': txn,
    })


# ---------------------------------------------------------------------------
# REQUIRED PAYMENTS
# ---------------------------------------------------------------------------

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def required_payments_list(request):

    qs = AllRequiredPayments.objects.select_related(
        'program', 'course', 'academic_session'
    ).order_by('-due_date')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(purpose__icontains=search)        |
            Q(program__name__icontains=search)  |
            Q(program__code__icontains=search)
        )

    active_filter = request.GET.get('active', '').strip()
    if active_filter == '1':
        qs = qs.filter(is_active=True)
    elif active_filter == '0':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    programs = Program.objects.filter(is_active=True).order_by('name')
    courses  = Course.objects.filter(is_active=True).order_by('code', 'name')
    form     = AllRequiredPaymentsForm()

    return render(request, 'management/required_payments.html', {
        'payments':  page_obj,
        'programs':  programs,
        'courses':   courses,
        'form':      form,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def required_payment_create(request):

    if request.method != 'POST':
        return redirect('management:required_payments_list')

    form = AllRequiredPaymentsForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, 'Required payment created.')
    else:
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:required_payments_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def required_payment_edit(request, pk):

    if request.method != 'POST':
        return redirect('management:required_payments_list')

    payment = get_object_or_404(AllRequiredPayments, pk=pk)
    form    = AllRequiredPaymentsForm(request.POST, instance=payment)
    if form.is_valid():
        form.save()
        messages.success(request, 'Payment updated.')
    else:
        msg = next(
            (e for errs in form.errors.values() for e in errs),
            'Please fix the errors.'
        )
        messages.error(request, msg)
    return redirect('management:required_payments_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def required_payment_delete(request, pk):

    if request.method != 'POST':
        return redirect('management:required_payments_list')

    payment = get_object_or_404(AllRequiredPayments, pk=pk)
    payment.delete()
    messages.success(request, 'Payment deleted.')
    return redirect('management:required_payments_list')


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def send_overdue_payment_reminders(request):
    """Send overdue payment reminder emails to students with unpaid fees"""
    
    if request.method != 'POST':
        return redirect('management:required_payments_list')
    
    try:
        from django.utils import timezone
        
        # Find all overdue fees that haven't been paid yet
        today = timezone.now().date()
        overdue_fees = FeePayment.objects.filter(
            fee__due_date__lt=today,
            status__in=['pending', 'failed'],
            user__isnull=False
        ).select_related('user', 'fee')
        
        reminder_count = 0
        error_count = 0
        
        for fee in overdue_fees:
            try:
                # Send reminder email
                send_overdue_payment_reminder_email(fee.user, fee)
                reminder_count += 1
            except Exception as e:
                import logging
                logger = logging.getLogger('melbac')
                logger.error(f'Failed to send overdue reminder for fee {fee.id}: {str(e)}')
                error_count += 1
        
        if reminder_count > 0:
            messages.success(
                request,
                f'Sent {reminder_count} overdue payment reminder(s). {error_count} failed if any.'
            )
        else:
            messages.info(request, 'No overdue payments found.')
    except ImportError:
        messages.error(request, 'FeePayment model not found.')
    except Exception as e:
        import logging
        logger = logging.getLogger('melbac')
        logger.error(f'Failed to send overdue payment reminders: {str(e)}')
        messages.error(request, 'An error occurred while sending reminders.')
    
    return redirect('management:required_payments_list')


# ---------------------------------------------------------------------------
# FINANCIAL ANALYTICS DASHBOARD
# ---------------------------------------------------------------------------

def financial_analytics(request):
    """Financial analytics — all student payment records."""

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

    # FeePayment → fee (AllRequiredPayments) → program, academic_session
    fee_qs = FeePayment.objects.select_related(
        'user', 'fee', 'fee__program', 'fee__academic_session'
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

    STAFF_ROLES = ['instructor', 'support', 'admin', 'content_manager', 'finance']

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

    form = StaffPayrollForm(request.POST)
    if form.is_valid():
        payroll = form.save()
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
    else:
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

    payroll = get_object_or_404(StaffPayroll, payroll_reference=payroll_reference)
    form    = StaffPayrollForm(request.POST, instance=payroll)
    if form.is_valid():
        # Track old status to detect changes
        old_status = payroll.payment_status
        
        updated_payroll = form.save()
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
                import logging
                logger = logging.getLogger('melbac')
                logger.error(f'Failed to send payroll notification email for {updated_payroll.payroll_reference}: {str(e)}')
    else:
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

    payroll = get_object_or_404(StaffPayroll, payroll_reference=payroll_reference)
    payroll.delete()
    messages.success(request, 'Payroll deleted.')
    return redirect('management:staff_payroll_list')

# ── SITE CONFIG VIEWS ────────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_config_general(request):
    """Edit base.html / global fields: identity, logos, SEO, footer, social, contact."""
    site = SiteConfig.objects.first()
    if request.method == 'POST':
        form = SiteConfigGeneralForm(request.POST, request.FILES, instance=site)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='SiteConfig',
                description='Updated general site configuration'
            )
            messages.success(request, 'General site settings saved.')
            return redirect('management:site_config_general')
    else:
        form = SiteConfigGeneralForm(instance=site)
    return render(request, 'management/site_config/general.html', {'form': form, 'site': site})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_config_index(request):
    """Edit index.html fields: hero slides, promo video, campus map."""
    site = SiteConfig.objects.first()
    if request.method == 'POST':
        form = SiteConfigIndexForm(request.POST, request.FILES, instance=site)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='SiteConfig',
                description='Updated index page configuration'
            )
            messages.success(request, 'Home page settings saved.')
            return redirect('management:site_config_index')
    else:
        form = SiteConfigIndexForm(instance=site)
    return render(request, 'management/site_config/index_page.html', {'form': form, 'site': site})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_config_about(request):
    """Edit about.html fields: mission, vision, values, virtual tour."""
    site = SiteConfig.objects.first()
    if request.method == 'POST':
        form = SiteConfigAboutForm(request.POST, request.FILES, instance=site)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='SiteConfig',
                description='Updated about page configuration'
            )
            messages.success(request, 'About page settings saved.')
            return redirect('management:site_config_about')
    else:
        form = SiteConfigAboutForm(instance=site)
    return render(request, 'management/site_config/about_page.html', {'form': form, 'site': site})

# ── SITE HISTORY MILESTONES ───────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_milestones_list(request):
    milestones = SiteHistoryMilestone.objects.all().order_by('display_order', 'year')
    return render(request, 'management/site_config/milestones_list.html', {
        'milestones': milestones,
        'active_count': milestones.filter(is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_milestone_create(request):
    if request.method == 'POST':
        form = SiteHistoryMilestoneForm(request.POST)
        if form.is_valid():
            milestone = form.save(commit=False)
            milestone.site = SiteConfig.objects.first()
            milestone.save()
            AuditLog.objects.create(
                user=request.user, action='create',
                model_name='SiteHistoryMilestone',
                description=f'Created milestone: {milestone}'
            )
            messages.success(request, 'Milestone created.')
            return redirect('management:site_milestones_list')
    else:
        form = SiteHistoryMilestoneForm()
    return render(request, 'management/site_config/milestone_form.html', {
        'form': form, 'milestone': None,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_milestone_edit(request, pk):
    milestone = get_object_or_404(SiteHistoryMilestone, pk=pk)
    if request.method == 'POST':
        form = SiteHistoryMilestoneForm(request.POST, instance=milestone)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='SiteHistoryMilestone',
                description=f'Updated milestone: {milestone}'
            )
            messages.success(request, 'Milestone updated.')
            return redirect('management:site_milestones_list')
    else:
        form = SiteHistoryMilestoneForm(instance=milestone)
    return render(request, 'management/site_config/milestone_form.html', {
        'form': form, 'milestone': milestone,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def site_milestone_delete(request, pk):
    milestone = get_object_or_404(SiteHistoryMilestone, pk=pk)
    if request.method == 'POST':
        milestone.delete()
        messages.success(request, 'Milestone deleted.')
    return redirect('management:site_milestones_list')


# ── TESTIMONIALS ──────────────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def testimonials_list(request):
    testimonials = Testimonial.objects.all().order_by('order')
    return render(request, 'management/site_config/testimonials_list.html', {
        'testimonials': testimonials,
        'active_count': testimonials.filter(is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def testimonial_create(request):
    if request.method == 'POST':
        form = TestimonialForm(request.POST, request.FILES)
        if form.is_valid():
            t = form.save()
            AuditLog.objects.create(
                user=request.user, action='create',
                model_name='Testimonial',
                description=f'Created testimonial: {t}'
            )
            messages.success(request, 'Testimonial created.')
            return redirect('management:testimonials_list')
    else:
        form = TestimonialForm()
    return render(request, 'management/site_config/testimonial_form.html', {
        'form': form, 'testimonial': None,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        form = TestimonialForm(request.POST, request.FILES, instance=testimonial)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='Testimonial',
                description=f'Updated testimonial: {testimonial}'
            )
            messages.success(request, 'Testimonial updated.')
            return redirect('management:testimonials_list')
    else:
        form = TestimonialForm(instance=testimonial)
    return render(request, 'management/site_config/testimonial_form.html', {
        'form': form, 'testimonial': testimonial,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def testimonial_delete(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == 'POST':
        testimonial.delete()
        messages.success(request, 'Testimonial deleted.')
    return redirect('management:testimonials_list')


# ── INSTITUTION MEMBERS ───────────────────────────────────────────────────────

@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_members_list(request):
    members = InstitutionMember.objects.all().order_by('member_type', 'display_order')
    return render(request, 'management/site_config/members_list.html', {
        'members': members,
        'admin_board_count':      members.filter(member_type='admin_board', is_active=True).count(),
        'academic_board_count':   members.filter(member_type='academic_board', is_active=True).count(),
        'advisorate_board_count': members.filter(member_type='advisorate_board', is_active=True).count(),
        'staff_count':            members.filter(member_type='staff', is_active=True).count(),
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_member_create(request):
    if request.method == 'POST':
        form = InstitutionMemberForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save()
            AuditLog.objects.create(
                user=request.user, action='create',
                model_name='InstitutionMember',
                description=f'Created member: {m}'
            )
            messages.success(request, 'Member created.')
            return redirect('management:institution_members_list')
    else:
        form = InstitutionMemberForm()
    return render(request, 'management/site_config/member_form.html', {
        'form': form, 'member': None,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_member_edit(request, pk):
    member = get_object_or_404(InstitutionMember, pk=pk)
    if request.method == 'POST':
        form = InstitutionMemberForm(request.POST, request.FILES, instance=member)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action='update',
                model_name='InstitutionMember',
                description=f'Updated member: {member}'
            )
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
    else:
        form = InstitutionMemberForm(instance=member)
    return render(request, 'management/site_config/member_form.html', {
        'form': form, 'member': member,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def institution_member_delete(request, pk):
    member = get_object_or_404(InstitutionMember, pk=pk)
    if request.method == 'POST':
        member.delete()
        messages.success(request, 'Member deleted.')
    return redirect('management:institution_members_list')

# ── Library: Item List ────────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_items_list(request):
    """
    Paginated, filterable list of all LibraryItems.
    Filters: q (search), category, access, status (active/inactive).
    """
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
        form = LibraryItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
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
    item = get_object_or_404(LibraryItem, pk=pk)
 
    if request.method == 'POST':
        form = LibraryItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
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
        title = item.title
        item.delete()
        messages.success(request, f'"{title}" removed from the library.')
    return redirect('management:library_items_list')
 
 
# ── Library: Toggle Active ────────────────────────────────────────────────────
 
@login_required(login_url='eduweb:auth_page')
@user_passes_test(is_admin)
def library_item_toggle_active(request, pk):
    """
    Quick-toggle is_active on a LibraryItem.
    Supports both standard POST redirect and AJAX JSON response.
    pk is a UUID.
    """
    item = get_object_or_404(LibraryItem, pk=pk)
    if request.method == 'POST':
        item.is_active = not item.is_active
        item.save(update_fields=['is_active'])
        state = 'published' if item.is_active else 'unpublished'
 
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
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

def _is_staff(user):
    return user.is_active and user.is_staff


@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
def admin_exam_list(request):
    STATUS_CHOICES = Exam.STATUS_CHOICES
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    session_id = request.GET.get('session', '')

    qs = Exam.objects.select_related('course', 'course__academic_course', 'instructor').order_by('-start_datetime')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(reference_code__icontains=search) |
            Q(course__title__icontains=search)
        )
    if session_id:
        qs = qs.filter(course__session_id=session_id)

    status_counts = {
        s: Exam.objects.filter(status=s).count()
        for s, _ in STATUS_CHOICES
    }

    sessions = AcademicSession.objects.order_by('-name')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'management/exam_list.html', {
        'page_obj': page_obj,
        'STATUS_CHOICES': STATUS_CHOICES,
        'status_filter': status_filter,
        'search': search,
        'session_id': session_id,
        'sessions': sessions,
        'status_counts': status_counts,
    })

@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
@require_POST
def admin_exam_toggle_active(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    exam.is_active = not exam.is_active
    exam.save(update_fields=['is_active'])
    state = 'activated' if exam.is_active else 'deactivated'
    messages.success(request, f'Exam {exam.reference_code} has been {state}.')
    return redirect('management:admin_exam_list')

@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
def admin_exam_detail(request, slug):
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
@user_passes_test(_is_staff)
@require_POST
def admin_exam_approve(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    if exam.status != Exam.SUBMITTED:
        messages.error(request, 'Only submitted exams can be approved.')
        return redirect('management:admin_exam_detail', slug=slug)

    prev = exam.status
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
@user_passes_test(_is_staff)
@require_POST
def admin_exam_reject(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    if exam.status != Exam.SUBMITTED:
        messages.error(request, 'Only submitted exams can be rejected.')
        return redirect('management:admin_exam_detail', slug=slug)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'A rejection reason is required.')
        return redirect('management:admin_exam_detail', slug=slug)

    prev = exam.status
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

    messages.warning(request, f'Exam {exam.reference_code} rejected.')
    return redirect('management:admin_exam_detail', slug=slug)


@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
@require_POST
def admin_exam_publish(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    if exam.status != Exam.APPROVED:
        messages.error(request, 'Only approved exams can be published.')
        return redirect('management:admin_exam_detail', slug=slug)

    prev = exam.status
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
@user_passes_test(_is_staff)
def admin_question_moderation(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    questions = exam.questions.order_by('created_at')

    if request.method == 'POST':
        q_id = request.POST.get('question_id')
        action = request.POST.get('action')
        question = get_object_or_404(ExamQuestion, pk=q_id, exam=exam)
        if action == 'activate':
            question.is_active = True
            question.save(update_fields=['is_active'])
            messages.success(request, f'Question activated.')
        elif action == 'deactivate':
            question.is_active = False
            question.save(update_fields=['is_active'])
            messages.warning(request, f'Question deactivated.')
        return redirect('management:admin_question_moderation', slug=slug)

    return render(request, 'management/question_moderation.html', {
        'exam': exam,
        'questions': questions,
    })


@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
def admin_exam_timetable_update(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    if request.method == 'POST':
        from django.utils.dateparse import parse_date, parse_time

        from datetime import datetime, timezone as dt_timezone
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
            from django.utils import timezone as dj_timezone
            import zoneinfo
            tz = zoneinfo.ZoneInfo('Africa/Lagos')
            start_datetime = dj_timezone.make_aware(datetime.combine(exam_date, start_time), tz)
            end_datetime = dj_timezone.make_aware(datetime.combine(exam_date, end_time), tz)

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
            exam.start_datetime = start_datetime
            exam.end_datetime = end_datetime
            exam.clash_notes = ''
            exam.save(update_fields=['start_datetime', 'end_datetime', 'clash_notes'])
            messages.success(request, 'Timetable updated successfully.')
            return redirect('management:admin_exam_detail', slug=slug)

    return render(request, 'management/exam_timetable.html', {'exam': exam})


@login_required(login_url='eduweb:auth_page')
@user_passes_test(_is_staff)
def admin_exam_responses(request, slug):
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
@user_passes_test(_is_staff)
@require_POST
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