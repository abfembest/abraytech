import json
import time
import uuid

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.eduweb.decorators import check_for_auth
from apps.eduweb.models import Notification
from apps.eduweb.views import generate_captcha

from . import services
from .emailservices import send_booking_confirmation_email, send_staff_booking_notification
from .models import ConsultationBooking, ConsultationOption, ConsultationSlot, bulk_blocking_bookings

import logging

logger = logging.getLogger(__name__)


class _SlotUnavailable(Exception):
    """Raised inside the booking transaction.atomic() block to abort and
    roll back cleanly when the fresh, lock-protected re-check finds the slot
    (or anything overlapping it) already taken — see book_consultation."""


def _notify_admins_new_booking(booking):
    """Fan out an in-app Notification to every admin-role user, same
    pattern as apps.management.views._notify / apps.marketing's marketer
    fan-out. Silently swallows failures — a notification glitch must never
    break the booking itself."""
    try:
        link = reverse('management:consultation_bookings_list')
    except Exception:
        link = ''
    title = 'New consultation booking'
    when = f"{booking.slot.date:%d %b}, {booking.slot.start_time:%I:%M %p}"
    amount = f"₦{booking.amount:,.0f}" if booking.amount else 'Free'
    message = f"{booking.name} booked {booking.service.title} — {when} ({amount})"
    for admin_user in User.objects.filter(profile__role='admin'):
        try:
            Notification.objects.create(
                user=admin_user, notification_type='consultation',
                title=title, message=message, link=link,
            )
        except Exception:
            logger.exception('Failed to create admin notification for booking %s', booking.pk)


def _confirm_booking(booking):
    """Common tail for both the free path and the paid-confirmed path —
    fires the in-app notification and both emails exactly once."""
    _notify_admins_new_booking(booking)
    send_booking_confirmation_email(booking)
    send_staff_booking_notification(booking)


def _available_slots_payload():
    candidates = list(ConsultationSlot.objects.filter(is_active=True, date__gte=timezone.localdate()))
    blocking = bulk_blocking_bookings(candidates)
    now = timezone.now()
    available = [
        s for s in candidates
        if s.is_active and s.start_datetime > now and blocking.get(s.pk) is None
    ]
    return [
        {
            'id': s.pk,
            'label': str(s),
            'duration': s.duration_minutes,
        }
        for s in available
    ]


# =============================================================================
# BOOKING — public, anonymous. @check_for_auth actively redirects logged-in
# LMS users away (this page is for prospective clients, not students), same
# guard the old eduweb.views.consultation_booking used.
# =============================================================================

def _bookable_options():
    """Every active (topic, length) combination, grouped for the picker:
    the distinct list of topics that have at least one, plus a
    service_id -> [option, ...] map for the JS to populate the length
    dropdown once a topic is chosen."""
    options_qs = ConsultationOption.objects.filter(
        is_active=True, service__is_active=True,
    ).select_related('service').order_by('service__title', 'duration_minutes')

    services_seen = {}
    options_by_service = {}
    for option in options_qs:
        services_seen.setdefault(option.service_id, option.service)
        options_by_service.setdefault(option.service_id, []).append({
            'id': option.pk,
            'duration': option.duration_minutes,
            'label': f"{option.get_duration_minutes_display()} — "
                     f"{'Free' if option.is_free else f'₦{option.price:,.0f}'}",
        })

    topics = sorted(services_seen.values(), key=lambda s: s.title)
    return topics, options_by_service


