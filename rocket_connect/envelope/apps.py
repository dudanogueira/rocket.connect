from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "envelope"
    verbose_name = _("Envelope")

    def ready(self):
        try:
            import envelope.signals  # noqa F401
        except ImportError:
            pass
