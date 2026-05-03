import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse

from .models import SiteConfig

logger = logging.getLogger(__name__)


def _site():
    """
    Helper — returns the live SiteConfig row, or a safe fallback object
    so email functions never crash if SiteConfig hasn't been set up yet.

    Every email function MUST call  site = _site()  at the top of its try
    block so that school_name / school_short_name are always dynamic and
    never hard-coded.
    """
    try:
        cfg = SiteConfig.get()
        if cfg:
            return cfg
    except Exception:
        pass

    class _Fallback:
        """
        Returned when SiteConfig is unavailable.
        Falls back to Django settings values where possible so at least
        contact details are still correct in emergencies.
        """
        school_name       = getattr(settings, 'SCHOOL_NAME',       'Our Institution')
        school_short_name = getattr(settings, 'SCHOOL_SHORT_NAME', 'Portal')
        email             = getattr(settings, 'CONTACT_EMAIL',      '')
        phone_admissions  = getattr(settings, 'CONTACT_PHONE',      '')
        email_admissions  = getattr(settings, 'CONTACT_EMAIL',      '')
        phone_primary     = getattr(settings, 'CONTACT_PHONE',      '')

        def __getattr__(self, name):
            return ''

    return _Fallback()


def _contact_email(site):
    """
    Return the best available contact e-mail address.
    Prefers site.email_admissions, then site.email, then the Django setting.
    """
    return (
        getattr(site, 'email_admissions', '') or
        getattr(site, 'email', '')            or
        getattr(settings, 'CONTACT_EMAIL', '')
    )


def _contact_phone(site):
    """Return the best available phone number from SiteConfig."""
    return (
        getattr(site, 'phone_admissions', '') or
        getattr(site, 'phone_primary', '')    or
        getattr(settings, 'CONTACT_PHONE', '')
    )


