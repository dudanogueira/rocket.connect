from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
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
        # crete default 2 connectors
        connectors2create = [
            {
                "external_token": "CONNECTOR_EXTERNAL_TOKEN1",
                "endpoint": "http://waautomate1:8002",
                "name": "WA instance1",
                "manager": "agent1",
            },
            {
                "external_token": "CONNECTOR_EXTERNAL_TOKEN2",
                "endpoint": "http://waautomate2:8002",
                "name": "WA instance2",
                "manager": "agent2",
            },
        ]
        for c2c in connectors2create:

            connector, connector_created = server.connectors.get_or_create(
                external_token=c2c["external_token"]
            )
            connector.name = c2c["name"]
            connector.connector_type = "waautomate"
            connector.department = "WA-DEPARTMENT"
            connector.managers = c2c["manager"]
            connector.config = {
                "api_key": "super_secret_key",
                "endpoint": c2c["endpoint"],
                "auto_answer_incoming_call": "Sorry, this number is for text messages only! "
                + "Please, call to (XX) XXXX-XXXX for voice support",
                "convert_incoming_call_to_text": "User tried to call",
                "auto_answer_on_audio_message": "Sorry, this number do not support Audio Messages! "
                + "Please, call to (XX) XXXX-XXXX for voice support",
                "convert_incoming_audio_to_text": "User sent audio",
                "chat_after_close_action": "archive",
            }
            connector.save()
            if connector_created:
                print("CONNECTOR CREATED: ", c2c)
            else:
                print("CONNECTOR UPDATED: ", c2c)

    def handle_rocketchat(self):
        server = Server.objects.first()
        rocket = server.get_rocket_client()
        # general settings are defined at docker env
        # create agents

        for agent in ["agent1", "agent2"]:
            data = {
                "email": agent + "@agent1.com",
                "name": agent,
                "password": agent,
                "username": agent,
            }
            agent1 = rocket.users_create(**data)
            if agent1.ok and agent1.json()["success"]:
                print("Agent created: ", agent)
            # add agent1 as agent in omnichannel
            aa = {}
            aa[agent] = rocket.livechat_create_user(user_type="agent", username=agent)
            if aa[agent] and aa[agent].json()["success"]:
                print("added as agent to livechat", agent)
                # add WA-DEPARTMENT
                # todo: add all agents to departaments
                new_department = {
                    "department": {
                        "_id": "department_test",
                        "enabled": True,
                        "showOnRegistration": True,
                        "showOnOfflineForm": True,
                        "email": "wa-department@email.com",
                        "name": "WA-DEPARTMENT",
                        "description": """wa-automate department, as configured on \n
                        WA Connector at Rocket Connect (http://127.0.0.1:8000/admin/instance/connector/1/change/)""",
                    },
                    "agents": [
                        {
                            "agentId": aa[agent].json()["user"]["_id"],
                            "username": aa[agent].json()["user"]["username"],
                            "count": 0,
                            "order": 0,
                        }
                    ],
                }
                rocket.call_api_post("livechat/department", **new_department)
        # create bot
        data = {
            "email": "bot@bot.com",
            "name": "Bot",
            "password": "bot",
            "username": "bot",
            "roles": ["bot"],
            "verified": True,
        }
        bot = rocket.users_create(**data)
        if bot.ok and bot.json()["success"]:
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
            ["Livechat_webhook_on_chat_taken", True],
            ["Livechat_webhook_on_chat_queued", True],
            ["Livechat_webhook_on_forward", True],
            ["Livechat_webhook_on_offline_msg", True],
            ["Accounts_TwoFactorAuthentication_Enabled", False],
            ["Accounts_TwoFactorAuthentication_By_Email_Enabled", False],
            ["API_Enable_Rate_Limiter", False],
            ["Log_Level", "2"],
        ]
        for config in configs:
            rocket.settings_update(config[0], config[1])

    def handle(self, *args, **options):
        self.handle_django()
        self.handle_rocketchat()
