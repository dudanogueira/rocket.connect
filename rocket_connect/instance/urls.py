from django.urls import re_path

from rocket_connect.instance.views import (
    connector_analyze,
    new_connector,
    new_server,
    server_detail_view,
)

app_name = "instance"
urlpatterns = [
    re_path(
        r"^server/(?P<server_id>\w+)/?$", view=server_detail_view, name="server_detail"
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/analyze/(?P<connector_id>\w+)/?$",
        view=connector_analyze,
        name="connector_analyze",
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/new_connector/?$",
        view=new_connector,
        name="new_connector",
    ),
    re_path(
        r"^new/server/?$",
        view=new_server,
        name="new_server",
    ),
]
