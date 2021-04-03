import tempfile
import base64
import mimetypes
from io import BytesIO
import qrcode
import zbarlight
from PIL import Image
from envelope.models import LiveChatRoom
import random
import string


class Connector(object):

    def __init__(self, connector, message):
        self.connector = connector
        self.config = self.connector.config
        self.message = message
        self.message_object = None
        self.rocket = None

    def incoming(self):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        print(
            "INTAKING. PLUGIN BASE, CONNECTOR {0}, MESSAGE {1}".format(
                self.connector.name,
                self.message
            )
        )

    def outcome_qrbase64(self, qrbase64):
        '''
        this method will send the qrbase64 image to the connector managers at RocketChat
        '''
        print("OUTCOME qr to outcome", qrbase64)
        server = self.connector.server
        # send message as bot
        rocket = self.get_rocket_client(bot=True)
        # create im for managers
        managers = self.connector.get_managers()
        im_room = rocket.im_create(username="", usernames=managers)
        response = im_room.json()
        if response['success']:
            # send qrcode
            try:
                data = qrbase64.split(',')[1]
            except IndexError:
                data = qrbase64
            imgdata = base64.b64decode(str.encode(data))
            with tempfile.NamedTemporaryFile(suffix='.png') as tmp:
                tmp.write(imgdata)
                rocket.rooms_upload(
                    rid=response['room']['rid'],
                    file=tmp.name
                )

    def get_qrcode_from_base64(self, qrbase64):
        try:
            data = qrbase64.split(',')[1]
        except IndexError:
            data = qrbase64
        img = Image.open(BytesIO(base64.b64decode(data)))
        code = zbarlight.scan_codes(['qrcode'], img)[0]
        return code

    def generate_qrcode(self, code):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=40,
            border=5,
        )

        qr.add_data(code)
        qr.make(fit=True)
        img = qr.make_image()

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_str

    def outcome_admin_message(self, text):
        rocket = self.get_rocket_client(bot=True)
        managers = self.connector.get_managers()
        im_room = rocket.im_create(username="", usernames=managers)
        response = im_room.json()
        text_message = ":rocket::rocket::rocket::rocket:CONNECT {0} > {1}".format(
            self.connector.name,
            text
        )
        if response['success']:
            rocket.chat_post_message(text=text_message, room_id=response['room']['rid'])

    def get_visitor_name(self):
        try:
            name = self.message['data']['data']['sender']['name']
        except IndexError:
            name = "Duda Nogueira"
        return name

    def get_visitor_username(self):
        try:
            visitor_username = "whatsapp:{0}".format(
                # works for wa-automate
                self.message['data']['data']['from']
            )
        except IndexError:
            visitor_username = "channel:visitor-username"
        return visitor_username

    def get_visitor_phone(self):
        try:
            visitor_phone = self.message['data']['data']['from'].split("@")[0]
        except IndexError:
            visitor_phone = "553199999999"
        return visitor_phone

    def get_visitor_json(self):
        visitor_name = self.get_visitor_name()
        visitor_username = self.get_visitor_username()
        visitor_phone = self.get_visitor_phone()
        visitor_token = self.get_visitor_connector_token()
        department = self.connector.department

        visitor = {
            "name": visitor_name,
            "username": visitor_username,
            "token": visitor_token,
            "phone": visitor_phone,
            "department": department,
            "customFields": [
                {
                    "key": "whatsapp_name",
                    "value": visitor_name,
                    "overwrite": False,
                },
                {
                    "key": "whatsapp_number",
                    "value": visitor_phone,
                    "overwrite": False,
                }
            ]
        }
        return visitor

    def get_visitor_id(self):
        try:
            # this works for wa-automate EASYAPI
            visitor_id = self.message['data']['data']['from']
            visitor_id = "whatsapp:{0}".format(visitor_id)
            return visitor_id
        except IndexError:
            return "channel:visitor-id"

    def get_visitor_connector_token(self):
        visitor_id = self.get_visitor_id()
        visitor_connector_token = "{0}@{1}".format(
            visitor_id,
            self.connector.token
        )
        return visitor_connector_token

    def get_room(self):
        room = None
        visitor_connector_token = self.get_visitor_connector_token()
        try:
            room = LiveChatRoom.objects.get(
                connector=self.connector,
                token=visitor_connector_token,
                open=True
            )
        except LiveChatRoom.DoesNotExist:
            # room not available, let's create one.
            # get the visitor json
            visitor_json = self.get_visitor_json()
            # get the visitor object
            rocket = self.get_rocket_client()
            visitor_object = rocket.livechat_register_visitor(
                visitor=visitor_json, token=visitor_connector_token
            )
            response = visitor_object.json()
            # we got a new room
            # this is where you can hook some "welcoming features"
            if response['success']:
                rc_room = rocket.livechat_room(token=visitor_connector_token)
                if rc_room.json()['success']:
                    room = LiveChatRoom.objects.create(
                        connector=self.connector,
                        token=visitor_connector_token,
                        room_id=rc_room.json()['room']['_id'],
                        open=True
                    )
        return room

    def get_message_id(self):
        try:
            # this works for wa-automate EASYAPI
            message_id = self.message['data']['data']['id']
        except IndexError:
            message_id = ''.join(random.choice(letters) for i in range(10))
        return message_id

    def get_message_body(self):
        try:
            # this works for wa-automate EASYAPI
            message_body = self.message['data']['data']['body']
        except IndexError:
            message_body = "New Message: {0}".format(
                ''.join(random.choice(letters) for i in range(10))
            ) 
        return message_body

    def get_rocket_client(self, bot=False):
        # this will prevent multiple client initiation at the same 
        # Classe initiation
        if not self.rocket:
            self.rocket = self.connector.server.get_rocket_client(bot=bot)
        return self.rocket

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
        pass
