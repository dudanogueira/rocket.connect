from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from instance.models import Server

wpp_admin_script = """// Check gist https://gist.github.com/dudanogueira/ae8e92c5071b750de405546980eba7dc"""


class Command(BaseCommand):
    help = "My shiny new management command."

    def handle_django(self):
        # create admin user
        User = get_user_model()
        admin, admin_created = User.objects.get_or_create(username="admin")
        # avoid touching created admin
        if admin_created:
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
        # create default server tasks
        installed_tasks = server.install_server_tasks()
        print("TASKS INSTALLED: ", installed_tasks)
        #
        server.url = "http://rocketchat:3000"
        server.external_url = "http://localhost:3000"
        server.admin_user = "adminrc"
        server.admin_password = "admin"
        server.bot_user = "bot"
        server.bot_password = "bot"
        server.managers = "admin,#manager_channel"
        server.external_token = "SERVER_EXTERNAL_TOKEN"
        server.owners.add(admin)
        server.save()

        #
        # create default asterisk
        #
        connector, connector_created = server.connectors.get_or_create(
            external_token="ASTERISK_CONNECTOR"
        )
        connector.config = {
            "queue_notify_map": {"*": "admin", "5002": "agent1,agent2,#general"},
            "userevent_context_filter": ["satisfacao-atendimento"],
            "notify_voicemail_template": "You've got a new Voicemail from Caller {{CallerIDNum}} at extension "
            + "{{extension}} and time {{now|date:'SHORT_DATETIME_FORMAT'}}. You have now {{New}} new "
            + "message{{New|pluralize}} and {{Old}} old{{New|pluralize}}",
            "notify_abandoned_queue_template": "A Queue Call was abandoned by the caller just now "
            + "({{now|date:'SHORT_DATETIME_FORMAT'}}). Caller: {{CallerIDName}} <{{CallerIDNum}}> at Queue {{Queue}}."
            + "The position at queue was {{Position}} and the caller waited for {{waitseconds}}",
        }
        connector.name = "ASTERISK CONNECTOR"
        connector.connector_type = "asterisk"
        connector.managers = "agent1,manager1"
        connector.save()
        if connector_created:
            print("CONNECTOR CREATED: ", connector)
        else:
            print("CONNECTOR UPDATED: ", connector)

        #
        # create default wppconnect
        #

        connector, connector_created = server.connectors.get_or_create(
            external_token="WPP_EXTERNAL_TOKEN"
        )
        connector.config = {
            "webhook": "http://django:8000/connector/WPP_EXTERNAL_TOKEN/",
            "endpoint": "http://wppconnect:21465",
            "secret_key": "THISISMYSECURETOKEN",
            "instance_name": "test",
            "include_connector_status": True,
            "enable_ack_receipt": True,
            "outcome_attachment_description_as_new_message": True,
            "active_chat_webhook_integration_token": "WPP_ZAPIT_TOKEN",
            "session_management_token": "session_management_secret_token",
            "department_triage_payload": {
                "message": "Message for your buttons",
                "options": {
                    "title": "Title text",
                    "footer": "Footer text",
                    "useTemplateButtons": "true",
                    "buttons": [
                        {"id": "2", "phoneNumber": "5531999999999", "text": "Call Us"},
                        {
                            "id": "3",
                            "url": "https://wppconnect-team.github.io/",
                            "text": "Long Life WPPCONNECT",
                        },
                    ],
                },
            },
            "no_agent_online_alert_admin": "No agent online!. **Message**: {{body}} **From**: {{from}}",
            "session_taken_alert_template": "You are now talking with {{agent.name}}"
            + "{% if department %} at department {{department.name}}{% endif %}",
        }
        connector.name = "WPPCONNECT CONNECTOR"
        connector.connector_type = "wppconnect"
        connector.managers = "agent1,manager1"
        connector.department = "WPPCONNECT-DEPARTMENT"
        connector.save()
        if connector_created:
            print("CONNECTOR CREATED: ", connector)
        else:
            print("CONNECTOR UPDATED: ", connector)

        # create default 1 facebook connector
        connector, connector_created = server.connectors.get_or_create(
            external_token="FACEBOOK_DEV_CONNECTOR"
        )
        connector.config = {
            "verify_token": "verify_token",
            "access_token": "generate this",
            "advanced_force_close_message": {
                "wa_automate_department": "Closing message for wa_automate_department department",
                "wppconnect_department": "Closing message for wppconnect department",
            },
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

        # create default 1 meta cloud connector
        connector, connector_created = server.connectors.get_or_create(
            external_token="META_CLOUD_API_WHATSAPP"
        )
        connector.config = {
            "verify_token": "verify_token_here",
            "bearer_token": "generate this at facebook for developers",
            "endpoint": "https://graph.facebook.com/v13.0/111042638282794/",
        }
        connector.name = "META CLOUD API WHATSAPP"
        connector.connector_type = "metacloudapi_whatsapp"
        connector.managers = ""
        connector.department = "METACLOUD-DEPARTMENT"
        connector.save()
        if connector_created:
            print("CONNECTOR CREATED: ", connector)
        else:
            print("CONNECTOR UPDATED: ", connector)

    def handle_rocketchat(self):
        server = Server.objects.first()
        rocket = server.get_rocket_client()
        # lets make sure admin is user, agent and manager
        admin = rocket.users_info(username="adminrc").json()["user"]
        updates = {"roles": ["admin", "user", "livechat-manager", "livechat-agent"]}
        rocket.users_update(user_id=admin["_id"], **updates)
        # set admin as available
        data = {"status": "available", "agentId": admin["_id"]}
        rocket.call_api_post(
            "livechat/agent.status",
        )

        # general settings are defined at docker env
        # create agents

        for user in ["agent1", "agent2"]:
            data = {
                "email": user + "@email.com",
                "name": user + " Name",
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
                            "count": 0,
                            "order": 0,
                        },
                        {
                            "agentId": admin["_id"],
                            "count": 0,
                            "order": 0,
                        },
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
                            "count": 0,
                            "order": 0,
                        },
                        {
                            "agentId": admin["_id"],
                            "count": 0,
                            "order": 0,
                        },
                    ],
                }
                rocket.call_api_post("livechat/department", **new_department)
                #
                # ADD WPPCONNECT DEPARTMENT
                #
                new_department = {
                    "department": {
                        "_id": "wppconnect_department",
                        "enabled": True,
                        "showOnRegistration": True,
                        "showOnOfflineForm": True,
                        "email": "wppconnect@email.com",
                        "name": "WPPCONNECT-DEPARTMENT",
                        "description": """wppconect department created by dev_settings""",
                    },
                    "agents": [
                        {
                            "agentId": aa[user].json()["user"]["_id"],
                            "count": 0,
                            "order": 0,
                        },
                        {
                            "agentId": admin["_id"],
                            "count": 0,
                            "order": 0,
                        },
                    ],
                }
                rocket.call_api_post("livechat/department", **new_department)
                #
                # ADD META CLOUD API DEPARTMENT
                #
                new_department = {
                    "department": {
                        "_id": "metacloud_api_department",
                        "enabled": True,
                        "showOnRegistration": True,
                        "showOnOfflineForm": True,
                        "email": "metacloud@email.com",
                        "name": "METACLOUD-DEPARTMENT",
                        "description": """meta cloud department created by dev_settings""",
                    },
                    "agents": [
                        {
                            "agentId": aa[user].json()["user"]["_id"],
                            "count": 0,
                            "order": 0,
                        },
                        {
                            "agentId": admin["_id"],
                            "count": 0,
                            "order": 0,
                        },
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
            "roles": ["bot", "livechat-agent"],
            "verified": True,
        }
        bot = rocket.users_create(**data)
        rocket.livechat_create_user(user_type="manager", username="bot")
        rocket.livechat_create_user(user_type="agent", username="bot")
        if bot.ok and bot.json()["success"]:
            print("Bot user created")

        # create channels
        channel = rocket.channels_create(name="manager_channel")
        if channel.ok:
            print("channel created: ", channel)
            # invite admin to channel
            user_id = rocket.users_info(username="admin").json()["user"]["_id"]
            channel_id = channel.json()["channel"]["_id"]
            rocket.channels_invite(room_id=channel_id, user_id=user_id)
            # add admin as manager
            rocket.livechat_create_user(user_type="manager", username="admin")
            rocket.livechat_create_user(user_type="agent", username="admin")

        # create teams
        public_team = rocket.teams_create("team-public", 0)
        private_team = rocket.teams_create("team-private", 1)
        print("teams created, public n private: ", public_team, private_team)
        # configure server webhook api
        configs = [
            ["Site_Url", "http://localhost:3000"],
            ["Livechat_webhookUrl", "http://django:8000/server/SERVER_EXTERNAL_TOKEN/"],
            ["Livechat_enabled", True],
            ["Livechat_AllowedDomainsList", "localhost"],
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
            ["Livechat_Routing_Method", "Manual_Selection"],
        ]
        for config in configs:
            rocket.settings_update(config[0], config[1])

        # create if dont exist:
        integrations = rocket.call_api_get("integrations.list").json()
        existing_integrations_name = [a["name"] for a in integrations["integrations"]]
        if "WPPCONNECT ACTIVE CHAT INTEGRATION" not in existing_integrations_name:
            print("CREATING WEBHOOK FOR ZAPIT  OUTGOING")
            payload = {
                "type": "webhook-outgoing",
                "enabled": True,
                "impersonateUser": True,
                "event": "sendMessage",
                "urls": ["http://django:8000/connector/WPP_EXTERNAL_TOKEN/"],
                "triggerWords": ["zapit"],
                "targetRoom": "",
                "channel": "#manager_channel",
                "username": "rocket.cat",
                "name": "WPPCONNECT ACTIVE CHAT INTEGRATION",
                "alias": "",
                "avatar": "",
                "emoji": "",
                "scriptEnabled": False,
                "script": "",
                "retryFailedCalls": True,
                "retryCount": 6,
                "retryDelay": "powers-of-ten",
                "triggerWordAnywhere": False,
                "runOnEdits": False,
                "token": "WPP_ZAPIT_TOKEN",
            }

            c = rocket.call_api_post("integrations.create", **payload)
            print(c.json())
        else:
            print("WEBHOOK FOR ZAPIT OUTGOING ALREADY EXISTS")

        # create webhook wppconnect manager:
        if "WPPCONNECT MANAGER INTEGRATION" not in existing_integrations_name:
            print("CREATING WEBHOOK FOR WPPCONNECT MANAGER OUTGOING")
            payload = {
                "type": "webhook-outgoing",
                "enabled": True,
                "impersonateUser": True,
                "event": "sendMessage",
                "urls": ["http://django:8000/connector/WPP_EXTERNAL_TOKEN/"],
                "triggerWords": ["rc"],
                "targetRoom": "",
                "channel": "#manager_channel",
                "username": "rocket.cat",
                "name": "WPPCONNECT MANAGER INTEGRATION",
                "alias": "",
                "avatar": "",
                "emoji": "",
                "scriptEnabled": True,
                "script": wpp_admin_script,
                "retryFailedCalls": True,
                "retryCount": 6,
                "retryDelay": "powers-of-ten",
                "triggerWordAnywhere": False,
                "runOnEdits": False,
                "token": "session_management_secret_token",
            }
            c = rocket.call_api_post("integrations.create", **payload)
            print(c.json())
        else:
            print("WEBHOOK FOR ZAPIT OUTGOING ALREADY EXISTS")

    def handle(self, *args, **options):
        self.handle_django()
        self.handle_rocketchat()
