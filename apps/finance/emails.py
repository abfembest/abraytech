import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _site_context():
    try:
        from apps.eduweb.models import SiteConfig
        site = SiteConfig.get()
        return {
            'site_name': site.school_name or 'Abraytech',
            'contact_email': getattr(site, 'email_info', '') or getattr(site, 'email', ''),
        }
    except Exception:
        return {
            'site_name': 'Abraytech',
            'contact_email': getattr(settings, 'DEFAULT_FROM_EMAIL', ''),
        }


def send_expiry_alert(subscription):
    ctx = {
        **_site_context(),
        'subscription': subscription,
        'days_left': subscription.days_until_expiry,
    }

    subject = f'Subscription expiring soon: {subscription.purpose}'
    plain = (
        f'{subscription.purpose} ({subscription.provider}) expires in '
        f'{subscription.days_until_expiry} days on {subscription.expiry_date}.'
    )
    html = render_to_string('emails/subscription_expiry_alert.html', ctx)

    from_email = settings.DEFAULT_FROM_EMAIL
    to_list = [subscription.contact_email] if subscription.contact_email else []
    owner_email = getattr(settings, 'SUBSCRIPTION_ALERT_EMAIL', None)
    if owner_email and owner_email not in to_list:
        to_list.append(owner_email)

    if not to_list:
        logger.warning('No recipients for subscription expiry alert pk=%s', subscription.pk)
        return False

    try:
        msg = EmailMultiAlternatives(subject, plain, from_email, to_list)
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            'subscription_expiry_alert_failed',
            extra={'subscription_id': subscription.pk},
        )
        return False
