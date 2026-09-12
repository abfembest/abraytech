import datetime

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.eduweb.models import Service

# Statuses that "hold" a day/time — a booking in one of these states blocks
# that stretch of time from being offered to anyone else. Anything outside
# this list (failed / expired / cancelled) has released its claim.
ACTIVE_BOOKING_STATUSES = ['pending_payment', 'confirmed', 'paid']

# How long a "pending payment" hold survives before it's treated as
# abandoned and the time is freed up again. Checked lazily (no background
# worker) whenever anyone next looks at that day.
PENDING_HOLD_MINUTES = 20

# How many days ahead the public page will ever offer, regardless of how
# far out an admin has opened a day for.
BOOKING_HORIZON_DAYS = 7


def _minutes(t):
    return t.hour * 60 + t.minute


def _time(m):
    m = max(0, min(int(m), 23 * 60 + 59))
    return datetime.time(m // 60, m % 60)


def compute_free_gaps(window_start, window_end, booked_ranges):
    """Pure interval-subtraction: given a day's open window and the
    (start, end) time ranges already booked inside it, return the list of
    still-free (start, end) gaps. No DB access — kept standalone so it's
    easy to reason about (and test) on its own."""
    w_start, w_end = _minutes(window_start), _minutes(window_end)
    if w_start >= w_end:
        return []

    merged = []
    for b_start, b_end in sorted((_minutes(s), _minutes(e)) for s, e in booked_ranges):
        b_start, b_end = max(b_start, w_start), min(b_end, w_end)
        if b_start >= b_end:
            continue
        if merged and b_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b_end))
        else:
            merged.append((b_start, b_end))

    gaps = []
    cursor = w_start
    for b_start, b_end in merged:
        if b_start > cursor:
            gaps.append((cursor, b_start))
        cursor = max(cursor, b_end)
    if cursor < w_end:
        gaps.append((cursor, w_end))

    return [(_time(s), _time(e)) for s, e in gaps]


class ConsultationDayWindow(models.Model):
    """One day an admin has explicitly opened up for consultations, and the
    hours they're available that day (e.g. 9:00 AM–5:00 PM). Not every day
    has one of these — only days admin has deliberately added are bookable
    at all, weekday or weekend. Carries no price of its own; see
    ConsultationOption for that."""

    date = models.DateField(unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True, help_text="Uncheck to close this day without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Consultation Day'
        verbose_name_plural = 'Consultation Days'
        ordering = ['date']

    def __str__(self):
        return f"{self.date:%a, %d %b %Y} · {self.start_time:%I:%M %p}–{self.end_time:%I:%M %p}"

    @property
    def is_bookable(self):
        if not self.is_active:
            return False
        today = timezone.localdate()
        return today <= self.date <= today + datetime.timedelta(days=BOOKING_HORIZON_DAYS)

    def expire_stale_holds(self):
        """Flip an abandoned pending-payment booking on this day to
        'expired' if its hold window has passed, freeing that time back up.
        Cheap, lazy alternative to a background job — this project has no
        task scheduler, so staleness is only ever resolved the next time
        someone actually looks at this day (rendering the picker, or trying
        to book it)."""
        cutoff = timezone.now() - datetime.timedelta(minutes=PENDING_HOLD_MINUTES)
        self.bookings.filter(status='pending_payment', created_at__lt=cutoff).update(status='expired')

    def free_gaps(self):
        """Still-open stretches of time today, after subtracting every
        active booking and (for today specifically) whatever time has
        already passed."""
        self.expire_stale_holds()
        window_start = self.start_time
        now = timezone.localtime()
        if self.date == now.date() and now.time() > window_start:
            window_start = now.time()

        booked = list(self.bookings.filter(status__in=ACTIVE_BOOKING_STATUSES).values_list('start_time', 'end_time'))
        return compute_free_gaps(window_start, self.end_time, booked)

    def fits(self, start_time, duration_minutes):
        """True if [start_time, start_time + duration) sits entirely inside
        one free gap — the authoritative fit check, re-run fresh (not
        trusting whatever the client last saw) right before a booking is
        created."""
        end_minutes = _minutes(start_time) + duration_minutes
        if end_minutes > _minutes(self.end_time):
            return False
        end_time = _time(end_minutes)
        return any(gap_start <= start_time and end_time <= gap_end for gap_start, gap_end in self.free_gaps())


class ConsultationOption(models.Model):
    """One selectable call length and its price — 30 min / 1hr / 1.5hr /
    2hr, each priced independently (blank = free). Global, not tied to any
    topic: what something costs depends on how long the call is, not what
    it's about."""

    DURATION_CHOICES = [(30, '30 minutes'), (60, '1 hour'), (90, '1.5 hours'), (120, '2 hours')]

    duration_minutes = models.PositiveSmallIntegerField(choices=DURATION_CHOICES, unique=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="What this length costs (NGN, via Paystack). Leave blank for a free consultation."
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to stop offering this length without deleting its booking history.")

    class Meta:
        verbose_name = 'Consultation Option'
        verbose_name_plural = 'Consultation Options'
        ordering = ['duration_minutes']

    def __str__(self):
        return f"{self.get_duration_minutes_display()} — {'Free' if self.is_free else f'₦{self.price:,.0f}'}"

    @property
    def is_free(self):
        return not self.price


class ConsultationBooking(models.Model):
    """One visitor's booking: a topic, a length/price option, and an exact
    (day, start, end) carved out of that day's open window. Payment fields
    mirror apps.store.Order's shape — same Paystack integration, reused
    here for an anonymous, no-login guest flow (this page actively
    redirects logged-in users away, see eduweb.decorators.check_for_auth)."""

    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('confirmed', 'Confirmed (Free)'),
        ('paid', 'Paid'),
        ('payment_failed', 'Payment Failed'),
        ('expired', 'Expired (Abandoned Payment)'),
        ('cancelled', 'Cancelled'),
    ]

    day_window = models.ForeignKey(ConsultationDayWindow, on_delete=models.PROTECT, related_name='bookings')
    start_time = models.TimeField()
    end_time = models.TimeField()
    option = models.ForeignKey(ConsultationOption, on_delete=models.PROTECT, related_name='bookings')
    topic = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='consultation_bookings')

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
            # A narrow DB-level backstop: two active bookings can never
            # share the exact same (day, start time). This alone doesn't
            # catch two *different* start times that overlap (e.g. 9:00 for
            # an hour vs 9:30 for 30 min) — that broader case has no simple
            # DB constraint on SQLite, so it's guarded at the application
            # level instead: see book_consultation, which locks the day
            # and re-verifies the exact requested range fits a free gap
            # before creating the row, inside the same transaction.
            models.UniqueConstraint(
                fields=['day_window', 'start_time'],
                condition=Q(status__in=['pending_payment', 'confirmed', 'paid']),
                name='one_active_booking_per_start_time',
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.day_window.date} {self.start_time:%I:%M %p}"

    @property
    def is_free(self):
        return not self.amount

    @property
    def duration_minutes(self):
        return self.option.duration_minutes