@check_for_auth
def book_consultation(request):
    topics, options_by_service = _bookable_options()

    if request.method == 'POST':
        session_answer = request.session.get('consultation_captcha_answer')
        user_answer = request.POST.get('captcha', '').strip()
        try:
            captcha_ok = int(user_answer) == int(session_answer)
        except (ValueError, TypeError):
            captcha_ok = False

        if not captcha_ok:
            messages.error(request, 'Incorrect bot check answer. Please try again.')
            return redirect('consultation:book_consultation')

        request.session.pop('consultation_captcha_answer', None)

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        company = request.POST.get('company', '').strip()
        message_text = request.POST.get('message', '').strip()
        option_id = request.POST.get('option_id')
        slot_id = request.POST.get('slot_id')

        if not name or not email or not option_id or not slot_id:
            messages.error(request, 'Please choose a topic, a length, a time, and provide your name and email.')
            return redirect('consultation:book_consultation')

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'Please enter a valid email address.')
            return redirect('consultation:book_consultation')

        if not (option_id.isdigit() and slot_id.isdigit()):
            # Only reachable via a hand-crafted POST (the real <select>s
            # only ever submit numeric ids) — fail the same clean way as a
            # missing field rather than letting a non-numeric pk blow up as
            # an unhandled 500 from the ORM.
            messages.error(request, 'That topic/time selection looks invalid. Please pick again.')
            return redirect('consultation:book_consultation')

        option = get_object_or_404(
            ConsultationOption.objects.select_related('service'),
            pk=option_id, is_active=True, service__is_active=True,
        )
        slot = get_object_or_404(ConsultationSlot, pk=slot_id, is_active=True)

        if slot.duration_minutes != option.duration_minutes:
            messages.error(request, "That time doesn't match the length you picked. Please pick again.")
            return redirect('consultation:book_consultation')

        is_free = option.is_free
        booking = None
        db_busy = False

        # A handful of quick retries absorbs SQLite's "database is locked"
        # under simultaneous writers (see the locking note below) — that
        # error means the lock was contended, not that the slot is actually
        # taken, so retrying is the honest response; only _SlotUnavailable/
        # IntegrityError mean someone genuinely got there first.
        for attempt in range(5):
            try:
                with transaction.atomic():
                    # Force the write-lock before re-checking availability,
                    # not after: a plain read-then-create lets two requests
                    # for *different but overlapping* slots (e.g. a 1hr slot
                    # and the 30-min slot inside it) both pass the "is it
                    # free?" check before either has committed, since
                    # neither slot row alone is covered by the DB
                    # uniqueness constraint below. Updating every slot in
                    # the overlap group here is the first write in the
                    # transaction, so it's what actually claims the lock —
                    # a concurrent request for any overlapping slot blocks
                    # on this exact statement until this transaction
                    # commits or rolls back, instead of racing past the
                    # same stale read.
                    overlap_ids = slot.overlapping_slot_ids()
                    ConsultationSlot.objects.filter(pk__in=overlap_ids).update(is_active=F('is_active'))

                    slot.refresh_from_db()
                    if not slot.is_available:
                        raise _SlotUnavailable()

                    booking = ConsultationBooking.objects.create(
                        slot=slot,
                        option=option,
                        name=name,
                        email=email,
                        phone=phone,
                        company=company,
                        message=message_text,
                        amount=None if is_free else option.price,
                        currency='NGN',
                        status='confirmed' if is_free else 'pending_payment',
                        payment_reference=None if is_free else f"csl_{uuid.uuid4().hex}",
                    )
                db_busy = False
                break
            except (_SlotUnavailable, IntegrityError):
                messages.error(request, 'Sorry — that time was just taken. Please pick another.')
                return redirect('consultation:book_consultation')
            except OperationalError as e:
                if 'locked' not in str(e).lower():
                    raise
                db_busy = True
                if attempt < 4:
                    time.sleep(0.1 * (attempt + 1))

        if db_busy or booking is None:
            logger.warning('Consultation booking gave up after repeated "database is locked" retries for slot %s', slot.pk)
            messages.error(request, "We're a little busy right now — please try booking again in a moment.")
            return redirect('consultation:book_consultation')

        if is_free:
            _confirm_booking(booking)
            messages.success(
                request,
                f"Thanks, {name.split(' ')[0]} — your free consultation is confirmed. "
                f"Check your email for the details.",
            )
            return redirect('consultation:book_consultation')

        data = services.initialize_transaction(booking, request)
        if data.get('status'):
            return redirect(data['data']['authorization_url'])

        booking.status = 'payment_failed'
        booking.save(update_fields=['status'])
        messages.error(request, 'Could not start payment right now. Please try again.')
        return redirect('consultation:book_consultation')

    captcha_question, captcha_answer = generate_captcha()
    request.session['consultation_captcha_answer'] = captcha_answer

    return render(request, 'consultation.html', {
        'topics': topics,
        'options_by_service': options_by_service,
        'slots': _available_slots_payload(),
        'captcha_question': captcha_question,
    })


