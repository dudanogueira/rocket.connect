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
from django.template import Context, Template
from envelope.models import LiveChatRoom
from PIL import Image

from emojipy import emojipy


class Connector:
    def __init__(self, connector, message, type, request=None):
        self.connector = connector
        self.type = type
        self.config = self.connector.config
        # get timezone
        if self.config:
            self.timezone = (
                self.config.get("timezone") or settings.TIME_ZONE or "America/Sao_Paulo"
            )
        # self.message must be a dictionary
        if message:
            self.message = json.loads(message)
        else:
            self.message = {}
        self.request = request
        self.message_object = None
        self.rocket = None
        self.room = None
        self.logger = logging.getLogger("teste")
    # if true, lists the connector on active chat forms and apis
    support_active_chat = False

    def status_session(self):
        return True

    def close_session(self):
        return True

    def logger_info(self, message):
        # Constrói a mensagem de saída inicial com base no conector e no tipo, ambos formatados de maneira específica
        output = f"{self.connector} > {self.type.upper()} > {message}"
        
        # Verifica se existe um atributo de mensagem definido
        if self.message:
            # Verifica se é possível obter um ID para a mensagem
            if self.get_message_id():
                # Se houver um ID de mensagem, prepende-o à saída
                output = f"MESSAGE ID {self.get_message_id()} > " + output
        
        # Registra a saída com o nível de informação (INFO) no logger
        self.logger.info(output)

    def logger_error(self, message):
        self.logger.error(f"{self.connector} > {self.type.upper()} > {message}")

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        self.logger_info(f"INCOMING MESSAGE: {self.message}")
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
                    msg=":rocket: Connect > *Connector Name*: {}".format(
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
                            msg=":rocket: Connect > *Connector Name*: {}".format(
                                self.connector.name
                            ),
                            description="Scan this QR Code at your Whatsapp Phone:",
                        )
                        self.logger_info(
                            "SENDING QRCODE TO ROOM... {}: {}".format(
                                channel, send_qr_code.json()
                            )
                        )
                else:
                    self.logger_error(
                        "FAILED TO SEND QRCODE TO ROOM... {}: {}".format(
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
            url = "{}/api/v1/livechat/upload/{}".format(
                self.connector.server.url, room_id
            )
            deliver = requests.post(url, headers=headers, files=files, data=data)
            self.logger_info(f"RESPONSE OF FILE OUTCOME: {deliver.json()}")
            timestamp = int(time.time())
            if self.message_object:
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
                    description_message_id = self.get_message_id() + "_description"
                    self.outcome_text(
                        room_id, description, message_id=description_message_id
                    )

            return deliver

    def outcome_text(self, room_id, text, message_id=None):
        deliver = self.room_send_text(room_id, text, message_id)
        timestamp = int(time.time())
        if self.message_object:
            self.message_object.payload[timestamp] = json.loads(deliver.request.body)
            self.message_object.response[timestamp] = deliver.json()
        if settings.DEBUG:
            self.logger_info(f"DELIVERING... {deliver.request.body}")
            self.logger_info(f"RESPONSE... {deliver.json()}")
        if deliver.ok:
            if settings.DEBUG:
                self.logger_info(f"MESSAGE DELIVERED... {deliver.request.body}")
            if self.message_object:
                self.message_object.delivered = True
                self.message_object.room = self.room
                self.message_object.save()
            return deliver
        else:
            self.logger_info("MESSAGE *NOT* DELIVERED...")
            # save payload and save message object
            if self.message_object:
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

    def outcome_admin_message(self, text, managers_channel=None):
        output = []
        managers = self.connector.get_managers()
        if not managers_channel:
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
            text_message = f":rocket: CONNECT {text}"
            if response.get("success"):
                if settings.DEBUG:
                    print("SENDING ADMIN MESSAGE")
                direct_message = self.rocket.chat_post_message(
                    alias=self.connector.name,
                    text=text_message,
                    room_id=response["room"]["rid"],
                )
                output.append(direct_message.ok)
            # send to managers channel
            for manager_channel in managers_channel:
                self.logger_info("OUTCOME ADMIN MESSAGE FOR " + manager_channel)
                manager_channel_message = self.rocket.chat_post_message(
                    text=text_message, channel=manager_channel.replace("#", "")
                )
                output.append(manager_channel_message.ok)
                if manager_channel_message.ok:
                    self.logger_info(
                        "OK! manager_channel_message payload received: {}".format(
                            manager_channel_message.json()
                        )
                    )
                else:
                    self.logger_info(
                        "ERROR! manager_channel_message: {}".format(
                            manager_channel_message.json()
                        )
                    )
            if output and all(output):
                return True
        # return false
        return False

    def get_visitor_name(self):
        try:
            name = self.message.get("data", {}).get("sender", {}).get("name")
        except IndexError:
            name = "Duda Nogueira"
        return name

    def get_visitor_username(self):
        try:
            visitor_username = "whatsapp:{}".format(
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

    def get_visitor_json(self, department=None):
        visitor_name = self.get_visitor_name()
        visitor_username = self.get_visitor_username()
        visitor_phone = self.get_visitor_phone()
        visitor_token = self.get_visitor_token()
        if not department:
            department = self.connector.department
        connector_name = self.connector.name

        visitor = {
            "username": visitor_username,
            "token": visitor_token,
            "phone": visitor_phone,
            "customFields": [
                {
                    "key": "connector_name",
                    "value": connector_name,
                    "overwrite": True,
                },
            ],
        }
        if department:
            visitor["department"] = department

        if visitor_name:
            visitor["customFields"].append(
                {
                    "key": "whatsapp_name",
                    "value": visitor_name,
                    "overwrite": self.config.get("overwrite_custom_fields", True),
                }
            )

        if visitor_phone:
            visitor["customFields"].append(
                {
                    "key": "whatsapp_number",
                    "value": visitor_phone,
                    "overwrite": self.config.get("overwrite_custom_fields", True),
                }
            )

        if visitor_name and not self.config.get("supress_visitor_name", False):
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
            visitor_id = self.get_incoming_visitor_id()
        else:
            visitor_id = self.message.get("visitor", {}).get("token").split(":")[1]
        visitor_id = str(visitor_id).strip()
        return visitor_id

    def get_visitor_token(self):
        try:
            # this works for wa-automate EASYAPI
            visitor_id = self.get_visitor_id()
            visitor_id = f"whatsapp:{visitor_id}"
            return visitor_id
        except IndexError:
            return "channel:visitor-id"

    def get_room(
        self,
        department=None,
        create=True,
        allow_welcome_message=True,
        check_if_open=False,
        force_transfer=None,
    ):
        open_rooms = None
        room = None
        room_created = False
        connector_token = self.get_visitor_token()
    
        # ignore some tokens
        if self.config.get("ignore_visitors_token"):
            if connector_token in self.config.get("ignore_visitors_token").split(","):
                self.logger_info(f"Ignoring visitor token {connector_token}")
                return room

        try:
            room = LiveChatRoom.objects.get(
                connector=self.connector, token=connector_token, open=True
            )
            self.logger_info(f"get_room, got {room}")
            if check_if_open:
                self.logger_info("checking if room is open")
                open_rooms = self.rocket.livechat_rooms(open="true").json()
                open_rooms_id = [r["_id"] for r in open_rooms["rooms"]]
                if room.room_id not in open_rooms_id:
                    self.logger_info(
                        "room was open in Rocket.Connect, but not in Rocket.Chat"
                    )
                    # close room
                    room.open = False
                    room.save()
                    raise LiveChatRoom.DoesNotExist

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
            print(LiveChatRoom.DoesNotExist)
            if create:
                print(self.get_visitor_json(department))
                self.logger_info("get_room, didn't got room")
                if self.config.get("open_room", True):
                    # room not available, let's create one.
                    # get the visitor json
                    visitor_json = self.get_visitor_json(department)
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
                            room_created = True
                        else:
                            #erros que podem ocorrer ou que estejá todos usuarios(agents) off
                            if rc_room_response["errorType"] == "no-agent-online":
                                self.logger_info("NO AGENTS ONLINE")
                                if self.config.get("no_agent_online_alert_admin"):
                                    # add message as template
                                    template = Template(
                                        self.config.get("no_agent_online_alert_admin")
                                    )
                                    context = Context(self.message)
                                    message = template.render(context)
                                    self.outcome_admin_message(message)
                                if self.config.get(
                                    "no_agent_online_autoanswer_visitor"
                                ):
                                    template = Template(
                                        self.config.get(
                                            "no_agent_online_autoanswer_visitor"
                                        )
                                    )
                                    context = Context(self.message)
                                    message = {"msg": template.render(context)}
                                    self.outgo_text_message(message)
                                if settings.DEBUG:
                                    print("Erro! No Agents Online")
        self.room = room
        # optionally force transfer to department
        if force_transfer:
            payload = {
                "rid": self.room.room_id,
                "token": self.room.token,
                "department": force_transfer,
            }
            force_transfer_response = self.rocket.call_api_post(
                "livechat/room.transfer", **payload
            )
            if force_transfer_response.ok:
                self.logger_info(f"Force Transfer Response: {force_transfer_response}")
            else:
                self.logger_error(f"Force Transfer ERROR: {force_transfer_response}")

        # optionally allow welcome message
        if allow_welcome_message:
            
            if self.config.get("welcome_message"):
                # only send welcome message when
                # 1 - open_room is False and there is a welcome_message
                # 2 - open_room is True, room_created is True and there is a welcome_message
                if (
                    not self.config.get("open_room", True)
                    and self.config.get("welcome_message")
                ) or (
                    self.config.get("open_room", True)
                    and room_created
                    and self.config.get("welcome_message")
                ):
                    # if we have room, send it using the room
                    if room_created:
                        payload = {
                            "rid": self.room.room_id,
                            "msg": self.config.get("welcome_message"),
                        }
                        a = self.outgo_message_from_rocketchat(payload)
                        print("AQUI! ", a)
                        self.logger_info(
                            "OUTWENT welcome message from Rocket.Chat " + str(payload)
                        )
                    # no room, send directly
                    else:
                        message = {"msg": self.config.get("welcome_message")}
                        self.outgo_text_message(message)

            if self.config.get("welcome_vcard") != {}:
                # only send welcome vcard when
                #
                # 1 - open_room is False and there is a welcome_vcard
                # 2 - open_room is True, room_created is True and there is a welcome_vcard
                if (
                    not self.config.get("open_room", True)
                    and self.config.get("welcome_vcard")
                ) or (
                    self.config.get("open_room", True)
                    and room_created
                    and self.config.get("welcome_vcard")
                ):
                    payload = self.config.get("welcome_vcard")
                    self.outgo_vcard(payload)
                    # if room was created
                    if room and self.config.get(
                        "alert_agent_of_automated_message_sent", False
                    ):
                        # let the agent know
                        self.outcome_text(
                            room_id=room.room_id,
                            text="VCARD SENT: {}".format(
                                self.config.get("welcome_vcard")
                            ),
                            message_id=self.get_message_id() + "VCARD",
                        )
        # save message obj
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

# Não sei se é mensagem do rocket.chat para o wpp
# Os unicos cantos que utiliza essa função é o waautomate e o proprio base
    def room_send_text(self, room_id, text, message_id=None):
        if settings.DEBUG:
            print(f"SENDING MESSAGE TO ROOM ID {room_id}: {text}")
        if not message_id:
            message_id = self.get_message_id()
        rocket = self.get_rocket_client()
        response = rocket.livechat_message(
            token=self.get_visitor_token(),
            rid=room_id,
            msg=text,
            _id=message_id,
        )
        if settings.DEBUG:
            self.logger_info(f"MESSAGE SENT. RESPONSE: {response.json()}")
        return response

    def register_message(self, type=None):
        self.logger_info(f"REGISTERING MESSAGE: {json.dumps(self.message)}")
        try:
            if not type:
                type = self.type
            self.message_object, created = self.connector.messages.get_or_create(
                envelope_id=self.get_message_id(), type=type
            )
            self.message_object.raw_message = self.message
            if not self.message_object.room:
                self.message_object.room = self.room
            self.message_object.save()
            if created:
                self.logger_info(f"NEW MESSAGE REGISTERED: {self.message_object.id}")
            else:
                self.logger_info(
                    f"EXISTING MESSAGE REGISTERED: {self.message_object.id}"
                )
            return self.message_object, created
        except IntegrityError:
            self.logger_info(
                f"CANNOT CREATE THIS MESSAGE AGAIN: {self.get_message_id()}"
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
            # other types of message
            if self.message.get("_id"):
                return self.message.get("_id")

        # last resource
        return self.get_incoming_message_id()

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
            message_body = "New Message: {}".format(
                "".join(random.choice(string.ascii_letters) for i in range(10))
            )
        return message_body

    def get_rocket_client(self, bot=False, force=False):
        # this will prevent multiple client initiation at the same
        # Classe initiation
        if not self.rocket or force:
            try:
                self.rocket = self.connector.server.get_rocket_client(bot=bot)
            except requests.exceptions.ConnectionError:
                # do something when rocketdown
                self.rocket_down()
                self.rocket = False
        return self.rocket

    def outgo_message_from_rocketchat(self, payload):
        self.get_rocket_client(bot=True, force=True)
        return self.rocket.chat_send_message(payload)

    def rocket_down(self):
        if settings.DEBUG:
            print("DO SOMETHING FOR WHEN ROCKETCHAT SERVER IS DOWN")

    def joypixel_to_unicode(self, content):
        return emojipy.Emoji().shortcode_to_unicode(content)

    # API METHODS
    def decrypt_media(self, message_id=None):
        if not message_id:
            message_id = self.get_message_id()
        url_decrypt = "{}/decryptMedia".format(self.config["endpoint"])
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
            # close all room from this server with same room_id
            LiveChatRoom.objects.filter(
                connector__server=self.connector.server, room_id=self.room.room_id
            ).update(open=False)
            self.post_close_room()

    def post_close_room(self):
        """
        Method that runs after the room is closed
        """
        if settings.DEBUG:
            print("Do stuff after the room is closed")

    #mensagens whats
    def ingoing(self):
        """
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        """
        self.logger_info(f"RECEIVED: {json.dumps(self.message)}")
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
            # TODO: move the close_message hook here as the actual department is not
            # being sent
            if settings.DEBUG:
                print("LivechatSession")
        if self.message.get("type") == "LivechatSessionTaken":
            #
                # This message is sent when the message if taken
                # message, created = self.register_message()
            self.handle_livechat_session_taken()
        if self.message.get("type") == "LivechatSessionForwarded":
            #
            # This message is sent when the message if Forwarded
            if settings.DEBUG:
                print("LivechatSessionForwarded")
        if self.message.get("type") == "LivechatSessionQueued":
            #
            # This message is sent when the Livechat is queued
            if settings.DEBUG:
                print("LivechatSessionQueued")
            self.handle_livechat_session_queued()
        if self.message.get("type") == "Message":
            message, created = self.register_message()
            ignore_close_message = self.message_object.room.token in self.config.get(
                "ignore_token_force_close_message", ""
            ).split(",")
            if not message.delivered:
                # prepare message to be sent to client
                for message in self.message.get("messages", []):
                    agent_name = self.get_agent_name(message)
                    # closing message, if not requested do ignore
                    if message.get("closingMessage"):
                        # cant trust the receiving department. let's query it.
                        # seems fixed in Six
                        self.get_rocket_client()
                        room_info = self.rocket.rooms_info(
                            room_id=self.message_object.room.room_id
                        ).json()
                        department = room_info.get("room", {}).get("departmentId")
                        message["msg"] = self.get_close_message(department=department)
                        print("SHOULD GET: ", message.get("msg"))
                        print("DEPARTMENT CLOSING: ", department)
                        print("ROOM INFo:", room_info)
                        if message.get("msg") and not ignore_close_message:
                            print("GOT IN!!!!")
                            if self.connector.config.get(
                                "add_agent_name_at_close_message"
                            ):
                                self.outgo_text_message(message, agent_name=agent_name)
                            else:
                                self.outgo_text_message(message)
                        # closing message without message, or mark
                        # ignored as delivered
                        else:
                            self.message_object.delivered = True
                            self.message_object.save()
                        # close room, after all
                        self.close_room()
                    else:
                        # regular message, maybe with attach
                        if message.get("attachments", {}):
                            # send file
                            self.outgo_file_message(message, agent_name=agent_name)
                        else:
                            self.outgo_text_message(message, agent_name=agent_name)
            else:
                self.logger_info("MESSAGE ALREADY SENT. IGNORING.")

    def get_agent_name(self, message):
        agent_name = message.get("u", {}).get("name", {})
        agent_username = message.get("u", {}).get("username", {})
        # check if agent name supression is configured
        supress = self.config.get("supress_agent_name", None)
        if supress:
            if supress == "*" or agent_username in supress.split(","):
                agent_name = None

        return self.change_agent_name(agent_name)

    def render_message_agent_template(self, message, agent_name):
        context = {"message": message, "agent_name": agent_name}
        context = Context(context)
        default_message_template = "*[{{agent_name}}]*\n{{message}}"
        message_template = self.config.get("message_template", default_message_template)
        template = Template(message_template)
        message = template.render(context)
        return message

    def get_close_message(self, department=None):
        """
        get the close message configured for the connector
        """
        close_message = None
        force_close_message = self.config.get("force_close_message", None)
        advanced_force_close_message = self.config.get(
            "advanced_force_close_message", None
        )
        if force_close_message:
            close_message = force_close_message
        if advanced_force_close_message:
            # only check for advanced if department ID is informed
            if not department:
                close_message = force_close_message
            else:
                try:
                    close_message = self.config.get(
                        "advanced_force_close_message", None
                    ).get(department, None)
                except KeyError:
                    close_message = None
        self.logger_info(f"GOT CLOSE MESSAGE: {close_message}")
        return close_message

    def change_agent_name(self, agent_name):
        return agent_name

    def outgo_text_message(self, message, agent_name=None):
        """
        this method should be overwritten to send the message back to the client
        """
        if agent_name:
            self.logger_info(f"OUTGOING MESSAGE {message} FROM AGENT {agent_name}")
        else:
            self.logger_info(f"OUTGOING MESSAGE {message}")
        return True

    def outgo_vcard(self, vcard_json):
        self.logger_info(f"OUTGOING VCARD {vcard_json}")

    def handle_incoming_call(self):
        if self.config.get("auto_answer_incoming_call"):
            self.logger_info(
                "auto_answer_incoming_call: {}".format(
                    self.config.get("auto_answer_incoming_call")
                )
            )
            message = {"msg": self.config.get("auto_answer_incoming_call")}
            self.outgo_text_message(message)
        if self.config.get("convert_incoming_call_to_text"):
            if self.room:
                self.outcome_text(
                    self.room.room_id,
                    text=self.config.get("convert_incoming_call_to_text"),
                )
        # mark incoming call message as delivered
        m = self.message_object
        m.delivered = True
        m.save()
        self.message_object = m
        self.logger_info(
            "handle_incoming_call marked message {} as read".format(
                self.message_object.id
            )
        )

    def handle_ptt(self):
        if self.config.get("auto_answer_on_audio_message"):
            self.logger_info(
                "auto_answer_on_audio_message: {}".format(
                    self.config.get("auto_answer_on_audio_message")
                )
            )
            message = {"msg": self.connector.config.get("auto_answer_on_audio_message")}
            self.outgo_text_message(message)
        if self.config.get("convert_incoming_audio_to_text"):
            if self.room:
                self.outcome_text(
                    self.room.room_id,
                    text=self.config.get("convert_incoming_audio_to_text"),
                )

    def handle_livechat_session_queued(self):
        self.logger_info("HANDLING LIVECHATSESSION QUEUED")

    def handle_livechat_session_taken(self):
        self.logger_info("HANDLING LIVECHATSESSION TAKEN")
        # print("\n\nTeste\n")
        if self.config.get("session_taken_alert_template"):
            # get departments to ignore
            ignore_departments = self.config.get(
                "session_taken_alert_ignore_departments"
            )
            if ignore_departments:
                transferred_department = self.message.get("visitor", {}).get(
                    "department"
                )
                departments_list = ignore_departments.split(",")
                ignore_departments = [i for i in departments_list]
                if transferred_department in ignore_departments:
                    self.logger_info(
                        "IGNORING LIVECHATSESSION Alert for DEPARTMENT {}".format(
                            self.message.get("department")
                        )
                    )
                    # ignore this message
                    return {
                        "success": False,
                        "message": "Ignoring department {}".format(
                            self.message.get("department")
                        ),
                    }
            self.get_rocket_client()
            # enrich context with department data
            department = self.rocket.call_api_get(
                "livechat/department/{}".format(self.message.get("departmentId"))
            ).json()
            self.message["department"] = department["department"]
            template = Template(self.config.get("session_taken_alert_template"))
            context = Context(self.message)
            message = template.render(context)
            message_payload = {"msg": str(message)}
            if (
                self.config.get("alert_agent_of_automated_message_sent", False)
                and self.room
            ):
                # let the agent know
                self.outcome_text(
                    self.room.room_id,
                    f"MESSAGE SENT: {message}",
                    message_id=self.get_message_id() + "SESSION_TAKEN",
                )
            
            outgo_text_obj = self.outgo_text_message(message_payload)
            self.logger_info(f"HANDLING LIVECHATSESSION TAKEN {outgo_text_obj}")
            return outgo_text_obj

    def handle_inbound(self, request):
        """
        this method will handle inbound payloads
        you can return

        {"success": True, "redirect":"http://rocket.chat"}

        for redirecting to a new page.
        """
        self.logger_info("HANDLING INBOUND, returning default")
        return {"success": True, "redirect": "http://rocket.chat"}


class BaseConnectorConfigForm(forms.Form):
    """
    Esta classe define o formulário base para configurar um conector.
    Ela herda da classe forms.Form do Django e é usada para definir os campos 
    e comportamentos para configurar um conector.
    """

    def __init__(self, *args, **kwargs):
        """
        Método inicializador da classe.
        """

        # Obtendo a instância do conector dos argumentos keyword.
        self.connector = kwargs.pop("connector")

        # Inicializa o formulário com as configurações do conector fornecido.
        super().__init__(*args, **kwargs, initial=self.connector.config)

    def save(self):
        """
        Método para salvar as configurações do formulário na instância do conector.
        """

        # Itera sobre cada campo processado e validado do formulário.
        for field in self.cleaned_data.keys():

            # Se o campo possuir algum valor, ele é adicionado ou atualizado no conector.
            if self.cleaned_data[field]:
                self.connector.config[field] = self.cleaned_data[field]
            else:
                # Se o campo estiver vazio e já existir na configuração do conector, ele é removido.
                if self.connector.config.get(field):
                    # Caso o campo seja booleano, ele é definido como False.
                    if type(self.fields[field]) == forms.fields.BooleanField:
                        self.connector.config[field] = False
                    else:
                        # Se não, o campo é deletado da configuração.
                        del self.connector.config[field]

            # Após atualizar as configurações, o conector é salvo.
            self.connector.save()

    # Campos do formulário:

    # Opção para decidir se uma sala de chat deve ser automaticamente criada.
    open_room = forms.BooleanField(
        required=False, initial=True, help_text="Desmarque para evitar a criação de uma sala"
    )

    # Lista de tokens de visitantes que devem ser ignorados pelo conector.
    ignore_visitors_token = forms.CharField(
        help_text="Não criar/obter salas para estes tokens", required=False
    )

    # Define o fuso horário associado ao conector.
    timezone = forms.CharField(help_text="Fuso horário para este conector", required=False)

    # Modelo para formatar mensagens enviadas pelo conector.
    message_template = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Template para renderizar a mensagem, padrão: *[{{agent_name}}]*\n{{message}}",
        required=False,
        initial="*[{{agent_name}}]*\n{{message}}",
    )

    # Mensagem específica para ser enviada quando uma conversa é encerrada pelo sistema.
    force_close_message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Forçar esta mensagem ao fechar",
        required=False,
    )
       # Opção avançada para customizar a mensagem de fechamento por departamento.
    advanced_force_close_message = forms.JSONField(
        required=False,
        help_text="Mensagem de fechamento configurável ou supressão por departamento."
    )

    # Tokens de visitantes que não devem receber a mensagem de fechamento.
    ignore_token_force_close_message = forms.CharField(
        help_text="Ignorar esses visitantes ao enviar mensagem de fechamento. "
        + 'Isso pode evitar "loop de bot". Tokens separados por vírgula',
        required=False,
    )

    # Decide se a descrição de um anexo deve ser tratada como uma nova mensagem.
    outcome_attachment_description_as_new_message = forms.BooleanField(
        required=False,
        help_text="Isso pode ser necessário para o bot reagir adequadamente"
    )

    # Decide se o nome do agente deve ser adicionado na mensagem de fechamento.
    add_agent_name_at_close_message = forms.BooleanField(required=False)

    # Lista de nomes de agentes que devem ter seus nomes suprimidos nas mensagens.
    supress_agent_name = forms.CharField(
        required=False,
        help_text="* para todos os agentes, ou agent1,agent2 para específicos"
    )

    # Decide se os campos customizados devem ser sobrescritos ao registrar um novo visitante.
    overwrite_custom_fields = forms.BooleanField(
        required=False, help_text="sobrescrever campos customizados no novo registro de visitante"
    )

    # Decide se o nome do visitante no conector deve ser usado ao substituir o nome do visitante.
    supress_visitor_name = forms.BooleanField(
        required=False,
        help_text="não sobrescrever nome do visitante com nome do visitante do conector"
    )

    # Decide se o status do conector deve ser incluído na carga útil do status.
    include_connector_status = forms.BooleanField(
        required=False,
        help_text="Inclui o status do conector na carga útil do status. Desative para melhor desempenho"
    )

    # Alerta o agente sempre que uma mensagem automatizada é enviada.
    alert_agent_of_automated_message_sent = forms.BooleanField(
        required=False,
        help_text="Alerte o agente sempre que enviar um texto automatizado."
        + "AVISO: essa opção fará com que um bot reaja a essas mensagens."
    )

    # Mensagem de resposta automática para chamadas recebidas.
    auto_answer_incoming_call = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Responder automaticamente esta mensagem em chamada recebida",
        required=False,
    )

    # Converte chamada recebida em texto específico.
    convert_incoming_call_to_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Converter uma Chamada Recebida para este texto (pode ser usado para forçar uma reação de bot)",
        required=False,
    )

    # Resposta automática para mensagens de áudio enviadas pelo usuário.
    auto_answer_on_audio_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Responder automaticamente com esta mensagem quando um usuário enviar um áudio (PTT)"
    )

    # Converte áudio recebido em texto específico.
    convert_incoming_audio_to_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Converter um áudio do usuário para esta mensagem (pode ser usado para forçar uma reação de bot)"
    )

    # Mensagem de boas-vindas para enviar automaticamente ao usuário.
    welcome_message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Responder automaticamente esta mensagem como Mensagem de Boas-Vindas",
        required=False,
    )

    # Payload para um VCard de boas-vindas.
    welcome_vcard = forms.JSONField(
        required=False, initial={}, help_text="O Payload para um VCard de Boas-Vindas"
    )

    # Modelo para alerta quando uma sessão é assumida.
    session_taken_alert_template = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Template para usar no alerta de sessão assumida. ex. "
        + "Você está agora conversando com {{agent.name}} no departamento {{department.name}}"
    )

    # Departamentos que devem ser ignorados para o alerta de sessão assumida.
    session_taken_alert_ignore_departments = forms.CharField(
        required=False,
        help_text="Ignorar estes IDs de departamentos para o alerta de sessão assumida. "
        + "múltiplos separados por vírgula. ex. departmentID1,departmentID2"
    )

    # Modelo para alertar o administrador quando nenhum agente estiver online.
    no_agent_online_alert_admin = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Template para alertar o administrador quando nenhum agente estiver online. "
        + "Exemplo: Nenhum agente online! **Mensagem**: {{body}} **De**: {{from}}"
    )

    # Modelo para resposta automática ao visitante quando nenhum agente estiver online.
    no_agent_online_autoanswer_visitor = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 15}),
        help_text="Template para responder automaticamente o visitante quando nenhum agente estiver online"
    )

