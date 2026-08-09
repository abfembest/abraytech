from django.db import migrations

SUPPORT_DEFAULTS = {
    'support_tickets':        {'can_view': True, 'can_create': True, 'can_edit': True},
    'support_knowledge_base': {'can_view': True, 'can_create': True, 'can_edit': True},
    'support_communications': {'can_view': True, 'can_create': True},
    'support_analytics':      {'can_view': True},
}
ADMIN_DEFAULTS = {
    'support_config': {'can_view': True, 'can_create': True, 'can_edit': True},
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


def seed_support_portal_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    _seed(StaffPermissionsMatrix, 'support', SUPPORT_DEFAULTS)
    _seed(StaffPermissionsMatrix, 'admin', ADMIN_DEFAULTS)


def remove_support_portal_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    StaffPermissionsMatrix.objects.filter(role='support', module__in=SUPPORT_DEFAULTS.keys(), user=None).delete()
    StaffPermissionsMatrix.objects.filter(role='admin', module__in=ADMIN_DEFAULTS.keys(), user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0036_support_role_modules'),
    ]

    operations = [
        migrations.RunPython(seed_support_portal_defaults, remove_support_portal_defaults),
    ]
