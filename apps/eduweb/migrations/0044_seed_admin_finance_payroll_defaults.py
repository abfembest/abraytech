from django.db import migrations

# The 'admin' role's StaffPermissionsMatrix rows were seeded (by whatever process
# originally populated them — not the dead `seed_defaults_for_role` classmethod,
# whose own dict doesn't match the live values either) with full CRUD on 'finance'
# but no row at all for 'finance_payroll'. staff_payroll_edit/staff_payroll_delete
# already gate on 'finance_payroll' specifically, so any non-superuser admin has
# been silently unable to edit or delete payroll records. Backfill the missing row.
ADMIN_FINANCE_PAYROLL_DEFAULT = {
    'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True,
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_admin_finance_payroll_default(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    field_values = {f: False for f in ALL_ACTION_FIELDS}
    field_values.update(ADMIN_FINANCE_PAYROLL_DEFAULT)
    StaffPermissionsMatrix.objects.update_or_create(
        role='admin', module='finance_payroll', user=None,
        defaults=field_values,
    )


def remove_admin_finance_payroll_default(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(role='admin', module='finance_payroll', user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0043_courseapplication_intake'),
    ]

    operations = [
        migrations.RunPython(seed_admin_finance_payroll_default, remove_admin_finance_payroll_default),
    ]
