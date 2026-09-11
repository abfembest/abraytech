"""Paystack integration for consultation bookings — mirrors
apps/store/services.py's shape exactly (key resolution via eduweb's shared
PaymentGateway config, falling back to settings.PAYSTACK_*), just keyed to
a ConsultationBooking instead of a store Order."""

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


def initialize_transaction(booking, request):
    """Kick off a Paystack Standard checkout for `booking`. Returns the
    parsed JSON response — caller checks data.get('status') and reads
    data['data']['authorization_url']."""
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/transaction/initialize',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        json={
            'email': booking.email,
            'amount': int(booking.amount * 100),
            'currency': 'NGN',
            'reference': booking.payment_reference,
            'callback_url': request.build_absolute_uri(reverse('consultation:booking_callback')),
            'metadata': {
                'booking_id': booking.id,
                'service': booking.service.title,
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
