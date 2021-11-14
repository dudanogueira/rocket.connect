from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "instance"
    verbose_name = _("Instance")

    def ready(self):
        try:
            import instance.signals  # noqa F401
        except ImportError:
            pass
