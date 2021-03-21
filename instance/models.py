from django.db import models
import uuid

class Server(models.Model):

    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    def __str__(self):
        return self.name
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    url = models.CharField(max_length=150)
    admin_user = models.CharField(max_length=50)
    admin_password = models.CharField(max_length=50)
    bot_user = models.CharField(max_length=50)
    bot_password = models.CharField(max_length=50)
    managers = models.CharField(max_length=50, help_text="separate users with comma, eg: user1,user2,user3")
    #meta
    created = models.DateTimeField(
            blank=True, auto_now_add=True, verbose_name="Created")
    updated = models.DateTimeField(
        blank=True, auto_now=True, verbose_name="Updated")


class Connector(models.Model):

    class Meta:
        verbose_name = "Connector"
        verbose_name_plural = "Connector"

    def __str__(self):
        return self.name
    
    name = models.CharField(max_length=50)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="connectors")
    connector_type = models.CharField(max_length=50)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created")
    updated = models.DateTimeField(
        blank=True, auto_now=True, verbose_name="Updated")