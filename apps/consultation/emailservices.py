"""Consultation booking emails — mirrors apps/store/emailservices.py's shape
(one module per app that sends its own mail, public send_* functions the
view imports). Both emails share one branded shell (_email_shell) so the
header/footer stay identical instead of drifting between the two."""

import logging

from django.conf import settings
from django.utils import timezone
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.mail import EmailMultiAlternatives

from apps.eduweb.emailservices import _resolve_sender
from apps.eduweb.models import SiteConfig

logger = logging.getLogger(__name__)

SITE_URL = 'https://abraytech.com'


def _site():
    try:
        cfg = SiteConfig.get()
        if cfg:
            return cfg
    except Exception:
        pass

    class _Fallback:
        school_short_name = getattr(settings, 'SCHOOL_SHORT_NAME', 'AbrayTech')

        def __getattr__(self, name):
            return ''

    return _Fallback()


def _when(booking):
    slot = booking.slot
    return f"{slot.date:%A, %d %B %Y}, {slot.start_time:%I:%M %p}–{slot.end_time:%I:%M %p}"


def _amount_line(booking):
    return f"NGN {intcomma(int(booking.amount))}" if booking.amount else "Free"


def _detail_row(label, value, is_last=False):
    border = '' if is_last else 'border-bottom:1px solid #E2E8F0;'
    return f"""
    <tr>
        <td style="padding:12px 4px;{border} font:600 13px Arial,sans-serif; color:#5B6478; width:120px; vertical-align:top;">{label}</td>
        <td style="padding:12px 4px;{border} font:600 14px Arial,sans-serif; color:#0F172A;">{value}</td>
    </tr>
    """


def _email_shell(preheader, eyebrow, heading, body_html, cta_label=None, cta_url=None):
    """One branded wrapper for every consultation email: navy/blue gradient
    header with the AT mark, a white content card, and a footer that always
    links back to abraytech.com — so a visitor's confirmation and a staff
    alert never look like they came from two different systems."""
    cta_html = ''
    if cta_label and cta_url:
        cta_html = f"""
        <div style="text-align:center; margin:28px 0 4px;">
            <a href="{cta_url}" style="display:inline-block; background:linear-gradient(90deg,#0B5CFF,#38BDF8);
               color:#ffffff; text-decoration:none; font:700 14px Arial,sans-serif; padding:13px 28px;
               border-radius:8px;">{cta_label}</a>
        </div>
        """

    return f"""
    <html>
    <body style="margin:0; padding:0; background-color:#F4FAFF; font-family:Arial,Helvetica,sans-serif;">
        <span style="display:none; font-size:1px; color:#F4FAFF; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden;">{preheader}</span>
        <div style="max-width:600px; margin:0 auto; padding:32px 16px;">

            <div style="background:linear-gradient(135deg,#071A3D 0%,#0B5CFF 55%,#38BDF8 100%);
                        border-radius:16px 16px 0 0; padding:32px 30px; text-align:center;">
                <table role="presentation" align="center" style="margin:0 auto 14px;">
                    <tr>
                        <td style="width:40px; height:40px; background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.35);
                                   border-radius:10px; text-align:center; vertical-align:middle;
                                   font:700 15px Arial,sans-serif; color:#ffffff;">AT</td>
                        <td style="padding-left:10px; font:700 19px Arial,sans-serif; color:#ffffff; letter-spacing:.02em;">AbrayTech</td>
                    </tr>
                </table>
                <p style="margin:0 0 10px; font:600 11px Arial,sans-serif; letter-spacing:.12em; text-transform:uppercase; color:#8AD8FF;">{eyebrow}</p>
                <h1 style="margin:0; font:700 24px Arial,sans-serif; color:#ffffff;">{heading}</h1>
            </div>

            <div style="background:#ffffff; padding:32px 30px; border-radius:0 0 16px 16px; box-shadow:0 2px 10px rgba(7,26,61,.06);">
                {body_html}
                {cta_html}
            </div>

            <div style="text-align:center; padding:26px 20px 0;">
                <p style="margin:0 0 6px; font:600 13px Arial,sans-serif; color:#071A3D;">
                    <a href="{SITE_URL}" style="color:#0B5CFF; text-decoration:none;">abraytech.com</a>
                </p>
                <p style="margin:0; font:400 12px Arial,sans-serif; color:#94A3B8; line-height:1.6;">
                    Software Development &middot; Cybersecurity &middot; AI &amp; Data &middot; IT Consulting<br>
                    &copy; {timezone.now().year} AbrayTech. All rights reserved.
                </p>
            </div>

        </div>
    </body>
    </html>
    """


