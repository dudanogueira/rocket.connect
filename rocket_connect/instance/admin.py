from django.contrib import admin

from .models import Connector, CustomDefaultMessages, Server


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    actions = (
        "install_server_tasks",
        "install_omnichannel_webhooks",
        "add_default_wppconnect",
    )

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

    def install_omnichannel_webhooks(self, request, queryset):
        for server in queryset.all():
            server.install_omnichannel_webhook()
            msg = f"Omnichannel configured for server {server}"
            self.message_user(request, msg)

    def add_default_wppconnect(self, request, queryset):
        for server in queryset.all():
            server.add_default_wppconnect()
            msg = f"WPPCONNECT Connector added configured for server {server}"
            self.message_user(request, msg)

    install_server_tasks.short_description = "Install Server Tasks"
    install_omnichannel_webhooks.short_description = (
        "Install Omnichannel Webhooks (with default settings)"
    )
    add_default_wppconnect.short_description = "Add Default WPPCONNECT Connector"


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "external_token", "server", "connector_type")
    list_filter = ("server", "connector_type", "created", "updated")


@admin.register(CustomDefaultMessages)
class CustomDefaultMessagesAdmin(admin.ModelAdmin):
    list_display = ("id", "server", "slug", "text", "created", "updated")
    list_filter = ("server", "created", "updated")
    search_fields = ("slug",)
