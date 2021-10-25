import base64
import json
import logging
import mimetypes
import random
import string
import tempfile
import time
from io import BytesIO

import qrcode
import requests
import zbarlight
from django import forms
from django.conf import settings
from django.db import IntegrityError
from django.http import JsonResponse
from envelope.models import LiveChatRoom
from PIL import Image

from emojipy import emojipy


class Connector(object):
    def __init__(self, connector, message, type, request=None):
        self.connector = connector
        self.type = type
        self.config = self.connector.config
        # get timezone
        self.timezone = (
            self.config.get("timezone") or settings.TIME_ZONE or "America/Sao_Paulo"
        )
        # self.message must be a dictionary
        if message:
            self.message = json.loads(message)
        else:
            self.message = None
        self.request = request
        self.message_object = None
        self.rocket = None
        self.room = None
        self.logger = logging.getLogger("teste")

    def logger_info(self, message):
        self.logger.info(
            "{0} > {1} > {2}".format(self.connector, self.type.upper(), message)
        )

    def logger_error(self, message):
        self.logger.error(
            "{0} > {1} > {2}".format(self.connector, self.type.upper(), message)
        )

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        self.logger_info("INCOMING MESSAGE: {0}".format(self.message))
        return JsonResponse(
            {
                "connector": self.connector.name,
            }
        )

    def outcome_qrbase64(self, qrbase64):
        """
        this method will send the qrbase64 image to the connector managers at RocketChat
        """
        # send message as bot
        rocket = self.get_rocket_client(bot=True)
        # create im for managers
        managers = self.connector.get_managers()
        if settings.DEBUG:
            print("GOT MANAGERS: ", managers)
        im_room = rocket.im_create(username="", usernames=managers)
        im_room_created = im_room.json()

        # send qrcode
        try:
            data = qrbase64.split(",")[1]
        except IndexError:
            data = qrbase64
        imgdata = base64.b64decode(str.encode(data))
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(imgdata)
            if im_room_created["success"]:
                rocket.rooms_upload(
                    rid=im_room_created["room"]["rid"],
                    file=tmp.name,
                    msg=":rocket: Connect > *Connector Name*: {0}".format(
                        self.connector.name
                    ),
                    description="Scan this QR Code at your Whatsapp Phone:",
                )
            # out come qr to room
            managers_channel = self.connector.get_managers_channel(as_string=False)
            for channel in managers_channel:
                # get room id
                room_infos = rocket.rooms_info(room_name=channel.replace("#", ""))
                if room_infos.ok:
                    rid = room_infos.json().get("room", {}).get("_id", None)
                    if rid:
                        send_qr_code = rocket.rooms_upload(
                            rid=rid,
                            file=tmp.name,
                            msg=":rocket: Connect > *Connector Name*: {0}".format(
                                self.connector.name
                            ),
                            description="Scan this QR Code at your Whatsapp Phone:",
                        )
                        self.logger_info(
                            "SENDING QRCODE TO ROOM... {0}: {1}".format(
                                channel, send_qr_code.json()
                            )
                        )
                else:
                    self.logger_error(
                        "FAILED TO SEND QRCODE TO ROOM... {0}: {1}".format(
                            channel, room_infos.json()
                        )
                    )

    def outcome_file(self, base64_data, room_id, mime, filename=None, description=None):
        if settings.DEBUG:
            print("OUTCOMING FILE TO ROCKETCHAT")
        # prepare payload
        filedata = base64.b64decode(base64_data)
        extension = mimetypes.guess_extension(mime)
        if not filename:
            # random filename
            filename = "".join(
                random.choices(string.ascii_letters + string.digits, k=16)
            )
        # write file to temp file
        # TODO: maybe dont touch the hard drive, keep it buffer
        with tempfile.NamedTemporaryFile(suffix=extension) as tmp:
            tmp.write(filedata)
            headers = {"x-visitor-token": self.get_visitor_token()}
            # TODO: open an issue to be able to change the ID of the uploaded file like a message allows
            files = {"file": (filename, open(tmp.name, "rb"), mime)}
            data = {}
            if description:
                data["description"] = description
            url = "{0}/api/v1/livechat/upload/{1}".format(
                self.connector.server.url, room_id
            )
            deliver = requests.post(url, headers=headers, files=files, data=data)
            timestamp = int(time.time())
            self.message_object.payload[timestamp] = {
                "data": "sent attached file to rocketchat"
            }
            if deliver.ok:
                if settings.DEBUG and deliver.ok:
                    print("teste, ", deliver)
                    print("OUTCOME FILE RESPONSE: ", deliver.json())
                self.message_object.response[timestamp] = deliver.json()
                self.message_object.delivered = deliver.ok
                self.message_object.save()

            if self.connector.config.get(
                "outcome_attachment_description_as_new_message", True
            ):
                if description:
                    self.outcome_text(room_id, description)

            return deliver

    def outcome_text(self, room_id, text):
        deliver = self.room_send_text(room_id, text)
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
            # TODO: when sending a message already sent, rocket doesnt return a identifiable message
            # file a bug, and test it more
            if r.get("error", "") in ["room-closed", "invalid-room", "invalid-token"]:
                self.room_close_and_reintake(self.room)
            return deliver

    def get_qrcode_from_base64(self, qrbase64):
        try:
            data = qrbase64.split(",")[1]
        except IndexError:
            data = qrbase64
        img = Image.open(BytesIO(base64.b64decode(data)))
        code = zbarlight.scan_codes(["qrcode"], img)[0]
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
        managers = self.connector.get_managers()
        managers_channel = self.connector.get_managers_channel(as_string=False)
        if settings.DEBUG:
            print("GOT MANAGERS: ", managers)
            print("GOT CHANNELS: ", managers_channel)
        if self.get_rocket_client(bot=True):
            # send to the managers
            im_room = self.rocket.im_create(username="", usernames=managers)
            response = im_room.json()
            if settings.DEBUG:
                print("CREATE ADMIN ROOM TO OUTCOME", im_room.json())
            text_message = ":rocket: CONNECT {0}".format(text)
            if response["success"]:
                if settings.DEBUG:
                    print("SENDING ADMIN MESSAGE")
                self.rocket.chat_post_message(
                    alias=self.connector.name,
                    text=text_message,
                    room_id=response["room"]["rid"],
                )
            # send to managers channel
            for manager_channel in managers_channel:
                manager_channel_message = self.rocket.chat_post_message(
                    text=text_message, channel=manager_channel.replace("#", "")
                )
                if manager_channel_message.ok:
                    self.logger_info(
                        "OK! manager_channel_message payload received: {0}".format(
                            manager_channel_message.json()
                        )
                    )
                else:
                    self.logger_info(
                        "ERROR! manager_channel_message: {0}".format(
                            manager_channel_message.json()
                        )
                    )

    def get_visitor_name(self):
        try:
            name = self.message.get("data", {}).get("sender", {}).get("name")
        except IndexError:
            name = "Duda Nogueira"
        return name

    def get_visitor_username(self):
        try:
            visitor_username = "whatsapp:{0}".format(
                # works for wa-automate
                self.message.get("data", {}).get("from")
            )
        except IndexError:
            visitor_username = "channel:visitor-username"
        return visitor_username

    def get_visitor_phone(self):
        try:
            visitor_phone = self.message.get("data", {}).get("from").split("@")[0]
        except IndexError:
            visitor_phone = "553199999999"
        return visitor_phone

    def get_visitor_json(self):
        visitor_name = self.get_visitor_name()
        visitor_username = self.get_visitor_username()
        visitor_phone = self.get_visitor_phone()
        visitor_token = self.get_visitor_token()
        department = self.connector.department
        connector_name = self.connector.name

        visitor = {
            "username": visitor_username,
            "token": visitor_token,
            "phone": visitor_phone,
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
                },
                {
                    "key": "connector_name",
                    "value": connector_name,
                    "overwrite": True,
                },
            ],
        }
        if department:
            visitor["department"] = department
        if visitor_name and not self.connector.config.get(
            "supress_visitor_name", False
        ):
            visitor["name"] = visitor_name

        if settings.DEBUG:
            print("GOT VISITOR JSON: ", visitor)

        return visitor

    def get_incoming_visitor_id(self):
        if self.message.get("event") == "onIncomingCall":
            # incoming call get different ID
            return self.message.get("data", {}).get("peerJid")
        else:
            return self.message.get("data", {}).get("from")

    def get_visitor_id(self):
        if self.type == "incoming":
            return self.get_incoming_visitor_id()
        else:
            return self.message.get("visitor", {}).get("token").split(":")[1]

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
                connector=self.connector, token=connector_token, open=True
            )
            print("get_room, got: ", room)
        except LiveChatRoom.MultipleObjectsReturned:
            # this should not happen. Mitigation for issue #12
            # TODO: replicate error at development
            return (
                LiveChatRoom.objects.filter(
                    connector=self.connector, token=connector_token, open=True
                )
                .order_by("-created")
                .last()
            )
        except LiveChatRoom.DoesNotExist:
            print("get_room, didnt get for: ", connector_token)
            if self.config.get("welcome_message"):
                message = {"msg": self.config.get("welcome_message")}
                self.outgo_text_message(message)
                # outcome this message to the agent
            if self.config.get("open_room", True):
                # room not available, let's create one.
                # get the visitor json
                visitor_json = self.get_visitor_json()
                # get the visitor object
                visitor_object = self.rocket.livechat_register_visitor(
                    visitor=visitor_json, token=connector_token
                )
                response = visitor_object.json()
                if settings.DEBUG:
                    print("VISITOR REGISTERING: ", response)
                # we got a new room
                # this is where you can hook some "welcoming features"
                if response["success"]:
                    rc_room = self.rocket.livechat_room(token=connector_token)
                    rc_room_response = rc_room.json()
                    if settings.DEBUG:
                        print("REGISTERING ROOM, ", rc_room_response)
                    if rc_room_response["success"]:
                        room = LiveChatRoom.objects.create(
                            connector=self.connector,
                            token=connector_token,
                            room_id=rc_room_response["room"]["_id"],
                            open=True,
                        )
                    else:
                        if rc_room_response["error"] == "no-agent-online":
                            if settings.DEBUG:
                                print("Erro! No Agents Online")
        self.room = room
        # tell agent that the welcome message was sent
        if self.config.get("welcome_message"):
            self.outcome_text(
                room.room_id,
                "MESSAGE SENT: {0}".format(self.config.get("welcome_message")),
            )
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
        if settings.DEBUG:
            print("SENDING MESSAGE TO ROOM ID {0}: {1}".format(room_id, text))
        rocket = self.get_rocket_client()
        response = rocket.livechat_message(
            token=self.get_visitor_token(),
            rid=room_id,
            msg=text,
            _id=self.get_message_id(),
        )
        if settings.DEBUG:
            print("MESSAGE SENT. RESPONSE: ", response.json())
        return response

    def register_message(self):
        try:
            self.message_object, created = self.connector.messages.get_or_create(
                envelope_id=self.get_message_id(), type=self.type
            )
            self.message_object.raw_message = self.message
            if not self.message_object.room:
                self.message_object.room = self.room
            self.message_object.save()
            if created:
                self.logger_info(
                    "NEW MESSAGE REGISTERED: {0}".format(self.message_object.id)
                )
            else:
                self.logger_info(
                    "EXISTING MESSAGE REGISTERED: {0}".format(self.message_object.id)
                )
            return self.message_object, created
        except IntegrityError:
            self.logger_info(
                "CANNOT CREATE THIS MESSAGE AGAIN: {0}".format(self.get_message_id())
            )
            return "", False

    def get_message_id(self):
        if self.type == "incoming":
            return self.get_incoming_message_id()
        if self.type == "ingoing":
            # rocketchat message id
            if self.message["messages"]:
                rc_message_id = self.message["messages"][0]["_id"]
                return rc_message_id
            else:
                return None

    def get_incoming_message_id(self):
        # this works for wa-automate EASYAPI
        try:
            message_id = self.message.get("data", {}).get("id")
        except IndexError:
            # for sake of forgiveness, lets make it random
            message_id = "".join(random.choice(string.ascii_letters) for i in range(10))
        print("MESSAGE ID ", message_id)
        return message_id

    def get_message_body(self):
        try:
            # this works for wa-automate EASYAPI
            message_body = self.message.get("data", {}).get("body")
        except IndexError:
            message_body = "New Message: {0}".format(
                "".join(random.choice(string.ascii_letters) for i in range(10))
            )
        return message_body

    def get_rocket_client(self, bot=False):
        # this will prevent multiple client initiation at the same
        # Classe initiation
        if not self.rocket:
            try:
                self.rocket = self.connector.server.get_rocket_client(bot=bot)
            except requests.exceptions.ConnectionError:
                # do something when rocketdown
                self.rocket_down()
                self.rocket = False
        return self.rocket

    def rocket_down(self):
        if settings.DEBUG:
            print("DO SOMETHING FOR WHEN ROCKETCHAT SERVER IS DOWN")

    def joypixel_to_unicode(self, content):
        return emojipy.Emoji().shortcode_to_unicode(content)

    # API METHODS
    def decrypt_media(self, message_id=None):
        if not message_id:
            message_id = self.get_message_id()
        url_decrypt = "{0}/decryptMedia".format(self.config["endpoint"])
        payload = {"args": {"message": message_id}}
        s = self.get_request_session()
        decrypted_data_request = s.post(url_decrypt, json=payload)
        # get decrypted data
        data = None
        if decrypted_data_request.ok:
            response = decrypted_data_request.json().get("response", None)
            if settings.DEBUG:
                print("DECRYPTED DATA: ", response)
            if response:
                data = response.split(",")[1]
        return data

    def close_room(self):
        if self.room:
            if settings.DEBUG:
                print("Closing Message...")
            self.room.open = False
            self.room.save()
            self.post_close_room()

    def post_close_room(self):
        """
        Method that runs after the room is closed
        """
        if settings.DEBUG:
            print("Do stuff after the room is closed")

    def ingoing(self):
        """
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        """
        self.logger_info("Processing ingoing message: {0}".format(self.message))
        # Session start
        if self.message.get("type") == "LivechatSessionStart":
            if settings.DEBUG:
                print("LivechatSessionStart")
            # some welcome message may fit here
        if self.message.get("type") == "LivechatSession":
            #
            # This message is sent at the end of the chat,
            # with all the chats from the session.
            # if the Chat Close Hook is On
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
        if self.message.get("type") == "LivechatSessionQueued":
            #
            # This message is sent when the message if Forwarded
            if settings.DEBUG:
                print("LivechatSessionQueued")
        if self.message.get("type") == "Message":
            message, created = self.register_message()

            # prepare message to be sent to client
            for message in self.message.get("messages", []):
                agent_name = self.get_agent_name(message)
                # closing message
                if message.get("closingMessage"):
                    if self.connector.config.get(
                        "force_close_message",
                    ):
                        message["msg"] = self.connector.config["force_close_message"]
                    if message.get("msg"):
                        if self.connector.config.get("add_agent_name_at_close_message"):
                            self.outgo_text_message(message, agent_name=agent_name)
                        else:
                            self.outgo_text_message(message)
                        self.close_room()
                    # closing message without message
                    else:
                        self.message_object.delivered = True
                        self.message_object.save()
                else:
                    # regular message, maybe with attach
                    if message.get("attachments", {}):
                        # send file
                        self.outgo_file_message(message, agent_name=agent_name)
                    else:
                        self.outgo_text_message(message, agent_name=agent_name)

    def get_agent_name(self, message):
        agent_name = message.get("u", {}).get("name", {})
        return self.change_agent_name(agent_name)

    def change_agent_name(self, agent_name):
        return agent_name

    def outgo_text_message(self, message, agent_name=None):
        """
        this method should be overwritten to send the message back to the client
        """
        if agent_name:
            self.logger_info(
                "OUTGOING MESSAGE {0} FROM AGENT {1}".format(message, agent_name)
            )
        else:
            self.logger_info("OUTGOING MESSAGE {0}".format(message))
        return True

    def handle_incoming_call(self):
        if self.connector.config.get("auto_answer_incoming_call"):
            self.logger_info(
                "auto_answer_incoming_call: {0}".format(
                    self.connector.config.get("auto_answer_incoming_call")
                )
            )
            message = {"msg": self.connector.config.get("auto_answer_incoming_call")}
            self.outgo_text_message(message)


class BaseConnectorConfigForm(forms.Form):
    def __init__(self, *args, **kwargs):
        # get the instance connector
        self.connector = kwargs.pop("connector")
        # pass the connector config as initial
        super().__init__(*args, **kwargs, initial=self.connector.config)

    def save(self):
        for field in self.cleaned_data.keys():
            if self.cleaned_data[field]:
                self.connector.config[field] = self.cleaned_data[field]
            else:
                if self.connector.config.get(field):
                    # if is a boolean field, mark as false
                    # else, delete
                    if type(self.fields[field]) == forms.fields.BooleanField:
                        self.connector.config[field] = False
                    else:
                        del self.connector.config[field]
            self.connector.save()

    timezone = forms.CharField(help_text="Timezone for this connector", required=False)
    force_close_message = forms.CharField(
        help_text="Force this message on close", required=False
    )
    auto_answer_incoming_call = forms.CharField(
        help_text="Auto answer this message on incoming call", required=False
    )
    outcome_attachment_description_as_new_message = forms.BooleanField(required=False)
    welcome_message = forms.CharField(
        help_text="Auto answer this message as Welcome Message", required=False
    )
    open_room = forms.BooleanField(required=False, initial=True)
