from django import forms
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    """
    Facebook Connector.
    """

    def populate_config(self):
        self.connector.config = {"verify_token": "verification-token"}
        self.save()

    def handle_challenge(self):
        self.logger_info(
            "VERIFYING INSTAGRAM DIRECT ENDPOINT against with path: "
            + str(self.request.get_full_path)
        )
        verify_token = self.request.GET.get("hub.verify_token")
        if verify_token == self.connector.config.get("verify_token"):
            self.logger_info(
                "VERIFYING INSTAGRAM DIRECT ENDPOINT against: "
                + str(self.request.GET.get("hub.challenge"))
            )
            challenge = self.request.GET.get("hub.challenge")
            text = "Connector {} Status: {}".format(
                self.connector.name,
                """:white_check_mark: :white_check_mark: :white_check_mark: """
                + "\n:satellite: Endpoint Sucessfuly verified by INSTAGRAM DIRECT!",
            )
            self.outcome_admin_message(text)
            return HttpResponse(challenge)
        else:
            self.logger_error("ERROR VERIFYING INSTAGRAM DIRECT ENDPOINT")
            text = "Connector {}. Status: {}".format(
                self.connector.name,
                """:warning: :warning: :warning: \n :satellite: Endpoint *NOT VERIFIED* by INSTAGRAM DIRECT!""",
            )
            self.outcome_admin_message(text)
            return HttpResponseForbidden()

    # main incoming hub
    def incoming(self):
        self.logger_info(f"INCOMING MESSAGE: {self.message}")
        # get rocket client
        self.get_rocket_client()
        if not self.rocket:
            return HttpResponse("Rocket Down!", status=503)

        # handle challenge
        if self.request and self.request.GET.get("hub.mode") == "subscribe":
            return self.handle_challenge()

        self.raw_message = self.message
        if self.message.get("object") == "instagram":
            pass

        return JsonResponse({})

    def get_incoming_message_id(self):
        return self.message.get("id")


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
