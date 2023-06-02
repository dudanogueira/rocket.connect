import datetime
import json
import logging
import uuid

import requests
from django.apps import apps
from django.conf import settings
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from envelope.models import Message
from rocketchat_API.APIExceptions.RocketExceptions import RocketAuthenticationException
from rocketchat_API.rocketchat import RocketChat

logger = logging.getLogger(__name__)


def random_string(size=20):
    return uuid.uuid4().hex[:size].upper()


class Server(models.Model):
    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    SERVER_TYPE = (
        ("rocketchat", "Rocket.Chat"),
        ("chatwoot", "Chatwoot"),
    )

    def get_icon(self):
        if self.type == "rocketchat":
            return static("images/rocket-chat-icon.svg")
        else:
            return static("images/chatwoot-icon.svg")

    def new_connector_url(self):
        if self.type == "rocketchat":
            return reverse(
                "instance:new_rocketchat_connector", args=[self.external_token]
            )
        else:
            return reverse(
                "instance:new_chatwoot_connector", args=[self.external_token]
            )

    def __str__(self):
        return self.name

    def status(self):
        if self.type == "rocketchat":
            auth_error = False
            alive = False
            info = []
            try:
                client = self.get_rocket_client()
                alive = True
                info = ["Version: " + client.info().json()["info"]["version"]]
                check_auth = client.users_list()
                if check_auth.status_code == 401:
                    auth_error = True
            except (
                requests.ConnectionError,
                json.JSONDecodeError,
                requests.models.MissingSchema,
            ):
                alive = False
            except RocketAuthenticationException:
                auth_error = True

        if self.type == "chatwoot":
            auth_error = False
            alive = False
            info = None
            headers = {"api_access_token": self.secret_token}
            try:
                check = requests.get(self.url + "/api/v1/profile", headers=headers)
                if check.ok:
                    alive = True
                    # register account_id
                    account_id = check.json()["account_id"]
                    account_info = requests.get(
                        self.url + f"/api/v1/accounts/{account_id}", headers=headers
                    ).json()
                    self.config["account_id"] = account_id
                    # register or create inbox
                    inboxes_request = requests.get(
                        self.url + "/api/v1/accounts/" + str(account_id) + "/inboxes",
                        headers=headers,
                    )
                    inboxes = inboxes_request.json()["payload"]
                    rocket_inbox = [
                        d
                        for d in inboxes
                        if d.get("name", "").upper() == "ROCKETCONNECT"
                    ]
                    if rocket_inbox:
                        self.config["rocketconnect_inbox_id"] = rocket_inbox[0]["id"]
                    else:
                        # create ROCKETCONNECT inbox
                        payload = {
                            "name": "ROCKETCONNECT",
                            "lock_to_single_conversation": True,
                            "channel": {
                                "type": "api",
                                "webhook_url": self.url
                                + "/server/"
                                + self.external_token
                                + "/",
                            },
                        }
                        inboxes_request = requests.post(
                            self.url
                            + "/api/v1/accounts/"
                            + str(account_id)
                            + "/inboxes",
                            headers=headers,
                            json=payload,
                        )
                    info = [
                        "ROCKETCONNECT_INBOX_ID: "
                        + str(self.config["rocketconnect_inbox_id"]),
                        "VERSION: " + account_info.get("latest_chatwoot_version"),
                    ]

                    self.save()
                if check.status_code == 401:
                    alive = True
                    auth_error = True
            except (
                requests.ConnectionError,
                json.JSONDecodeError,
                requests.models.MissingSchema,
            ):
                alive = False

        return {
            "auth_error": auth_error,
            "alive": alive,
            "info": info,
        }

    def get_rocket_client(self, bot=False):
        """
        this will return a working ROCKETCHAT_API instance
        """
        if bot:
            if self.bot_user_id and self.bot_user_token:
                rocket = RocketChat(
                    auth_token=self.bot_user_token,
                    user_id=self.bot_user_id,
                    server_url=self.url,
                )
            else:
                rocket = RocketChat(
                    self.bot_user, self.bot_password, server_url=self.url
                )
        else:
            if self.admin_user_id and self.admin_user_token:
                rocket = RocketChat(
                    auth_token=self.admin_user_token,
                    user_id=self.admin_user_id,
                    server_url=self.url,
                )

            else:
                rocket = RocketChat(
                    self.admin_user, self.admin_password, server_url=self.url
                )

        return rocket

    def get_managers(self, as_string=True):
        """
        this method will return the managers (user@1,user2,user3,#channel1,#channel2)
        and the bot. The final result should be:
        user1,user2,user3
        Obs: it will remove all channels
        """
        # remove the channels
        managers = [i for i in self.managers.split(",") if i[0] != "#"]
        managers.append(self.bot_user)
        if as_string:
            return ",".join(managers)
        return list(set(managers))

    def get_managers_channel(self, as_string=True):
        # keep only the channels
        managers_channel = [i for i in self.managers.split(",") if i[0] == "#"]
        if as_string:
            return ",".join(managers_channel)
        return list(set(managers_channel))

    def get_open_rooms(self, **kwargs):
        rocket = self.get_rocket_client()
        rooms = rocket.livechat_rooms(open="true", **kwargs)
        if rooms.ok and rooms.json().get("rooms"):
            return rooms.json()
        else:
            return []

    def get_custom_messages(self, term=None):
        messages = self.custom_messages.filter(enabled=True).values("slug", "text")
        if term:
            messages = messages.filter(
                models.Q(slug__icontains=term) | models.Q(text__icontains=term)
            )
        return messages

    def import_custom_messages(self, messages_csv_tabbed):
        # disable all messages
        self.custom_messages.all().update(enabled=False)
        for m in messages_csv_tabbed.splitlines():
            mm = m.split("\t")
            message, created = self.custom_messages.get_or_create(slug=mm[0])
            try:
                order = int(mm[1])
                text = mm[2]
            except ValueError:
                text = mm[1]
            message.text = text
            message.enabled = True
            message.order = order
            message.save()

    def room_sync(self, execute=False):
        """
        Close all open rooms not open in Rocket.Chat
        """
        open_rooms = self.get_open_rooms()
        if open_rooms:
            open_rooms = open_rooms.get("rooms", [])
        open_rooms_id = [r["_id"] for r in open_rooms]
        # get all open rooms in connector, except the actually open ones
        LiveChatRoom = apps.get_model(app_label="envelope", model_name="LiveChatRoom")
        close_rooms = LiveChatRoom.objects.filter(
            connector__server=self, open=True
        ).exclude(room_id__in=open_rooms_id)
        total = close_rooms.count()
        closed_rooms_id = close_rooms.values_list("room_id", flat=True)
        response = {"total": total, "close_rooms_id": list(closed_rooms_id)}
        if execute:
            close_room_response = close_rooms.update(open=False)
            response["executed"] = close_room_response
        return response

    def delete_delivered_messages(self, age=None, execute=False):
        if age and type(age) == int:
            now = timezone.now()
            target_date = now - datetime.timedelta(days=age)
            messages = Message.objects.filter(
                room__connector__server=self, delivered=True, created__lte=target_date
            )
            if execute:
                return messages.delete()
            else:
                return messages

    def force_delivery(self):
        """
        this method will force the intake of every undelivered message
        """
        for connector in self.connectors.all():
            connector.force_delivery()

    def multiple_connector_admin_message(self, text):
        """
        this method will send an admin message to all active connectors
        """
        output = []
        for connector in self.connectors.filter(enabled=True):
            Connector = connector.get_connector_class()
            conncetor_cls = Connector(connector, message={}, type="outgoing")
            text = f"{connector.name} > {text}"
            message_sent = conncetor_cls.outcome_admin_message(text=text)
            output.append(message_sent)
        if output and all(output):
            return True
        return False

    def get_external_url(self):
        if not self.external_url:
            return self.url
        return self.external_url

    def install_server_tasks(self):
        """
        this method will create, if not created alread,
        all the server tasks for a server, disabled by default
        """
        added_tasks = []
        # make sure with have a crontab
        crontab = CrontabSchedule.objects.first()
        if not crontab:
            crontab = CrontabSchedule.objects.create()
            crontab.hour = 4
            crontab.save()
        #
        # T1 server_maintenance
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.server_maintenance",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"General Maintenance for {self.name} (ID {self.id})."
                + "Sync rooms and Remove delivered messages (Age in days).",
                crontab=crontab,
                task="instance.tasks.server_maintenance",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "delete_delivered_messages_age": 15,
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T2 alert_last_message_open_chat
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.alert_last_message_open_chat",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Alert Open Rooms for {self.name} (ID {self.id})",
                crontab=crontab,
                task="instance.tasks.alert_last_message_open_chat",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "seconds_last_message": 30,
                        "notification_target": "#general,{{room.servedBy.username}}",
                        "notification_template": ":warning: Open Omnichannel Room for "
                        + "{{room.fname}}: {{external_url}}/omnichannel/current/{{room.id}}\n*Last Message*:"
                        + " {{room.lastMessage.msg}} - {{room.lastMessage.u.name}}/{{room.lastMessage.u.username}}"
                        + "\n*Serverd by*: @{{room.servedBy.username}}"
                        + "\n*Last Message*: {{room.lm_obj|date:'SHORT_DATETIME_FORMAT'}} (_{{room.lm_obj|timesince}}_)"
                        + "\n*Chat Started At*: {{room.ts_obj|date:'SHORT_DATETIME_FORMAT'}}"
                        + "(_{{room.ts_obj|timesince}}_)",
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T3 alert_open_rooms_generic_webhook
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.alert_open_rooms_generic_webhook",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Generic Webhook for Open Rooms for {self.name} (ID {self.id})",
                crontab=crontab,
                task="instance.tasks.alert_open_rooms_generic_webhook",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "endpoint": "https://rocketconnect.requestcatcher.com/test",
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T4 change_user_status
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.change_user_status",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Change status for {self.name} (ID {self.id})",
                crontab=crontab,
                task="instance.tasks.change_user_status",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "users": "bot",
                        "status": "online",
                        "message": "Some status",
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T5 close_abandoned_chats
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.close_abandoned_chats",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Close Abandoned Chats for {self.name} (ID {self.id})",
                description="close all open rooms that the last message from last_message_users "
                + "with more then last_message_seconds. before, send a closing_message.",
                crontab=crontab,
                task="instance.tasks.close_abandoned_chats",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "last_message_users": "bot,otherbot",
                        "last_message_seconds": 600,
                        "closing_message": "Due to inactivity, your chat is being closed.",
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T6 alert_undelivered_messages
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.alert_undelivered_messages",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Alert Undelivered Messages for {self.name} (ID {self.id})",
                description="""Alert about Undelivered messages""",
                crontab=crontab,
                task="instance.tasks.alert_undelivered_messages",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "notification_target": "general,otherchannel",
                        "notification_template": "Found {{undelivered_messages.count}} undelivered messages",
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        #
        # T7 manage_abandoned_chats
        #
        task = PeriodicTask.objects.filter(
            task="instance.tasks.manage_abandoned_chats",
            kwargs__contains=self.external_token,
        )
        if not task.exists():
            crontab = CrontabSchedule.objects.first()
            task = PeriodicTask.objects.create(
                enabled=False,
                name=f"Manage Abandoned Calls for {self.name} (ID {self.id})",
                description="""This task can transfer to department or agent"""
                + """, close or just alert the user on abandoned chats""",
                crontab=crontab,
                task="instance.tasks.manage_abandoned_chats",
                kwargs=json.dumps(
                    {
                        "server_token": self.external_token,
                        "excluded_departments": [],
                        "message_template": "This chat is abandoned",
                        "last_message_seconds": 10,
                        "last_message_users": "*",
                        "action": "transfer|close|alert",
                        "target_department_id": None,
                        "target_agent_user_id": None,
                    }
                ),
            )
            self.tasks.add(task)
            added_tasks.append(task)
        # return added tasks
        return added_tasks

    def install_omnichannel_webhook(
        self, rocketconnect_url="http://rocketconnect:5000"
    ):
        output = []
        rocket = self.get_rocket_client()
        configs = [
            [
                "Livechat_webhookUrl",
                f"{rocketconnect_url}/server/{self.external_token}/",
            ],
            ["Livechat_enabled", True],
            ["Livechat_accept_chats_with_no_agents", True],
            ["Livechat_secret_token", self.secret_token],
            ["Livechat_webhook_on_start", True],
            ["Livechat_webhook_on_close", True],
            ["Livechat_webhook_on_agent_message", True],
            ["Livechat_webhook_on_chat_taken", True],
            ["Livechat_webhook_on_chat_queued", True],
            ["Livechat_webhook_on_forward", True],
            ["Livechat_webhook_on_offline_msg", True],
            ["Accounts_TwoFactorAuthentication_Enabled", False],
            ["Accounts_TwoFactorAuthentication_By_Email_Enabled", False],
            ["Log_Level", "2"],
            ["Livechat_Routing_Method", "Manual_Selection"],
        ]
        for config in configs:
            r = rocket.settings_update(config[0], config[1])
            output.append(r)
        return output

    def install_default_wppconnect(self, name="WPPCONNECT"):
        random = random_string(size=5)
        name = f"{name} {random}"
        connector = self.connectors.create(
            name=name,
            connector_type="wppconnect",
        )
        config = {
            "webhook": f"http://rocketconnect:5000/connector/{connector.external_token}/",
            "endpoint": "http://wppconnect:21465",
            "open_room": True,
            "secret_key": "My53cr3tKY",
            "instance_name": f"wppconnect_connector_{random}",
            "enable_ack_receipt": True,
        }
        connector.config = config
        return connector.save()

    def active_chat_connectors(self):
        enabled_connectors = self.connectors.filter(enabled=True)
        supported_connectors_ids = []
        for connector in enabled_connectors:
            cls = connector.get_connector_class()
            if cls.support_active_chat:
                supported_connectors_ids.append(connector.id)
        return enabled_connectors.filter(id__in=supported_connectors_ids)

    #
    # CHATWOOT
    #

    def chatwoot_get_or_create_contact(self, visitor_json, avatar_url=None):
        identifier = visitor_json.get("token")
        headers = {"api_access_token": self.secret_token}
        payload = {
            "payload": [
                {
                    "attribute_key": "identifier",
                    "filter_operator": "equal_to",
                    "values": [identifier],
                }
            ]
        }
        url = "{}/api/v1/accounts/{}/contacts/filter".format(
            self.url, self.config.get("account_id")
        )
        contact_search = requests.post(url, headers=headers, json=payload)
        if contact_search.ok:
            # contact found
            if contact_search.json().get("payload"):
                output = contact_search.json()
                contact_status = "found"
            else:
                # contact not found, create one
                url = "{}/api/v1/accounts/{}/contacts".format(
                    self.url, self.config.get("account_id")
                )
                payload = {
                    "name": visitor_json.get("name"),
                    "identifier": visitor_json.get("token"),
                    "phone_number": "+" + visitor_json.get("phone"),
                    "avatar_url": avatar_url,
                }
                contact_new = requests.post(url, headers=headers, json=payload)
                output = contact_new.json()
                contact_status = "created"
        logger.info(
            f"CHATWOOT CONTACT ({contact_status}) URL {url} / output: {output} "
        )
        return output

    def chatwoot_get_or_create_conversation(
        self, contact_id, connector_inbox_id, identifier
    ):
        headers = {"api_access_token": self.secret_token}
        create = False
        open_item = None
        url = "{}/api/v1/accounts/{}/contacts/{}/conversations".format(
            self.url, self.config.get("account_id"), contact_id
        )
        conversations_list = requests.get(url, headers=headers)
        conversation_json = conversations_list.json()
        logger.debug(
            f"CHATWOOT CONTACT ID ({contact_id}) CONVERSATIONS {conversation_json}"
        )

        if conversations_list.ok:
            if not conversation_json.get("payload"):
                create = True
            if conversation_json.get("payload"):
                # get first open conversation from this contact
                open_item = None
                for item in conversation_json.get("payload"):
                    if (
                        item["status"] == "open"
                        and item["inbox_id"] == connector_inbox_id
                    ):
                        open_item = item
                        break
        # open new conversation
        if open_item:
            logger.debug(f"CHATWOOT GOT CONVERSATION ({open_item})")
            return open_item
        else:
            create = True
        if create:
            payload = {"inbox_id": connector_inbox_id, "contact_id": contact_id}
            url = "{}/api/v1/accounts/{}/conversations".format(
                self.url, self.config.get("account_id")
            )
            new_conversation = requests.post(url, headers=headers, json=payload).json()
            return new_conversation

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="servers", blank=True
    )
    type = models.TextField(choices=SERVER_TYPE, default="rocketchat")
    external_token = models.CharField(max_length=50, default=random_string, unique=True)
    secret_token = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="same secret_token used at Rocket.Chat Omnichannel Webhook Config",
    )
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    url = models.CharField(max_length=150)
    external_url = models.CharField(
        max_length=150,
        blank=True,
        help_text="This field is used to link to actual server. If blank, url is used.",
    )
    admin_user = models.CharField(max_length=50, blank=True)
    admin_password = models.CharField(max_length=50, blank=True)
    admin_user_id = models.CharField(
        max_length=50, blank=True, help_text="Admin User Personal Access Token"
    )
    admin_user_token = models.CharField(max_length=50, blank=True)
    bot_user = models.CharField(max_length=50, blank=True)
    bot_password = models.CharField(max_length=50, blank=True)
    bot_user_id = models.CharField(
        max_length=50, blank=True, help_text="Bot User Personal Access Token"
    )
    bot_user_token = models.CharField(max_length=50, blank=True)

    managers = models.CharField(
        max_length=50,
        help_text="separate users or channels with comma, eg: user1,user2,user3,#channel1,#channel2",
    )
    tasks = models.ManyToManyField("django_celery_beat.PeriodicTask", blank=True)
    config = models.JSONField(
        blank=True,
        null=True,
        help_text="General Config for this Server",
        default=dict,
    )
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")


