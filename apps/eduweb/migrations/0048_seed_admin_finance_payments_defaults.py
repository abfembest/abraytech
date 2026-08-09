from django.db import migrations

# Same gap as 0044 (finance_payroll), now hit again: 'admin' has full CRUD on
# the coarse 'finance' module but no row at all for 'finance_payments' or
# 'finance_subscriptions'. Required-payment create/edit/delete now lives
# solely under payment/views.py (management's duplicate CRUD was collapsed
# into it), gated on 'finance_payments' specifically — without this backfill
# every non-superuser admin would silently lose the create/edit/delete access
# they had via the old management:required_payment_* endpoints.
ADMIN_FINANCE_MODULE_DEFAULTS = {
    'finance_payments': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True, 'can_export': True},
    'finance_subscriptions': {'can_view': True, 'can_edit': True},
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_admin_finance_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    for module, true_flags in ADMIN_FINANCE_MODULE_DEFAULTS.items():
        field_values = {f: False for f in ALL_ACTION_FIELDS}
        field_values.update(true_flags)
        StaffPermissionsMatrix.objects.update_or_create(
            role='admin', module=module, user=None,
            defaults=field_values,
        )


def remove_admin_finance_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(
        role='admin', module__in=list(ADMIN_FINANCE_MODULE_DEFAULTS), user=None,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0047_courseapplication_transcript_fields'),
    ]

    operations = [
        migrations.RunPython(seed_admin_finance_defaults, remove_admin_finance_defaults),
    ]
