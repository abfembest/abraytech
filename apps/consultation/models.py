import datetime

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.eduweb.models import Service

# Statuses that "hold" a slot — a slot with a booking in one of these states
# is never offered to anyone else. Anything outside this list (failed /
# expired / cancelled) has released its claim on the slot. Kept at module
# level so both the DB constraint below and application code reference the
# exact same list.
ACTIVE_BOOKING_STATUSES = ['pending_payment', 'confirmed', 'paid']

# How long a "pending payment" hold survives before it's treated as
# abandoned and the slot is freed up again. Checked lazily (no background
# worker) whenever anyone next looks at that slot.
PENDING_HOLD_MINUTES = 20


class ConsultationSlot(models.Model):
    """One admin-opened block of time a visitor can book a consultation call
    into. Carries no price or topic of its own — see ConsultationOption for
    that. A slot is purely "we are free to take a call at this time";
    whichever topic/length gets booked into it, the slot itself is consumed
    for every other topic too, since staff can only be in one call at once."""

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide from the booking page without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Consultation Slot'
        verbose_name_plural = 'Consultation Slots'
        ordering = ['date', 'start_time']
        constraints = [
            models.UniqueConstraint(fields=['date', 'start_time', 'end_time'], name='unique_consultation_slot_time'),
        ]

    def __str__(self):
        return f"{self.date:%a, %d %b %Y} · {self.start_time:%I:%M %p}–{self.end_time:%I:%M %p}"

    @property
    def duration_minutes(self):
        start = datetime.datetime.combine(self.date, self.start_time)
        end = datetime.datetime.combine(self.date, self.end_time)
        return int((end - start).total_seconds() // 60)

    @property
    def start_datetime(self):
        naive = datetime.datetime.combine(self.date, self.start_time)
        return timezone.make_aware(naive) if timezone.is_naive(naive) else naive

    @property
    def is_past(self):
        return self.start_datetime <= timezone.now()

    def overlapping_slot_ids(self):
        """This slot's own id plus every other slot on the same date whose
        [start, end) time range overlaps it — e.g. a 30-min slot generated
        inside a 1hr slot's window. Different-length slots are separate rows
        (see the app docstring), so availability has to be computed across
        this whole overlapping group, not just the one row a visitor picks —
        otherwise booking a 1hr slot would leave the 30-min slots sitting
        inside it still showing as bookable, and vice versa. Also used by
        the booking view to claim a write-lock across the whole group before
        re-checking availability — see book_consultation."""
        return list(
            ConsultationSlot.objects.filter(
                date=self.date, start_time__lt=self.end_time, end_time__gt=self.start_time,
            ).values_list('pk', flat=True)
        )

    def expire_stale_hold(self):
        """Flip an abandoned pending-payment booking on this slot — or any
        slot overlapping it — to 'expired' if its hold window has passed,
        freeing the whole group back up. Cheap, lazy alternative to a
        background job — this project has no task scheduler, so staleness is
        only ever resolved the next time someone actually looks at the slot
        (rendering the picker, or trying to book it)."""
        cutoff = timezone.now() - datetime.timedelta(minutes=PENDING_HOLD_MINUTES)
        ConsultationBooking.objects.filter(
            slot_id__in=self.overlapping_slot_ids(), status='pending_payment', created_at__lt=cutoff,
        ).update(status='expired')

    @property
    def active_booking(self):
        """The booking — on this slot or on any overlapping one — that's
        currently holding this time. None means this exact stretch of time
        is genuinely free."""
        self.expire_stale_hold()
        return ConsultationBooking.objects.filter(
            slot_id__in=self.overlapping_slot_ids(), status__in=ACTIVE_BOOKING_STATUSES,
        ).order_by('created_at').first()

    @property
    def is_available(self):
        return self.is_active and not self.is_past and self.active_booking is None


def expire_stale_holds_bulk(dates=None):
    """Expire every abandoned pending-payment booking across (optionally)
    a given set of dates in one query, instead of the several separate
    UPDATEs that calling .expire_stale_hold() once per slot would run."""
    cutoff = timezone.now() - datetime.timedelta(minutes=PENDING_HOLD_MINUTES)
    qs = ConsultationBooking.objects.filter(status='pending_payment', created_at__lt=cutoff)
    if dates is not None:
        qs = qs.filter(slot__date__in=dates)
    qs.update(status='expired')


def bulk_blocking_bookings(slots):
    """Given an iterable of ConsultationSlot instances, return
    {slot.pk: blocking_booking_or_None} for the whole batch in a small,
    constant number of queries — used anywhere a whole day/range of slots
    is rendered at once (the public picker, the admin slot list), where
    calling .active_booking per slot would run ~4 queries per row (an N+1
    that gets worse as more slots are generated)."""
    slots = list(slots)
    if not slots:
        return {}

    dates = {s.date for s in slots}
    expire_stale_holds_bulk(dates)

    bookings = list(
        ConsultationBooking.objects.filter(
            slot__date__in=dates, status__in=ACTIVE_BOOKING_STATUSES,
        ).select_related('slot').order_by('created_at')
    )

    result = {}
    for slot in slots:
        result[slot.pk] = next(
            (b for b in bookings if b.slot.date == slot.date
             and b.slot.start_time < slot.end_time and b.slot.end_time > slot.start_time),
            None,
        )
    return result


class ConsultationOption(models.Model):
    """One selectable (length, price) combination for a Service topic — a
    topic can offer 30 min AND 1hr side by side (each priced separately, one
    of them free is fine too), and the visitor picks which one they want
    after picking the topic. Not every topic has to offer both; each
    (service, duration) pair exists at most once."""

    DURATION_CHOICES = [(30, '30 minutes'), (60, '1 hour')]

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='consultation_options')
    duration_minutes = models.PositiveSmallIntegerField(choices=DURATION_CHOICES)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="What this length costs (NGN, via Paystack). Leave blank for a free consultation."
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to stop offering this length without deleting its booking history.")

    class Meta:
        verbose_name = 'Consultation Option'
        verbose_name_plural = 'Consultation Options'
        ordering = ['service', 'duration_minutes']
        constraints = [
            models.UniqueConstraint(fields=['service', 'duration_minutes'], name='one_option_per_service_duration'),
        ]

    def __str__(self):
        return f"{self.service.title} — {self.get_duration_minutes_display()}"

    @property
    def is_free(self):
        return not self.price


