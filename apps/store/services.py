"""Paystack integration — key resolution mirrors eduweb.views' Stripe trio
(_active_stripe_gateway/get_stripe_secret_key/get_stripe_public_key), and
the transaction calls it wraps."""

import logging
from urllib.parse import quote

import requests
from django.conf import settings
from django.urls import reverse

from apps.eduweb.models import PaymentGateway, decrypt_secret

PAYSTACK_BASE_URL = 'https://api.paystack.co'

logger = logging.getLogger(__name__)


def _call_paystack(method, path, **kwargs):
    """One Paystack API call. A network error, timeout or non-JSON reply
    comes back as a failed result (status False, unreachable True) instead
    of an exception, so checkout, the payment callback and staff refunds
    show a message rather than a server error."""
    try:
        response = requests.request(
            method, f'{PAYSTACK_BASE_URL}{path}',
            headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
            timeout=15, **kwargs,
        )
        return response.json()
    except (requests.RequestException, ValueError):
        logger.warning('Paystack %s %s failed', method, path, exc_info=True)
        return {
            'status': False,
            'unreachable': True,
            'message': 'Could not reach Paystack. Please try again shortly.',
        }


def _active_paystack_gateway() -> "PaymentGateway | None":
    return PaymentGateway.objects.filter(gateway_type='paystack', is_active=True).first()


def get_paystack_secret_key() -> str:
    gw = _active_paystack_gateway()
    decrypted = decrypt_secret(gw.api_secret) if gw else ''
    return decrypted or settings.PAYSTACK_SECRET_KEY


def get_paystack_public_key() -> str:
    gw = _active_paystack_gateway()
    return (gw.api_key if gw and gw.api_key else settings.PAYSTACK_PUBLIC_KEY)


def initialize_transaction(order, request):
    """Kick off a Paystack Standard checkout for `order`. Returns the parsed
    JSON response — caller checks data.get('status') and reads
    data['data']['authorization_url']."""
    return _call_paystack(
        'POST', '/transaction/initialize',
        json={
            'email': order.buyer_email,
            'amount': int(order.amount * 100),
            'currency': 'NGN',
            'reference': order.payment_reference,
            'callback_url': request.build_absolute_uri(reverse('store:checkout_callback')),
            'metadata': {
                'order_id': order.id,
                'order_number': order.order_number,
            },
        },
    )


def verify_transaction(reference):
    """Verify a Paystack transaction by reference. Returns the parsed JSON
    response — caller checks data.get('status') and
    data['data']['status'] == 'success'."""
    return _call_paystack('GET', f'/transaction/verify/{quote(str(reference), safe="")}')


def create_refund(order, amount=None):
    """Issue a refund for `order` via Paystack's /refund endpoint. Omitting
    `amount` refunds the full original charge (whole-order refund flow);
    passing `amount` (a Decimal, in the order's own currency units) issues
    a partial refund for just that much — used by the per-item Return
    flow, where only some of an order's items are being refunded. Amount
    is converted to kobo since the store is NGN/Paystack-only. Returns the
    parsed JSON response — caller checks data.get('status'); Paystack
    accepting the request just means it's queued for processing on their
    side, not that funds have already moved."""
    payload = {'transaction': order.payment_reference}
    if amount is not None:
        payload['amount'] = int(amount * 100)
    return _call_paystack('POST', '/refund', json=payload)
