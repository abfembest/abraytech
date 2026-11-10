from datetime import date

from django.core.management.base import BaseCommand

from apps.eduweb.models import InstitutionalSubscription
from apps.finance.emails import send_expiry_alert


class Command(BaseCommand):
    help = 'Check subscription expiry dates and send alerts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would happen without sending emails.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = date.today()
        alerted = 0

        subs = InstitutionalSubscription.objects.filter(
            expiry_date__gt=today,
            alert_sent_date__isnull=True,
        ).exclude(alert_days_before=0)

        for sub in subs:
            if sub.days_until_expiry <= sub.alert_days_before:
                if dry_run:
                    self.stdout.write(
                        f'  [DRY-RUN] Would alert: {sub.purpose} '
                        f'(expires {sub.expiry_date}, {sub.days_until_expiry}d left)'
                    )
                else:
                    send_expiry_alert(sub)
                    sub.alert_sent_date = today
                    sub.save(update_fields=['alert_sent_date', 'updated_at'])
                    self.stdout.write(f'  Alerted: {sub.purpose} ({sub.days_until_expiry}d left)')
                alerted += 1

        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'{prefix}Done: {alerted} alert(s) sent.'))
