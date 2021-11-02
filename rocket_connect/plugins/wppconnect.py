import base64
import time
import urllib.parse as urlparse

import requests
from django import forms
from django.conf import settings
from django.core import validators
from django.http import HttpResponse, JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    """
        how to run wa-automate:
        npx @open-wa/wa-automate    -w 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    -e 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    --session-id 'test-session' \
                                    --kill-client-on-logout \
                                    --event-mode
    """

    def populate_config(self):
        self.connector.config = {
            "webhook": "http://127.0.0.1:8000/connector/WPP_EXTERNAL_TOKEN/",
            "endpoint": "http://wppconnect:8080",
            "secret_key": "My53cr3tKY",
            "instance_name": "test",
        }
        self.save()

    def generate_token(self):
        # generate token
        endpoint = "{0}/api/{1}/{2}/generate-token".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
            self.config.get("secret_key"),
        )
        token = requests.post(endpoint)
        if token.ok:
            token = token.json()
            self.connector.config["token"] = token
            self.connector.save()
            return token
        return False

    def status_session(self):
        # generate token
        endpoint = "{0}/api/{1}/status-session".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )
        token = self.config.get("token", {}).get("token")
        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        status_req = requests.get(endpoint, headers=headers)
        if status_req.ok:
            status = status_req.json()
            return status
        return False

    def close_session(self):
        # generate token
        endpoint = "{0}/api/{1}/close-session".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )
        token = self.config.get("token", {}).get("token")
        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        status_req = requests.post(endpoint, headers=headers)
        if status_req.ok:
            status = status_req.json()
            return status
        return False

    def check_number_status(self, number):
        endpoint = "{0}/api/{1}/check-number-status/{2}".format(
            self.config.get("endpoint"), self.config.get("instance_name"), number
        )

        token = self.config.get("token", {}).get("token")

        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        data = {"webhook": self.config.get("webhook")}
        start_session_req = requests.get(endpoint, headers=headers, json=data)
        self.logger.info(
            "CHECKING NUMBER: {0}: {1}".format(number, start_session_req.json())
        )
        return start_session_req.json()

    def active_chat(self):
        # get the number reference
        reference = self.message.get("text").split()[1]
        # get the number, or all
        number = reference.split("@")[0]
        check_number = self.check_number_status(number)
        # could not get number validation
        if (
            not check_number.get("response")
            and check_number.get("status") == "Disconnected"
        ):
            return {
                "text": "CONNECTOR *{0}* IS DISCONNECTED".format(self.connector.name)
            }
        # construct message
        message_raw = " ".join(self.message.get("text").split()[2:])
        if not message_raw:
            return {
                "text": "NO MESSAGE TO SEND!! SYNTAX: {0} {1} <TEXT HERE>".format(
                    self.message.get("trigger_word"), reference
                )
            }

        # number checking
        if check_number.get("response", {}).get("canReceiveMessage", False):
            # can receive messages
            if "@" in reference:
                # a new room was asked to be created (@ included)
                try:
                    department = reference.split("@")[1]
                except IndexError:
                    # no department provided
                    department = None

                # check if department is valid
                print("AQUI", department)
            else:
                # no department, just send the message
                self.message["chatId"] = number
                message = {"msg": message_raw}
                sent = self.outgo_text_message(message)
                if sent.ok:
                    return {"text": "SENT {0} > {1}".format(number, message_raw)}

        # if cannot receive message, report
        else:
            # check_number failed, not a valid number
            # report back that it was not able to send the message
            return {"text": "INVALID NUMBER: {0}".format(number)}

    def start_session(self):
        endpoint = "{0}/api/{1}/start-session".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )

        token = self.config.get("token", {}).get("token")

        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        data = {"webhook": self.config.get("webhook")}
        start_session_req = requests.post(endpoint, headers=headers, json=data)
        if start_session_req.ok:
            start_session = start_session_req.json()
            return start_session
        return False

    def initialize(self):
        """
        c = Connector.objects.get(pk=12)
        cls = c.get_connector_class()
        ci = cls(connector=c, message={}, type="incoming")
        """
        # generate token
        self.generate_token()
        # start session
        return self.start_session()

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        self.logger_info("INCOMING MESSAGE: {0}".format(self.message))
        # qr code
        if self.message.get("event") == "qrcode":
            base64_fixed_code = self.message.get("qrcode")
            self.outcome_qrbase64(base64_fixed_code)

        # admin message
        if self.message.get("event") == "status-find":
            text = "Session: {0}. Status: {1}".format(
                self.message.get("session"), self.message.get("status")
            )
            if self.message.get("status") == "inChat":
                text = (
                    text
                    + ":white_check_mark::white_check_mark::white_check_mark:"
                    + "SUCESS!!!      :white_check_mark::white_check_mark::white_check_mark:"
                )
            self.outcome_admin_message(text)

        if self.message.get("event") == "incomingcall":
            # handle incoming call
            self.get_rocket_client()
            message, created = self.register_message()
            room = self.get_room()
            self.handle_incoming_call()

        # message
        if self.message.get("event") in ["onmessage", "unreadmessages"]:
            if self.message.get("event") == "unreadmessages":
                self.logger_info(
                    "PROCESSING UNREAD MESSAGE. PAYLOAD {0}".format(self.message)
                )
                # if it's a message from Me, ignore:
                if self.message.get("id", {}).get("fromMe"):
                    return JsonResponse({})
                # adapt unread messages to intake like a regular message
                pass
            # direct messages only
            if not self.message.get(
                "isGroupMsg", False
            ) and "status@broadcast" not in self.message.get("from"):
                # register message
                message, created = self.register_message()
                if not message.delivered:
                    # get rocket client
                    self.get_rocket_client()
                    if not self.rocket:
                        return HttpResponse("Rocket Down!", status=503)
                    # get room
                    room = self.get_room()
                    #
                    # no room was generated
                    #
                    if not room:
                        return JsonResponse({"message": "no room generated"})

                    #
                    # type uknown
                    #
                    if self.message.get("type") == "unknown":
                        # in case it has message object attached
                        if not self.message_object.delivered:
                            self.message_object.delivered = True
                            self.message_object.save()
                        return JsonResponse({"message": "uknown type"})

                    #
                    # process different type of messages
                    #
                    if self.message.get("type") == "chat":
                        # deliver text message
                        message = self.get_message_body()
                        if room:
                            deliver = self.outcome_text(room.room_id, message)
                            if settings.DEBUG:
                                print("DELIVER OF TEXT MESSAGE:", deliver.ok)
                    elif self.message.get("type") == "location":
                        lat = self.message.get("lat")
                        lng = self.message.get("lng")
                        link = "https://www.google.com/maps/search/?api=1&query={0}+{1}".format(
                            lat, lng
                        )
                        text = "Lat:{0}, Long:{1}: Link: {2}".format(
                            lat,
                            lng,
                            link,
                        )
                        self.outcome_text(
                            room.room_id, text, message_id=self.get_message_id()
                        )
                    else:
                        if self.message.get("type") == "ptt":
                            self.handle_ptt()
                        # media type
                        mime = self.message.get("mimetype")
                        file_sent = self.outcome_file(
                            self.message.get("body"),
                            room.room_id,
                            mime,
                            description=self.message.get("caption", None),
                        )
                        if file_sent.ok:
                            self.message_object.delivered = True
                            self.message_object.save()
                else:
                    self.logger_info(
                        "Message Object {0} Already delivered. Ignoring".format(
                            message.id
                        )
                    )

        # unread messages - just logging
        if self.message.get("event") == "unreadmessages":
            if "status@broadcast" not in self.message.get(
                "from"
            ) and not self.message.get("id", {}).get("fromMe", False):
                self.logger_info(
                    "PROCESSED UNREAD MESSAGE. PAYLOAD {0}".format(self.message)
                )

        # webhook active chat integration
        if self.message.get("token") == self.config.get(
            "active_chat_webhook_integration_token"
        ):
            self.logger_info("active_chat_webhook_integration_token triggered")
            # message, created = self.register_message()
            req = self.active_chat()
            return JsonResponse(req)

        return JsonResponse({})

    def get_incoming_message_id(self):
        # unread messages has a different structure
        if self.message.get("event") == "unreadmessages":
            return self.message.get("id", {}).get("_serialized")
        else:
            return self.message.get("id")

    def get_incoming_visitor_id(self):
        if self.message.get("event") == "incomingcall":
            return self.message.get("peerJid")
        else:
            if self.message.get("event") == "unreadmessages":
                return self.message.get("from")
            else:
                return self.message.get("chatId")

    def get_visitor_name(self):
        name = self.message.get("sender", {}).get("name")
        if not name:
            name = self.message.get("chatId")
        return name

    def get_visitor_phone(self):
        if self.message.get("event") == "incomingcall":
            visitor_phone = self.message.get("peerJid").split("@")[0]
        else:
            visitor_phone = self.message.get("from").split("@")[0]
        return visitor_phone

    def get_visitor_username(self):
        if self.message.get("event") == "incomingcall":
            visitor_username = "whatsapp:{0}".format(
                # works for wa-automate
                self.message.get("peerJid")
            )
        else:
            visitor_username = "whatsapp:{0}".format(self.message.get("from"))
        return visitor_username

    def get_message_body(self):
        return self.message.get("body")

    def get_request_session(self):
        s = requests.Session()
        s.headers = {"content-type": "application/json"}
        token = self.connector.config.get("token", {}).get("token")
        if token:
            s.headers.update({"Authorization": "Bearer {0}".format(token)})
        return s

    def outgo_text_message(self, message, agent_name=None):
        content = message["msg"]
        content = self.joypixel_to_unicode(content)
        # message may not have an agent
        if agent_name:
            content = "*[" + agent_name + "]*\n" + content

        payload = {"phone": self.get_visitor_id(), "message": content, "isGroup": False}
        session = self.get_request_session()
        # TODO: Simulate typing
        # See: https://github.com/wppconnect-team/wppconnect-server/issues/59
        url = self.connector.config["endpoint"] + "/api/{0}/send-message".format(
            self.connector.config["instance_name"]
        )
        self.logger_info(
            "OUTGOING TEXT MESSAGE. URL: {0}. PAYLOAD {1}".format(url, payload)
        )
        timestamp = int(time.time())
        try:
            sent = session.post(url, json=payload)
            if self.message_object:
                self.message_object.delivered = sent.ok
                self.message_object.response[timestamp] = sent.json()
        except requests.ConnectionError:
            if self.message_object:
                self.message_object.delivered = False
                self.logger_info("CONNECTOR DOWN: {0}".format(self.connector))
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()

        return sent

    def outgo_file_message(self, message, agent_name=None):
        # if its audio, treat different
        # ppt = False
        # if message["file"]["type"] == "audio/mpeg":
        #     ppt = True

        # to avoid some networking problems,
        # we use the same url as the configured one, as some times
        # the url to get the uploaded file may be different
        # eg: the publicFilePath is public, but waautomate is running inside
        # docker
        file_url = (
            self.connector.server.url
            + message["attachments"][0]["title_link"]
            + "?"
            + urlparse.urlparse(message["fileUpload"]["publicFilePath"]).query
        )
        content = base64.b64encode(requests.get(file_url).content).decode("utf-8")
        mime = self.message["messages"][0]["fileUpload"]["type"]
        payload = {
            "phone": self.get_visitor_id(),
            "base64": "data:{0};base64,{1}".format(mime, content),
            "isGroup": False,
        }
        if settings.DEBUG:
            print("PAYLOAD OUTGOING FILE: ", payload)
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/api/{0}/send-file-base64".format(
            self.connector.config["instance_name"]
        )
        sent = session.post(url, json=payload)
        if sent.ok:
            timestamp = int(time.time())
            if settings.DEBUG:
                print("RESPONSE OUTGOING FILE: ", sent.json())
            self.message_object.payload[timestamp] = payload
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            self.message_object.save()
            # self.send_seen()

    def outgo_vcard(self, payload):
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/api/{0}/contact-vcard".format(
            self.connector.config["instance_name"]
        )
        self.logger_info("OUTGOING VCARD. URL: {0}. PAYLOAD {1}".format(url, payload))
        timestamp = int(time.time())
        try:
            # replace destination phone
            payload["phone"] = self.get_visitor_phone()
            sent = session.post(url, json=payload)
            self.message_object.delivered = sent.ok
            self.message_object.response[timestamp] = sent.json()
        except requests.ConnectionError:
            self.message_object.delivered = False
            self.logger_info("CONNECTOR DOWN: {0}".format(self.connector))
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()


class ConnectorConfigForm(BaseConnectorConfigForm):

    webhook = forms.CharField(
        help_text="Where WPPConnect will send the events", required=True
    )
    endpoint = forms.CharField(
        help_text="Where your WPPConnect is installed", required=True
    )
    secret_key = forms.CharField(
        help_text="The secret key for your WPPConnect instance", required=True
    )
    instance_name = forms.CharField(
        help_text="WPPConnect instance name", validators=[validators.validate_slug]
    )

    active_chat_webhook_integration_token = forms.CharField(
        required=False,
        help_text="Put here the same token used for the active chat integration",
        validators=[validators.validate_slug],
    )

    field_order = [
        "webhook",
        "endpoint",
        "secret_key",
        "instance_name",
        "active_chat_webhook_integration_token",
    ]