def send_booking_confirmation_email(booking):
    """Sent to the visitor once their booking is confirmed — immediately for
    a free topic, right after Paystack confirms payment for a paid one.
    Returns bool success, matching eduweb.emailservices' convention — never
    raises."""
    try:
        site = _site()
        subject = f"Consultation Confirmed — {booking.service.title}"
        when = _when(booking)
        amount_line = _amount_line(booking)
        first_name = booking.name.split(' ')[0]

        body_html = f"""
        <p style="margin:0 0 18px; font:400 15px/1.6 Arial,sans-serif; color:#1E293B;">Hi <strong>{first_name}</strong>,</p>
        <p style="margin:0 0 22px; font:400 15px/1.6 Arial,sans-serif; color:#1E293B;">
            Thanks for booking with {site.school_short_name} — your consultation is confirmed. Here's a summary for your records:
        </p>
        <table role="presentation" style="width:100%; border-collapse:collapse; background:#F4FAFF; border-radius:10px; padding:4px 16px;">
            {_detail_row('Topic', booking.service.title)}
            {_detail_row('When', when)}
            {_detail_row('Amount', amount_line, is_last=True)}
        </table>
        <p style="margin:22px 0 0; font:400 15px/1.6 Arial,sans-serif; color:#1E293B;">
            We'll be in touch shortly with the call link and any details we need from you beforehand.
            If anything changes on your end, just reply to this email — we read every one.
        </p>
        <p style="margin:24px 0 0; font:400 15px/1.6 Arial,sans-serif; color:#1E293B;">
            Best regards,<br>
            <strong style="color:#071A3D;">The {site.school_short_name} Team</strong>
        </p>
        """

        html_content = _email_shell(
            preheader=f"Your {booking.service.title} consultation is confirmed for {when}.",
            eyebrow='Consultation Booking',
            heading='You’re Confirmed!',
            body_html=body_html,
            cta_label='Visit abraytech.com',
            cta_url=SITE_URL,
        )

        text_content = (
            f"You're Confirmed!\n\n"
            f"Hi {first_name},\n\n"
            f"Thanks for booking with {site.school_short_name} — your consultation is confirmed.\n\n"
            f"Topic: {booking.service.title}\n"
            f"When: {when}\n"
            f"Amount: {amount_line}\n\n"
            f"We'll be in touch shortly with the call link and any details we need from you beforehand.\n\n"
            f"Best regards,\nThe {site.school_short_name} Team\n\n"
            f"{SITE_URL}"
        )

        connection, from_email = _resolve_sender('consultation')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[booking.email], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send consultation confirmation email for booking %s', booking.pk)
        return False


def send_staff_booking_notification(booking):
    """Sent to CONTACT_EMAIL the moment a booking is confirmed (free or
    paid), so staff don't rely solely on checking the admin list."""
    recipient = getattr(settings, 'CONTACT_EMAIL', '')
    if not recipient:
        return False
    try:
        when = _when(booking)
        amount_line = _amount_line(booking)
        subject = f"New consultation booking — {booking.service.title}"
        bookings_url = f"{SITE_URL}/management/consultation/bookings/"
        mailto = f"mailto:{booking.email}"

        body_html = f"""
        <p style="margin:0 0 20px; font:400 15px/1.6 Arial,sans-serif; color:#1E293B;">
            A new consultation booking just came in.
        </p>
        <table role="presentation" style="width:100%; border-collapse:collapse; background:#F4FAFF; border-radius:10px; padding:4px 16px;">
            {_detail_row('Name', f'{booking.name} &mdash; <a href="{mailto}" style="color:#0B5CFF; text-decoration:none;">{booking.email}</a>')}
            {_detail_row('Topic', booking.service.title)}
            {_detail_row('When', when)}
            {_detail_row('Amount', amount_line)}
            {_detail_row('Phone', booking.phone or '—')}
            {_detail_row('Company', booking.company or '—')}
            {_detail_row('Message', booking.message or '—', is_last=True)}
        </table>
        """

        html_content = _email_shell(
            preheader=f"{booking.name} booked {booking.service.title} — {when}.",
            eyebrow='Staff Alert',
            heading='New Consultation Booking',
            body_html=body_html,
            cta_label='View in Admin',
            cta_url=bookings_url,
        )

        text_content = (
            f"New Consultation Booking\n\n"
            f"Name: {booking.name} ({booking.email})\n"
            f"Topic: {booking.service.title}\n"
            f"When: {when}\n"
            f"Amount: {amount_line}\n"
            f"Phone: {booking.phone or '-'}\n"
            f"Company: {booking.company or '-'}\n"
            f"Message: {booking.message or '-'}\n\n"
            f"View in Admin: {bookings_url}"
        )

        connection, from_email = _resolve_sender('consultation')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[recipient], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send staff booking notification for booking %s', booking.pk)
        return False
