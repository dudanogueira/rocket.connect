import base64
import json
import time
import urllib.parse as urlparse

import requests
from django import forms
from django.db import models
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    # main incoming hub
    def incoming(self):
        """
        Message Types Reference:
        https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
        """
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
                return self.handle_message()
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
                                return self.handle_message()
                        # it has a status receipt
                        if change["value"].get("statuses") and self.config.get(
                            "enable_ack_receipt", True
                        ):
                            # handle read receipt
                            # get the message id and body
                            for status in change["value"]["statuses"]:
                                self.logger_info(f"ACK RECEIPT {status}")
                                msg_id = status["id"]
                                status = status["status"]
                                messages_to_search = self.connector.messages.filter(
                                    models.Q(response__id__contains=msg_id)
                                    | models.Q(
                                        response__messages__contains=[{"id": msg_id}]
                                    )
                                )
                                print("FOUND: ", messages_to_search)
                                for message in messages_to_search:
                                    original_message = self.rocket.chat_get_message(
                                        msg_id=message.envelope_id
                                    )
                                    body = original_message.json()["message"]["msg"]
                                    body = body.replace(":ballot_box_with_check:", "")
                                    body = body.replace(":white_check_mark:", "")
                                    if status == "sent":
                                        mark = ":ballot_box_with_check:"
                                    else:
                                        mark = ":white_check_mark:"
                                    payload = {
                                        "room_id": message.room.room_id,
                                        "msg_id": message.envelope_id,
                                        "text": f"{mark} {body}",
                                    }
                                    update_response = self.rocket.chat_update(**payload)
                                    self.logger_info(
                                        f"ACK RECEIPT UPDATE RESPONSE {update_response}"
                                    )

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
        if self.message.get("type") == "unsupported":
            # do nothing
            return JsonResponse({"message": "unsupported type"})

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
        return JsonResponse({"sucess": True})

    def handle_media(self):
        # register message
        message, created = self.register_message()
        room = self.get_room()
        # get media id
        media_type = self.message["type"]
        media_id = self.message[media_type]["id"]
        # get media url
        graph_url = self.config.get("graph_url", "https://graph.facebook.com/v14.0/")
        url = graph_url + media_id
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

    def get_graphql_endpoint(self, method=""):
        return "{}/{}/{}".format(
            self.config.get("graph_url"), self.config.get("telephone_number_id"), method
        )

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
        url = self.get_graphql_endpoint(method="messages")
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

    def outgo_file_message(self, message, agent_name=None):
        file_url = (
            self.connector.server.get_external_url()
            + message["attachments"][0]["title_link"]
            + "?"
            + urlparse.urlparse(message["fileUpload"]["publicFilePath"]).query
        )
        mime = self.message["messages"][0]["fileUpload"]["type"]
        filename = self.message["messages"][0]["file"]["name"]
        caption = self.message["messages"][0]["attachments"][0].get("description", None)
        endpoint_messages = self.get_graphql_endpoint(method="messages")
        session = self.get_request_session()
        to = self.get_visitor_id().split("@")[0]
        # BR exception
        # meta will send the number as 55319XXXXXXX
        # but will require 5531*9*9XXXXXXX here
        if len(to) == 12 and to.startswith("55"):
            to = to[0:4] + "9" + to[4:]

        file = {
            "link": file_url,
            # "filename": filename
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
        }
        if "image" in mime:
            payload["type"] = "image"
            payload["image"] = file
            payload["image"]["caption"] = caption

        elif "audio" in mime:
            payload["type"] = "audio"
            payload["audio"] = file

        else:
            payload["type"] = "document"
            payload["document"] = file
            payload["document"]["filename"] = filename

        send_file = session.post(endpoint_messages, json=payload)
        self.logger_info(
            f"OUTGO file {send_file.json()} with payload {json.dumps(payload)} and mimetype {mime}"
        )
        if send_file.ok:
            timestamp = int(time.time())
            self.message_object.payload[timestamp] = payload
            self.message_object.delivered = True
            self.message_object.response = send_file.json()
            self.message_object.save()
            # self.send_seen()

    def status_session(self):
        # generate token
        status = {}
        if self.config.get("endpoint"):
            endpoint = self.get_graphql_endpoint()
            session = self.get_request_session()
            try:
                status_req = session.get(endpoint)
                if status_req.ok:
                    status = status_req.json()
            except requests.exceptions.MissingSchema:
                return {
                    "success": False,
                    "message": f"Could not get endpoint: {endpoint}",
                }
        return status


class ConnectorConfigForm(BaseConnectorConfigForm):
    graph_url = forms.CharField(
        help_text="Facebook GraphQl endpoint with version, eg https://graph.facebook.com/v14.0/",
        required=True,
        initial="https://graph.facebook.com/v14.0/",
    )
    telephone_number_id = forms.CharField(
        help_text="Telephone Number ID",
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

    enable_ack_receipt = forms.BooleanField(required=False, initial=True)

    field_order = [
        "graph_url",
        "telephone_number_id",
        "verify_token",
        "bearer_token",
        "allowed_media_types",
    ]
