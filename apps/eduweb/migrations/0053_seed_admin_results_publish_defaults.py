from django.db import migrations

# New 'results_publish' module (StaffPermissionsMatrix.MODULE_CHOICES) backs the
# registrar "compile & approve results" console (management:results_publish /
# results_publish_detail) — gates whether CourseGrade.result_status can be
# flipped to 'released' so students actually see a grade. Kept as its own
# module rather than folded into 'academic_progression': releasing results to
# the whole student body is a distinct, higher-blast-radius action than
# running level-progression decisions.
#
# Mirrors 0051_seed_admin_core_module_defaults's pattern exactly — additive
# only (get_or_create), so this only fills the gap for environments that don't
# already have a custom-tuned row for role='admin' + this module.
ADMIN_RESULTS_PUBLISH_DEFAULT = {'can_view': True, 'can_edit': True, 'can_approve': True}
ALL_ACTION_FIELDS = ['can_view', 'can_create', 'can_edit', 'can_delete', 'can_approve', 'can_export']


def seed_admin_results_publish_default(apps, schema_editor):
    StaffPermissionsMatrix = apps.get_model('eduweb', 'StaffPermissionsMatrix')
    field_values = {f: False for f in ALL_ACTION_FIELDS}
    field_values.update(ADMIN_RESULTS_PUBLISH_DEFAULT)
    StaffPermissionsMatrix.objects.get_or_create(
        role='admin', module='results_publish', user=None,
        defaults=field_values,
    )


def noop_reverse(apps, schema_editor):
    # Not reversed — see 0051's identical reasoning: a row created here is
    # indistinguishable from one that may already have existed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0052_institutionalsubscription'),
    ]

    operations = [
        migrations.RunPython(seed_admin_results_publish_default, noop_reverse),
    ]
