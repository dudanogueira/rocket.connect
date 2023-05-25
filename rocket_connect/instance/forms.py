from django.forms import (
    CharField,
    ChoiceField,
    Form,
    ModelChoiceField,
    ModelForm,
    Textarea,
)
from instance.models import Connector, Server


class NewServerForm(ModelForm):
    class Meta:
        model = Server
        fields = [
            "name",
            "url",
            "external_url",
            "secret_token",
            "admin_user_id",
            "admin_user_token",
            "managers",
        ]


class NewInboundForm(Form):
    def __init__(self, *args, **kwargs):
        server = kwargs.pop("server")
        super().__init__(*args, **kwargs)
        self.fields["connector"].queryset = server.active_chat_connectors()
        self.fields["connector"].initial = server.active_chat_connectors().first()

    number = CharField(label="Number", max_length=100, help_text="eg. 553199851212")
    destination = ChoiceField(choices=[])
    text = CharField(
        label="Text",
        max_length=100,
        widget=Textarea(attrs={"rows": 4, "cols": 15}),
    )
    connector = ModelChoiceField(queryset=None)


class NewConnectorForm(ModelForm):
    def __init__(self, *args, **kwargs):
        server = kwargs.pop("server")
        super().__init__(*args, **kwargs)
        connector_choices = [
            ("wppconnect", "WPPConnect"),
            ("codechat", "CodeChat - IN DEVELOPMENT"),
            ("facebook", "Meta Cloud Facebook"),
            ("metacloudapi_whatsapp", "Meta Cloud WhatsApp"),
            ("instagram_direct", "Meta Cloud Instagram"),
        ]
        # get departments
        rocket = server.get_rocket_client()
        departments_raw = rocket.call_api_get("livechat/department").json()
        departments_choice = [
            (d["name"], d["name"]) for d in departments_raw["departments"]
        ]
        # adapt fields
        self.fields["connector_type"] = ChoiceField(
            required=False, choices=connector_choices
        )
        self.fields["custom_connector_type"] = CharField(
            required=False, help_text="overwrite the connector type with a custom one"
        )
        self.fields["department"] = ChoiceField(
            required=False, choices=departments_choice
        )

    class Meta:
        model = Connector
        fields = ["external_token", "name", "connector_type", "department", "managers"]
