from django.urls import re_path

from rocket_connect.instance.views import active_chat
from rocket_connect.instance.views import connector_analyze
from rocket_connect.instance.views import new_chatwoot_connector
from rocket_connect.instance.views import new_rocketchat_connector
from rocket_connect.instance.views import new_server
from rocket_connect.instance.views import new_server_chatwoot
from rocket_connect.instance.views import new_server_rocket_chat
from rocket_connect.instance.views import server_detail_view
from rocket_connect.instance.views import server_monitor_view

app_name = "instance"
urlpatterns = [
    re_path(
        r"^server/(?P<server_id>\w+)/monitor/?$",
        view=server_monitor_view,
        name="server_monitor",
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/?$",
        view=server_detail_view,
        name="server_detail",
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
        r"^server/(?P<server_id>\w+)/new/rocketchat/connector/?$",
        view=new_rocketchat_connector,
        name="new_rocketchat_connector",
    ),
    re_path(
        r"^server/(?P<server_id>\w+)/new/chatwoot/connector/?$",
        view=new_chatwoot_connector,
        name="new_chatwoot_connector",
    ),
    re_path(
        r"^new/server/?$",
        view=new_server,
        name="new_server",
    ),
    re_path(
        r"^new/server/rocketchat/?$",
        view=new_server_rocket_chat,
        name="new_server_rocketchat",
    ),
    re_path(
        r"^new/server/chatwoot/?$",
        view=new_server_chatwoot,
        name="new_server_chatwoot",
    ),
]
