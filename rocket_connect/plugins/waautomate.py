
from .base import Connector as ConnectorBase
from instance import tasks
import mimetypes
import requests
import base64
import tempfile
import json
import time
from django.conf import settings
from envelope.models import Message


class Connector(ConnectorBase):
    '''
        how to run wa-automate:
        npx @open-wa/wa-automate    -w 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    -e 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    --session-id 'test-session' \
                                    --kill-client-on-logout \
                                    --event-mode
    '''

    def populate_config(self):
        self.connector.config = {
            "endpoint": "http://waautomate:8002",
            "convert_incoming_call_to_text": "User tried to call",
            "auto_answer_incoming_call": "Sorry, this number is for text messages only",
            "api_key": "super_secret_key"
        }
        self.save()

    def incoming(self):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        #
        # USER MESSAGES
        #
        #
        # wa automate messages come with data as dictionaries
        if self.message.get('event') == "onMessage":
            # No Group Messages
            if not self.message.get('data', {}).get('isGroupMsg'):
                # create message
                message, created = self.register_message()
                if settings.DEBUG:
                    if created:
                        print("NEW MESSAGE REGISTERED: ", self.message_object.id)
                    else:
                        print("EXISTING MESSAGE: ", self.message_object.id)
                # get a room
                room = self.get_room()
                if room:
                    mimetypes_to_upload = [
                        'audio/ogg; codecs=opus',
                        'application/pdf',
                        'image/webp'
                    ]
                    print("got room: ", room.room_id)
                    #
                    # MEDIA (PICTURE) MESSAGE
                    #
                    if self.message.get('data', {}).get('isMedia'):
                        mime = self.message.get('data', {}).get('mimetype')
                        # decrypt media
                        data = self.decrypt_media()
                        # we  got data
                        # HERE we send the media file
                        #
                        if data:
                            file_sent = self.outcome_file(data, room.room_id, mime)
                        else:
                            file_sent = False
                        # if file was sent
                        if file_sent.ok:
                            self.message_object.delivered = True
                        # if caption, send it too
                        if self.message.get('data', {}).get('caption'):
                            caption = self.message.get('data', {}).get('caption')
                            rocket = self.get_rocket_client(bot=True)
                            deliver = self.room_send_text(
                                text=caption,
                                room_id=room.room_id
                            )
                            if deliver.ok:
                                if settings.DEBUG:
                                    print("message delivered ", self.message_object.id)
                                self.message_object.delivered = True
                                # send seen
                                self.send_seen()
                            else:
                                # room can be closed on RC and open here
                                r = deliver.json()
                                if r['error'] == "room-closed":
                                    self.room_close_and_reintake(room)
                        # save if image and/or caption was delivered
                        self.message_object.save()
                    #
                    # PTT / OGG / VOICE OVER WHATSAPP

                    elif self.message.get('data', {}).get('mimetype') in mimetypes_to_upload:
                        mime = self.message.get('data', {}).get('mimetype')
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
                    #
                    #
                    # TEXT ONLY MESSAGE
                    #
                    else:
                        deliver = self.room_send_text(
                            room.room_id, self.get_message_body()
                        )
                        self.message_object.payload = json.loads(deliver.request.body)
                        self.message_object.response = deliver.json()
                        if deliver.ok:
                            if settings.DEBUG:
                                print("message delivered ", self.message_object.id)
                            self.message_object.delivered = True
                            self.message_object.room = room
                            self.message_object.save()
                            # send seen
                            self.send_seen()
                        else:
                            # save payload and save message object
                            self.message_object.save()
                            # room can be closed on RC and open here
                            r = deliver.json()
                            if r['error'] == "room-closed":
                                self.room_close_and_reintake(room)

        # here we get regular events (Battery, Plug Status)
        if self.message.get('event') == 'onBattery':
            # this prevent some bogus request from wa after logout on this event
            if self.message.get('data') and int(self.message.get('data')):
                text_message = ":battery:\n:satellite:  Battery level: {0}%".format(
                    self.message.get('data')
                )
                self.outcome_admin_message(text_message)

        # here we get regular events (Battery, Plug Status)
        if self.message.get('event') == 'onPlugged':
            if self.message.get('data') == True:
                text_message = ":radioactive:\n:satellite:  Device is charging"
                self.outcome_admin_message(text_message)
            if self.message.get('data') == False:
                text_message = ":electric_plug:\n:satellite:  Device is unplugged"
                self.outcome_admin_message(text_message)

        # when device logged out
        if self.message.get('event') == 'onLogout':
            text_message = ":warning::warning::warning::warning:\n:satellite: Device Logged Out!"
            self.outcome_admin_message(text_message)

            #
            # ADMIN / CONNECTION MESSAGES
            #

        # state changed
        if self.message.get('event') == 'onStateChanged':
            text_message = ":information_source:\n:satellite: {0} > {1}: {2} ".format(
                self.message.get('sessionId'),
                self.message.get('event'),
                self.message.get('data')
            )
            self.outcome_admin_message(text_message)

        # incoming call
        if self.message.get('event') == 'onIncomingCall':
            if self.connector.config.get('auto_answer_incoming_call'):
                message = {
                    "msg": self.connector.config.get('auto_answer_incoming_call')
                }
                # TODO: store this out message at database
                self.outgo_text_message(message)
            if self.connector.config.get('convert_incoming_call_to_text'):
                # change the message to the custom one
                # adapt to be like a regular incoming
                # this event doesnt come with the name, lets get it from the api
                visitor_id = self.message.get('data', {}).get('peerJid')
                payload = {
                    "args": {
                        "contactId": visitor_id
                    }
                }
                session = self.get_request_session()
                url = self.connector.config['endpoint'] + "/getContact"
                r = session.post(url, json=payload)
                if r.ok:
                    visitor_name = r.json()['response']['formattedName']
                self.message = {
                    "ts": int(time.time()),
                    "event": "onMessage",
                    "data": {
                        "body": self.connector.config.get('convert_incoming_call_to_text'),
                        "from": visitor_id,
                        "isGroup": False,
                        "id": self.message.get('id'),
                        "sender": {
                            "name": visitor_name
                        }

                    }
                }
                self.incoming()

        # sesion launch and qr code
        if self.message.get('namespace') and self.message.get('data'):
            message = self.message
            # OPEN WA REDY. Get unread messages
            if '@OPEN-WA ready' in message.get('data'):
                print('INITIATING INTAKE UNREAD TASK')
                tasks.intake_unread_messages.delay(self.connector.id)

            if message.get('namespace') == 'qr':
                # recreate qrcode image. WA-Automate doesnt work on older phones
                # too small, can't focus.
                code = self.get_qrcode_from_base64(message.get('data'))
                base64_fixed_code = self.generate_qrcode(code)
                self.outcome_qrbase64(base64_fixed_code)
            else:
                text_message = ":information_source:\n:satellite: {0} > {1}: {2} ".format(
                    message.get('sessionId'),
                    message.get('namespace'),
                    message.get('data') if message.get('data') != "SUCCESS"
                    else ":white_check_mark::white_check_mark::white_check_mark:      SUCESS!!!      :white_check_mark::white_check_mark::white_check_mark:"
                )
                self.outcome_admin_message(text_message)

    def get_request_session(self):
        s = requests.Session()
        s.headers = {'content-type': 'application/json'}
        if self.connector.config["api_key"]:
            s.headers.update({'api_key': self.connector.config["api_key"]})
        return s

    def send_seen(self, visitor_id=None):
        if not visitor_id:
            visitor_id = self.get_visitor_id()
        payload = {
            "args": {
                "chatId": visitor_id
            }
        }

        session = self.get_request_session()
        url = self.connector.config['endpoint'] + "/sendSeen"
        r = session.post(url, json=payload)
        return r.json()

    def intake_unread_messages(self):
        session = self.get_request_session()
        url = self.connector.config['endpoint'] + "/getAllUnreadMessages"
        r = session.post(url, json=payload)
        if r.ok and r.json().get('response', {}):
            for message in r.json().get('response', {}):
                # for each unread message, initiate a connector
                formated_message = {
                    'ts': int(time.time()),
                    'event': 'onMessage',
                    'data': message
                }
                new_connector = Connector(self.connector, formated_message, type=self.type)
                # for each connector instance, income message
                new_connector.incoming()
                # send seen
                new_connector.send_seen(message['from'])
        return r.json().get('response', {})

    def outgo_text_message(self, message):

        # message may not have an agent
        if message.get('u', {}):
            agent_name = message.get('u', {}).get('name', {})
        else:
            agent_name = None

        if agent_name:
            content = "*[" + agent_name + "]*\n" + message['msg']
        else:
            content = message['msg']
        payload = {
            "args": {
                "to": self.get_visitor_id(),
                "content": content
            }
        }
        if settings.DEBUG:
            print("outgo payload", payload)

        session = self.get_request_session()
        url = self.connector.config['endpoint'] + "/sendText"
        sent = session.post(url, json=payload)
        if sent.ok and self.message_object:
            self.message_object.delivered = True
        self.message_object.payload = payload
        self.message_object.response = sent.json()
        self.message_object.save()

    def outgo_file_message(self, message):
        # if its audio, treat different
        ppt = False
        if message["file"]["type"] == "audio/mpeg":
            ppt = True
        payload = {
            "args": {
                "to": self.get_visitor_id(),
                "url": message["fileUpload"]["publicFilePath"],
                "filename": message["attachments"][0]["title"],
                "caption": message["attachments"][0]["description"],
                "waitForId": False,
                "withoutPreview": False,
                "ptt": ppt,
            }
        }
        if settings.DEBUG:
            print("PAYLOAD OUTGING FILE: ", payload)
        session = self.get_request_session()
        url = self.connector.config['endpoint'] + "/sendFileFromUrl"
        sent = session.post(url, json=payload)
        if sent.ok:
            self.message_object.payload = payload
            self.message_object.delivered = True
            self.message_object.response = sent.json()
            self.message_object.save()