from django.db import migrations

FINANCE_PORTAL_DEFAULTS = {
    'finance_payments':      {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True, 'can_export': True},
    'finance_subscriptions': {'can_view': True},
    'finance_payroll':       {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_finance_portal_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    for module, true_flags in FINANCE_PORTAL_DEFAULTS.items():
        field_values = {f: False for f in ALL_ACTION_FIELDS}
        field_values.update(true_flags)
        StaffPermissionsMatrix.objects.update_or_create(
            role='finance', module=module, user=None,
            defaults=field_values,
        )


def remove_finance_portal_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(role='finance', module__in=FINANCE_PORTAL_DEFAULTS.keys(), user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0034_finance_role_modules'),
    ]

    operations = [
        migrations.RunPython(seed_finance_portal_defaults, remove_finance_portal_defaults),
    ]
