from django.db import migrations

# No tracked migration has ever seeded the bulk of the 'admin' role's
# StaffPermissionsMatrix defaults (only two narrow gap-fills exist: 0044 for
# finance_payroll, 0048 for finance_payments/finance_subscriptions) — the
# core admin rows only exist in the current DB from whatever untracked
# process originally populated them. Now that is_staff no longer gives
# 'admin'-role users an unconditional bypass (see 0050 and
# eduweb.security_middleware._load_permissions), every environment needs
# these baseline rows present so admin access doesn't regress to nothing.
#
# Deliberately additive-only (get_or_create, not update_or_create): if a row
# for role='admin' + this module already exists — with these values or
# custom-tuned ones — it is left completely untouched. This only fills
# genuine gaps, mirroring ROLE_DEFAULT_PERMISSIONS['admin'] in eduweb/models.py.
ADMIN_CORE_MODULE_DEFAULTS = {
    'user_management': {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'academics':       {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'lms_courses':     {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'applications':    {'can_view': True, 'can_edit': True},
    'exams':           {'can_view': True, 'can_edit': True, 'can_approve': True},
    'enrollments':     {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'finance':         {'can_view': True, 'can_edit': True, 'can_export': True},
    'communications':  {'can_view': True, 'can_create': True, 'can_delete': True},
    'blog':            {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'library':         {'can_view': True, 'can_create': True, 'can_edit': True, 'can_delete': True},
    'site_content':    {'can_view': True, 'can_edit': True},
    'security_audit':  {'can_view': True},
    'support_config':  {'can_view': True, 'can_create': True, 'can_edit': True},
    'academic_progression': {'can_view': True, 'can_edit': True, 'can_approve': True},
}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_admin_core_defaults(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    for module, true_flags in ADMIN_CORE_MODULE_DEFAULTS.items():
        field_values = {f: False for f in ALL_ACTION_FIELDS}
        field_values.update(true_flags)
        StaffPermissionsMatrix.objects.get_or_create(
            role='admin', module=module, user=None,
            defaults=field_values,
        )


def noop_reverse(apps, schema_editor):
    # Deliberately not reversed — rows created here are indistinguishable
    # from ones that may already have existed for the same role+module, so
    # there is nothing safe to delete on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0050_reset_is_staff_decouple_from_role'),
    ]

    operations = [
        migrations.RunPython(seed_admin_core_defaults, noop_reverse),
    ]
