import base64
import time
import urllib.parse as urlparse

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse

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
            # auto answer
            if self.connector.config.get("auto_answer_incoming_call"):
                self.logger_info(
                    "auto_answer_incoming_call: {0}".format(
                        self.connector.config.get("auto_answer_incoming_call")
                    )
                )
                message = {
                    "msg": self.connector.config.get("auto_answer_incoming_call")
                }
                self.outgo_text_message(message)

        # message
        if self.message.get("event") == "onmessage":
            # direct messages only
            if not self.message.get("isGroupMsg") and  'status@broadcast' not in self.message.get("from"):
                # register message
                message, created = self.register_message()
                # get rocket client
                self.get_rocket_client()
                if not self.rocket:
                    return HttpResponse("Rocket Down!", status=503)
                # get room
                room = self.get_room()
                if not self.message.get("isMedia") and self.message.get("type") not in [
                    "document",
                    "ptt",
                ]:
                    # deliver text message
                    message = self.get_message_body()
                    deliver = self.outcome_text(room.room_id, message)
                    if settings.DEBUG:
                        print("DELIVER OF TEXT MESSAGE:", deliver.ok)
                else:
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

        return JsonResponse({})

    def get_incoming_message_id(self):
        return self.message.get("id")

    def get_incoming_visitor_id(self):
        if self.message.get("event") == "incomingcall":
            return self.message.get("peerJid")
        else:
            return self.message.get("chatId")

    def get_visitor_name(self):
        name = self.message.get("sender", {}).get("name")
        if not name:
            name = self.message.get("chatId")
        return name

    def get_visitor_phone(self):
        try:
            visitor_phone = self.message.get("from").split("@")[0]
        except IndexError:
            visitor_phone = "553199999999"
        return visitor_phone

    def get_visitor_username(self):
        try:
            visitor_username = "whatsapp:{0}".format(
                # works for wa-automate
                self.message.get("from")
            )
        except IndexError:
            visitor_username = "channel:visitor-username"
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
            self.message_object.delivered = sent.ok
            self.message_object.response[timestamp] = sent.json()
        except requests.ConnectionError:
            self.message_object.delivered = False
            self.logger_info("CONNECTOR DOWN: {0}".format(self.connector))
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()

        return sent.json()

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
