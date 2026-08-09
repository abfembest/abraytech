from django.db import migrations

INSTRUCTOR_DEFAULTS = {
    'dashboard':                 {'can_view': True},
    'instructor_courses':        {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'instructor_assessments':    {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'instructor_analytics':      {'can_view': True, 'can_export': True},
    'instructor_resources':      {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'instructor_communications': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_instructor_role_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    for module, true_flags in INSTRUCTOR_DEFAULTS.items():
        field_values = {f: False for f in ALL_ACTION_FIELDS}
        field_values.update(true_flags)
        StaffPermissionsMatrix.objects.update_or_create(
            role='instructor', module=module, user=None,
            defaults=field_values,
        )


def remove_instructor_role_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(role='instructor', module__in=INSTRUCTOR_DEFAULTS.keys(), user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0032_instructor_role_and_modules'),
    ]

    operations = [
        migrations.RunPython(seed_instructor_role_defaults, remove_instructor_role_defaults),
    ]
