from django.db import models
import uuid
from rocketchat_API.rocketchat import RocketChat


class Server(models.Model):

    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Servers"

    def __str__(self):
        return self.name

    def get_rocket_client(self, bot=False):
        '''
            this will return a working ROCKETCHAT_API instance
        '''
        if bot:
            user = self.bot_user
            pwd = self.bot_password
        else:
            user = self.admin_user
            pwd = self.admin_password
        rocket = RocketChat(user, pwd, server_url=self.url)
        return rocket
    
    def send_admin_message(self, message, roomId):
        r = self.get_rocket_client()
        # create the admin room for this instance
        r.chat_post_message(

        )

    def get_managers(self):
        '''
        this method will return the managers (user1,user2,user3)
        and the bot. The final result should be:
        'manager1,manager2,manager3,bot_user'
        '''
        managers = self.managers.split(',')
        managers.append(self.bot_user)
        managers = ",".join(managers)
        return managers



    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    url = models.CharField(max_length=150)
    admin_user = models.CharField(max_length=50)
    admin_password = models.CharField(max_length=50)
    bot_user = models.CharField(max_length=50)
    bot_password = models.CharField(max_length=50)
    managers = models.CharField(max_length=50, help_text="separate users with comma, eg: user1,user2,user3")
    # meta
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, help_text="Connector Name")
    token = models.CharField(max_length=50, help_text="Connector Token that is aggregated to visitor token")
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="connectors")
    connector_type = models.CharField(max_length=50)
    department = models.CharField(max_length=50, blank=True, null=True)
    # meta
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created")
    updated = models.DateTimeField(
        blank=True, auto_now=True, verbose_name="Updated")
