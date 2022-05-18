import json
import uuid

import requests
from django.apps import apps
from django.conf import settings
from django.db import models
from rocketchat_API.APIExceptions.RocketExceptions import RocketAuthenticationException
from rocketchat_API.rocketchat import RocketChat


def random_string():
    return uuid.uuid4().hex[:20].upper()


class Server(models.Model):
    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    def __str__(self):
        return self.name

    def status(self):
        auth_error = False
        alive = False
        info = None
        try:
            client = self.get_rocket_client()
            alive = True
            info = client.info().json()
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

    def get_open_rooms(self):
        rocket = self.get_rocket_client()
        rooms = rocket.livechat_rooms(open="true")
        if rooms.ok:
            return rooms.json()["rooms"]
        else:
            return []

    def sync_open_rooms(self, default_connector=None, filter_token=None):
        """This method will get the open rooms, filter by a word in token
        and recreate the rooms binded to the default connector.
        The idea is to help on a migration where the actual open rooms has no
        reference at Rocket Connect
        """
        rooms = self.get_open_rooms()
        for room in rooms:
            if filter_token:
                # pass if do not match filter
                if filter_token not in room.get("v", {}).get("token"):
                    pass
                else:
                    LiveChatRoom = apps.get_model("envelope.LiveChatRoom")
                    room_item, created = LiveChatRoom.objects.get_or_create(
                        connector=default_connector,
                        token=room.get("v", {}).get("token"),
                        room_id=room.get("_id", {}),
                    )
                    room_item.open = True
                    room_item.save()
                    if created:
                        print("ROOM CREATED:", room["v"]["token"])
                    else:
                        print("ROOM UPDATED:", room["v"]["token"])

    def force_delivery(self):
        """
        this method will force the intake of every undelivered message
        """
        for connector in self.connectors.all():
            connector.force_delivery()

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="servers", blank=True
    )
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
    admin_user = models.CharField(max_length=50)
    admin_password = models.CharField(max_length=50)
    admin_user_id = models.CharField(
        max_length=50, blank=True, help_text="Admin User Personal Access Token"
    )
    admin_user_token = models.CharField(max_length=50, blank=True)
    bot_user = models.CharField(max_length=50)
    bot_password = models.CharField(max_length=50)
    bot_user_id = models.CharField(
        max_length=50, blank=True, help_text="Bot User Personal Access Token"
    )
    bot_user_token = models.CharField(max_length=50, blank=True)

    managers = models.CharField(
        max_length=50,
        help_text="separate users or channels with comma, eg: user1,user2,user3,#channel1,#channel2",
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
        # get connector
        Connector = self.get_connector_class()
        # initiate with fake message, as it doesnt matter
        connector = Connector(self, {}, "incoming")
        # return initialize result
        try:
            # return informations from the connector
            status = connector.status_session()
            if self.config.get("include_connector_status"):
                status["connector"] = self.connector_status()
            return status
        except requests.ConnectionError:
            return {"success": False}

    def initialize(self, request=None):
        """
        this method will instantiate the connector instance logic from the plugin
        """
        # get connector
        Connector = self.get_connector_class()
        # initiate with fake message, as it doesnt matter
        connector = Connector(self, {}, "incoming")
        # return initialize result
        return connector.initialize()

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
        # initiate with raw message
        connector = Connector(self, request.body, "incoming", request)
        # income message
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
        blank=True, null=True, help_text="Connector General configutarion"
    )
    secondary_connectors = models.ManyToManyField("self", blank=True)
    enabled = models.BooleanField(default=True)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")
