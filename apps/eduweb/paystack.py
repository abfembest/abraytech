"""
apps/eduweb/paystack.py

Paystack (NGN) payment gateway for the student/school payment flow —
application fees and required fees (AllRequiredPayments/FeePayment) —
offered alongside the existing Stripe (USD) flow in views.py
(create_payment_intent/confirm_payment/stripe_webhook), which this module
does not modify.

Deliberately self-contained: apps/store has its own, separate Paystack
integration (apps/store/services.py) for the product-store checkout. The
two are not shared — they just happen to read credentials from the same
PaymentGateway DB row, so switching that row's keys/active flag affects
both.

Mirrors the shape of the Stripe flow: the server computes the amount
(never trusts the client), a payment row is created 'pending' before the
gateway call, and confirmation/webhook are both idempotent via
get_or_create on gateway_payment_id — same pattern as
confirm_payment/stripe_webhook.
"""

import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .emailservices import send_certificate_ready_email
from .models import (
    AllRequiredPayments,
    ApplicationPayment,
    AuditLog,
    Certificate,
    CourseApplication,
    FeePayment,
    PaymentGateway,
    SiteConfig,
    decrypt_secret,
)
from .views import _get_client_ip

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = 'https://api.paystack.co'

# Amount mismatch is compared to the nearest Naira to absorb rounding from
# the USD->NGN quantize step, mirroring store's services._confirm_paid_order
# guard against a cheaper/forged reference being swapped in.
AMOUNT_TOLERANCE = Decimal('1.00')


# =============================================================================
# CREDENTIALS — mirrors the Stripe trio in views.py
# (_active_stripe_gateway/get_stripe_secret_key/get_stripe_public_key).
# Independent of apps/store's own copy; both just read the same
# PaymentGateway table, so there's no drift.
# =============================================================================

def _active_paystack_gateway() -> "PaymentGateway | None":
    return PaymentGateway.objects.filter(gateway_type='paystack', is_active=True).first()


def get_paystack_secret_key() -> str:
    gw = _active_paystack_gateway()
    decrypted = decrypt_secret(gw.api_secret) if gw else ''
    return decrypted or settings.PAYSTACK_SECRET_KEY


def get_paystack_public_key() -> str:
    gw = _active_paystack_gateway()
    return (gw.api_key if gw and gw.api_key else settings.PAYSTACK_PUBLIC_KEY)


FX_API_URL = 'https://open.er-api.com/v6/latest/USD'
FX_CACHE_KEY = 'eduweb:fx:usd_ngn'
FX_CACHE_TIMEOUT = 60 * 60          # 1h — open.er-api's free tier refreshes about daily anyway,
                                     # mirrors apps/widgets/services.py's proven FX pattern
FX_REQUEST_TIMEOUT = 5


