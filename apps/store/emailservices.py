"""Store order emails — mirrors apps/eduweb/emailservices.py's shape
(one module per app that sends its own mail, public send_* functions other
views import) rather than living inline in views.py."""

import logging

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse

from apps.eduweb.emailservices import _resolve_sender
from apps.eduweb.models import SiteConfig

logger = logging.getLogger(__name__)


def _site():
    try:
        cfg = SiteConfig.get()
        if cfg:
            return cfg
    except Exception:
        pass

    class _Fallback:
        school_name = getattr(settings, 'SCHOOL_NAME', 'Our Institution')
        school_short_name = getattr(settings, 'SCHOOL_SHORT_NAME', 'Store')

        def __getattr__(self, name):
            return ''

    return _Fallback()


def _order_items_rows_html(order):
    rows = ''
    for item in order.items.all():
        variant_suffix = (
            f'<br><span style="color:#6b7280;font-size:12px;">{item.variant_label}</span>'
            if item.variant_label else ''
        )
        rows += f"""
        <tr>
            <td style="padding:10px;border:1px solid #ddd;">{item.product_title}{variant_suffix}</td>
            <td style="padding:10px;border:1px solid #ddd;text-align:center;">{item.quantity}</td>
            <td style="padding:10px;border:1px solid #ddd;text-align:right;">NGN {intcomma(int(item.unit_price))}</td>
            <td style="padding:10px;border:1px solid #ddd;text-align:right;">NGN {intcomma(int(item.line_total))}</td>
        </tr>
        """
    return rows


def _order_items_text(order):
    lines = []
    for item in order.items.all():
        variant_suffix = f" ({item.variant_label})" if item.variant_label else ''
        lines.append(f"  - {item.product_title}{variant_suffix} x{item.quantity} — NGN {intcomma(int(item.line_total))}")
    return '\n'.join(lines)


