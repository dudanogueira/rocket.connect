import json

import requests
from django import forms
from django.core import validators
from django.http import JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    #
    # SESSION MANAGEMENT
    #
    def initialize(self):
        endpoint_create = "{}/instance/create".format(
            self.config.get("endpoint"),
        )
        secret_key = self.config.get("secret_key")
        webhook_url = self.config.get("webhook")
        instance_name = self.config.get("instance_name")
        headers = {"apiKey": secret_key, "Content-Type": "application/json"}
        # GET {{baseUrl}}/instance/create with { "instanceName": "codechat"}
        payload = {"instanceName": instance_name}
        headers = {"Content-Type": "application/json", "apikey": secret_key}

        create_instance_response = requests.request(
            "POST", endpoint_create, json=payload, headers=headers
        )
        output = {}
        output["instance_create"] = {
            "endpoint": endpoint_create,
            **create_instance_response.json(),
        }
        # GET {{baseUrl}}/instance/connect/{{instance}}

        endpoint_connect = "{}/instance/connect/{}".format(
            self.config.get("endpoint"), instance_name
        )
        connect_instance_response = requests.request(
            "GET", endpoint_connect, json=payload, headers=headers
        )
        output["instance_connect"] = {
            "endpoint": endpoint_connect,
            **connect_instance_response.json(),
        }
        # POST {{baseUrl}}/webhook/set/{{instance}}
        endpoint_webhook_set = "{}/webhook/set/{}".format(
            self.config.get("endpoint"), instance_name
        )
        payload = {"enabled": True, "url": webhook_url}
        connect_instance_response = requests.request(
            "POST", endpoint_webhook_set, json=payload, headers=headers
        )
        output["instance_webhook"] = {
            "endpoint": endpoint_webhook_set,
            **connect_instance_response.json(),
        }
        return output

    def status_session(self):
        if self.config.get("endpoint", None):
            # GET {{baseUrl}}/instance/connectionState/{{instance}}
            secret_key = self.config.get("secret_key")
            instance_name = self.config.get("instance_name")
            headers = {"apiKey": secret_key, "Content-Type": "application/json"}

            endpoint_status = "{}/instance/connect/{}".format(
                self.config.get("endpoint"), instance_name
            )
            status_instance_response = requests.request(
                "GET", endpoint_status, headers=headers
            )
            if status_instance_response:
                return status_instance_response.json()
            return {"error": "no endpoint"}
        else:
            return {"error": "no endpoint"}

    def close_session(self):
        # DELETE {{baseUrl}}/instance/logout/{{instance}}
        secret_key = self.config.get("secret_key")
        instance_name = self.config.get("instance_name")
        headers = {"apiKey": secret_key, "Content-Type": "application/json"}
        endpoint_status = "{}/instance/logout/{}".format(
            self.config.get("endpoint"), instance_name
        )
        status_instance_response = requests.request(
            "DELETE", endpoint_status, headers=headers
        )
        return status_instance_response.ok

    #
    # INCOMING HANDLERS
    #

    def incoming(self):
        message = json.dumps(self.message)
        self.logger_info(f"INCOMING MESSAGE: {message}")
        #
        # qrcode reading
        #
        if self.message.get("event") == "qrcode.updated":
            base64 = self.message.get("data", {}).get("qrcode", {}).get("base64")
            if base64:
                self.outcome_qrbase64(base64)
        #
        # connection update
        #
        if self.message.get("event") == "connection.update":
            data = self.message.get("data", {})
            text = "*CONNECTOR NAME:* {} > {}".format(
                self.connector.name, json.dumps(data)
            )
            if data.get("state") == "open":
                text = text + "\n" + " ✅ " * 6
            self.outcome_admin_message(text)
        #
        # message upsert
        #
        if self.message.get("event") == "messages.upsert":
            department = None
            message, created = self.register_message()
            if not message.delivered:
                # get room
                room = self.get_room(department)
                if not room:
                    return JsonResponse({"message": "no room generated"})
                #
                # oucome if text
                #
                if (
                    self.message.get("data", {})
                    .get("message", {})
                    .get("extendedTextMessage")
                ):
                    text = (
                        self.message.get("data", {})
                        .get("message", {})
                        .get("extendedTextMessage")
                        .get("text")
                    )
                    deliver = self.outcome_text(room.room_id, text)
                    print(deliver)
                #
                # outcome if image
                #
                if self.message.get("data", {}).get("message", {}).get("imageMessage"):
                    pass

            else:
                self.logger_info(
                    f"Message Object {message.id} Already delivered. Ignoring"
                )

        return JsonResponse({})

    #
    # OUTGO
    #

    def outgo_text_message(self, message, agent_name=None):
        print("MESSAGE!!!", message)

    #
    # MESSAGE METADA DATA
    #
    def get_incoming_message_id(self):
        id = None
        if self.message.get("event") == "messages.upsert":
            id = self.message.get("data", {}).get("key", {}).get("id")
        return id

    def get_visitor_name(self):
        name = self.message.get("data", {}).get("pushName")
        if name:
            return name
        return None

    def get_visitor_phone(self):
        remoteJid = self.message.get("data", {}).get("key", {}).get("remoteJid")
        if remoteJid:
            return remoteJid.split("@")[0]

        return None

    def get_visitor_username(self):
        visitor_username = f"whatsapp:{self.get_visitor_phone()}@c.us"
        return visitor_username

    def get_incoming_visitor_id(self):
        return self.get_visitor_phone() + "@c.us"


class ConnectorConfigForm(BaseConnectorConfigForm):
    webhook = forms.CharField(
        help_text="Where WPPConnect will send the events", required=True, initial=""
    )
    endpoint = forms.CharField(
        help_text="Where your WPPConnect is installed",
        required=True,
        initial="http://codechat:8083",
    )
    secret_key = forms.CharField(
        help_text="The secret ApiKey for your CodeChat instance",
        required=True,
    )
    instance_name = forms.CharField(
        help_text="CodeChat instance name", validators=[validators.validate_slug]
    )

    field_order = [
        "webhook",
        "endpoint",
        "secret_key",
        "instance_name",
    ]
