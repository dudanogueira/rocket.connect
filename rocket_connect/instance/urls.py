from django.urls import re_path

from rocket_connect.instance.views import connector_analyze, server_detail_view

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
]