# =============================================================================
# PAYMENT CONFIRMATION — shared idempotent helper used by both the
# redirect-back callback and the webhook, mirroring apps.store.views'
# _confirm_paid_order so a replayed webhook or a callback-after-webhook is
# always a safe no-op.
# =============================================================================

def _confirm_paid_booking(booking, data):
    with transaction.atomic():
        booking = ConsultationBooking.objects.select_for_update().get(pk=booking.pk)
        if booking.status == 'paid':
            return booking

        if not booking.amount:
            # A free booking (or one with corrupted metadata) has no price
            # to compare against — this should be unreachable in practice
            # since free bookings never get a payment_reference to begin
            # with, but a malformed/forged webhook payload could still land
            # here, so fail safe instead of crashing on `None * 100`.
            logger.warning(
                'Paystack confirm called for consultation booking %s with no amount set', booking.pk,
            )
            return booking

        expected_kobo = int(booking.amount * 100)
        paid_kobo = data.get('amount')
        paid_currency = (data.get('currency') or '').upper()
        if paid_kobo != expected_kobo or (paid_currency and paid_currency != booking.currency):
            logger.warning(
                'Paystack amount/currency mismatch for consultation booking %s: expected %s kobo %s, got %s kobo %s',
                booking.pk, expected_kobo, booking.currency, paid_kobo, paid_currency,
            )
            booking.status = 'payment_failed'
            booking.payment_metadata = data
            booking.save(update_fields=['status', 'payment_metadata'])
            return booking

        booking.status = 'paid'
        booking.paid_at = timezone.now()
        booking.gateway_payment_id = str(data.get('id', ''))
        booking.payment_metadata = data
        booking.save(update_fields=['status', 'paid_at', 'gateway_payment_id', 'payment_metadata'])
        _confirm_booking(booking)
    return booking


def booking_callback(request):
    reference = request.GET.get('reference', '').strip()
    if not reference:
        messages.error(request, "We couldn't find that payment. Please try booking again.")
        return redirect('consultation:book_consultation')
    booking = get_object_or_404(ConsultationBooking, payment_reference=reference)
    data = services.verify_transaction(reference)

    verified = bool(data.get('status') and data.get('data', {}).get('status') == 'success')
    if verified:
        booking = _confirm_paid_booking(booking, data['data'])
        if booking.status == 'paid':
            messages.success(
                request,
                f"Thanks, {booking.name.split(' ')[0]} — your payment went through and your consultation "
                f"is confirmed. Check your email for the details.",
            )
        else:
            messages.error(request, "We couldn't confirm that payment. If you were charged, please contact us.")
    else:
        if booking.status != 'paid':
            booking.status = 'payment_failed'
            booking.save(update_fields=['status'])
        messages.error(request, "We couldn't confirm that payment. Please try booking again.")

    return redirect('consultation:book_consultation')


@csrf_exempt
@require_POST
def paystack_webhook(request):
    import hashlib
    import hmac

    signature = request.headers.get('X-Paystack-Signature', '')
    expected = hmac.new(
        services.get_paystack_secret_key().encode(), request.body, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning('Consultation Paystack webhook signature mismatch')
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except (ValueError, TypeError):
        logger.warning('Consultation Paystack webhook: could not parse payload')
        return HttpResponse(status=200)

    if event.get('event') == 'charge.success':
        reference = (event.get('data', {}).get('reference') or '').strip()
        if not reference:
            return HttpResponse(status=200)
        booking = ConsultationBooking.objects.filter(payment_reference=reference).first()
        if booking is not None:
            _confirm_paid_booking(booking, event['data'])

    return HttpResponse(status=200)
