from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "rocket_connect.instance"
    verbose_name = _("Instance")

    def ready(self):
        try:
            import rocket_connect.instance.signals  # noqa F401
        except ImportError:
            pass
