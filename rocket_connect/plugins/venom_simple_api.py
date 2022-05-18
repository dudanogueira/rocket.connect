import json
import time

import requests
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

    def get_request_session(self):
        s = requests.Session()
        s.headers = {"content-type": "application/json"}
        if self.connector.config.get("api_key"):
            s.headers.update({"api_key": self.connector.config["api_key"]})
        return s

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        if self.message.get("event") == "onMessage":
            if self.message.get("event") == "onMessage":
                # No Group Messages
                if not self.message.get("data", {}).get("isGroupMsg"):
                    # create message
                    message, created = self.register_message()
                    self.rocket = self.get_rocket_client()
                    if not self.rocket:
                        return HttpResponse("Rocket Down!", status=503)
                    # get a room
                    room = self.get_room()
                    if room:
                        if self.message.get("data", {}).get("isMedia"):
                            print("treat media")
                        else:
                            message = self.get_message_body()
                            deliver = self.outcome_text(room.room_id, message)
                            if settings.DEBUG:
                                print("DELIVER OF TEXT MESSAGE:", deliver.ok)

                # get a room
                room = self.get_room()
        if self.message.get("event") == "OnQRCode":
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)
            self.outcome_qrbase64(self.message["data"]["base64Qrimg"])
            self.outcome_admin_message(
                "Attempt: {}".format(self.message["data"]["attempts"])
            )

        if self.message.get("event") == "onStateChanged":
            self.outcome_admin_message(self.message.get("data"))

        return JsonResponse({})

    def outgo_text_message(self, message, agent_name=None):
        content = message["msg"]
        # message may not have an agent
        if agent_name:
            content = "*[" + agent_name + "]*\n" + content
        payload = {"args": {"to": self.get_visitor_id(), "content": content}}
        url = self.connector.config["endpoint"] + "/sendText"
        content = self.joypixel_to_unicode(content)
        if settings.DEBUG:
            print("outgo payload", payload)
            print("outgo url", url)
        # TODO: self.full_simulate_typing()
        session = self.get_request_session()
        timestamp = int(time.time())
        try:
            sent = session.post(url, json=payload)
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            if settings.DEBUG:
                print("SAVING RESPONSE: ", self.message_object.response)
            # self.send_seen()
        except requests.ConnectionError:
            self.message_object.delivered = False
            if settings.DEBUG:
                print("CONNECTOR DOWN: ", self.connector)
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()
