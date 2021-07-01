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
        # qr code
        if self.message.get("event") == "qrcode":
            base64_fixed_code = self.message.get("qrcode")
            self.outcome_qrbase64(base64_fixed_code)

        # message
        elif self.message.get("event") == "onmessage":
            # direct messages only
            if not self.message.get("isGroupMsg"):
                # register message
                message, created = self.register_message()
                # get rocket client
                self.get_rocket_client()
                if not self.rocket:
                    return HttpResponse("Rocket Down!", status=503)
                # get room
                room = self.get_room()
                # deliver text message
                message = self.get_message_body()
                deliver = self.outcome_text(room.room_id, message)
                if settings.DEBUG:
                    print("DELIVER OF TEXT MESSAGE:", deliver.ok)

        return JsonResponse({})

    def get_incoming_message_id(self):
        return self.message.get("id")

    def get_incoming_visitor_id(self):
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