class Connector(models.Model):
    class Meta:
        verbose_name = "Connector"
        verbose_name_plural = "Connector"

    def __str__(self):
        return self.name

    def get_connector_class(self):
        connector_type = self.connector_type
        # import the connector plugin
        plugin_string = f"rocket_connect.plugins.{connector_type}"
        try:
            plugin = __import__(plugin_string, fromlist=["Connector"])
        # no connector plugin, going base
        except ModuleNotFoundError:
            raise
            # plugin = __import__(
            #     'rocket_connect.plugins.base',
            #     fromlist=['Connector']

            # )
        # initiate connector plugin
        return plugin.Connector

    def get_connector_config_form(self):
        connector_type = self.connector_type
        # import the connector plugin
        plugin_string = f"rocket_connect.plugins.{connector_type}"
        try:
            plugin = __import__(plugin_string, fromlist=["ConnectorConfigForm"])
            # return form or false
            return getattr(plugin, "ConnectorConfigForm", False)
        # no form for you
        except ModuleNotFoundError:
            pass
        return False

    def status_session(self, request=None):
        """
        this method will get the possible status_session of the connector instance logic from the plugin
        """
        status = {
            "ServerType": self.server.type,
        }
        # get connector
        Connector = self.get_connector_class()
        # initiate with fake message, as it doesnt matter
        connector = Connector(self, {}, "incoming")
        if self.server.type == "chatwoot":
            status.update(
                {
                    "connector_contact_id": self.config.get(
                        "chatwoot_connector_contact_id"
                    ),
                    "connector_conversation_id": self.config.get(
                        "connector_conversation_id"
                    ),
                    "connector_inbox_id": self.config.get("connector_inbox_id"),
                }
            )

        # return initialize result
        try:
            # return informations from the connector
            status.update(connector.status_session())
            if self.config.get("include_connector_status"):
                status["connector"] = self.connector_status()
            return status
        except requests.ConnectionError:
            return {"success": False, "message": "ConnectionError"}

    def initialize(self, request=None):
        """
        this method will instantiate the connector instance logic from the plugin
        """
        status = {
            "ServerType": self.server.type,
        }
        if self.server.type == "chatwoot":
            headers = {"api_access_token": self.server.secret_token}
            # if not contact yet:
            if not self.config.get("chatwoot_connector_contact_id"):
                # check for this connector contact
                payload = {"q": self.external_token}
                search_contact = requests.get(
                    self.server.url
                    + "/api/v1/accounts/"
                    + str(self.server.config["account_id"])
                    + "/contacts/search",
                    headers=headers,
                    json=payload,
                )
                if search_contact.json().get("payload"):
                    chatwoot_connector_contact_id = (
                        search_contact.json().get("payload")[0].get("id")
                    )
                    self.config[
                        "chatwoot_connector_contact_id"
                    ] = chatwoot_connector_contact_id
                    self.save()
                else:
                    payload = {"name": self.name, "identifier": self.external_token}
                    create = requests.post(
                        self.server.url
                        + "/api/v1/accounts/"
                        + str(self.server.config["account_id"])
                        + "/contacts",
                        headers=headers,
                        json=payload,
                    )
                    if create.ok:
                        if create.json().get("payload"):
                            chatwoot_connector_contact_id = (
                                create.json().get("payload").get("id")
                            )
                            self.config[
                                "chatwoot_connector_contact_id"
                            ] = chatwoot_connector_contact_id
                            self.save()
            # if not conversation yet:
            if not self.config.get("connector_conversation_id"):
                payload = {
                    "source_id": self.external_token,
                    "inbox_id": self.server.config.get("rocketconnect_inbox_id"),
                    "contact_id": self.config.get("chatwoot_connector_contact_id"),
                    "status": "open",
                }
                create_conversation = requests.post(
                    self.server.url
                    + "/api/v1/accounts/"
                    + str(self.server.config["account_id"])
                    + "/conversations",
                    headers=headers,
                    json=payload,
                )
                if create_conversation.ok:
                    self.config[
                        "connector_conversation_id"
                    ] = create_conversation.json().get("id")
                    self.save()
            # create the connector INBOX
            if not self.config.get("connector_inbox_id"):
                payload = {
                    "name": self.name,
                    "lock_to_single_conversation": self.config.get(
                        "connector_inbox_id", False
                    ),
                    "channel": {
                        "type": "api",
                        "webhook_url": self.config.get("webhook") + "?ingoing=1",
                    },
                }
                create_inbox = requests.post(
                    self.server.url
                    + "/api/v1/accounts/"
                    + str(self.server.config["account_id"])
                    + "/inboxes",
                    headers=headers,
                    json=payload,
                )
                if create_inbox.ok:
                    self.config["connector_inbox_id"] = create_inbox.json().get("id")
                    self.save()
            status.update(
                {
                    "success": True,
                    "connector_contact_id": self.config.get(
                        "chatwoot_connector_contact_id"
                    ),
                    "connector_conversation_id": self.config.get(
                        "connector_conversation_id"
                    ),
                }
            )

        # get connector
        Connector = self.get_connector_class()
        # initiate with fake message, as it doesnt matter
        connector = Connector(self, {}, "incoming")
        # return initialize result
        connector_init = connector.initialize()
        status.update(connector_init)
        return status

    def close_session(self, request=None):
        """
        this method will instantiate the connector instance logic from the plugin
        """
        # get connector
        Connector = self.get_connector_class()
        # initiate with fake message, as it doesnt matter
        connector = Connector(self, {}, "incoming")
        # return close session result
        return connector.close_session()

    def intake(self, request):
        """
        this method will intake the raw message, and apply the connector logic
        it will also get the secondary_connectors attached to the connector
        and run it as well
        """
        # get connector
        Connector = self.get_connector_class()
        # income message
        if self.server.type == "chatwoot" and request.GET.get("ingoing"):
            # at chatwoot, both incoming and ingoing comes thru here
            connector = Connector(self, request.body, "ingoing", request)
            main_incoming = connector.ingoing()
            connector.get_room(create=False)
        else:
            # initiate with raw message
            connector = Connector(self, request.body, "incoming", request)
            main_incoming = connector.incoming()

        # secondary connectors
        for secondary_connector in self.secondary_connectors.all():
            SConnector = secondary_connector.get_connector_class()
            sconnector = SConnector(
                secondary_connector, request.body, "incoming", request
            )
            # log it
            connector.logger_info(
                "RUNING SECONDARY CONNECTOR *{}* WITH BODY {}:".format(
                    sconnector.connector, request.body
                )
            )
            sconnector.incoming()
        # return main incoming
        return main_incoming

    def outtake(self, message):
        # get connector
        Connector = self.get_connector_class()
        # initiate with raw message
        connector = Connector(self, message, "outgoing")
        # income message
        connector.outgoing()

    def inbound_intake(self, request):
        # get connector
        Connector = self.get_connector_class()
        # initiate with raw message
        connector = Connector(self, {}, "inbound")
        # handle inbound requests
        return connector.handle_inbound(request)

    def get_managers(self, as_string=True):
        """
        this method will return the managers both from server and
        connector (user1,user2,user3) or ['user1', 'user2, 'usern']
        and the bot. The final result should be:
        a string or a list, without the channels
        """
        managers = self.server.get_managers(as_string=False)
        if self.managers:
            connector_managers = [i for i in self.managers.split(",") if i[0] != "#"]
            managers.extend(connector_managers)
        managers = list(set(managers))
        if as_string:
            return ",".join(managers)
        return managers

    def get_managers_channel(self, as_string=True):
        """
        this method will return the managers channel both from server and
        connector (user1,user2,user3) or ['user1', 'user2, 'usern']
        and the bot. The final result should be:
        a string or a list, but only channels
        """
        managers = self.server.get_managers_channel(as_string=False)
        if self.managers:
            connector_managers = [i for i in self.managers.split(",") if i[0] == "#"]
            managers.extend(connector_managers)
        managers = list(set(managers))
        if as_string:
            return ",".join(managers)
        return managers

    def force_delivery(self):
        messages = self.messages.filter(delivered=False)
        for message in messages:
            message.force_delivery()

    def connector_status(self):
        """
        this method will return the status of the connector
        """
        return self.messages.aggregate(
            undelivered_messages=models.Count(
                "id",
                models.Q(delivered=False) | models.Q(delivered=None),
                distinct=True,
            ),
            total_messages=models.Count("id", distinct=True),
            open_rooms=models.Count(
                "room__id", models.Q(room__open=True), distinct=True
            ),
            total_rooms=models.Count("room__id", distinct=True),
            last_message=models.Max("created"),
            total_visitors=models.Count("room__token", distinct=True),
        )

    def room_sync(self, execute=False):
        """
        Close all open rooms not open in Rocket.Chat
        """
        rocket = self.server.get_rocket_client()
        open_rooms = rocket.livechat_rooms(open="true").json()
        open_rooms_id = [r["_id"] for r in open_rooms["rooms"]]
        # get all open rooms in connector, except the actually open ones
        close_rooms = self.rooms.filter(open=True).exclude(room_id__in=open_rooms_id)
        total = close_rooms.count()
        if execute:
            close_rooms.update(open=False)
        response = {"total": total}
        return response

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    external_token = models.CharField(max_length=50, default=random_string, unique=True)
    name = models.CharField(
        max_length=50, help_text="Connector Name, ex: LAB PHONE (+55 33 9 99851212)"
    )
    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="connectors"
    )
    connector_type = models.CharField(max_length=50)
    department = models.CharField(max_length=50, blank=True, null=True)
    managers = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="separate users or channels with comma, eg: user1,user2,user3,#channel1,#channel2",
    )
    config = models.JSONField(
        blank=True, null=True, help_text="Connector General configutarion", default=dict
    )
    secondary_connectors = models.ManyToManyField("self", blank=True)
    enabled = models.BooleanField(default=True)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")


class CustomDefaultMessages(models.Model):
    class Meta:
        verbose_name = "CustomMessages"
        verbose_name_plural = "Custom Messagess"
        ordering = ["order"]

    def __str__(self):
        return self.slug

    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="custom_messages"
    )
    enabled = models.BooleanField(default=True)
    slug = models.SlugField(blank=False, null=False)
    text = models.TextField(blank=False, null=False)
    # meta
    order = models.IntegerField(default=0)
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")
