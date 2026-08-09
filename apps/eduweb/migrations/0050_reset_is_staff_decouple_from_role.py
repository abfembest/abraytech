from django.db import migrations


def reset_is_staff(apps, schema_editor):
    """
    Historically, User.is_staff was force-synced to (profile.role == 'admin')
    by UserProfile.save() and by several management/views.py call sites (all
    removed in this change) — is_staff carried no meaning independent of role.
    Now that it's an independently-managed flag (full admin-portal bypass —
    see StaffPermissionsMatrix.ADMIN_PORTAL_MODULES), reset it to False for
    every non-superuser so it starts meaning what it's now meant to mean.
    Specific accounts that should keep unrestricted admin-portal access get
    is_staff re-granted deliberately via the user edit form afterwards.
    """
    User = apps.get_model('auth', 'User')
    User.objects.filter(is_superuser=False, is_staff=True).update(is_staff=False)


def noop_reverse(apps, schema_editor):
    # Not meaningfully reversible — the prior is_staff values were only ever
    # a derived mirror of profile.role, which is still intact on UserProfile
    # and can be used to recompute them by hand if this is ever rolled back.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('eduweb', '0049_userprofile_verification_token_created'),
    ]

    operations = [
        migrations.RunPython(reset_is_staff, noop_reverse),
    ]
