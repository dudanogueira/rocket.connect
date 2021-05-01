from django import __version__ as DJANGO_VERSION
from django.conf import settings

from rocket_connect import __version__ as ROCKET_CONNECT_VERSION


def settings_context(_request):
    """Settings available by default to the templates context."""
    # Note: we intentionally do NOT expose the entire settings
    # to prevent accidental leaking of sensitive information
    return {
        "DEBUG": settings.DEBUG,
        "ROCKET_CONNECT_VERSION": ROCKET_CONNECT_VERSION,
        "DJANGO_VERSION": DJANGO_VERSION,
    }
