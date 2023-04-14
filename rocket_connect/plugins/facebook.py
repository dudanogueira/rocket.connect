import base64
import json
import time

import requests
from django import forms
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from requests_toolbelt import MultipartEncoder

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    """
    Facebook Connector.
    """

    def populate_config(self):
        self.connector.config = {"verify_token": "verification-token"}
        self.save()

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        # log incoming connector
        self.get_rocket_client()
        # it can be a reintake, and no request is provided
        # so it will not be a verification step
        if self.request:
            mode = self.request.GET.get("hub.mode")
            verify_token = self.request.GET.get("hub.verify_token")

            # facebook subscription
            if self.request.GET:
                if mode == "subscribe" and verify_token == self.connector.config.get(
                    "verify_token"
                ):
                    if settings.DEBUG:
                        print("VERIFYING FACEBOOK ENDPOINT")
                    challenge = self.request.GET.get("hub.challenge")
                    text_message = """:white_check_mark: :white_check_mark: :white_check_mark:\n
                    :satellite:  Endpoint Sucessfuly verified by Facebook"""
                    self.outcome_admin_message(text_message)
                    return HttpResponse(challenge)
                else:
                    text_message = (
                        ":warning: :warning: :warning: \n "
                        + "satellite:  Error while verifying endpoint by Facebook"
                    )
                    self.outcome_admin_message(text_message)
                    return HttpResponseForbidden()

        # POST REQUEST
        if self.message.get("object") == "page":
            # register message
            message, created = self.register_message()
            # get room
            room = self.get_room()
            if not room:
                return JsonResponse({"message": "no room generated"})
            for entry in self.message.get("entry", []):
                # register message
                message, created = self.register_message()
                # Gets the body of the webhook event
                webhook_event = entry["messaging"][0]
                #
                # TODO: Check differente type of messages.
                # has attachments
                if webhook_event["message"].get("attachments"):
                    #
                    # TODO: grant attachments delivery, like text messages
                    #
                    for attachment in webhook_event["message"].get("attachments", []):
                        if attachment.get("type") == "location":
                            lat = attachment["payload"]["coordinates"]["lat"]
                            lng = attachment["payload"]["coordinates"]["long"]
                            link = "https://www.google.com/maps/search/?api=1&query={}+{}".format(
                                lat, lng
                            )
                            text = f"Lat:{lat}, Long:{lng}: Link: {link}"
                            deliver = self.outcome_text(room.room_id, text)
                        else:
                            url = attachment["payload"]["url"]
                            r = requests.get(url)
                            base = base64.b64encode(r.content)
                            mime = r.headers["Content-Type"]
                            self.outcome_file(base, room.room_id, mime)
                    if webhook_event["message"].get("text"):
                        deliver = self.outcome_text(
                            room.room_id, webhook_event["message"].get("text")
                        )
                    # RETURN 200
                    return HttpResponse("EVENT_RECEIVED")

                if self.get_message_body():
                    deliver = self.outcome_text(room.room_id, self.get_message_body())
                    if deliver.ok:
                        return HttpResponse("EVENT_RECEIVED")

        return JsonResponse({"ae": 1})

    def get_incoming_message_id(self):
        # rocketchat doesnt accept facebook original id
        return self.message["entry"][0]["messaging"][0]["message"]["mid"][0:10]

    def get_incoming_visitor_id(self):
        return self.message["entry"][0]["messaging"][0]["sender"]["id"]

    def get_visitor_token(self):
        visitor_id = self.get_visitor_id()
        token = f"facebook:{visitor_id}"
        return token

    def get_visitor_username(self):
        return f"facebook:{self.get_visitor_id()}"

    def get_visitor_json(self, department=None):
        # cal api to get more infos
        url = "https://graph.facebook.com/{0}?fields=first_name,last_name,profile_pic&access_token={1}"
        url = url.format(self.get_visitor_id(), self.connector.config["access_token"])
        data = requests.get(url)
        if settings.DEBUG:
            print("GETTING FACEBOOK CONTACT: ", url)
            print("GOT: ", data.json())
        if data.ok:
            visitor_name = "{} {}".format(
                data.json()["first_name"], data.json()["last_name"]
            )
        else:
            if settings.DEBUG:
                print("COULD NOT CONNECTO TO FACEBOOK GRAPH API")
            visitor_name = self.get_visitor_token()

        visitor_username = self.get_visitor_username()
        visitor_phone = ""
        visitor_token = self.get_visitor_token()
        department = self.connector.department

        visitor = {
            "name": visitor_name,
            "username": visitor_username,
            "token": visitor_token,
            "phone": visitor_phone,
            "department": department,
            "customFields": [
                {
                    "key": "whatsapp_name",
                    "value": visitor_name,
                    "overwrite": False,
                },
                {
                    "key": "whatsapp_number",
                    "value": visitor_phone,
                    "overwrite": False,
                },
            ],
        }
        return visitor

    def get_message_body(self):
        message_body = self.message["entry"][0]["messaging"][0]["message"]["text"]
        return message_body

    def outgo_text_message(self, message, agent_name=None):
        visitor_id = self.get_visitor_id()
        if agent_name:
            content = "*[" + agent_name + "]*\n" + message["msg"]
        else:
            content = message["msg"]
        # replace emojis
        content = self.joypixel_to_unicode(content)
        url = "https://graph.facebook.com/v2.6/me/messages?access_token={}".format(
            self.connector.config["access_token"]
        )
        payload = {"recipient": {"id": visitor_id}, "message": {"text": content}}
        sent = requests.post(url=url, json=payload)
        # register outcome
        timestamp = int(time.time())
        if sent.ok and self.message_object:
            self.message_object.delivered = True
        self.message_object.payload[timestamp] = payload
        self.message_object.response[timestamp] = sent.json()
        self.message_object.save()

    def outgo_file_message(self, message, agent_name):
        visitor_id = self.get_visitor_id()
        access_token = self.connector.config["access_token"]
        mime = message["file"]["type"]
        filename = message["attachments"][0]["title"]

        # get rocketchat file
        url = message["fileUpload"]["publicFilePath"]
        get_file = requests.get(url)
        if "audio" in mime:
            file_type = "audio"
        elif "image" in mime:
            file_type = "image"
        elif "video" in mime:
            file_type = "video"
        else:
            file_type = "file"

        params = {"access_token": access_token}
        m = MultipartEncoder(
            fields={
                "recipient": json.dumps({"id": visitor_id}),
                "message": json.dumps(
                    {
                        "attachment": {
                            "type": file_type,
                            "payload": {"is_reusable": False},
                        }
                    }
                ),
                "filedata": (filename, get_file.content, mime),
            }
        )

        sent = requests.post(
            "https://graph.facebook.com/v10.0/me/messages",
            data=m,
            headers={"Content-Type": m.content_type},
            params=params,
        )
        payload = m.fields
        payload["filedata"] = "FILE ATTACHED"
        if settings.DEBUG:
            print("PAYLOAD OUTGING FILE: ", payload)
        timestamp = int(time.time())
        self.message_object.payload[timestamp] = payload
        if sent.ok:
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            if message["attachments"][0].get("description"):
                formatted_message = {
                    "u": {"name": message["u"]["name"]},
                    "msg": message["attachments"][0].get("description"),
                }
                agent_name = self.get_agent_name(message)
                self.outgo_text_message(formatted_message, agent_name)
        self.message_object.save()

    def change_agent_name(self, agent_name):
        """
        SHow only first and last name of those who has 3+ name parts
        """
        parts = agent_name.split(" ")
        if len(parts) >= 2:
            return " ".join([parts[0], parts[-1]])
        else:
            return agent_name


class ConnectorConfigForm(BaseConnectorConfigForm):
    access_token = forms.CharField(
        help_text="Facebook Access Token to get contact info",
        required=False,
    )
    verify_token = forms.CharField(
        help_text="The same verify token to be provided at Facebook Developer Page",
        required=True,
    )

    field_order = ["access_token", "verify_token"]