#######################################################
# EMAIL VERIFICATION - SENT AT SIGNUP
#######################################################
def send_verification_email(request, user):
    """
    Send email verification link to new user at signup.

    Trigger: Called in auth_page() view after user creation
    Purpose: Verify user's email address before account activation
    Recipients: New user

    Args:
        request: HTTP request object (for building absolute URL)
        user: User object with unverified email

    Returns:
        bool: True if email sent successfully, False otherwise

    Security:
        - Token expires in 24 hours
        - One-time use verification token
    """
    try:
        site  = _site()
        profile = user.profile
        token = profile.verification_token
        get_current_site(request)           # kept for side-effects / future use
        verification_url = request.build_absolute_uri(
            reverse('eduweb:verify_email', kwargs={'token': str(token)})
        )

        subject = f'Verify Your {site.school_short_name} Account'

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;
                         line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto;
                            padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg,
                                #840384 0%, #a855f7 100%);
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">
                            Welcome to {site.school_short_name}!
                        </h1>
                    </div>
                    <div style="background-color: white;
                                padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">
                            Dear <strong>
                                {user.get_full_name() or user.username}
                            </strong>,
                        </p>
                        <p>
                            Thank you for creating an account with
                            {site.school_name}. Please verify
                            your email address to complete your registration.
                        </p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{verification_url}"
                               style="display: inline-block;
                                      padding: 15px 40px;
                                      background: linear-gradient(135deg,
                                      #840384 0%, #a855f7 100%);
                                      color: white;
                                      text-decoration: none;
                                      border-radius: 8px;
                                      font-weight: bold;
                                      font-size: 16px;">
                                Verify Email Address
                            </a>
                        </div>
                        <p style="font-size: 14px; color: #666;">
                            Or copy and paste this link into your browser:
                        </p>
                        <p style="font-size: 14px; color: #1D4ED8;
                                  word-break: break-all;">
                            {verification_url}
                        </p>
                        <p style="font-size: 14px; color: #666;
                                  margin-top: 30px;">
                            This link will expire in 24 hours.
                        </p>
                        <p>
                            Best regards,<br>
                            <strong style="color: #840384;">
                                The {site.school_short_name} Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = f"""
Welcome to {site.school_name}!

Dear {user.get_full_name() or user.username},

Thank you for creating an account. Please verify your email address by
clicking the link below:

{verification_url}

This link will expire in 24 hours.

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        # NOTE: Do NOT recurse here — log and return False so the caller
        #       can decide how to handle the failure gracefully.
        logger.error(
            "Verification email failed for %s: %s", user.email, e,
            exc_info=True,
        )
        return False


#######################################################
# VERIFICATION SUCCESS - SENT AFTER EMAIL VERIFICATION
#######################################################
def send_verification_success_email(user):
    """
    Send welcome email after successful email verification.

    Trigger: Called in verify_email() view after verification success
    Purpose: Confirm successful verification and guide next steps
    Recipients: Newly verified user

    Args:
        user: User object with verified email

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        contact = _contact_email(site)
        subject = f'Email Verified - Welcome to {site.school_short_name}!'

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;
                         line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto;
                            padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg,
                                #10b981 0%, #059669 100%);
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">
                            ✓ Email Verified!
                        </h1>
                    </div>
                    <div style="background-color: white;
                                padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">
                            Dear <strong>
                                {user.get_full_name() or user.username}
                            </strong>,
                        </p>
                        <p>
                            Congratulations! Your email has been successfully
                            verified. Your account is now active.
                        </p>

                        <div style="background-color: #d1fae515;
                                    padding: 20px; border-radius: 8px;
                                    margin: 25px 0;
                                    border-left: 4px solid #10b981;">
                            <h3 style="color: #10b981; margin-top: 0;">
                                Next Steps
                            </h3>
                            <ol style="margin: 10px 0; padding-left: 20px;">
                                <li>Log in to your account</li>
                                <li>Complete your application</li>
                                <li>Upload required documents</li>
                                <li>Track your application status</li>
                            </ol>
                        </div>

                        <p>
                            If you have any questions, please contact us at
                            <a href="mailto:{contact}">
                                {contact}
                            </a>
                        </p>

                        <p>
                            Best regards,<br>
                            <strong style="color: #840384;">
                                The {site.school_short_name} Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = f"""
Email Verified - Welcome to {site.school_short_name}!

Dear {user.get_full_name() or user.username},

Congratulations! Your email has been successfully verified.
Your account is now active.

Next Steps:
1. Log in to your account
2. Complete your application
3. Upload required documents
4. Track your application status

If you have any questions, please contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Verification success email failed for %s: %s", user.email, e,
            exc_info=True,
        )
        return False


#######################################################
# APPLICATION SUBMISSION - SENT TO APPLICANT
#######################################################
def send_application_confirmation_email(application):
    """
    Send confirmation email when application is submitted.

    Trigger: Called in submit_application() view
    Purpose: Confirm receipt of application
    Recipients: Applicant

    Args:
        application: CourseApplication object

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        subject = f'Application Received - {application.application_id}'

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
                            Application Received!
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
                        <p>
                            Thank you for applying to {site.school_name}.
                            We have received your application.
                        </p>
                        <div style="background-color: #E6F0FF;
                                    padding: 20px; border-radius: 8px;
                                    margin: 25px 0;">
                            <h3 style="color: #0F2A44; margin-top: 0;">
                                Application Details
                            </h3>
                            <p>
                                <strong>Application ID:</strong>
                                {application.application_id}
                            </p>
                            <p>
                                <strong>Program:</strong>
                                {application.program.name}
                            </p>
                            <p>
                                <strong>Degree Level:</strong>
                                {application.program.get_degree_level_display()}
                            </p>
                            <p>
                                <strong>Faculty:</strong>
                                {application.program.department.faculty.name}
                            </p>
                            <p>
                                <strong>Submission Date:</strong>
                                {application.submitted_at.strftime('%B %d, %Y')
                                 if application.submitted_at else 'Pending'}
                            </p>
                        </div>
                        <p>
                            Our admissions team will review your application
                            and contact you within 5-7 business days.
                        </p>
                        <p>
                            Best regards,<br>
                            <strong style="color: #0F2A44;">
                                The {site.school_short_name} Admissions Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_body = (
            f"Dear {application.first_name} {application.last_name},\n\n"
            f"Thank you for applying to {site.school_name}. "
            f"Your application has been received.\n\n"
            f"Application ID: {application.application_id}\n"
            f"Program: {application.program.name}\n\n"
            f"Our admissions team will contact you within 5-7 business days.\n\n"
            f"Best regards,\nThe {site.school_short_name} Admissions Team"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Application confirmation email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False


#######################################################
# APPLICATION SUBMISSION - SENT TO ADMIN
#######################################################
def send_application_admin_notification(application):
    """
    Send notification to admin when new application submitted.

    Trigger: Called in submit_application() view
    Purpose: Alert admin team of new application requiring review
    Recipients: Admin team (site.email_admissions or settings.CONTACT_EMAIL)

    Args:
        application: CourseApplication object

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        contact = _contact_email(site)
        subject = f'New Application - {application.application_id}'

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>New Course Application Received</h2>
                <p>
                    <strong>Application ID:</strong>
                    {application.application_id}
                </p>
                <p>
                    <strong>Name:</strong>
                    {application.get_full_name()}
                </p>
                <p>
                    <strong>Email:</strong>
                    {application.email}
                </p>
                <p>
                    <strong>Course:</strong>
                    {application.program.name} ({application.program.code})
                </p>
                <p>
                    <strong>Degree Level:</strong>
                    {application.program.get_degree_level_display()}
                </p>
                <p>
                    <strong>Faculty:</strong>
                    {application.program.department.faculty.name}
                </p>
                <p>
                    <strong>Intake:</strong>
                    {application.intake.get_intake_period_display()}
                    {application.intake.year}
                </p>
                <p>
                    <strong>Study Mode:</strong>
                    {application.get_study_mode_display()}
                </p>
                <p>
                    <strong>Submitted:</strong>
                    {application.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
                     if application.submitted_at else 'Draft'}
                </p>
            </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"New application from {application.get_full_name()}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[contact],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Admin notification email failed for application %s: %s",
            application.application_id, e, exc_info=True,
        )
        return False


#######################################################
# DOCUMENT UPLOAD SUCCESS - SENT TO APPLICANT
#######################################################
def send_document_upload_confirmation(application, documents):
    """
    Send confirmation email when documents uploaded successfully.

    Trigger: Called after upload(s) in upload_application_file() view
    Purpose: Confirm receipt of uploaded document(s)
    Recipients: Applicant

    Args:
        application: CourseApplication object
        documents: Single ApplicationDocument or list of ApplicationDocument objects

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site = _site()

        # Ensure documents is a list
        if not isinstance(documents, list):
            documents = [documents]

        doc_count = len(documents)

        if doc_count == 1:
            subject = f'Document Uploaded - {application.application_id}'
        else:
            subject = f'{doc_count} Documents Uploaded - {application.application_id}'

        # Build document list HTML
        docs_html = ""
        for idx, doc in enumerate(documents, 1):
            docs_html += f"""
            <div style="background-color: #f9fafb;
                        padding: 12px 15px;
                        border-radius: 6px;
                        margin-bottom: 8px;">
                <p style="margin: 0;">
                    <strong>{idx}. {doc.get_file_type_display()}</strong>
                    &nbsp;—&nbsp;{doc.original_filename}
                </p>
            </div>
            """

        # Build document list text
        docs_text = ""
        for idx, doc in enumerate(documents, 1):
            docs_text += f"  {idx}. {doc.get_file_type_display()} — {doc.original_filename}\n"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;
                         line-height: 1.6;
                         color: #333;">
                <div style="max-width: 600px;
                            margin: 0 auto;
                            padding: 20px;
                            background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg,
                                #10b981 0%, #059669 100%);
                                padding: 30px;
                                text-align: center;">
                        <h1 style="color: white; margin: 0;">
                            📄 {'Documents' if doc_count > 1 else 'Document'} Uploaded
                        </h1>
                    </div>
                    <div style="background-color: white;
                                padding: 30px;
                                margin-top: 20px;">
                        <p style="font-size: 16px;">
                            Dear <strong>
                                {application.first_name}
                                {application.last_name}
                            </strong>,
                        </p>
                        <p>
                            Your {'documents have' if doc_count > 1 else 'document has'}
                            been successfully uploaded to your application.
                        </p>

                        <div style="background-color: #E6F0FF;
                                    padding: 20px;
                                    border-radius: 8px;
                                    margin: 25px 0;">
                            <p style="margin: 0;">
                                <strong>Application ID:</strong>
                                {application.application_id}
                            </p>
                        </div>

                        <h3 style="color: #0F2A44;">
                            {'Documents' if doc_count > 1 else 'Document'} Uploaded
                        </h3>
                        {docs_html}

                        <p>
                            You can continue uploading additional documents
                            or submit your application when ready.
                        </p>

                        <p>
                            Best regards,<br>
                            <strong style="color: #0F2A44;">
                                The {site.school_short_name} Admissions Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = f"""
{'Documents' if doc_count > 1 else 'Document'} Uploaded Successfully

Dear {application.first_name} {application.last_name},

Your {'documents have' if doc_count > 1 else 'document has'} been
successfully uploaded to your application.

Application ID: {application.application_id}

{'Documents' if doc_count > 1 else 'Document'} uploaded:
{docs_text}

You can continue uploading additional documents or submit your
application when ready.

Best regards,
The {site.school_short_name} Admissions Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Document upload confirmation email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False


#######################################################
# DOCUMENT UPLOAD - SENT TO ADMIN
#######################################################
def send_document_upload_admin_notification(application, documents):
    """
    Notify admin when applicant uploads document(s).

    Trigger: Called after upload(s) in upload_application_file() view
    Purpose: Alert admin of new documents requiring verification
    Recipients: Admin team (site.email_admissions or settings.CONTACT_EMAIL)

    Args:
        application: CourseApplication object
        documents: Single ApplicationDocument or list of ApplicationDocument objects

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        contact = _contact_email(site)

        # Ensure documents is a list
        if not isinstance(documents, list):
            documents = [documents]

        doc_count = len(documents)

        if doc_count == 1:
            subject = f'New Document Uploaded - {application.application_id}'
        else:
            subject = f'{doc_count} New Documents Uploaded - {application.application_id}'

        # Build document table rows
        docs_html = ""
        for idx, doc in enumerate(documents, 1):
            docs_html += f"""
            <tr>
                <td style="padding: 10px;
                           border: 1px solid #ddd;">
                    {idx}
                </td>
                <td style="padding: 10px;
                           border: 1px solid #ddd;">
                    {doc.get_file_type_display()}
                </td>
                <td style="padding: 10px;
                           border: 1px solid #ddd;">
                    {doc.original_filename}
                </td>
                <td style="padding: 10px;
                           border: 1px solid #ddd;">
                    {doc.get_file_size_display()}
                </td>
                <td style="padding: 10px;
                           border: 1px solid #ddd;">
                    {doc.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')}
                </td>
            </tr>
            """

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>
                    {'New Documents Uploaded' if doc_count > 1 else 'New Document Uploaded'}
                </h2>
                <p>
                    An applicant has uploaded
                    {doc_count}
                    {'documents' if doc_count > 1 else 'document'}.
                </p>

                <h3>Applicant Information</h3>
                <table style="border-collapse: collapse;
                              width: 100%;
                              max-width: 600px;">
                    <tr>
                        <td style="padding: 8px;
                                   font-weight: bold;
                                   width: 150px;">
                            Name:
                        </td>
                        <td style="padding: 8px;">
                            {application.get_full_name()}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">
                            Email:
                        </td>
                        <td style="padding: 8px;">
                            {application.email}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">
                            Application ID:
                        </td>
                        <td style="padding: 8px;">
                            {application.application_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">
                            Course:
                        </td>
                        <td style="padding: 8px;">
                            {application.program.name}
                        </td>
                    </tr>
                </table>

                <h3>
                    {'Documents' if doc_count > 1 else 'Document'} Uploaded
                </h3>
                <table style="border-collapse: collapse;
                              width: 100%;
                              max-width: 800px;">
                    <thead>
                        <tr style="background-color: #f2f2f2;">
                            <th style="padding: 10px;
                                       border: 1px solid #ddd;
                                       text-align: left;">
                                #
                            </th>
                            <th style="padding: 10px;
                                       border: 1px solid #ddd;
                                       text-align: left;">
                                Type
                            </th>
                            <th style="padding: 10px;
                                       border: 1px solid #ddd;
                                       text-align: left;">
                                Filename
                            </th>
                            <th style="padding: 10px;
                                       border: 1px solid #ddd;
                                       text-align: left;">
                                Size
                            </th>
                            <th style="padding: 10px;
                                       border: 1px solid #ddd;
                                       text-align: left;">
                                Uploaded
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {docs_html}
                    </tbody>
                </table>

                <p style="margin-top: 20px;">
                    Please review the
                    {'documents' if doc_count > 1 else 'document'}
                    in the admin panel.
                </p>
            </body>
        </html>
        """

        text_body = (
            f"{'New documents' if doc_count > 1 else 'New document'} "
            f"uploaded by {application.get_full_name()} "
            f"for application {application.application_id}"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[contact],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Document upload admin notification failed for application %s: %s",
            application.application_id, e, exc_info=True,
        )
        return False


#######################################################
# CONTACT FORM - SENT TO ADMIN
#######################################################
def send_admin_email(contact_message):
    """
    Send contact form submission to admin.

    Trigger: Called in contact_submit() view
    Purpose: Forward user inquiry to admin team
    Recipients: Admin team (site.email_admissions or settings.CONTACT_EMAIL)

    Args:
        contact_message: ContactMessage object

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        contact = _contact_email(site)
        subject = (
            f'New Contact Form Submission - '
            f'{contact_message.get_subject_display()}'
        )

        text_content = f"""
New contact form submission from {site.school_name} website:

Name: {contact_message.name}
Email: {contact_message.email}
Subject: {contact_message.get_subject_display()}

Message:
{contact_message.message}

Submitted at: {contact_message.created_at.strftime('%Y-%m-%d %H:%M:%S')}
        """

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
                            New Contact Form Submission
                        </h1>
                    </div>
                    <div style="background-color: white;
                                padding: 30px; margin-top: 20px;">
                        <h3 style="color: #0F2A44;">
                            Contact Information
                        </h3>
                        <p>
                            <strong>Name:</strong>
                            {contact_message.name}
                        </p>
                        <p>
                            <strong>Email:</strong>
                            {contact_message.email}
                        </p>
                        <p>
                            <strong>Subject:</strong>
                            {contact_message.get_subject_display()}
                        </p>

                        <h3 style="color: #0F2A44; margin-top: 30px;">
                            Message
                        </h3>
                        <div style="background-color: #f9fafb;
                                    padding: 15px; border-radius: 5px;
                                    border-left: 3px solid #1D4ED8;">
                            <p style="margin: 0; white-space: pre-wrap;">
                                {contact_message.message}
                            </p>
                        </div>

                        <p style="margin-top: 30px;
                                  font-size: 14px; color: #666;">
                            Submitted at:
                            {contact_message.created_at.strftime('%B %d, %Y at %I:%M %p')}
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[contact],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info("Admin notification sent successfully to %s", contact)
        return True

    except Exception as e:
        logger.error("Admin contact-form email failed: %s", e, exc_info=True)
        return False


#######################################################
# CONTACT FORM - SENT TO USER
#######################################################
def send_user_confirmation_email(contact_message):
    """
    Send confirmation email to user who submitted contact form.

    Trigger: Called in contact_submit() view
    Purpose: Acknowledge receipt of contact form submission
    Recipients: Contact form submitter

    Args:
        contact_message: ContactMessage object

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site  = _site()
        phone = _contact_phone(site)
        subject = (
            f'Thank you for contacting {site.school_short_name} - '
            'We received your message'
        )

        text_content = f"""
Dear {contact_message.name},

Thank you for contacting {site.school_name} ({site.school_short_name}).
We have received your message and will respond within 1-2 business days.

Your Message Details:
Subject: {contact_message.get_subject_display()}
Message: {contact_message.message}

If you have any urgent questions, please call us at {phone}.

Best regards,
The {site.school_short_name} Admissions Team
        """

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
                            Thank You for Contacting Us!
                        </h1>
                    </div>
                    <div style="background-color: white;
                                padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px; margin-bottom: 20px;">
                            Dear <strong>{contact_message.name}</strong>,
                        </p>
                        <p style="font-size: 16px; margin-bottom: 20px;">
                            Thank you for reaching out to {site.school_name}.
                            We have received your message and our
                            team will review it carefully.
                        </p>
                        <div style="background-color: #E6F0FF;
                                    padding: 20px; border-radius: 8px;
                                    margin: 25px 0;">
                            <h3 style="color: #0F2A44; margin-top: 0;">
                                Your Message Summary
                            </h3>
                            <p>
                                <strong>Subject:</strong>
                                {contact_message.get_subject_display()}
                            </p>
                        </div>
                        <p style="font-size: 16px;">
                            Best regards,<br>
                            <strong style="color: #0F2A44;">
                                The {site.school_short_name} Admissions Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[contact_message.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(
            "Confirmation email sent successfully to %s", contact_message.email
        )
        return True

    except Exception as e:
        logger.error(
            "User confirmation email failed for %s: %s",
            contact_message.email, e, exc_info=True,
        )
        return False


#######################################################
# PAYMENT CONFIRMATION
#######################################################
def send_payment_emails(payment):
    """
    Send payment confirmation to user and vendor.

    Trigger: Called after successful payment processing
    Purpose: Confirm payment receipt
    Recipients: User and vendor

    Args:
        payment: ApplicationPayment object

    Returns:
        None (sends two separate emails)

    Note: Currency symbol is resolved dynamically from SiteConfig.
    """
    site = _site()

    # Resolve currency symbol dynamically from SiteConfig or payment object.
    # If payment carries its own currency code, prefer that; fall back to
    # the site-wide default currency.
    currency_symbols = {
        'USD': '$', 'GBP': '£', 'EUR': '€', 'JPY': '¥',
        'CAD': 'C$', 'AUD': 'A$', 'NGN': '₦',
    }
    currency_code = (
        getattr(payment, 'currency', None) or
        getattr(site, 'default_currency', 'GBP')
    )
    symbol = currency_symbols.get(str(currency_code).upper(), currency_code + ' ')

    user = getattr(payment, 'user', None) or getattr(payment.application, 'user', None)
    user_email = user.email if user and user.email else payment.application.email

    send_mail(
        "Payment Receipt",
        f"""
Payment Successful

Amount: {symbol}{payment.amount}
Application ID: {payment.application.application_id}
Reference: {payment.payment_reference}

Best regards,
The {site.school_short_name} Team
        """,
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
        fail_silently=True,
    )


#######################################################
# ADMISSION ACCEPTANCE
#######################################################
def send_admission_acceptance_email(application):
    """
    Send confirmation when student accepts admission offer.

    Trigger: Called in accept_admission() view
    Purpose: Confirm admission acceptance and provide next steps
    Recipients: Student who accepted admission

    Args:
        application: CourseApplication object with admission_accepted=True

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        subject = f'Admission Accepted - {application.admission_number}'

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
                            🎓 Welcome to {site.school_short_name}!
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
                                Admission Acceptance Confirmed!
                            </h3>
                            <p>
                                <strong>Admission Number:</strong>
                                {application.admission_number}
                            </p>
                            <p>
                                <strong>Program:</strong>
                                {application.program.name}
                            </p>
                        </div>

                        <h4>Next Steps:</h4>
                        <ol>
                            <li>Department approval is in progress</li>
                            <li>
                                You will receive portal access
                                once approved
                            </li>
                            <li>
                                Keep this admission number for
                                all correspondence
                            </li>
                        </ol>

                        <p style="margin-top: 30px;">
                            Welcome aboard!<br>
                            <strong style="color: #0F2A44;">
                                The {site.school_short_name} Team
                            </strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Admission Accepted - {application.admission_number}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Admission acceptance email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False


#######################################################
# PASSWORD RESET EMAIL
#######################################################
def send_password_reset_email(request, user):
    """
    Send password reset link to user.

    Trigger: Called in forgot_password() view
    Token expires in 1 hour.

    Args:
        request: HTTP request object (for building absolute URL)
        user: User object requesting password reset

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        site    = _site()
        profile = user.profile
        token   = profile.generate_password_reset_token()
        reset_url = request.build_absolute_uri(
            reverse('eduweb:reset_password', kwargs={'token': str(token)})
        )

        subject = f'Reset Your {site.school_short_name} Password'

        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
              <div style="background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                          padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 Password Reset</h1>
              </div>
              <div style="background-color: white; padding: 30px; margin-top: 20px;">
                <p style="font-size: 16px;">
                  Dear <strong>{user.get_full_name() or user.username}</strong>,
                </p>
                <p>
                  We received a request to reset your {site.school_short_name} account password.
                  Click the button below to set a new password.
                </p>
                <div style="text-align: center; margin: 30px 0;">
                  <a href="{reset_url}"
                     style="display: inline-block; padding: 15px 40px;
                            background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                            color: white; text-decoration: none; border-radius: 8px;
                            font-weight: bold; font-size: 16px;">
                    Reset My Password
                  </a>
                </div>
                <p style="font-size: 14px; color: #666;">
                  Or copy and paste this link into your browser:
                </p>
                <p style="font-size: 13px; color: #1D4ED8; word-break: break-all;">
                  {reset_url}
                </p>
                <p style="font-size: 14px; color: #dc2626; margin-top: 20px;">
                  ⚠️ This link will expire in <strong>1 hour</strong>.
                </p>
                <p style="font-size: 14px; color: #666;">
                  If you did not request a password reset, please ignore this email.
                  Your password will remain unchanged.
                </p>
                <p>
                  Best regards,<br>
                  <strong style="color: #840384;">
                    The {site.school_short_name} Team
                  </strong>
                </p>
              </div>
            </div>
          </body>
        </html>
        """

        text_content = f"""
Password Reset — {site.school_name}

Dear {user.get_full_name() or user.username},

Click the link below to reset your password (expires in 1 hour):

{reset_url}

If you did not request this, ignore this email.

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Password reset email failed for %s: %s", user.email, e,
            exc_info=True,
        )
        return False

#######################################################
# APPLICATION SUBMITTED FOR REVIEW - SENT TO APPLICANT
#######################################################
def send_application_submitted_email(application):
    """
    Send confirmation when an applicant formally submits their application
    for admissions review (after documents are uploaded).
 
    Trigger: Called in submit_application() view after application.mark_as_submitted()
    Purpose: Confirm submission and set expectations on review timeline
    Recipients: Applicant
 
    Args:
        application: CourseApplication object whose status has just changed
                     to 'under_review' (or equivalent submitted state)
 
    Returns:
        bool: True if email sent successfully, False otherwise
 
    ── Replace in views.py ──────────────────────────────────────────────────
    OLD (inside submit_application, after application.mark_as_submitted()):
 
        try:
            applicant_name = ...
            subject = 'Application Submitted Successfully - MIU'
            html_message = f\"\"\"...(long inline HTML)...\"\"\"
            email = EmailMultiAlternatives(subject, ..., [application.email])
            email.attach_alternative(html_message, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            print(f"Error sending submission email: {e}")
 
    NEW (single line, inside the same if-block):
 
        send_application_submitted_email(application)
    ─────────────────────────────────────────────────────────────────────────
    """
    try:
        site    = _site()
        contact = _contact_email(site)
 
        applicant_name = (
            application.get_full_name()
            if hasattr(application, 'get_full_name')
            else f"{application.first_name} {application.last_name}"
        )
 
        doc_count  = application.documents.count() if hasattr(application, 'documents') else 0
        subject    = f'Application Submitted Successfully - {site.school_short_name}'
 
        html_content = f"""
        <html>
        <head>
            <style>
                body      {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header   {{ background: linear-gradient(135deg, #840384 0%, #6B21A8 100%);
                             color: white; padding: 30px; text-align: center;
                             border-radius: 10px 10px 0 0; }}
                .content  {{ background: #f9fafb; padding: 30px;
                             border-radius: 0 0 10px 10px; }}
                .info-box {{ background: #DBEAFE; padding: 15px;
                             border-left: 4px solid #3B82F6;
                             margin: 20px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✅ Application Submitted!</h1>
                </div>
                <div class="content">
                    <p>Dear {applicant_name},</p>
 
                    <p>
                        Your application <strong>({application.application_id})</strong>
                        has been successfully submitted to
                        <strong>{site.school_name}</strong> for review.
                    </p>
 
                    <div class="info-box">
                        <strong>📝 Documents uploaded:</strong> {doc_count} file(s)<br>
                        <strong>⏰ Estimated review time:</strong> 4–6 weeks
                    </div>
 
                    <h3>What Happens Next?</h3>
                    <ol>
                        <li>Our admissions committee will review your application</li>
                        <li>You will receive email updates on your application status</li>
                        <li>A final decision will be communicated within 4–6 weeks</li>
                        <li>You can track your status anytime through your dashboard</li>
                    </ol>
 
                    <p>
                        If you have any questions, contact us at
                        <a href="mailto:{contact}">{contact}</a>
                    </p>
 
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Admissions Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
 
        text_content = f"""
Application Submitted Successfully — {site.school_name}
 
Dear {applicant_name},
 
Your application ({application.application_id}) has been successfully submitted
for admissions review.
 
Documents uploaded : {doc_count} file(s)
Estimated review   : 4–6 weeks
 
What Happens Next?
1. Our admissions committee will review your application.
2. You will receive email updates on your application status.
3. A final decision will be communicated within 4–6 weeks.
4. You can track your status anytime through your dashboard.
 
Questions? Contact us at {contact}
 
Best regards,
The {site.school_short_name} Admissions Team
        """
 
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
 
    except Exception as e:
        logger.error(
            "Application submitted email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False
 
 
#######################################################
# ADMISSION OFFER ACCEPTED - SENT TO APPLICANT
#######################################################
def send_admission_offer_accepted_email(application):
    """
    Send confirmation when a student formally accepts their admission offer
    and an admission number has been issued.
 
    Trigger: Called in accept_admission() view after application.accept_admission()
             and application.issue_admission_number() both succeed.
    Purpose: Confirm the acceptance, share the admission number, and outline
             the next steps (department approval → portal access).
    Recipients: Applicant
 
    Args:
        application: CourseApplication object with admission_accepted=True
                     and admission_number already set.
 
    Returns:
        bool: True if email sent successfully, False otherwise
 
    NOTE
    ----
    The existing send_admission_acceptance_email() in emailservices.py covers a
    DIFFERENT trigger — it fires when the *admin* records an accepted state on
    the model, not when the student clicks "Accept Offer" in the portal.
    This function covers the student-facing self-service acceptance flow.
 
    ── Replace in views.py ──────────────────────────────────────────────────
    OLD (inside accept_admission, after application.issue_admission_number()):
 
        try:
            applicant_name = ...
            subject = 'Admission Acceptance Confirmed - Modern International University'
            html_message = f\"\"\"...(long inline HTML)...\"\"\"
            email = EmailMultiAlternatives(subject, ..., [application.email])
            email.attach_alternative(html_message, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            print(f"Error sending confirmation email: {e}")
 
    NEW (single line, inside the same if-block):
 
        send_admission_offer_accepted_email(application)
    ─────────────────────────────────────────────────────────────────────────
    """
    try:
        site    = _site()
        contact = _contact_email(site)
 
        applicant_name = (
            application.get_full_name()
            if hasattr(application, 'get_full_name')
            else f"{application.first_name} {application.last_name}"
        )
 
        subject = (
            f'Admission Acceptance Confirmed — '
            f'{site.school_name}'
        )
 
        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #840384 0%, #6B21A8 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .highlight {{ background: #FEF3C7; padding: 15px;
                              border-left: 4px solid #F59E0B;
                              margin: 20px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Admission Acceptance Confirmed!</h1>
                </div>
                <div class="content">
                    <p>Dear {applicant_name},</p>
 
                    <p>
                        Congratulations! We have received your acceptance of the
                        admission offer from <strong>{site.school_name}</strong>.
                    </p>
 
                    <div class="highlight">
                        <strong>Your Admission Number:</strong>
                        {application.admission_number}
                    </div>
 
                    <h3>📋 Next Steps:</h3>
                    <ol>
                        <li>
                            Your application is now pending
                            <strong>department approval</strong>
                        </li>
                        <li>
                            You will receive another email once the department
                            head approves your admission
                        </li>
                        <li>
                            After approval, you will gain access to the
                            <strong>Student Portal</strong>
                        </li>
                        <li>Keep your admission number safe for future reference</li>
                    </ol>
 
                    <p>
                        <strong>Estimated time:</strong> Department approval
                        typically takes 2–3 business days.
                    </p>
 
                    <p>
                        If you have any questions, please contact our admissions
                        team at <a href="mailto:{contact}">{contact}</a>
                    </p>
 
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Admissions Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
 
        text_content = f"""
Admission Acceptance Confirmed — {site.school_name}
 
Dear {applicant_name},
 
Congratulations! We have received your acceptance of the admission offer.
 
Your Admission Number: {application.admission_number}
 
Next Steps:
1. Your application is now pending department approval.
2. You will receive another email once the department head approves.
3. After approval, you will gain access to the Student Portal.
4. Keep your admission number safe for future reference.
 
Estimated time: Department approval typically takes 2–3 business days.
 
Questions? Contact us at {contact}
 
Best regards,
The {site.school_short_name} Admissions Team
        """
 
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
 
    except Exception as e:
        logger.error(
            "Admission offer accepted email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False


#######################################################
# CERTIFICATE FEE PAID — SENT TO STUDENT
#######################################################
def send_certificate_fee_paid_email(user, certificate):
    """
    Sent when a student's certificate fee payment is confirmed
    and their certificate is now available to download.

    Trigger: Call after Certificate.mark_paid() succeeds in the
             payment confirmation flow.
    Recipients: Student
    """
    try:
        site = _site()
        contact = _contact_email(site)

        if certificate.certificate_type == 'program' and certificate.program:
            cert_title = certificate.program.name
        elif certificate.course:
            cert_title = certificate.course.title
        else:
            cert_title = 'Your Certificate'

        subject = f'Your Certificate is Ready — {site.school_short_name}'

        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .btn       {{ display: inline-block; padding: 14px 32px;
                              background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎓 Certificate Ready!</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p>
                        Great news! Your payment has been confirmed and your certificate
                        for <strong>{cert_title}</strong> is now available to download.
                    </p>
                    <p><strong>Certificate ID:</strong> {certificate.certificate_id}</p>
                    <p style="font-size:13px; color:#666;">
                        If you have any issues accessing your certificate, contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Certificate Ready — {site.school_name}

Dear {user.get_full_name() or user.username},

Your payment has been confirmed and your certificate for "{cert_title}"
is now available to download from your student portal.

Certificate ID: {certificate.certificate_id}

Visit: /student/certificates/

Questions? Contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Certificate fee paid email failed for %s: %s",
            user.email, e, exc_info=True,
        )
        return False


#######################################################
# GRADUATION CONFIRMED — SENT TO STUDENT
#######################################################
def send_graduation_confirmed_email(user, application):
    """
    Sent when admin marks a student's CourseApplication as
    is_graduated=True, confirming program completion.

    Trigger: Call after application.is_graduated is set to True
             and application.save() in the management view.
    Recipients: Student
    """
    try:
        site = _site()
        contact = _contact_email(site)

        program_name = (
            application.program.name
            if application.program
            else 'your program'
        )

        subject = f'Congratulations, You Have Graduated! — {site.school_short_name}'

        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .highlight {{ background: #FEF3C7; padding: 15px;
                              border-left: 4px solid #F59E0B;
                              margin: 20px 0; border-radius: 5px; }}
                .btn       {{ display: inline-block; padding: 14px 32px;
                              background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎓 Congratulations, Graduate!</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{application.get_full_name()}</strong>,</p>
                    <p>
                        It is with great pride that <strong>{site.school_name}</strong>
                        officially confirms your graduation from
                        <strong>{program_name}</strong>.
                    </p>
                    <div class="highlight">
                        <strong>Admission Number:</strong> {application.admission_number}<br>
                        <strong>Program:</strong> {program_name}<br>
                        <strong>Graduation Date:</strong> {application.graduated_at}
                    </div>
                    <h3>📋 Next Steps:</h3>
                    <ol>
                        <li>Log in to your Student Portal to view your graduation status</li>
                        <li>Pay the certificate fee to receive your official certificate</li>
                        <li>Request your official academic transcript if needed</li>
                    </ol>
                    <p style="font-size:13px; color:#666;">
                        For any enquiries, contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        With warmest congratulations,<br>
                        <strong>The {site.school_short_name} Academic Office</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Congratulations, Graduate! — {site.school_name}

Dear {application.get_full_name()},

{site.school_name} officially confirms your graduation from {program_name}.

Admission Number : {application.admission_number}
Program          : {program_name}
Graduation Date  : {application.graduated_at}

Next Steps:
1. Log in to your Student Portal to view your graduation status.
2. Pay the certificate fee to receive your official certificate.
3. Request your academic transcript if needed.

Questions? Contact us at {contact}

With warmest congratulations,
The {site.school_short_name} Academic Office
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[application.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Graduation confirmed email failed for %s: %s",
            application.email, e, exc_info=True,
        )
        return False

#######################################################
# ASSIGNMENT GRADED — SENT TO STUDENT
#######################################################
def send_assignment_graded_email(user, submission):
    """
    Sent when an instructor grades a student's assignment submission.

    Trigger: Call after AssignmentSubmission.status is set to 'graded'
             and submission.save() in the management/instructor grading view.
    Recipients: Student
    """
    try:
        site = _site()
        contact = _contact_email(site)

        assignment_title = submission.assignment.title
        course_title = submission.assignment.lesson.course.title
        score = submission.score
        max_score = submission.assignment.max_score
        graded_by = (
            (submission.graded_by.get_full_name() or submission.graded_by.username)
            if submission.graded_by
            else site.school_short_name
        )

        subject = f'Assignment Graded: {assignment_title} — {site.school_short_name}'

        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #840384 0%, #a855f7 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .score-box {{ background: #DBEAFE; padding: 15px;
                              border-left: 4px solid #3B82F6;
                              margin: 20px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📝 Assignment Graded</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p>
                        Your assignment <strong>"{assignment_title}"</strong>
                        in <strong>{course_title}</strong> has been graded.
                    </p>
                    <div class="score-box">
                        <strong>Score:</strong> {score} / {max_score}<br>
                        <strong>Graded by:</strong> {graded_by}
                    </div>
                    <p>
                        Log in to your student portal to view detailed feedback.
                    </p>
                    <p style="font-size:13px; color:#666;">
                        Questions? Contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Assignment Graded — {site.school_name}

Dear {user.get_full_name() or user.username},

Your assignment "{assignment_title}" in "{course_title}" has been graded.

Score    : {score} / {max_score}
Graded by: {graded_by}

Log in to your student portal to view detailed feedback.

Questions? Contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Assignment graded email failed for %s: %s",
            user.email, e, exc_info=True,
        )
        return False


#######################################################
# NEW MESSAGE RECEIVED — SENT TO RECIPIENT
#######################################################
def send_new_message_email(recipient, sender, message):
    """
    Sent when a student or staff sends a new message via the inbox.

    Trigger: Call in compose_message() and message_thread() views
             after Message.save(), only if the recipient has email
             notifications enabled (check profile preference if applicable).
    Recipients: Message recipient
    """
    try:
        site = _site()
        contact = _contact_email(site)

        sender_name = sender.get_full_name() or sender.username
        subject_line = message.subject

        subject = f'New Message from {sender_name} — {site.school_short_name}'

        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #0F2A44 0%, #1D4ED8 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .msg-box   {{ background: #f0f4ff; padding: 15px;
                              border-left: 4px solid #1D4ED8;
                              margin: 20px 0; border-radius: 5px; }}
                .btn       {{ display: inline-block; padding: 12px 28px;
                              background: linear-gradient(135deg, #0F2A44 0%, #1D4ED8 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✉️ New Message</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{recipient.get_full_name() or recipient.username}</strong>,</p>
                    <p>
                        You have received a new message from
                        <strong>{sender_name}</strong>.
                    </p>
                    <div class="msg-box">
                        <strong>Subject:</strong> {subject_line}
                    </div>
                    <p style="font-size:13px; color:#666;">
                        Questions? Contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
New Message — {site.school_name}

Dear {recipient.get_full_name() or recipient.username},

You have received a new message from {sender_name}.

Subject: {subject_line}

Log in to your inbox to read and reply:
/student/inbox/

Questions? Contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "New message email failed for %s: %s",
            recipient.email, e, exc_info=True,
        )
        return False


#######################################################
# CERTIFICATE READY FOR DOWNLOAD — SENT TO STUDENT
#######################################################
def send_certificate_ready_email(user, certificate):
    """
    Sent when a certificate payment is completed and certificate is ready for download.
    
    Trigger: Call in confirm_payment() or when certificate.mark_paid() is called
             after successful payment
    Recipients: Student
    """
    try:
        site = _site()
        contact = _contact_email(site)
        
        cert_title = (
            certificate.program.name if certificate.certificate_type == 'program'
            else (certificate.course.title if certificate.course else 'Course Certificate')
        )
        
        subject = f'Your {cert_title} Certificate is Ready — {site.school_short_name}'
        
        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .btn       {{ display: inline-block; padding: 12px 28px;
                              background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 14px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎓 Certificate Ready!</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p>
                        Congratulations! Your <strong>{cert_title}</strong> certificate
                        payment has been processed and your certificate is now ready for download.
                    </p>
                    <p>Certificate ID: <strong>{certificate.certificate_id}</strong></p>
                    <p style="text-align: center;">
                        <a href="/student/certificates/" class="btn">
                            Download Certificate
                        </a>
                    </p>
                    <p style="font-size:13px; color:#666; margin-top: 30px;">
                        Questions? Contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Your Certificate is Ready — {site.school_name}

Dear {user.get_full_name() or user.username},

Congratulations! Your {cert_title} certificate payment has been processed
and your certificate is now ready for download.

Certificate ID: {certificate.certificate_id}

Download your certificate:
/student/certificates/

Questions? Contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    
    except Exception as e:
        logger.error(
            "Certificate ready email failed for %s: %s",
            user.email, e, exc_info=True,
        )
        return False


#######################################################
# TRANSCRIPT GENERATED — SENT TO STUDENT
#######################################################
def send_transcript_generated_email(user, application):
    """
    Sent when a student's academic transcript has been generated and is ready for download.
    
    Trigger: Call in management view when transcript is marked as issued
             (application.transcript_issued = True)
    Recipients: Student
    """
    try:
        site = _site()
        contact = _contact_email(site)
        
        program_name = application.program.name if application.program else 'Your Program'
        
        subject = f'Your Academic Transcript is Ready — {site.school_short_name}'
        
        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .btn       {{ display: inline-block; padding: 12px 28px;
                              background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 14px; margin: 20px 0; }}
                .info-box  {{ background: #eff6ff; padding: 15px;
                              border-left: 4px solid #3b82f6;
                              margin: 20px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📄 Transcript Generated</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p>
                        Your official academic transcript for <strong>{program_name}</strong>
                        has been generated and is ready for download.
                    </p>
                    <div class="info-box">
                        <strong>Application ID:</strong> {application.application_id}<br>
                        <strong>Program:</strong> {program_name}
                    </div>
                    <p>
                        You can download your transcript from your student portal or
                        request official copies to be sent to external institutions.
                    </p>
                    <p style="text-align: center;">
                        <a href="/student/dashboard/" class="btn">
                            View My Records
                        </a>
                    </p>
                    <p style="font-size:13px; color:#666; margin-top: 30px;">
                        Questions? Contact us at
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Your Academic Transcript is Ready — {site.school_name}

Dear {user.get_full_name() or user.username},

Your official academic transcript for {program_name} has been generated
and is ready for download.

Application ID: {application.application_id}
Program: {program_name}

View your records and download your transcript:
/student/dashboard/

Questions? Contact us at {contact}

Best regards,
The {site.school_short_name} Team
        """
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    
    except Exception as e:
        logger.error(
            "Transcript generated email failed for %s: %s",
            user.email, e, exc_info=True,
        )
        return False


#######################################################
# PAYMENT REMINDER — OVERDUE FEES
#######################################################
def send_overdue_payment_reminder_email(user, fee):
    """
    Sent when a student has an overdue fee payment (due_date has passed).
    
    Trigger: Call from management command or cron job that checks
             AllRequiredPayments where due_date < today and student hasn't paid
    Recipients: Student with overdue fees
    """
    try:
        site = _site()
        contact = _contact_email(site)
        
        subject = f'Payment Reminder: Overdue Fee — {site.school_short_name}'
        
        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .btn       {{ display: inline-block; padding: 12px 28px;
                              background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
                              color: white; text-decoration: none;
                              border-radius: 8px; font-weight: bold; font-size: 14px; margin: 20px 0; }}
                .alert     {{ background: #fee2e2; padding: 15px;
                              border-left: 4px solid #dc2626;
                              margin: 20px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ Payment Reminder</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <div class="alert">
                        <strong>You have an OVERDUE payment</strong><br>
                        Please settle this fee as soon as possible to avoid disruption to your account.
                    </div>
                    <p>
                        <strong>Fee Purpose:</strong> {fee.purpose}<br>
                        <strong>Amount Due:</strong> {fee.currency} {fee.amount:.2f}<br>
                        <strong>Due Date:</strong> {fee.due_date.strftime('%B %d, %Y')}
                    </p>
                    <p style="text-align: center;">
                        <a href="/student/payments/" class="btn">
                            Pay Now
                        </a>
                    </p>
                    <p>
                        If you have already processed this payment, please
                        disregard this message. Your account will be updated within 24 hours.
                    </p>
                    <p style="font-size:13px; color:#666; margin-top: 30px;">
                        For payment assistance, contact
                        <a href="mailto:{contact}">{contact}</a>.
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Payment Reminder: Overdue Fee — {site.school_name}

Dear {user.get_full_name() or user.username},

You have an OVERDUE payment. Please settle this fee as soon as possible
to avoid disruption to your account.

Fee Purpose: {fee.purpose}
Amount Due: {fee.currency} {fee.amount:.2f}
Due Date: {fee.due_date.strftime('%B %d, %Y')}

Pay now at:
/student/payments/

If you have already processed this payment, disregard this message.
Your account will be updated within 24 hours.

For assistance, contact {contact}

Best regards,
The {site.school_short_name} Team
        """
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    
    except Exception as e:
        logger.error(
            "Overdue payment reminder email failed for %s: %s",
            user.email, e, exc_info=True,
        )
        return False


#######################################################
# PAYROLL PAYMENT NOTIFICATION — SENT TO STAFF
#######################################################
def send_payroll_payment_notification_email(payroll):
    """
    Sent to staff member when their payroll has been marked as paid.
    
    Trigger: Call in payroll update view when payment_status is changed to 'paid'
    Recipients: Staff member
    """
    try:
        site = _site()
        contact = _contact_email(site)
        user = payroll.staff
        
        subject = f'Your Payroll Payment Processed — {site.school_short_name}'
        
        month_name = payroll.get_month_name() or 'N/A'
        
        html_content = f"""
        <html>
        <head>
            <style>
                body       {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container  {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header    {{ background: linear-gradient(135deg, #059669 0%, #10b981 100%);
                              color: white; padding: 30px; text-align: center;
                              border-radius: 10px 10px 0 0; }}
                .content   {{ background: #f9fafb; padding: 30px;
                              border-radius: 0 0 10px 10px; }}
                .details   {{ background: #f0fdf4; padding: 15px;
                              border-left: 4px solid #10b981;
                              margin: 20px 0; border-radius: 5px; font-size: 14px; }}
                .amount    {{ font-size: 24px; font-weight: bold; color: #059669; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💰 Payroll Payment Processed</h1>
                </div>
                <div class="content">
                    <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p>
                        Your payroll for <strong>{month_name} {payroll.year}</strong> has been
                        processed and payment has been sent to your registered bank account.
                    </p>
                    <div class="details">
                        <strong>Payroll Details:</strong><br>
                        Reference: {payroll.payroll_reference}<br>
                        Period: {month_name} {payroll.year}<br>
                        Gross Salary: <span class="amount">{payroll.currency} {payroll.gross_salary:.2f}</span><br>
                        Net Salary: <span class="amount">{payroll.currency} {payroll.net_salary:.2f}</span><br>
                        Payment Date: {payroll.payment_date.strftime('%B %d, %Y') if payroll.payment_date else 'Processed'}<br>
                        Payment Method: {payroll.get_payment_method_display() if hasattr(payroll, 'get_payment_method_display') else payroll.payment_method}
                    </div>
                    <p>
                        If you have any questions about your payroll or
                        do not see the payment reflected in your account within 2-3 business days,
                        please contact our finance team.
                    </p>
                    <p style="font-size:13px; color:#666; margin-top: 30px;">
                        Finance Contact: <a href="mailto:{contact}">{contact}</a>
                    </p>
                    <p>
                        Best regards,<br>
                        <strong>The {site.school_short_name} Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Your Payroll Payment Has Been Processed — {site.school_name}

Dear {user.get_full_name() or user.username},

Your payroll for {month_name} {payroll.year} has been processed and
payment has been sent to your registered bank account.

Payroll Details:
Reference: {payroll.payroll_reference}
Period: {month_name} {payroll.year}
Gross Salary: {payroll.currency} {payroll.gross_salary:.2f}
Net Salary: {payroll.currency} {payroll.net_salary:.2f}
Payment Date: {payroll.payment_date.strftime('%B %d, %Y') if payroll.payment_date else 'Processed'}
Payment Method: {payroll.get_payment_method_display() if hasattr(payroll, 'get_payment_method_display') else payroll.payment_method}

If you do not see the payment within 2-3 business days or have questions,
please contact our finance team at {contact}.

Best regards,
The {site.school_short_name} Team
        """
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    
    except Exception as e:
        logger.error(
            "Payroll payment notification email failed for %s: %s",
            payroll.staff.email, e, exc_info=True,
        )
        return False


#######################################################
# ADMIN-CREATED USER — VERIFICATION + CREDENTIALS EMAIL
#######################################################
def send_admin_created_user_email(request, user, raw_password):
    """
    Sent when an admin creates a new user account.

    Flow:
      1. Generates a fresh verification token on the profile.
      2. Sends ONE email containing:
         - Login credentials (username + temporary password)
         - Verification link
         - Clear instruction: verify FIRST, then log in.

    Returns True on success, False on failure (non-fatal).
    """
    try:
        site    = _site()
        school  = site.school_short_name or site.school_name or 'Portal'
        profile = user.profile

        # Rotate token so it is always fresh for admin-created accounts
        token = profile.generate_verification_token()

        verification_url = request.build_absolute_uri(
            reverse('eduweb:verify_email', kwargs={'token': str(token)})
        )

        subject = f'Your {school} Account — Verify Your Email to Get Started'

        text_body = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"An administrator has created a {school} portal account for you.\n\n"
            f"--- Your Login Credentials ---\n"
            f"Username : {user.username}\n"
            f"Password : {raw_password}\n\n"
            f"IMPORTANT: You must verify your email address BEFORE you can log in.\n\n"
            f"Click the link below to verify your email:\n"
            f"{verification_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"Once verified, you can log in and change your password immediately.\n\n"
            f"— {school} Team"
        )

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
                    padding:0;background:#f4f4f4;">
          <div style="background:linear-gradient(135deg,#840384 0%,#a855f7 100%);
                      padding:30px;text-align:center;border-radius:10px 10px 0 0;">
            <h1 style="color:white;margin:0;font-size:24px;">
              Welcome to {school}!
            </h1>
          </div>
          <div style="background:#ffffff;padding:30px;border-radius:0 0 10px 10px;">
            <p style="font-size:16px;">
              Dear <strong>{user.get_full_name() or user.username}</strong>,
            </p>
            <p>
              An administrator has created a portal account for you on
              <strong>{site.school_name}</strong>.
            </p>

            <!-- Credentials box -->
            <div style="background:#f5f5f5;border-radius:8px;
                        padding:16px 20px;margin:20px 0;
                        border-left:4px solid #840384;">
              <p style="margin:4px 0;font-size:15px;">
                <strong>Username:</strong> {user.username}
              </p>
              <p style="margin:4px 0;font-size:15px;">
                <strong>Password:</strong>
                <code style="background:#ede9fe;padding:2px 6px;
                             border-radius:4px;">{raw_password}</code>
              </p>
            </div>

            <!-- Verification warning -->
            <div style="background:#fef9c3;border:1px solid #fde047;
                        border-radius:8px;padding:14px 18px;margin:20px 0;">
              <p style="margin:0;font-size:14px;color:#713f12;">
                ⚠️ <strong>Important:</strong> You must verify your email address
                <em>before</em> you can log in. Please click the button below first.
              </p>
            </div>

            <!-- Verify button -->
            <div style="text-align:center;margin:28px 0;">
              <a href="{verification_url}"
                 style="display:inline-block;padding:14px 36px;
                        background:linear-gradient(135deg,#840384 0%,#a855f7 100%);
                        color:white;text-decoration:none;
                        border-radius:8px;font-weight:bold;font-size:15px;">
                Verify My Email Address
              </a>
            </div>

            <p style="font-size:13px;color:#666;">
              Or copy and paste this link:<br>
              <a href="{verification_url}"
                 style="color:#1D4ED8;word-break:break-all;">
                {verification_url}
              </a>
            </p>
            <p style="font-size:13px;color:#666;margin-top:20px;">
              This link expires in <strong>24 hours</strong>.
              After verifying, please log in and change your password immediately.
            </p>
            <p>
              Best regards,<br>
              <strong style="color:#840384;">The {school} Team</strong>
            </p>
          </div>
        </div>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@portal.edu'),
            to=[user.email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        return True

    except Exception as e:
        logger.error(
            "Admin-created user email failed for %s: %s", user.email, e,
            exc_info=True,
        )
        return False