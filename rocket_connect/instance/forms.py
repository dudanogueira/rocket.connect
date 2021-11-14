from django.forms import CharField, ChoiceField, ModelForm
from instance.models import Connector, Server


class NewServerForm(ModelForm):
    class Meta:
        model = Server
        fields = [
            "name",
            "url",
            "secret_token",
            "admin_user_id",
            "admin_user_token",
            "managers",
        ]


class NewConnectorForm(ModelForm):
    def __init__(self, *args, **kwargs):
        server = kwargs.pop("server")
        super(NewConnectorForm, self).__init__(*args, **kwargs)
        connector_choices = [("wppconnect", "WPPConnect"), ("facebook", "Facebook")]
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
