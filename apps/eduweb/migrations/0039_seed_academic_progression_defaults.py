from django.db import migrations

ADMIN_DEFAULTS = {
    'academic_progression': {'can_view': True, 'can_edit': True, 'can_approve': True},
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def _seed(model, role, defaults):
    for module, true_flags in defaults.items():
        field_values = {f: False for f in ALL_ACTION_FIELDS}
        field_values.update(true_flags)
        model.objects.update_or_create(
            role=role, module=module, user=None,
            defaults=field_values,
        )


def seed_academic_progression_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    _seed(StaffPermissionsMatrix, 'admin', ADMIN_DEFAULTS)


def remove_academic_progression_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(role='admin', module__in=ADMIN_DEFAULTS.keys(), user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0038_program_min_cgpa_to_progress_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_academic_progression_defaults, remove_academic_progression_defaults),
    ]
