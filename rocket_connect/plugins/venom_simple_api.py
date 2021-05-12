import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse

from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    def __init__(self, connector, message, type, request=None):
        self.connector = connector
        self.type = type
        if settings.DEBUG:
            print("TYPE: ", self.type)
        self.config = self.connector.config
        # self.message must be a dictionary
        if message:
            self.message = json.loads(message)
        else:
            self.message = None
        self.request = request
        self.message_object = None
        self.rocket = None
        self.room = None

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        print(
            "INTAKING. PLUGIN BASE, CONNECTOR {0}, MESSAGE {1}".format(
                self.connector.name, self.message
            )
        )
        if self.message.get("event") == "OnQRCode":
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)

            self.outcome_qrbase64(self.message["data"]["base64Qrimg"])
        return JsonResponse({})
