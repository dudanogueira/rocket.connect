from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from instance.models import Server

class Command(BaseCommand):
    help = "My shiny new management command."

    def handle(self, *args, **options):
        # create admin user
        User = get_user_model()
        admin,admin_created = User.objects.get_or_create(username="admin")
        admin.set_password("admin")
        admin.save()
        # create default server and default connector
        server,server_created = Server.objects.get_or_create(
            name="rocketchat_dev_server"
        )
        if server_created:
            server.url = "http://rocketchat:3000"
            server.admin_user = "admin"
            server.admin_password = "admin"
            server.bot_user = "bot"
            server.bot_password = "bot"
            server.managers = "debug"
            server.save()
        # crete default connector
        connector,connector_created = server.connectors.get_or_create(
            name="wa-automate",
            external_token="CONNECTOR_EXTERNAL_TOKEN"
        )
        if connector_created:
            connector.token="wa-instance1"
            connector.connector_type="waautomate"
            connector.department="WA-DEPARTMENT"
            connector.managers="agent1"
            connector.config={
                "endpoint": "http://waautomate:8080"
            }
            connector.save()


