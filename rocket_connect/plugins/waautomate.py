
from .base import Connector as ConnectorBase
import mimetypes
import requests
import base64
import tempfile
from django.conf import settings


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
        if self.message.get('data') and type(self.message['data']) == dict:
            try:
                #
                # on Any Message
                if self.message['data']['event'] == "onAnyMessage":
                    # No Group Messages
                    if not self.message['data']['data']['isGroupMsg']:
                        # create message
                        message, created = self.connector.messages.get_or_create(
                            envelope_id=self.get_message_id()
                        )
                        message.raw_message = self.message
                        message.save()
                        self.message_object = message
                        if settings.DEBUG:
                            print("NEW MESSAGE REGISTERED: ", message.id)
                        # get a room
                        room = self.get_room()
                        if room:
                            print("got room: ", room.room_id)
                            #
                            # MEDIA MESSAGE
                            #
                            if self.message['data']['data'].get('isMedia'):
                                mime = self.message['data']['data'].get('mimetype')
                                extension = mimetypes.guess_extension(mime)
                                filename = self.message['data']['data'].get('filehash').replace(".", "")
                                filename_extension = "{0}{1}".format(
                                    filename,
                                    extension
                                )
                                # decrypt media
                                url_decrypt = "{0}/decryptMedia".format(
                                    self.config['endpoint']
                                )
                                payload = {
                                    "args": {
                                        "message": self.get_message_id()
                                    }
                                }
                                decrypted_data_request = requests.post(
                                    url_decrypt, json=payload
                                )
                                if decrypted_data_request.ok:
                                    data = decrypted_data_request.json()['response'].split(',')[1]
                                filedata = base64.b64decode(data)
                                rocket = self.get_rocket_client()
                                with tempfile.NamedTemporaryFile(suffix=extension) as tmp:
                                    tmp.write(filedata)
                                    headers = {
                                        'x-visitor-token': self.get_visitor_connector_token()
                                    }
                                    files = {
                                        'file': (filename, open(tmp.name, 'rb'), mime)
                                    }
                                    url = "{0}/api/v1/livechat/upload/{1}".format(
                                        self.connector.server.url,
                                        room.room_id
                                    )

                                    file_sent = requests.post(
                                        url,
                                        headers=headers,
                                        files=files
                                    )
                                    if file_sent.ok:
                                        message.delivered = True
                                    # if caption, send it too
                                    if self.message['data']['data'].get('caption'):
                                        deliver = rocket.chat_post_message(
                                            text=self.message['data']['data'].get('caption'), room_id=room.room_id
                                        )
                                        if deliver.ok:
                                            print("message delivered ", message.id)
                                            message.deliverd = True
                                            message.save()
                                        else:
                                            # room can be closed on RC and open here
                                            r = deliver.json()
                                            if r['error'] == "room-closed":
                                                room.open = False
                                                room.save()
                                                # reintake the message
                                                # so now it can go to a new room
                                                self.incoming()
                                    message.save()

                            #
                            # TEXT ONLY MESSAGE
                            #
                            else:
                                rocket = self.get_rocket_client()
                                deliver = rocket.livechat_message(
                                    token=self.get_visitor_connector_token(),
                                    rid=room.room_id,
                                    msg=self.get_message_body(),
                                    _id=self.get_message_id()
                                )
                                if deliver.ok:
                                    print("message delivered ", message.id)
                                    message.deliverd = True
                                    message.save()
                                else:
                                    # room can be closed on RC and open here
                                    r = deliver.json()
                                    if r['error'] == "room-closed":
                                        room.open = False
                                        room.save()
                                        # reintake the message
                                        # so now it can go to a new room
                                        self.incoming()
            except KeyError:
                pass
        #
        # ADMIN / CONNECTION MESSAGES
        #
        if self.message.get('namespace') and self.message.get('data') != '':
            message = self.message
            if message.get('namespace') == 'qr':
                text = "SESSION ID: {0}".format(message.get('sessionId'))
                # recreate qrcode image. WA-Automate doesnt work on older phones
                # too small, can't focus.
                code = self.get_qrcode_from_base64(message.get('data'))
                base64_fixed_code = self.generate_qrcode(code)
                self.outcome_qrbase64(base64_fixed_code)
            else:
                text_message = "{0} > {1}: {2} ".format(
                    message.get('sessionId'),
                    message.get('namespace'),
                    message.get('data') if message.get('data') != "SUCCESS"
                    else "SUCESS!!! :white_check_mark: :white_check_mark: :white_check_mark:"
                )
                self.outcome_admin_message(text_message)

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
