import json
import random
import time

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from instance import tasks

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
            "endpoint": "http://waautomate:8002",
            "convert_incoming_call_to_text": "User tried to call",
            "auto_answer_incoming_call": "Sorry, this number is for text messages only",
            "api_key": "super_secret_key",
        }
        self.save()

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        #
        # EVENTS
        #
        #
        if self.message.get("event") == "onMessage":
            # No Group Messages
            if not self.message.get("data", {}).get("isGroupMsg"):
                # create message
                message, created = self.register_message()
                self.rocket = self.get_rocket_client()
                if not self.rocket:
                    return HttpResponse("Rocket Down!", status=503)

                # get a room
                room = self.get_room()
                if room:
                    mimetypes_to_upload = [
                        "audio/ogg; codecs=opus",
                        "application/pdf",
                        "image/webp",
                    ]
                    print("got room: ", room.room_id)
                    #
                    # MEDIA (PICTURE) MESSAGE
                    #
                    if self.message.get("data", {}).get("isMedia"):
                        if settings.DEBUG:
                            print("MEDIA FILE")
                        mime = self.message.get("data", {}).get("mimetype")
                        # decrypt media
                        data = self.decrypt_media()
                        # we  got data
                        # HERE we send the media file
                        #
                        # if caption, send it too
                        if data:
                            file_sent = self.outcome_file(
                                data,
                                room.room_id,
                                mime,
                                description=self.message.get("data", {}).get(
                                    "caption", None
                                ),
                            )
                        else:
                            file_sent = False
                        # if file was sent
                        if file_sent.ok:
                            self.message_object.delivered = True

                    #
                    # PTT / OGG / VOICE OVER WHATSAPP

                    elif (
                        self.message.get("data", {}).get("mimetype")
                        in mimetypes_to_upload
                    ):
                        if self.message.get("data", {}).get("type") == "sticker":
                            if settings.DEBUG:
                                print("STICKER! ")
                                self.room_send_text(room.room_id, "User sent sticker")
                        else:
                            mime = self.message.get("data", {}).get("mimetype")
                            if "audio/ogg" in mime:
                                if self.connector.config.get(
                                    "auto_answer_on_audio_message", False
                                ):
                                    message = {
                                        "msg": self.connector.config.get(
                                            "auto_answer_on_audio_message"
                                        )
                                    }
                                    deliver = self.outgo_text_message(message)
                                if self.connector.config.get(
                                    "convert_incoming_audio_to_text"
                                ):
                                    deliver = self.outcome_text(
                                        room.room_id,
                                        self.connector.config.get(
                                            "convert_incoming_audio_to_text"
                                        ),
                                    )
                            # decrypt media
                            data = self.decrypt_media()
                            # we  got data
                            if data:
                                file_sent = self.outcome_file(data, room.room_id, mime)
                            else:
                                file_sent = False
                            # if file was sent
                            if file_sent.ok:
                                self.message_object.delivered = True
                                self.message_object.save()
                    #
                    # SEND LOCATION
                    #
                    elif (
                        self.message.get("data", {}).get("mimetype") is None
                        and self.message.get("data", {}).get("type") == "location"
                    ):
                        lat = self.message.get("data", {}).get("lat")
                        lng = self.message.get("data", {}).get("lng")
                        link = "https://www.google.com/maps/search/?api=1&query={0}+{1}".format(
                            lat, lng
                        )
                        text = "Lat:{0}, Long:{1}: Link: {2}".format(lat, lng, link)
                        self.outcome_text(room.room_id, text)
                    #
                    #
                    # TEXT ONLY MESSAGE
                    #
                    else:
                        if self.message.get("data", {}).get("quotedMsg"):
                            quote_type = (
                                self.message.get("data", {})
                                .get("quotedMsg")
                                .get("type")
                            )
                            if settings.DEBUG:
                                print("MESSAGE IS A REPLY. TYPE: ", quote_type)
                            if quote_type == "chat":
                                quoted_body = (
                                    self.message.get("data", {})
                                    .get("quotedMsg")
                                    .get("body")
                                )
                                message = ":arrow_forward:  IN RESPONSE TO: {0} \n:envelope: {1}"
                                message = message.format(
                                    quoted_body,
                                    self.get_message_body(),
                                )
                            elif quote_type in ["document", "image", "ptt"]:
                                message = "DOCUMENT RESENT:\n {0}".format(
                                    self.get_message_body()
                                )
                                quoted_id = self.message.get("data", {}).get(
                                    "quotedMsg"
                                )["id"]
                                quoted_mime = self.message.get("data", {}).get(
                                    "quotedMsg"
                                )["mimetype"]
                                data = self.decrypt_media(quoted_id)
                                # we  got data
                                # HERE we send the media file
                                #
                                if data:
                                    file_sent = self.outcome_file(
                                        data, room.room_id, quoted_mime
                                    )
                                else:
                                    file_sent = False
                        else:
                            message = self.get_message_body()
                        deliver = self.outcome_text(room.room_id, message)
                        if settings.DEBUG:
                            print("DELIVER OF TEXT MESSAGE:", deliver.ok)

        # here we get regular events (Battery, Plug Status)
        if self.message.get("event") == "onBattery":
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)
            # this prevent some bogus request from wa after logout on this event
            if self.message.get("data") and int(self.message.get("data")):
                text_message = ":battery:\n:satellite:  Battery level: {0}%".format(
                    self.message.get("data")
                )
                self.outcome_admin_message(text_message)

        # here we get regular events (Battery, Plug Status)
        if self.message.get("event") == "onPlugged":
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)

            if self.message.get("data") is True:
                text_message = ":radioactive:\n:satellite:  Device is charging"
                self.outcome_admin_message(text_message)
            if self.message.get("data") is False:
                text_message = ":electric_plug:\n:satellite:  Device is unplugged"
                self.outcome_admin_message(text_message)

        # when device logged out
        if self.message.get("event") == "onLogout":
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)
            text_message = (
                ":warning::warning::warning::warning:\n:satellite: Device Logged Out!"
            )
            self.outcome_admin_message(text_message)

            #
            # ADMIN / CONNECTION MESSAGES
            #

        # state changed
        if self.message.get("event") == "onStateChanged":
            # for some reason, some times, the lib sends this very frequently
            # https://github.com/open-wa/wa-automate-nodejs/issues/949
            if self.message.get("data") not in ["TIMEOUT", "CONNECTED"]:
                self.rocket = self.get_rocket_client()
                if not self.rocket:
                    return HttpResponse("Rocket Down!", status=503)

                text_message = (
                    ":information_source:\n:satellite: {0} > {1}: {2} ".format(
                        self.message.get("sessionId"),
                        self.message.get("event"),
                        self.message.get("data"),
                    )
                )
                self.outcome_admin_message(text_message)

        # incoming call
        if self.message.get("event") == "onIncomingCall":
            self.register_message()
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)
            self.get_room()
            if self.connector.config.get("auto_answer_incoming_call"):
                message = {
                    "msg": self.connector.config.get("auto_answer_incoming_call")
                }
                self.outgo_text_message(message)
            if self.connector.config.get("convert_incoming_call_to_text"):
                # change the message to the custom one
                # adapt to be like a regular incoming
                # this event doesnt come with the name, lets get it from the api
                visitor_id = self.message.get("data", {}).get("peerJid")
                payload = {"args": {"contactId": visitor_id}}
                session = self.get_request_session()
                url = self.connector.config["endpoint"] + "/getContact"
                r = session.post(url, json=payload)
                if r.ok:
                    visitor_name = r.json()["response"]["formattedName"]
                self.message = {
                    "ts": int(time.time()),
                    "event": "onMessage",
                    "data": {
                        "body": self.connector.config.get(
                            "convert_incoming_call_to_text"
                        ),
                        "from": visitor_id,
                        "isGroup": False,
                        "id": self.message.get("id"),
                        "sender": {"name": visitor_name},
                    },
                }
                self.incoming()

        #
        #   LAUNCH EVENTS AND QRCODE
        #
        if self.message.get("namespace") and self.message.get("data"):
            # get rocket or return error
            self.rocket = self.get_rocket_client()
            if not self.rocket:
                return HttpResponse("Rocket Down!", status=503)
            message = self.message
            # OPEN WA REDY. Get unread messages
            if "@OPEN-WA ready" in message.get("data"):
                print("INITIATING INTAKE UNREAD TASK")
                tasks.intake_unread_messages.delay(self.connector.id)

            if message.get("namespace") == "qr":
                # recreate qrcode image. WA-Automate doesnt work on older phones
                # too small, can't focus.
                code = self.get_qrcode_from_base64(message.get("data"))
                base64_fixed_code = self.generate_qrcode(code)
                self.outcome_qrbase64(base64_fixed_code)
            else:
                text_message = ":information_source:\n:satellite: {0} > {1}: {2} ".format(
                    message.get("sessionId"),
                    message.get("namespace"),
                    message.get("data")
                    if message.get("data") != "SUCCESS"
                    else """:white_check_mark::white_check_mark::white_check_mark:
                          SUCESS!!!      :white_check_mark::white_check_mark::white_check_mark:""",
                )
                self.outcome_admin_message(text_message)

        return JsonResponse({})

    def get_request_session(self):
        s = requests.Session()
        s.headers = {"content-type": "application/json"}
        if self.connector.config.get("api_key"):
            s.headers.update({"api_key": self.connector.config["api_key"]})
        return s

    def send_seen(self, visitor_id=None):
        if not visitor_id:
            visitor_id = self.get_visitor_id()
        payload = {"args": {"chatId": visitor_id}}

        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/sendSeen"
        r = session.post(url, json=payload)
        return r.json()

    def simulate_typing(self, visitor_id=None, active=False):
        if not visitor_id:
            visitor_id = self.get_visitor_id()
        payload = {"args": {"to": visitor_id, "on": active}}
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/simulateTyping"
        try:
            r = session.post(url, json=payload)
            return r.json()
        except requests.ConnectionError:
            return False

    def full_simulate_typing(self, visitor_id=None):
        self.simulate_typing(visitor_id=visitor_id, active=True)
        time.sleep(random.randint(2, 3))
        self.simulate_typing(visitor_id=visitor_id, active=False)

    def intake_unread_messages(self):
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/getAllUnreadMessages"
        r = session.post(url, json={})
        if r.ok and r.json().get("response", {}):
            for message in r.json().get("response", {}):
                # for each unread message, initiate a connector
                formated_message = {
                    "ts": int(time.time()),
                    "event": "onMessage",
                    "data": message,
                }
                new_connector = Connector(
                    self.connector, json.dumps(formated_message), type=self.type
                )
                # for each connector instance, income message
                new_connector.incoming()
                # send seen
                new_connector.send_seen(message["from"])
        return r.json().get("response", {})

    def outgo_text_message(self, message, agent_name=None):
        # rocketchat reply message
        quoted_message = None
        if message["msg"][0:3] == "[ ]":
            if settings.DEBUG:
                print("MESSAGE IS REPLY:", message)
            # rocketchat reply messages be like:
            # '[ ](http://127.0.0.1:3000/live/X4LBZsCGETBzDxfM2?msg=LbpTduzFvJnrctk85) asdasdas
            # message id is, like, LbpTduzFvJnrctk85
            message_id = message["msg"].split(")")[0].split("=")[1]
            content = message["msg"].split(")")[1].strip()
            try:
                # try to get message from RC
                quoted_message = self.connector.messages.get(envelope_id=message_id)
                # define the message id.
                # if its ingoing (from RC to WA), the correct ID will be at the response
                if quoted_message.type == "ingoing":
                    quoted_message_id = quoted_message.response[
                        next(iter(quoted_message.response))
                    ]["response"]
                else:
                    # otherwise, its the envelope_id
                    quoted_message_id = message_id

            except self.connector.messages.model.DoesNotExist:
                pass
                # TODO: Alert agent that the reply did not work
        else:
            content = message["msg"]

        # message may not have an agent
        if agent_name:
            content = "*[" + agent_name + "]*\n" + content

        # replace emojis
        if quoted_message:
            url = self.connector.config["endpoint"] + "/reply"
            payload = {
                "args": {
                    "to": self.get_visitor_id(),
                    "content": content,
                    "sendSeen": True,
                    "quotedMsgId": quoted_message_id,
                }
            }
        else:
            payload = {"args": {"to": self.get_visitor_id(), "content": content}}
            url = self.connector.config["endpoint"] + "/sendText"

        content = self.joypixel_to_unicode(content)
        if settings.DEBUG:
            print("outgo payload", payload)

        session = self.get_request_session()

        self.full_simulate_typing()
        timestamp = int(time.time())
        try:
            sent = session.post(url, json=payload)
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            self.send_seen()
        except requests.ConnectionError:
            self.message_object.delivered = False
            if settings.DEBUG:
                print("CONNECTOR DOWN: ", self.connector)
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()

    def outgo_file_message(self, message, agent_name=None):
        # if its audio, treat different
        ppt = False
        if message["file"]["type"] == "audio/mpeg":
            ppt = True
        payload = {
            "args": {
                "to": self.get_visitor_id(),
                "url": message["fileUpload"]["publicFilePath"],
                "filename": message["attachments"][0]["title"],
                "caption": message["attachments"][0].get("description"),
                "waitForId": True,
                "withoutPreview": False,
                "ptt": ppt,
            }
        }
        if settings.DEBUG:
            print("PAYLOAD OUTGOING FILE: ", payload)
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/sendFileFromUrl"
        self.full_simulate_typing()
        sent = session.post(url, json=payload)
        if sent.ok:
            timestamp = int(time.time())
            if settings.DEBUG:
                print("RESPONSE OUTGOING FILE: ", sent.json())
            self.message_object.payload[timestamp] = payload
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            self.message_object.save()
            self.send_seen()

    def post_close_room(self, visitor_id=None):
        # TODO: this should have a delay, as sometimes it doesn
        # work. Maybe the delay can help
        # TODO2: have some way to sync the open chat on phone with rooms
        # on both rocketchat and rocketconnect
        if not visitor_id:
            visitor_id = self.get_visitor_id()

        # what to do with a closed room
        if self.connector.config.get("chat_after_close_action"):
            action = self.connector.config.get("chat_after_close_action")

            if action == "archive":
                url = self.connector.config["endpoint"] + "/archiveChat"
                payload = {"args": {"id": visitor_id, "archive": "true"}}

            elif action == "delete":
                payload = {"args": {"chatId": visitor_id}}
                url = self.connector.config["endpoint"] + "/deleteChat"

            session = self.get_request_session()
            sent = session.post(url, json=payload)

            if settings.DEBUG:
                print("CHAT AFTER CLOSE ACTION: ", action)
                print("PAYLOAD: ", payload)
                print("URL: ", url)
                print("RESPONSE: ", sent.json())

            if self.message_object:
                timestamp = int(time.time())
                self.message_object.payload[timestamp] = payload
                self.message_object.response[timestamp] = sent.json()
                self.message_object.save()
            return sent

    def change_agent_name(self, agent_name):
        """
        SHow only first and last name of those who has 3+ name parts
        """
        parts = agent_name.split(" ")
        if len(parts) >= 2:
            return " ".join([parts[0], parts[-1]])
        else:
            return agent_name

    def get_visitor_name(self):
        token = self.message.get("data", {}).get("sender", {}).get("id", None)
        pushname = self.message.get("data", {}).get("sender", {}).get("pushname", None)
        name = self.message.get("data", {}).get("sender", {}).get("name", None)
        name = pushname or name
        if not name:
            # try to get visitor name from api
            # some times it doesn't get the name from the incoming
            # message
            payload = {"args": {"contactId": token}}
            url = self.connector.config["endpoint"] + "/getContact"
            session = self.get_request_session()
            sent = session.post(url, json=payload)
            if sent.ok:
                push_name = sent.json().get("response", {}).get("pushname")
                if push_name:
                    name = push_name
            else:
                # last fallback, use id as name, as rocketchat requires a name.
                name = self.message.get("data", {}).get("sender", {}).get("id", None)
        return name
