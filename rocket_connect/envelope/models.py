import json
import uuid

from django.db import models


class LiveChatRoom(models.Model):
    class Meta:
        verbose_name = "Live Chat Room"
        verbose_name_plural = "Live Chat Rooms"

    def __str__(self):
        return f"{self.token} at {self.room_id}"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    connector = models.ForeignKey(
        "instance.Connector", on_delete=models.CASCADE, related_name="rooms"
    )
    token = models.CharField(max_length=50, blank=True, null=True)
    room_id = models.CharField(max_length=50, blank=True, null=True)
    open = models.BooleanField(default=False)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")


class Message(models.Model):
    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ("created",)
        unique_together = [("envelope_id", "type")]

    # STAGE TYPE CHOICES
    STAGE_CHOICES = [
        ["incoming", "Incoming Message"],
        ["ingoing", "Ingoing Message"],
        ["active_chat", "Active Chat"],
    ]

    def get_connector(self):
        Connector = self.connector.get_connector_class()
        message = json.dumps(self.raw_message)
        return Connector(self.connector, message, self.type)

    def force_delivery(self):
        c = self.get_connector()
        if c.type == "incoming":
            c.incoming()
        elif c.type == "active_chat":
            c.active_chat()
        else:
            c.ingoing()
        return c.message_object.delivered

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=50, choices=STAGE_CHOICES, default="incoming")
    envelope_id = models.CharField(max_length=100)
    room = models.ForeignKey(
        LiveChatRoom,
        on_delete=models.CASCADE,
        related_name="messages",
        blank=True,
        null=True,
    )
    connector = models.ForeignKey(
        "instance.Connector", on_delete=models.CASCADE, related_name="messages"
    )
    raw_message = models.JSONField(
        blank=True, null=True, help_text="the message that first came to be connected"
    )
    payload = models.JSONField(
        blank=True,
        null=True,
        help_text="the message that goes gout, after processed",
        default=dict,
    )
    response = models.JSONField(blank=True, null=True, default=dict)
    delivered = models.BooleanField(default=False)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")
