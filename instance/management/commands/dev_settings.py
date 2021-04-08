from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from instance.models import Server


class Command(BaseCommand):
    help = "My shiny new management command."

    def handle_django(self):
        # create admin user
        User = get_user_model()
        admin, admin_created = User.objects.get_or_create(username="admin")
        admin.set_password("admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()
        # create default server and default connector
        server, server_created = Server.objects.get_or_create(
            name="rocketchat_dev_server"
        )
        if server_created:
            server.url = "http://rocketchat:3000"
            server.admin_user = "admin"
            server.admin_password = "admin"
            server.bot_user = "bot"
            server.bot_password = "bot"
            server.managers = "admin"
            server.external_token = "SERVER_EXTERNAL_TOKEN"
            server.save()
        # crete default connector
        connector, connector_created = server.connectors.get_or_create(
            name="wa-automate",
            external_token="CONNECTOR_EXTERNAL_TOKEN"
        )
        if connector_created:
            connector.connector_type = "waautomate"
            connector.department = "WA-DEPARTMENT"
            connector.managers = "agent1"
            connector.config = {
                "endpoint": "http://waautomate:8080"
            }
            connector.save()

    def handle_rocketchat(self):
        server = Server.objects.first()
        rocket = server.get_rocket_client()
        # general settings are defined at docker env
        # create agent1
        data = {
            "email": "agent1@agent1.com",
            "name": "Agent 1",
            "password": "agent1",
            "username": "agent1",
        }
        agent1 = rocket.users_create(
            **data
        )
        if agent1.ok and agent1.json()['success']:
            print("Agent 1 user created")
        # add agent1 as agent in omnichannel
        aa = rocket.livechat_create_user(
            user_type="agent",
            username="agent1"
        )
        if aa.ok and aa.json()['success']:
            print("Agent 1 added as agent")
            # add WA-DEPARTMENT

            new_department = {
                "department": {
                    "_id": 'department_test',
                    "enabled": True,
                    "showOnRegistration": True,
                    "showOnOfflineForm": True,
                    "email": "wa-department@email.com",
                    "name": "WA-DEPARTMENT",
                    "description": "wa-automate department, as configured on \nWA Connector at Rocket Connect (http://127.0.0.1:8000/admin/instance/connector/1/change/)"
                },
                "agents": [{
                    "agentId": aa.json()['user']['_id'],
                    "username": aa.json()['user']['username'],
                    "count": 0,
                    "order": 0
                }]
            }
            new_dpto = rocket.call_api_post(
                "livechat/department",
                **new_department
            )
        # create bot
        data = {
            "email": "bot@bot.com",
            "name": "Bot",
            "password": "bot",
            "username": "bot",
            "roles": ['bot'],
            "verified": True
        }
        bot = rocket.users_create(
            **data
        )
        if bot.ok and bot.json()['success']:
            print("Bot user created")
        # configure server webhook api
        configs = [
            ["Livechat_webhookUrl", "http://django:8000/server/SERVER_EXTERNAL_TOKEN/"],
            ["Livechat_secret_token", "secret_token"],
            ["Livechat_webhook_on_start", True],
            ["Livechat_webhook_on_close", True],
            ["Livechat_webhook_on_agent_message", True],
        ]
        for config in configs:
            rocket.settings_update(config[0], config[1])


    def handle(self, *args, **options):
        self.handle_django()
        self.handle_rocketchat()
