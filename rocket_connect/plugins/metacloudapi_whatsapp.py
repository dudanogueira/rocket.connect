import base64
import time

import requests
from django import forms
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):

    # main incoming hub
    def incoming(self):
        self.logger_info(f"INCOMING MESSAGE: {self.message}")
        # no rocket client, abort
        # get rocket client
        self.get_rocket_client()
        if not self.rocket:
            return HttpResponse("Rocket Down!", status=503)

        # handle challenge
        if self.request and self.request.GET.get("hub.mode") == "subscribe":
            return self.handle_challenge()
        # handle regular messages
        self.raw_message = self.message
        if self.message.get("object") == "whatsapp_business_account":
            # it can be a forced delivery
            if not self.message.get("entry"):
                # here it can be a status message
                self.handle_message()
            else:
                for entry in self.message.get("entry"):
                    for change in entry["changes"]:
                        self.change = change
                        # it has messages
                        if change["value"].get("messages"):
                            for message in change["value"]["messages"]:
                                self.message = message
                                # enrich message
                                self.message["metadata"] = change["value"]["metadata"]
                                self.message["profile"] = change["value"]["contacts"]
                                self.message["object"] = self.raw_message["object"]
                                # handle text message
                                self.handle_message()
                        # it has a status receipt
                        if change["value"].get("statuses"):
                            # TODO: handle read receipt
                            pass

        return JsonResponse({})

    def handle_challenge(self):
        self.logger_info(
            "VERIFYING META CLOUD ENDPOINT against with path: "
            + str(self.request.get_full_path)
        )
        verify_token = self.request.GET.get("hub.verify_token")
        if verify_token == self.connector.config.get("verify_token"):
            self.logger_info(
                "VERIFYING META CLOUD ENDPOINT against: "
                + str(self.request.GET.get("hub.challenge"))
            )
            challenge = self.request.GET.get("hub.challenge")
            text = "Connector: {}. Status: {}".format(
                self.connector.name,
                """:white_check_mark: :white_check_mark: :white_check_mark: :satellite:"""
                + "\nEndpoint Sucessfuly verified by Meta Cloud!",
            )
            self.outcome_admin_message(text)
            return HttpResponse(challenge)
        else:
            self.logger_error("ERROR VERIFYING META CLOUD ENDPOINT")
            text = "Connector: {}. Status: {}".format(
                self.connector.name,
                """:warning: :warning: :warning: :satellite: \n*Endpoint NOT VERIFIED* by Meta Cloud!""",
            )
            self.outcome_admin_message(text)
            return HttpResponseForbidden()

    def handle_message(self):
        message, created = self.register_message()
        room = self.get_room()
        # no room was generated
        if not room:
            return JsonResponse({"message": "no room generated"})

        allowed_media_types = self.config.get(
            "allowed_media_types",
            "audio,image,video,document,sticker,text,location,contacts",
        ).split(",")
        if self.message.get("type") in allowed_media_types:
            # outcome text message
            #
            if self.message.get("type") == "text":
                # outcome text message
                #
                self.outcome_text(room.room_id, self.message["text"]["body"])
            elif self.message.get("type") == "location":
                message = "Location: lat {} long {}".format(
                    self.message["location"]["latitude"],
                    self.message["location"]["longitude"],
                )
                self.outcome_text(room.room_id, message)
            elif self.message.get("type") == "contacts":
                print("AQUI ", self.message)
                for contact in self.message["contacts"]:
                    message = "Contact: {}  {}".format(
                        contact["name"]["formatted_name"], contact["phones"]
                    )
                    self.outcome_text(room.room_id, message)
            else:
                self.handle_media()
        else:
            # outcome text message, alerting this is not allowed
            # TODO, improve this to outcome and outgo customizable messages
            payload = {
                "rid": self.room.room_id,
                "msg": "This media type is not allowed",
            }
            self.outgo_message_from_rocketchat(payload)
            message.delivered = True
            message.save()

    def handle_media(self):
        # register message
        message, created = self.register_message()
        room = self.get_room()
        # get media id
        media_type = self.message["type"]
        media_id = self.message[media_type]["id"]
        # get media url
        # TODO config api version
        url = "https://graph.facebook.com/v13.0/" + media_id
        session = self.get_request_session()
        media_info = session.get(
            url,
        )
        mime = media_info.json().get("mime_type")
        description = None
        if self.message.get("image", {}).get("caption"):
            description = self.message.get("image", {}).get("caption")

        # get media base64
        media_url = media_info.json().get("url")
        base64_data = base64.b64encode(session.get(media_url).content)
        self.outcome_file(base64_data, room.room_id, mime, description)

    def get_incoming_message_id(self):
        return self.message.get("id")

    def get_visitor_phone(self):
        return self.message["from"]

    def get_visitor_name(self):
        return self.message["profile"][0]["profile"]["name"]

    def get_visitor_token(self):
        return "whatsapp:" + self.message["from"] + "@c.us"

    def get_request_session(self):
        s = requests.Session()
        s.headers = {"content-type": "application/json"}
        token = self.connector.config.get("bearer_token")
        if token:
            s.headers.update({"Authorization": f"Bearer {token}"})
        return s

    def outgo_text_message(self, message, agent_name=None):
        sent = False
        if type(message) == str:
            content = message
        else:
            content = message["msg"]
        content = self.joypixel_to_unicode(content)
        # message may not have an agent
        if agent_name:
            content = "*[" + agent_name + "]*\n" + content
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "messages"
        # get number
        number = self.message["visitor"]["token"].split("@")[0].split(":")[1]
        payload = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "to": number,
            "type": "text",
            "text": {"body": content},
        }
        self.logger_info(f"OUTGOING TEXT MESSAGE. URL: {url}. PAYLOAD {payload}")
        # try with regular number
        sent = session.post(url, json=payload)
        # this is due to BRazil's WhatsApp API not handling 55319[9] correctly
        if not sent.ok:
            if payload["to"].startswith("55"):
                # 5531XXXXXXXX - > 55319XXXXXXXX
                payload["to"] = payload["to"].replace(
                    payload["to"][:4], payload["to"][:4] + "9"
                )
                # retry with different number
                sent = session.post(url, json=payload)
        # we got the message sent!
        if sent.ok:
            timestamp = int(time.time())
            if self.message_object:
                self.message_object.delivered = sent.ok
                self.message_object.response[timestamp] = sent.json()
                if sent.ok:
                    if not self.message_object.response.get("id"):
                        self.message_object.response["id"] = [
                            sent.json()["messages"][0]["id"]
                        ]
                    else:
                        self.message_object.response["id"].append(
                            sent.json()["messages"][0]["id"]
                        )
            self.message_object.save()
            # message not sent
        else:
            self.logger_info(f"ERROR SENDING MESSAGE {sent.json()}")
            if self.message_object:
                self.message_object.delivered = False
                self.logger_info(f"CONNECTOR DOWN: {self.connector}")

        return sent

    def status_session(self):
        # generate token
        status = {}
        if self.config.get("endpoint"):
            endpoint = self.config.get("endpoint")
            session = self.get_request_session()
            status_req = session.get(endpoint)
            if status_req.ok:
                status = status_req.json()
        return status


class ConnectorConfigForm(BaseConnectorConfigForm):

    endpoint = forms.CharField(
        help_text="Where to connect to your meta cloud accont",
        required=True,
        initial="",
    )
    verify_token = forms.CharField(
        help_text="The verify token for the Challenge",
        required=True,
    )

    bearer_token = forms.CharField(
        required=True,
        help_text="The bearer token for the Meta Cloud account",
    )

    allowed_media_types = forms.CharField(
        help_text="Allowed Media Types",
        required=True,
        initial="audio,image,video,document,sticker,text,location,contacts",
    )

    field_order = ["endpoint", "verify_token", "bearer_token", "allowed_media_types"]
