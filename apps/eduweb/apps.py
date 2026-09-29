from django.apps import AppConfig


class EduwebConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.eduweb'
    label = 'eduweb'

    def ready(self):
        from .public_cache import connect_signals
        connect_signals()