def send_order_confirmation_email(order):
    """Sent to the buyer once payment is confirmed. Returns bool success,
    matching eduweb.emailservices' convention — never raises."""
    try:
        site = _site()
        subject = f"Order Confirmation — {order.order_number}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg, #071A3D 0%, #0B5CFF 55%, #38BDF8 100%);
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">🛍️ Order Confirmed!</h1>
                    </div>
                    <div style="background-color: white; padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">Dear <strong>{order.buyer_name}</strong>,</p>
                        <p>
                            Thank you for shopping with {site.school_short_name}. We've received your
                            order and will be in touch to arrange fulfillment.
                        </p>

                        <div style="background-color: #EAF6FF; padding: 20px; border-radius: 8px; margin: 25px 0;">
                            <p style="margin: 0;"><strong>Order Number:</strong> {order.order_number}</p>
                            <p style="margin: 5px 0 0;"><strong>Order Date:</strong> {order.created_at.strftime('%B %d, %Y')}</p>
                        </div>

                        <h3 style="color: #071A3D;">Items Ordered</h3>
                        <table style="border-collapse: collapse; width: 100%;">
                            <thead>
                                <tr style="background-color: #f2f2f2;">
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Item</th>
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Qty</th>
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: right;">Unit Price</th>
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: right;">Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {_order_items_rows_html(order)}
                            </tbody>
                            <tfoot>
                                <tr>
                                    <td colspan="3" style="padding: 10px; border: 1px solid #ddd; text-align: right; font-weight: bold;">Order Total</td>
                                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; font-weight: bold;">NGN {intcomma(int(order.amount))}</td>
                                </tr>
                            </tfoot>
                        </table>

                        <h3 style="color: #071A3D; margin-top: 30px;">Delivering To</h3>
                        <div style="background-color: #f9fafb; padding: 15px; border-radius: 5px; border-left: 3px solid #0B5CFF;">
                            <p style="margin: 0;">{order.delivery_address}, {order.delivery_city}, {order.delivery_state}</p>
                            <p style="margin: 5px 0 0; color: #666;">{order.delivery_phone}</p>
                        </div>

                        <p style="margin-top: 30px;">
                            You can track this order any time from
                            <strong>My Orders</strong> in your account.
                        </p>

                        <p>
                            Best regards,<br>
                            <strong style="color: #071A3D;">The {site.school_short_name} Store Team</strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = (
            f"Order Confirmed — {order.order_number}\n\n"
            f"Dear {order.buyer_name},\n\n"
            f"Thank you for shopping with {site.school_short_name}. We've received your order "
            f"and will be in touch to arrange fulfillment.\n\n"
            f"Order Number: {order.order_number}\n"
            f"Order Date: {order.created_at.strftime('%B %d, %Y')}\n\n"
            f"Items Ordered:\n{_order_items_text(order)}\n\n"
            f"Order Total: NGN {intcomma(int(order.amount))}\n\n"
            f"Delivering to:\n{order.delivery_address}, {order.delivery_city}, {order.delivery_state}\n"
            f"{order.delivery_phone}\n\n"
            f"You can track this order any time from My Orders in your account.\n\n"
            f"Best regards,\nThe {site.school_short_name} Store Team"
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[order.buyer_email], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send order confirmation email for %s', order.order_number)
        return False


def send_staff_order_notification(order):
    """Sent to CONTACT_EMAIL when an order is paid, so staff don't rely
    solely on checking the admin dashboard for new orders to fulfill."""
    recipient = getattr(settings, 'CONTACT_EMAIL', '')
    if not recipient:
        return False
    try:
        subject = f"New order to fulfill — {order.order_number}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #071A3D;">New Paid Order Received</h2>
                <p>A customer order has been paid and is ready for fulfillment.</p>

                <h3>Order Information</h3>
                <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                    <tr>
                        <td style="padding: 8px; font-weight: bold; width: 150px;">Order Number:</td>
                        <td style="padding: 8px;">{order.order_number}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Buyer:</td>
                        <td style="padding: 8px;">{order.buyer_name} ({order.buyer_email})</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Total:</td>
                        <td style="padding: 8px;">NGN {intcomma(int(order.amount))}</td>
                    </tr>
                </table>

                <h3>Items</h3>
                <table style="border-collapse: collapse; width: 100%; max-width: 800px;">
                    <thead>
                        <tr style="background-color: #f2f2f2;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Item</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Qty</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: right;">Unit Price</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: right;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {_order_items_rows_html(order)}
                    </tbody>
                </table>

                <h3>Deliver To</h3>
                <p>
                    {order.delivery_address}, {order.delivery_city}, {order.delivery_state}<br>
                    Phone: {order.delivery_phone}
                </p>

                <p style="margin-top: 20px;">Please fulfill this order from the Store &rsaquo; Orders queue in the admin panel.</p>
            </body>
        </html>
        """

        text_content = (
            f"New paid order: {order.order_number}\n"
            f"Buyer: {order.buyer_name} ({order.buyer_email})\n\n"
            f"Items:\n{_order_items_text(order)}\n\n"
            f"Total: NGN {intcomma(int(order.amount))}\n\n"
            f"Deliver to: {order.delivery_address}, {order.delivery_city}, {order.delivery_state}\n"
            f"Phone: {order.delivery_phone}\n\n"
            f"Please fulfill this order from the Store > Orders queue in the admin panel."
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[recipient], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send staff order notification for %s', order.order_number)
        return False


def send_order_refunded_email(order):
    """Sent to the buyer once a refund has been accepted by Paystack."""
    try:
        site = _site()
        subject = f"Order Refunded — {order.order_number}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg, #071A3D 0%, #0B5CFF 55%, #38BDF8 100%);
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">Order Refunded</h1>
                    </div>
                    <div style="background-color: white; padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">Dear <strong>{order.buyer_name}</strong>,</p>
                        <p>
                            Your order has been refunded. The refund has been submitted to Paystack
                            and should reflect on your original payment method within a few business days,
                            depending on your bank.
                        </p>

                        <div style="background-color: #EAF6FF; padding: 20px; border-radius: 8px; margin: 25px 0;">
                            <p style="margin: 0;"><strong>Order Number:</strong> {order.order_number}</p>
                            <p style="margin: 5px 0 0;"><strong>Refunded Amount:</strong> NGN {intcomma(int(order.amount))}</p>
                        </div>

                        {f'<p><strong>Reason:</strong> {order.refund_reason}</p>' if order.refund_reason else ''}

                        <p style="margin-top: 30px;">
                            If you have any questions about this refund, please get in touch.
                        </p>

                        <p>
                            Best regards,<br>
                            <strong style="color: #071A3D;">The {site.school_short_name} Store Team</strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = (
            f"Order Refunded — {order.order_number}\n\n"
            f"Dear {order.buyer_name},\n\n"
            f"Your order has been refunded. The refund has been submitted to Paystack and should "
            f"reflect on your original payment method within a few business days.\n\n"
            f"Order Number: {order.order_number}\n"
            f"Refunded Amount: NGN {intcomma(int(order.amount))}\n"
            + (f"Reason: {order.refund_reason}\n" if order.refund_reason else '')
            + f"\nBest regards,\nThe {site.school_short_name} Store Team"
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[order.buyer_email], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send refund email for %s', order.order_number)
        return False


def send_refund_request_staff_notification(order):
    """Sent to CONTACT_EMAIL when a customer submits a cancel/refund
    request — staff must review and approve/reject it from the admin order
    detail page; this email never triggers the refund itself."""
    recipient = getattr(settings, 'CONTACT_EMAIL', '')
    if not recipient:
        return False
    try:
        subject = f"Refund request — {order.order_number}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #071A3D;">Customer Requested a Cancellation / Refund</h2>
                <p>A customer has asked to cancel/refund an order. This requires your review — nothing has been refunded yet.</p>

                <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                    <tr>
                        <td style="padding: 8px; font-weight: bold; width: 150px;">Order Number:</td>
                        <td style="padding: 8px;">{order.order_number}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Buyer:</td>
                        <td style="padding: 8px;">{order.buyer_name} ({order.buyer_email})</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Amount:</td>
                        <td style="padding: 8px;">NGN {intcomma(int(order.amount))}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold;">Current Status:</td>
                        <td style="padding: 8px;">{order.get_status_display()}</td>
                    </tr>
                </table>

                <h3>Customer's Reason</h3>
                <div style="background-color: #f9fafb; padding: 15px; border-radius: 5px; border-left: 3px solid #0B5CFF; white-space: pre-wrap;">{order.refund_request_reason}</div>

                <p style="margin-top: 20px;">Review and approve or reject this request from the Store &rsaquo; Orders queue in the admin panel.</p>
            </body>
        </html>
        """

        text_content = (
            f"Customer requested a cancellation/refund for {order.order_number}\n\n"
            f"Buyer: {order.buyer_name} ({order.buyer_email})\n"
            f"Amount: NGN {intcomma(int(order.amount))}\n"
            f"Current Status: {order.get_status_display()}\n\n"
            f"Customer's Reason:\n{order.refund_request_reason}\n\n"
            f"Review and approve or reject this request from the Store > Orders queue in the admin panel."
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[recipient], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send refund request notification for %s', order.order_number)
        return False


def send_refund_request_rejected_email(order):
    """Sent to the buyer when staff decline their cancel/refund request."""
    try:
        site = _site()
        subject = f"About your refund request — {order.order_number}"

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
                    <div style="background: linear-gradient(135deg, #071A3D 0%, #0B5CFF 55%, #38BDF8 100%);
                                padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0;">Update on Your Request</h1>
                    </div>
                    <div style="background-color: white; padding: 30px; margin-top: 20px;">
                        <p style="font-size: 16px;">Dear <strong>{order.buyer_name}</strong>,</p>
                        <p>
                            We've reviewed your cancellation/refund request for order
                            <strong>{order.order_number}</strong> and are unable to approve it at this time.
                        </p>

                        {f'<div style="background-color: #f9fafb; padding: 15px; border-radius: 5px; border-left: 3px solid #0B5CFF;"><strong>Reason:</strong> {order.refund_reason}</div>' if order.refund_reason else ''}

                        <p style="margin-top: 20px;">
                            If you believe this was a mistake or have more information to share, please reach out to us directly.
                        </p>

                        <p>
                            Best regards,<br>
                            <strong style="color: #071A3D;">The {site.school_short_name} Store Team</strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        text_content = (
            f"About your refund request — {order.order_number}\n\n"
            f"Dear {order.buyer_name},\n\n"
            f"We've reviewed your cancellation/refund request for order {order.order_number} and are "
            f"unable to approve it at this time.\n\n"
            + (f"Reason: {order.refund_reason}\n\n" if order.refund_reason else '')
            + f"If you believe this was a mistake or have more information to share, please reach out to us directly.\n\n"
            f"Best regards,\nThe {site.school_short_name} Store Team"
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[order.buyer_email], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send refund-rejected email for %s', order.order_number)
        return False


def send_store_password_reset_email(request, user):
    """Send a password-reset link for a store account. Mirrors
    apps.eduweb.emailservices.send_password_reset_email's shape exactly
    (same UserProfile.generate_password_reset_token()/1-hour expiry), just
    pointed at store:reset_password instead of eduweb:reset_password —
    the store has its own login, so it needs its own reset link target.
    Returns bool success, matching every other function in this module."""
    try:
        site    = _site()
        profile = user.profile
        token   = profile.generate_password_reset_token()
        reset_url = request.build_absolute_uri(
            reverse('store:reset_password', kwargs={'token': str(token)})
        )

        subject = f'Reset Your {site.school_short_name} Store Password'

        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
              <div style="background: linear-gradient(135deg, #071A3D 0%, #0B5CFF 55%, #38BDF8 100%);
                          padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 Password Reset</h1>
              </div>
              <div style="background-color: white; padding: 30px; margin-top: 20px;">
                <p style="font-size: 16px;">
                  Dear <strong>{user.get_full_name() or user.username}</strong>,
                </p>
                <p>
                  We received a request to reset your {site.school_short_name} Store account password.
                  Click the button below to set a new password.
                </p>
                <div style="text-align: center; margin: 30px 0;">
                  <a href="{reset_url}"
                     style="display: inline-block; padding: 15px 40px;
                            background: linear-gradient(135deg, #071A3D 0%, #0B5CFF 55%, #38BDF8 100%);
                            color: white; text-decoration: none; border-radius: 8px;
                            font-weight: bold;">
                    Reset Password
                  </a>
                </div>
                <p style="color: #6b7280; font-size: 13px;">
                  This link expires in 1 hour. If you didn't request this, you can safely ignore this email.
                </p>
              </div>
            </div>
          </body>
        </html>
        """

        text_content = (
            f"Reset your {site.school_short_name} Store password\n\n"
            f"Dear {user.get_full_name() or user.username},\n\n"
            f"We received a request to reset your {site.school_short_name} Store account password. "
            f"Visit the link below to set a new password (expires in 1 hour):\n\n"
            f"{reset_url}\n\n"
            f"If you didn't request this, you can safely ignore this email."
        )

        connection, from_email = _resolve_sender('store')
        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email,
            to=[user.email], connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send store password reset email for %s', user.email)
        return False