class ConsultationBooking(models.Model):
    """One visitor's booking against a slot + (topic, length) option.
    Payment fields mirror apps.store.Order's shape (payment_reference /
    gateway_payment_id / payment_metadata) — same Paystack integration,
    reused here for an anonymous, no-login guest flow (this page actively
    redirects logged-in users away, see eduweb.decorators.check_for_auth)."""

    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('confirmed', 'Confirmed (Free)'),
        ('paid', 'Paid'),
        ('payment_failed', 'Payment Failed'),
        ('expired', 'Expired (Abandoned Payment)'),
        ('cancelled', 'Cancelled'),
    ]

    slot = models.ForeignKey(ConsultationSlot, on_delete=models.PROTECT, related_name='bookings')
    option = models.ForeignKey(ConsultationOption, on_delete=models.PROTECT, related_name='bookings')

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=150, blank=True)
    message = models.TextField(blank=True)

    # Snapshotted from option.price at booking time, same reasoning as
    # store.OrderItem.unit_price — a later price change on the option must
    # never alter what an already-made booking says it costs. Null/blank
    # means free.
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment')

    payment_reference = models.CharField(max_length=100, unique=True, blank=True, null=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    payment_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Consultation Booking'
        verbose_name_plural = 'Consultation Bookings'
        ordering = ['-created_at']
        constraints = [
            # The actual no-double-booking guarantee: the database itself
            # refuses a second active booking on the same slot, regardless
            # of timing — not an application-level check-then-write race.
            models.UniqueConstraint(
                fields=['slot'],
                condition=Q(status__in=['pending_payment', 'confirmed', 'paid']),
                name='one_active_booking_per_slot',
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.slot}"

    @property
    def is_free(self):
        return not self.amount

    @property
    def service(self):
        return self.option.service
