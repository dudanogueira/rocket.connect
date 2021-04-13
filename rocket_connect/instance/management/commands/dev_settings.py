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
                "api_key": "super_secret_key",
                "endpoint": "http://waautomate:8002",
                "auto_answer_incoming_call": '''Sorry, this number is for text messages only.
                    Please, call to (XX) XXXX-XXXX for voice support''',
                "convert_incoming_call_to_text": "User tried to call",
                "auto_answer_on_audio_message": '''Sorry, this number do not support Audio Messages.
                        Please, call to (XX) XXXX-XXXX for voice support''',
                "convert_incoming_audio_to_text": "User sent audio"
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
                    "description": '''wa-automate department, as configured on \n
                    WA Connector at Rocket Connect (http://127.0.0.1:8000/admin/instance/connector/1/change/)'''
                },
                "agents": [{
                    "agentId": aa.json()['user']['_id'],
                    "username": aa.json()['user']['username'],
                    "count": 0,
                    "order": 0
                }]
            }
            rocket.call_api_post(
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
            ["Site_Url", "http://rocketchat:3000"],
            ["Livechat_webhookUrl", "http://django:8000/server/SERVER_EXTERNAL_TOKEN/"],
            ["Livechat_enabled", True],
            ["Livechat_accept_chats_with_no_agents", True],
            ["Livechat_secret_token", "secret_token"],
            ["Livechat_webhook_on_start", True],
            ["Livechat_webhook_on_close", True],
            ["Livechat_webhook_on_agent_message", True],
            ["Accounts_TwoFactorAuthentication_Enabled", False],
            ["Accounts_TwoFactorAuthentication_By_Email_Enabled", False],
            ["API_Enable_Rate_Limiter", False],
        ]
        for config in configs:
            rocket.settings_update(config[0], config[1])

    def handle(self, *args, **options):
        self.handle_django()
        self.handle_rocketchat()
