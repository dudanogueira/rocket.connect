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
import requests
import json
import time
from emojipy import emojipy
from django.conf import settings


class Connector(object):

    def __init__(self, connector, message, type, request=None):
        self.connector = connector
        self.type = type
        if settings.DEBUG:
            print("TYPE: ", self.type)
        self.config = self.connector.config
        # self.message must be a dictionary
        if message:
            self.message = json.loads(message)
        else:
            self.message = None
        self.request = request
        self.message_object = None
        self.rocket = None
        self.room = None

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
                    file=tmp.name,
                    msg=":rocket: Connect > *Connector Name*: {0}".format(self.connector.name),
                    description="Scan this QR Code at your Whatsapp Phone:"
                )

    def outcome_file(self, base64_data, room_id, mime, filename=None):
        if settings.DEBUG:
            print("OUTCOMING FILE TO ROCKETCHAT")
        # prepare payload
        filedata = base64.b64decode(base64_data)
        rocket = self.get_rocket_client()
        extension = mimetypes.guess_extension(mime)
        if not filename:
            # random filename
            filename = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        filename_extension = "{0}{1}".format(
            filename,
            extension
        )
        # write file to temp file
        # TODO: maybe dont touch the hard drive, keep it buffer
        with tempfile.NamedTemporaryFile(suffix=extension) as tmp:
            tmp.write(filedata)
            headers = {
                'x-visitor-token': self.get_visitor_token()
            }
            files = {
                'file': (filename, open(tmp.name, 'rb'), mime)
            }
            url = "{0}/api/v1/livechat/upload/{1}".format(
                self.connector.server.url,
                room_id
            )
            print(url)
            deliver = requests.post(
                url,
                headers=headers,
                files=files
            )
            timestamp = int(time.time())
            #byte_body = deliver.request.body.decode("ascii", "ignore")
            self.message_object.payload[timestamp] = {"data": "sent attached file to rocketchat"}
            self.message_object.response[timestamp] = deliver.json()
            self.message_object.save()
            return deliver

    def outcome_text(self, room_id, text):
        deliver = self.room_send_text(
            room_id, text
        )
        timestamp = int(time.time())
        self.message_object.payload[timestamp] = json.loads(deliver.request.body)
        self.message_object.response[timestamp] = deliver.json()
        if settings.DEBUG:
            print("DELIVERING... ", deliver.request.body)
            print("RESPONSE", deliver.json())
        if deliver.ok:
            if settings.DEBUG:
                print("message delivered ", self.message_object.id)
            self.message_object.delivered = True
            self.message_object.room = self.room
            self.message_object.save()
            return deliver
        else:
            # save payload and save message object
            self.message_object.save()
            # room can be closed on RC and open here
            r = deliver.json()
            if r['error'] in ["room-closed", "invalid-room"]:
                self.room_close_and_reintake(room)
            return deliver

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
        text_message = ":rocket:CONNECT {0}".format(
            text
        )
        if response['success']:
            rocket.chat_post_message(
                alias=self.connector.name,
                text=text_message,
                room_id=response['room']['rid']
            )

    def get_visitor_name(self):
        try:
            name = self.message.get('data', {}).get('sender', {}).get('name')
        except IndexError:
            name = "Duda Nogueira"
        return name

    def get_visitor_username(self):
        try:
            visitor_username = "whatsapp:{0}".format(
                # works for wa-automate
                self.message.get('data', {}).get('from')
            )
        except IndexError:
            visitor_username = "channel:visitor-username"
        return visitor_username

    def get_visitor_phone(self):
        try:
            visitor_phone = self.message.get('data', {}).get('from').split("@")[0]
        except IndexError:
            visitor_phone = "553199999999"
        return visitor_phone

    def get_visitor_json(self):
        visitor_name = self.get_visitor_name()
        visitor_username = self.get_visitor_username()
        visitor_phone = self.get_visitor_phone()
        visitor_token = self.get_visitor_token()
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

    def get_incoming_visitor_id(self):
        if self.message.get("event") == "onIncomingCall":
            # incoming call get different ID
            return self.message.get('data', {}).get('peerJid')
        else:
            return self.message.get('data', {}).get('from')

    def get_visitor_id(self):
        if self.type == "incoming":
            return self.get_incoming_visitor_id()
        else:
            return self.message.get('visitor', {}).get('token').split(":")[1]

    def get_visitor_token(self):
        try:
            # this works for wa-automate EASYAPI
            visitor_id = self.get_visitor_id()
            visitor_id = "whatsapp:{0}".format(visitor_id)
            return visitor_id
        except IndexError:
            return "channel:visitor-id"

    def get_room(self):
        room = None
        connector_token = self.get_visitor_token()
        try:
            room = LiveChatRoom.objects.get(
                connector=self.connector,
                token=connector_token,
                open=True
            )
            print("get_room, got: ", room)
        except LiveChatRoom.DoesNotExist:
            print("get_room, didnt get for: ", connector_token)
            # room not available, let's create one.
            # get the visitor json
            visitor_json = self.get_visitor_json()
            # get the visitor object
            rocket = self.get_rocket_client()
            visitor_object = rocket.livechat_register_visitor(
                visitor=visitor_json, token=connector_token
            )
            response = visitor_object.json()
            if settings.DEBUG:
                print("VISITOR REGISTERING: ", response)
            # we got a new room
            # this is where you can hook some "welcoming features"
            if response['success']:
                rc_room = rocket.livechat_room(token=connector_token)
                rc_room_response = rc_room.json()
                if settings.DEBUG:
                    print("REGISTERING ROOM, ", rc_room_response)
                if rc_room_response['success']:
                    room = LiveChatRoom.objects.create(
                        connector=self.connector,
                        token=connector_token,
                        room_id=rc_room_response['room']['_id'],
                        open=True
                    )
                else:
                    if rc_room_response["error"] == "no-agent-online":
                        if settings.DEBUG:
                            print("Erro! No Agents Online")
        self.room = room
        if self.message_object:
            self.message_object.room = room
            self.message_object.save()

        return room

    def room_close_and_reintake(self, room):
        if settings.DEBUG:
            print("ROOM IS CLOSED. CLOSING AND REINTAKING")
        room.open = False
        room.save()
        # reintake the message
        # so now it can go to a new room
        self.incoming()

    def room_send_text(self, room_id, text):
        rocket = self.get_rocket_client()
        response = rocket.livechat_message(
            token=self.get_visitor_token(),
            rid=room_id,
            msg=text,
            _id=self.get_message_id()
        )
        return response

    def register_message(self):
        self.message_object, created = self.connector.messages.get_or_create(
            envelope_id=self.get_message_id(),
            type=self.type
        )
        self.message_object.raw_message = self.message
        self.message_object.room = self.room
        self.message_object.save()
        if settings.DEBUG:
            if created:
                print("NEW MESSAGE REGISTERED: ", self.message_object.id)
            else:
                print("EXISTING MESSAGE: ", self.message_object.id)
        return self.message_object, created

    def get_message_id(self):
        if self.type == "incoming":
            return self.get_incoming_message_id()
        if self.type == "ingoing":
            # rocketchat message id
            if self.message['messages']:
                rc_message_id = self.message['messages'][0]['_id']
                return rc_message_id
            else:
                return None

    def get_incoming_message_id(self):
        # this works for wa-automate EASYAPI
        try:
            message_id = self.message.get('data', {}).get('id')
        except IndexError:
            # for sake of forgiveness, lets make it random
            message_id = ''.join(random.choice(letters) for i in range(10))
        print("MESSAGE ID ", message_id)
        return message_id

    def get_message_body(self):
        try:
            # this works for wa-automate EASYAPI
            message_body = self.message.get('data', {}).get('body')
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

    def joypixel_to_unicode(self, content):
        return emojipy.Emoji().shortcode_to_unicode(content)

    # API METHODS
    def decrypt_media(self):
        url_decrypt = "{0}/decryptMedia".format(
            self.config['endpoint']
        )
        payload = {
            "args": {
                "message": self.get_message_id()
            }
        }
        s = self.get_request_session()
        decrypted_data_request = s.post(
            url_decrypt, json=payload
        )
        # get decrypted data
        data = None
        if decrypted_data_request.ok:
            data = decrypted_data_request.json()['response'].split(',')[1]
        return data

    def close_room(self):
        if self.room:
            if settings.DEBUG:
                print("Closing Message...")
            self.room.open = False
            self.room.save()

    def ingoing(self):
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
        # Session start
        if self.message.get('type') == "LivechatSessionStart":
            if settings.DEBUG:
                print("LivechatSessionStart")
            # todo: mark as seen
            # todo: simulate typing
            # some welcome message may fit here
        if self.message.get("type") == "LivechatSession":
            #
            # This message is sent at the end of the chat,
            # with all the chats from the session. Not Sure Why.
            if settings.DEBUG:
                print("LivechatSession")

        if self.message.get("type") == "LivechatSessionTaken":
            #
            # This message is sent when the message if taken
            if settings.DEBUG:
                print("LivechatSessionTaken")
        if self.message.get("type") == "LivechatSessionForwarded":
            #
            # This message is sent when the message if Forwarded
            if settings.DEBUG:
                print("LivechatSessionForwarded")

        if self.message.get("type") == "Message":
            message, created = self.register_message()

            # prepare message to be sent to client
            for message in self.message.get('messages', []):
                if message.get("attachments", {}):
                    # send file
                    self.outgo_file_message(message)
                else:
                    self.outgo_text_message(message)

                # closing message
                if message.get('closingMessage'):
                    # TODO: add custom closing message
                    self.close_room()
