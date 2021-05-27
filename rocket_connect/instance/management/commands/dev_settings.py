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
        admin.email = "admin@admin.com"
        admin.save()
        # create email to avoid asking at first login
        email, created = admin.emailaddress_set.get_or_create(email="admin@admin.com")
        email.verified = True
        email.primary = True
        email.save()
        # create default server and default connector
        server, server_created = Server.objects.get_or_create(
            name="rocketchat_dev_server"
        )
        if server_created:
            print("SERVER CREATED")
        else:
            print("SERVER UPDATED")
        server.url = "http://rocketchat:3000"
        server.admin_user = "admin"
        server.admin_password = "admin"
        server.bot_user = "bot"
        server.bot_password = "bot"
        server.managers = "admin"
        server.external_token = "SERVER_EXTERNAL_TOKEN"
        server.owners.add(admin)
        server.save()
        # crete default 2 WA-automate connectors
        connectors2create = [
            {
                "external_token": "CONNECTOR_EXTERNAL_TOKEN1",
                "endpoint": "http://waautomate1:8002",
                "name": "WA instance1",
                "manager": "manager1,agent1",
            },
            {
                "external_token": "CONNECTOR_EXTERNAL_TOKEN2",
                "endpoint": "http://waautomate2:8002",
                "name": "WA instance2",
                "manager": "manager2,agent2",
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
                "outcome_message_with_quoted_message": False,
                "outcome_attachment_description_as_new_message": False,
                "supress_visitor_name": False,
                "force_close_message": "This is a default closing message per connector.",
            }
            connector.save()
            if connector_created:
                print("CONNECTOR CREATED: ", c2c)
            else:
                print("CONNECTOR UPDATED: ", c2c)

        # create default 1 facebook connector
        connector, connector_created = server.connectors.get_or_create(
            external_token="FACEBOOK_DEV_CONNECTOR"
        )
        connector.config = {
            "verify_token": "verify_token",
            "access_token": "generate this",
        }
        connector.name = "FACEBOOK CONNECTOR"
        connector.connector_type = "facebook"
        connector.managers = "agent1,manager1"
        connector.department = "FACEBOOK-DEPARTMENT"
        connector.save()
        if connector_created:
            print("CONNECTOR CREATED: ", connector)
        else:
            print("CONNECTOR UPDATED: ", connector)

    def handle_rocketchat(self):
        server = Server.objects.first()
        rocket = server.get_rocket_client()
        # general settings are defined at docker env
        # create agents

        for user in ["agent1", "agent2"]:
            data = {
                "email": user + "@email.com",
                "name": user,
                "password": user,
                "username": user,
            }
            agent1 = rocket.users_create(**data)
            if agent1.ok and agent1.json()["success"]:
                print("Agent created: ", user)
            # add agent1 as agent in omnichannel
            aa = {}
            aa[user] = rocket.livechat_create_user(user_type="agent", username=user)
            if aa[user] and aa[user].json()["success"]:
                print("added as agent to livechat", user)
                # add WA-DEPARTMENT
                # todo: add all agents to departaments
                new_department = {
                    "department": {
                        "_id": "wa_automate_department",
                        "enabled": True,
                        "showOnRegistration": True,
                        "showOnOfflineForm": True,
                        "email": "wa-department@email.com",
                        "name": "WA-DEPARTMENT",
                        "description": """wa-automate department created by dev_settings""",
                    },
                    "agents": [
                        {
                            "agentId": aa[user].json()["user"]["_id"],
                            "username": aa[user].json()["user"]["username"],
                            "count": 0,
                            "order": 0,
                        }
                    ],
                }
                rocket.call_api_post("livechat/department", **new_department)
                #
                # ADD FACEBOOK DEPARTMENT
                #
                new_department = {
                    "department": {
                        "_id": "facebook_department",
                        "enabled": True,
                        "showOnRegistration": True,
                        "showOnOfflineForm": True,
                        "email": "facebook@email.com",
                        "name": "FACEBOOK-DEPARTMENT",
                        "description": """facebook department created by dev_settings""",
                    },
                    "agents": [
                        {
                            "agentId": aa[user].json()["user"]["_id"],
                            "username": aa[user].json()["user"]["username"],
                            "count": 0,
                            "order": 0,
                        }
                    ],
                }
                rocket.call_api_post("livechat/department", **new_department)

        for user in ["manager1", "manager2"]:
            data = {
                "email": user + "@email.com",
                "name": user + " Full Name",
                "password": user,
                "username": user,
            }
            agent1 = rocket.users_create(**data)
            if agent1.ok and agent1.json()["success"]:
                print("Manager created: ", user)
            # add user as Manager in omnichannel
            aa = {}
            aa[user] = rocket.livechat_create_user(user_type="manager", username=user)

        #
        # create bot
        #
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
