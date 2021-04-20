from django.urls import re_path

from rocket_connect.instance.views import server_detail_view

app_name = "instance"
urlpatterns = [
    re_path(
        r"^server/(?P<server_id>\w+)/?$", view=server_detail_view, name="server_detail"
    )
]
