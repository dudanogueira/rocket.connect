import uuid

from django.apps import apps
from django.conf import settings
from django.db import models
from rocketchat_API.rocketchat import RocketChat


def random_string():
    return uuid.uuid4().hex[:20].upper()


class Server(models.Model):
    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    def __str__(self):
        return self.name

    def get_rocket_client(self, bot=False):
        """
        this will return a working ROCKETCHAT_API instance
        """
        if bot:
            user = self.bot_user
            pwd = self.bot_password
        else:
            user = self.admin_user
            pwd = self.admin_password
        rocket = RocketChat(user, pwd, server_url=self.url)
        return rocket

    def get_managers(self, as_string=True):
        """
        this method will return the managers (user1,user2,user3)
        and the bot. The final result should be:
        'manager1,manager2,manager3,bot_user'
        """
        managers = self.managers.split(",")
        managers.append(self.bot_user)
        if as_string:
            return ",".join(managers)
        return managers

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
    secret_token = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    url = models.CharField(max_length=150)
    admin_user = models.CharField(max_length=50)
    admin_password = models.CharField(max_length=50)
    bot_user = models.CharField(max_length=50)
    bot_password = models.CharField(max_length=50)
    managers = models.CharField(
        max_length=50, help_text="separate users with comma, eg: user1,user2,user3"
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
        plugin_string = "rocket_connect.plugins.{0}".format(connector_type)
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

    def intake(self, request):
        """
        this method will intake the raw message, and apply the connector logic
        """
        # get connector
        Connector = self.get_connector_class()
        # initiate with raw message
        connector = Connector(self, request.body, "incoming", request)
        # income message
        return connector.incoming()

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
        a string or a list
        """
        managers = self.server.get_managers(as_string=False)
        if self.managers:
            connector_managers = self.managers.split(",")
            managers.extend(connector_managers)
        if as_string:
            return ",".join(managers)
        return managers

    def force_delivery(self):
        messages = self.messages.filter(delivered=False)
        for message in messages:
            message.force_delivery()

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
        help_text="separate users with comma, eg: user1,user2,user3",
    )
    config = models.JSONField(
        blank=True, null=True, help_text="Connector General configutarion"
    )
    enabled = models.BooleanField(default=True)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")
