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
    
    # Inicialização do formulário.
    def __init__(self, *args, **kwargs):
        # Retirando o servidor dos argumentos passados.
        server = kwargs.pop("server")
        # Chamada ao método de inicialização da classe base.
        super().__init__(*args, **kwargs)
        # Definindo o queryset do campo "connector" com os conectores ativos do servidor.
        self.fields["connector"].queryset = server.active_chat_connectors()
        # Definindo o valor inicial do campo "connector" para o primeiro conector ativo.
        self.fields["connector"].initial = server.active_chat_connectors().first()

    # Campo para informar o número.
    number = CharField(label="Number", max_length=100, help_text="eg. 553199851212")
    # Campo de seleção para o destino.
    destination = ChoiceField(choices=[])
    # Campo de texto para a mensagem.
    text = CharField(
        label="Text",
        max_length=100,
        widget=Textarea(attrs={"rows": 4, "cols": 15}),
    )
    # Campo para selecionar o conector.
    connector = ModelChoiceField(queryset=None)


# Formulário para adicionar um novo conector.
class NewConnectorForm(ModelForm):
    
    # Inicialização do formulário.
    def __init__(self, *args, **kwargs):
        # Retirando o servidor dos argumentos passados.
        server = kwargs.pop("server")
        # Chamada ao método de inicialização da classe base.
        super().__init__(*args, **kwargs)
        # Lista predefinida de escolhas para o tipo de conector.
        connector_choices = [
            ("wppconnect", "WPPConnect"),
            ("facebook", "Meta Cloud Facebook"),
            ("metacloudapi_whatsapp", "Meta Cloud WhatsApp"),
            ("instagram_direct", "Meta Cloud Instagram"),
        ]
        
        # Buscando os departamentos a partir do cliente do Rocket.
        rocket = server.get_rocket_client()
        departments_raw = rocket.call_api_get("livechat/department").json()
        # Processando os departamentos brutos para criar uma lista de escolhas.
        departments_choice = [
            (d["name"], d["name"]) for d in departments_raw["departments"]
        ]
        
        # Adaptando campos com base nos dados obtidos.
        self.fields["connector_type"] = ChoiceField(
            required=False, choices=connector_choices
        )
        self.fields["custom_connector_type"] = CharField(
            required=False, help_text="overwrite the connector type with a custom one"
        )
        self.fields["department"] = ChoiceField(
            required=False, choices=departments_choice
        )

    # Metaclasse para definir informações adicionais do formulário.
    class Meta:
        # Modelo base para este formulário.
        model = Connector
        # Campos que serão exibidos e manipulados.
        fields = ["external_token", "name", "connector_type", "department", "managers"]
