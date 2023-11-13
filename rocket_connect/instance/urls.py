from django.urls import re_path

from rocket_connect.instance.views import (
    active_chat,
    connector_analyze,
    new_connector,
    new_server,
    server_detail_view,
    server_monitor_view,
    macro_chat,
)

app_name = "instance"
urlpatterns = [
    re_path(
        r"^server/(?P<server_id>\w+)/monitor/?$",
        view=server_monitor_view,
        name="server_monitor",
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/?$", view=server_detail_view, name="server_detail"
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/active-chat/?$",
        view=active_chat,
        name="active_chat",
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
    re_path(
        r"^server/(?P<server_id>[^/]+)/(?P<connector_id>[^/]+)?$",
        view=macro_chat,
        name="mateus",
    ),
    
]