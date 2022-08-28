from django.contrib import admin

from .models import Connector, Server


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    actions = ("install_server_tasks",)

    list_display = (
        "id",
        "name",
        "enabled",
        "url",
        "admin_user",
        "admin_password",
        "bot_user",
        "bot_password",
        "managers",
        "created",
        "updated",
    )
    list_filter = ("enabled", "created", "updated")
    search_fields = ("name",)

    def install_server_tasks(self, request, queryset):
        for server in queryset.all():
            added_tasks = server.install_server_tasks()
            msg = f"Tasks added for server {server}: {len(added_tasks)}"
            self.message_user(request, msg)

    install_server_tasks.short_description = "Install Server Tasks"


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "external_token", "server", "connector_type")
    list_filter = ("server", "connector_type", "created", "updated")
