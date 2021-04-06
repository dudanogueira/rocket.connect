from django.db import models
from instance.models import Server, Connector
import uuid


class LiveChatRoom(models.Model):

    class Meta:
        verbose_name = "Live Chat Room"
        verbose_name_plural = "Live Chat Rooms"

    def __str__(self):
        return "{0} at {1}".format(
            self.token,
            self.room_id
        )

    uuid = models.UUIDField(
        default=uuid.uuid4, editable=False
    )
    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="rooms")
    token = models.CharField(max_length=50, blank=True, null=True)
    room_id = models.CharField(max_length=50, blank=True, null=True)
    open = models.BooleanField(default=False)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created")
    updated = models.DateTimeField(
        blank=True, auto_now=True, verbose_name="Updated")


class Message(models.Model):

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = 'created',
        unique_together = [('envelope_id', 'type')]

    # STAGE TYPE CHOICES
    STAGE_CHOICES = [
        ['incoming', 'Incoming Message'],
        ['ingoing', 'Ingoing Message'],
    ]

    def get_connector(self):
        Connector = self.connector.get_connector_class()
        return Connector(self.connector, self.raw_message, self.type)

    uuid = models.UUIDField(
        default=uuid.uuid4, editable=False
    )
    type = models.CharField(max_length=50, choices=STAGE_CHOICES, default="incoming")
    envelope_id = models.CharField(max_length=100)
    room = models.ForeignKey(LiveChatRoom, on_delete=models.CASCADE, related_name="messages", blank=True, null=True)
    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="messages")
    raw_message = models.JSONField(blank=True, null=True, help_text="the message that first came to be connected")
    payload = models.JSONField(blank=True, null=True, help_text="the message that goes gout, after processed")
    response = models.JSONField(blank=True, null=True)
    delivered = models.BooleanField(null=True)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(
        blank=True, auto_now=True, verbose_name="Updated")
