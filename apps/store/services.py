"""Paystack integration — key resolution mirrors eduweb.views' Stripe trio
(_active_stripe_gateway/get_stripe_secret_key/get_stripe_public_key), and
the transaction calls it wraps."""

import requests
from django.conf import settings
from django.urls import reverse

from apps.eduweb.models import PaymentGateway, decrypt_secret

PAYSTACK_BASE_URL = 'https://api.paystack.co'


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
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/transaction/initialize',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
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
        timeout=15,
    )
    return response.json()


def verify_transaction(reference):
    """Verify a Paystack transaction by reference. Returns the parsed JSON
    response — caller checks data.get('status') and
    data['data']['status'] == 'success'."""
    response = requests.get(
        f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        timeout=15,
    )
    return response.json()


def create_refund(order):
    """Issue a full refund for `order` via Paystack's /refund endpoint.
    Omitting 'amount' refunds the full original charge. Returns the parsed
    JSON response — caller checks data.get('status'); Paystack accepting
    the request just means it's queued for processing on their side, not
    that funds have already moved."""
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/refund',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        json={'transaction': order.payment_reference},
        timeout=15,
    )
    return response.json()
