
from .base import Connector as ConnectorBase
import mimetypes
import requests
import base64
import tempfile
import json
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
            "endpoint": "http://waautomate:8080"
        }
        self.save()

    def incoming(self):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        # print(
        #     "INTAKING. PLUGIN WA-AUTOMATE, CONNECTOR {0}, MESSAGE {1}".format(
        #         connector.name,
        #         message
        #     )
        # )

        #
        # USER MESSAGES
        #
        #
        # wa automate messages come with data as dictionaries
        if self.message.get('event') == "onAnyMessage" and \
            self.message.get('data', {}).get('data', {}).get('type') != 'sticker':
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
                        if deliver.ok:
                            if settings.DEBUG:
                                print("message delivered ", self.message_object.id)
                            self.message_object.delivered = True
                            self.message_object.room = room
                            self.message_object.save()
                            # save payload and save message object
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
            else:
                text_message = ":electric_plug:\n:satellite:  Device is unplugged"
            self.outcome_admin_message(text_message)

        # when device logged out
        if self.message.get('event') == 'onLogout':
            text_message = ":warning::warning::warning::warning:\n:satellite: Device Logged Out!"
            self.outcome_admin_message(text_message)

            #
            # ADMIN / CONNECTION MESSAGES
            #

        if self.message.get('namespace') and self.message.get('data'):
            message = self.message
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

    def ingoing(self):
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
        # Session start
        if self.message.get('type') == "LivechatSessionStart":
            print("Starting Session")
            # todo: mark as seen
            # todo: simulate typing
            # some welcome message may fit here

        else:
            message, created = self.register_message()
            if settings.DEBUG:
                if created:
                    print("NEW MESSAGE REGISTERED: ", self.message_object.id)
                else:
                    print("EXISTING MESSAGE: ", self.message_object.id)
            # prepare message to be sent to client
            for message in self.message.get('messages', []):
                self.outgo_text_message(message)

    def outgo_text_message(self, message):
        payload = {
            "args": {
                "to": self.outgo_destintion(),
                "content": message['msg']
            }
        }
        sent = requests.post(
            self.connector.config['endpoint'] + "/sendText",
            json=payload
        )
        if sent.ok:
            self.message_object.payload = payload
            self.message_object.delivered = True
            self.message_object.save()