def _fetch_live_usd_to_ngn_rate() -> "Decimal | None":
    """Free, no-key live USD->NGN rate (open.er-api.com), cached for
    FX_CACHE_TIMEOUT. Returns None on any failure — callers must fall back
    to SiteConfig.usd_to_ngn_rate rather than raising into a payment flow."""
    cached = cache.get(FX_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        response = requests.get(FX_API_URL, timeout=FX_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    rate = data.get('rates', {}).get('NGN')
    if not rate:
        return None

    rate = Decimal(str(rate)).quantize(Decimal('0.01'))
    cache.set(FX_CACHE_KEY, rate, FX_CACHE_TIMEOUT)
    return rate


def get_usd_to_ngn_rate() -> Decimal:
    """Rate precedence:
    1. SiteConfig.usd_to_ngn_rate, if use_manual_usd_to_ngn_rate is checked
       — a deliberate admin override; the live lookup is skipped entirely.
    2. The live rate (cached up to 1h) from open.er-api.com.
    3. SiteConfig.usd_to_ngn_rate again, this time as a downtime fallback
       (live lookup failed and no override was requested).
    4. A hardcoded last resort, if SiteConfig itself doesn't exist yet.
    """
    site_config = SiteConfig.get()

    if site_config and site_config.use_manual_usd_to_ngn_rate and site_config.usd_to_ngn_rate:
        return site_config.usd_to_ngn_rate

    live_rate = _fetch_live_usd_to_ngn_rate()
    if live_rate is not None:
        return live_rate

    if site_config and site_config.usd_to_ngn_rate:
        return site_config.usd_to_ngn_rate
    return Decimal('1500.00')


def usd_to_ngn(usd_amount: Decimal) -> Decimal:
    return (usd_amount * get_usd_to_ngn_rate()).quantize(Decimal('0.01'))


# =============================================================================
# PAYSTACK API
# =============================================================================

def initialize(email, amount, currency, reference, metadata, callback_url=None):
    """Kick off a Paystack transaction. `amount` is in the major unit
    (Naira); converted to kobo here. Returns the parsed JSON — caller
    checks data.get('status') and reads data['data']['access_code']."""
    payload = {
        'email': email,
        'amount': int(amount * 100),
        'currency': currency,
        'reference': reference,
        'metadata': metadata,
    }
    if callback_url:
        payload['callback_url'] = callback_url
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/transaction/initialize',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        json=payload,
        timeout=15,
    )
    return response.json()


def verify(reference):
    """Verify a Paystack transaction by reference. Returns the parsed JSON
    — caller checks data.get('status') and data['data']['status'] == 'success'."""
    response = requests.get(
        f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        timeout=15,
    )
    return response.json()


def refund(reference, amount=None):
    """Issue a refund via Paystack's /refund endpoint. Omitting `amount`
    refunds the full original charge. Returns the parsed JSON response —
    caller checks data.get('status'); Paystack accepting the request just
    means it's queued for processing, not that funds have already moved."""
    payload = {'transaction': reference}
    if amount is not None:
        payload['amount'] = int(amount * 100)
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/refund',
        headers={'Authorization': f'Bearer {get_paystack_secret_key()}'},
        json=payload,
        timeout=15,
    )
    return response.json()


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    expected = hmac.new(
        get_paystack_secret_key().encode(), payload, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')


# =============================================================================
# INITIALIZE TRANSACTION
# =============================================================================

@require_POST
@login_required
def initialize_paystack_transaction(request):
    """Create a Paystack transaction for either a student fee or an
    application — the Paystack counterpart to create_payment_intent.
    Server computes the NGN-equivalent amount from
    SiteConfig.usd_to_ngn_rate; the client never supplies an amount."""
    try:
        payload = request.body.decode('utf-8')
        if not payload:
            return JsonResponse({'success': False, 'error': 'Empty request body'}, status=400)

        data           = json.loads(payload)
        application_id = data.get('application_id')
        student_fee_id = data.get('student_fee_id')

        if not application_id and not student_fee_id:
            return JsonResponse(
                {'success': False, 'error': 'Provide application_id or student_fee_id'},
                status=400,
            )

        with transaction.atomic():

            # ── Student fee ───────────────────────────────────────────────
            if student_fee_id:
                fee        = get_object_or_404(AllRequiredPayments, id=student_fee_id, is_active=True)
                ngn_amount = usd_to_ngn(fee.amount)

                existing = FeePayment.objects.filter(
                    fee=fee, user=request.user
                ).select_for_update().first()
                if existing and existing.status == 'success':
                    return JsonResponse({'success': False, 'error': 'Payment already made'}, status=400)

                reference = f"FEE{fee.id}-{uuid.uuid4().hex[:10].upper()}"
                result = initialize(
                    email=request.user.email,
                    amount=ngn_amount,
                    currency='NGN',
                    reference=reference,
                    metadata={
                        'type':           'student_fee',
                        'student_fee_id': str(fee.id),
                        'purpose':        fee.purpose,
                        'user_id':        request.user.id,
                    },
                )
                if not result.get('status'):
                    return JsonResponse(
                        {'success': False, 'error': result.get('message', 'Could not start Paystack payment')},
                        status=400,
                    )

                if existing:
                    existing.gateway_payment_id = reference
                    existing.amount             = ngn_amount
                    existing.currency           = 'NGN'
                    existing.gateway            = 'paystack'
                    existing.status             = 'pending'
                    existing.payment_metadata   = result['data']
                    existing.save(update_fields=[
                        'gateway_payment_id', 'amount', 'currency', 'gateway', 'status', 'payment_metadata',
                    ])
                else:
                    FeePayment.objects.create(
                        fee=fee,
                        user=request.user,
                        gateway=            'paystack',
                        gateway_payment_id= reference,
                        amount=             ngn_amount,
                        currency=           'NGN',
                        status=             'pending',
                        payment_metadata=   result['data'],
                    )
                return JsonResponse({
                    'success':    True,
                    'access_code': result['data']['access_code'],
                    'reference':  reference,
                    'public_key': get_paystack_public_key(),
                })

            # ── Application payment ─────────────────────────────────────────
            application = get_object_or_404(
                CourseApplication,
                application_id__iexact=application_id,
                user=request.user,
            )
            if application.is_paid:
                return JsonResponse({'success': False, 'error': 'Application already paid'}, status=400)

            ngn_amount = usd_to_ngn(application.application_fee)

            existing = ApplicationPayment.objects.filter(
                application=application
            ).select_for_update().first()
            if existing and existing.status == 'success':
                return JsonResponse({'success': False, 'error': 'Payment already made'}, status=400)

            reference = f"APP-{application.application_id}-{uuid.uuid4().hex[:8].upper()}"
            result = initialize(
                email=request.user.email,
                amount=ngn_amount,
                currency='NGN',
                reference=reference,
                metadata={
                    'type':           'application',
                    'application_id': application.application_id,
                    'user_id':        request.user.id,
                },
            )
            if not result.get('status'):
                return JsonResponse(
                    {'success': False, 'error': result.get('message', 'Could not start Paystack payment')},
                    status=400,
                )

            if existing:
                existing.gateway_payment_id = reference
                existing.amount             = ngn_amount
                existing.currency           = 'NGN'
                existing.gateway            = 'paystack'
                existing.status             = 'pending'
                existing.save(update_fields=[
                    'gateway_payment_id', 'amount', 'currency', 'gateway', 'status',
                ])
            else:
                ApplicationPayment.objects.create(
                    application=        application,
                    gateway=            'paystack',
                    gateway_payment_id= reference,
                    amount=             ngn_amount,
                    currency=           'NGN',
                    status=             'pending',
                )
            return JsonResponse({
                'success':    True,
                'access_code': result['data']['access_code'],
                'reference':  reference,
                'public_key': get_paystack_public_key(),
            })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception:
        logger.exception("initialize_paystack_transaction failed")
        return JsonResponse({'success': False, 'error': 'Unable to start payment'}, status=500)


# =============================================================================
# CONFIRM PAYMENT — the Paystack counterpart to confirm_payment. Always
# independently re-verifies with Paystack's API rather than trusting the
# client, and checks the verified amount/currency against what was
# expected before crediting anything (same guard store's
# _confirm_paid_order already uses).
# =============================================================================

@require_POST
@login_required
def confirm_paystack_payment(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    reference = data.get('reference')
    if not reference:
        return JsonResponse({'success': False, 'error': 'Missing reference'}, status=400)

    result = verify(reference)
    if not result.get('status') or result.get('data', {}).get('status') != 'success':
        return JsonResponse({'success': False, 'error': 'Payment not successful'}, status=400)

    tx            = result['data']
    metadata      = tx.get('metadata') or {}
    payment_type  = metadata.get('type')
    paid_amount   = Decimal(tx.get('amount', 0)) / Decimal(100)
    paid_currency = (tx.get('currency') or '').upper()

    # ── Student fee ───────────────────────────────────────────────────────
    if payment_type == 'student_fee':
        student_fee_id = metadata.get('student_fee_id')
        if not student_fee_id:
            return JsonResponse(
                {'success': False, 'error': 'student_fee_id missing in transaction'},
                status=400,
            )
        try:
            fee = AllRequiredPayments.objects.get(id=student_fee_id)
        except AllRequiredPayments.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Fee not found'}, status=404)

        expected_amount = usd_to_ngn(fee.amount)
        if paid_currency != 'NGN' or abs(paid_amount - expected_amount) > AMOUNT_TOLERANCE:
            logger.warning(
                'Paystack amount/currency mismatch for fee %s: expected NGN %s, got %s %s',
                fee.id, expected_amount, paid_currency, paid_amount,
            )
            return JsonResponse({'success': False, 'error': 'Payment amount mismatch'}, status=400)

        with transaction.atomic():
            payment, created = FeePayment.objects.select_for_update().get_or_create(
                gateway_payment_id=reference,
                defaults={
                    'fee':              fee,
                    'user':             request.user,
                    'gateway':          'paystack',
                    'amount':           paid_amount,
                    'currency':         paid_currency,
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
                    f'for "{fee.purpose}" (Paystack transaction {reference}).'
                ),
                ip_address=_get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )

            if created and 'certificate' in fee.purpose.lower():
                try:
                    pending_cert = Certificate.objects.filter(
                        student=request.user, payment_status='unpaid',
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

    # ── Application payment ─────────────────────────────────────────────────
    application_id = metadata.get('application_id')
    if not application_id:
        return JsonResponse(
            {'success': False, 'error': 'Application ID missing in transaction'},
            status=400,
        )

    try:
        application = CourseApplication.objects.get(
            application_id=application_id, user=request.user,
        )
    except CourseApplication.DoesNotExist:
        return JsonResponse(
            {'success': False, 'error': 'Application not found or access denied'},
            status=404,
        )

    expected_amount = usd_to_ngn(application.application_fee)
    if paid_currency != 'NGN' or abs(paid_amount - expected_amount) > AMOUNT_TOLERANCE:
        logger.warning(
            'Paystack amount/currency mismatch for application %s: expected NGN %s, got %s %s',
            application.application_id, expected_amount, paid_currency, paid_amount,
        )
        return JsonResponse({'success': False, 'error': 'Payment amount mismatch'}, status=400)

    # Idempotency: handle duplicate confirm calls (e.g. webhook raced us)
    payment = ApplicationPayment.objects.filter(gateway_payment_id=reference).first()
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
                    f'application fee for {application.application_id} (Paystack transaction {reference}).'
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
            gateway_payment_id=reference,
            defaults={
                'application':      application,
                'gateway':          'paystack',
                'amount':           paid_amount,
                'currency':         paid_currency,
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
                f'application fee for {application.application_id} (Paystack transaction {reference}).'
            ),
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

    return JsonResponse({
        'success':      True,
        'payment_id':   payment.id,
        'redirect_url': reverse('eduweb:application_status'),
    })


# =============================================================================
# WEBHOOK — mirrors eduweb:stripe_webhook's shape (verify signature, handle
# a successful charge, idempotent get_or_create). Separate from the
# store app's own store:paystack_webhook, which only handles Order.
# =============================================================================

@csrf_exempt
def paystack_webhook(request):
    signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
    if not verify_webhook_signature(request.body, signature):
        logger.warning("Paystack webhook signature mismatch (eduweb)")
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        logger.warning("Paystack webhook: could not parse payload (eduweb)")
        return HttpResponse(status=400)

    if event.get('event') != 'charge.success':
        return HttpResponse(status=200)

    tx            = event.get('data', {})
    reference     = tx.get('reference')
    metadata      = tx.get('metadata') or {}
    payment_type  = metadata.get('type')
    paid_amount   = Decimal(tx.get('amount', 0)) / Decimal(100)
    paid_currency = (tx.get('currency') or '').upper()

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
                gateway_payment_id=reference,
                defaults={
                    'fee':              fee,
                    'user_id':          metadata.get('user_id'),
                    'gateway':          'paystack',
                    'amount':           paid_amount,
                    'currency':         paid_currency,
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
                    f'Paystack webhook confirmed payment of {payment.currency} {payment.amount} '
                    f'for "{fee.purpose}" (Paystack transaction {reference}).'
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
                gateway_payment_id=reference,
                defaults={
                    'application':      application,
                    'gateway':          'paystack',
                    'amount':           paid_amount,
                    'currency':         paid_currency,
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
                    f'Paystack webhook confirmed payment of {payment.currency} {payment.amount} '
                    f'application fee for {application.application_id} (Paystack transaction {reference}).'
                ),
            )

    return HttpResponse(status=200)
