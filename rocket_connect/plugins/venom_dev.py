
import tempfile
import base64
import mimetypes
from envelope.models import LiveChatRoom


class Connector(object):

    def incoming(self, message):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        print(
            "INTAKING. PLUGIN VENOM DEV, CONNECTOR {0}, MESSAGE ID {1}".format(
                message.connector.name,
                message.id
            )
        )
        # if the message is qr code type
        if message.raw_message.get('topic') == 'qrcode':
            server = message.connector.server
            # send message as bot
            rocket = server.get_rocket_client(bot=True)
            # create im for managers
            managers = server.get_managers()
            im_room = rocket.im_create(username="", usernames=managers)
            response = im_room.json()
            if response['success']:
                # send message

                fp = tempfile.TemporaryFile()
                data = message.raw_message['base64Qrimg'].split(',')[1]
                imgdata = base64.b64decode(data)
                with tempfile.NamedTemporaryFile(suffix='.png') as tmp:
                    print(tmp.name)
                    tmp.write(imgdata)
                    rocket.rooms_upload(
                        rid=response['room']['rid'],
                        file=tmp.name
                    )
                    # f gets closed when you exit the with statement
                    # Now save the value of filename to your database
                    message = "CONNECTOR: {0} \nSESSION: {1}\nATTEMPT: {2}".format(
                        message.connector.name,
                        message.raw_message['session'],
                        message.raw_message['attempt']
                    )
                    rocket.chat_post_message(text=message, room_id=response['room']['rid'])

        # if is a status session change
        elif message.raw_message.get('topic') == 'status_session':
            server = message.connector.server
            rocket = server.get_rocket_client(bot=True)
            managers = server.get_managers()
            im_room = rocket.im_create(username="", usernames=managers)
            response = im_room.json()
            if response['success']:
                if message.raw_message['message'] == "inChat":
                    message = "{0}: READY! :rocket: :rocket: :rocket: :rocket:".format(
                        message.raw_message['session']
                    )
                else:

                    message = "CONNECTOR: {0}\nSESSION: {1}\n STATUS: {2} ".format(
                        message.connector.name,
                        message.raw_message['session'],
                        message.raw_message['message']
                    )
                rocket.chat_post_message(text=message, room_id=response['room']['rid'])

        # if is a new message
        elif message.raw_message.get('isNewMsg'):
            # check if visitor has an open livechat room
            visitor_token = self.get_visitor_token(message)
            rocket = message.connector.server.get_rocket_client()
            room = None
            try:
                room = LiveChatRoom.objects.get(
                    connector=message.connector,
                    token=visitor_token,
                    open=True
                )
            except LiveChatRoom.DoesNotExist:
                # room not available, let's create one.
                
                # preparing visitor informations
                visitor = self.get_visitor(message)
                visitor_object = rocket.livechat_register_visitor(
                    visitor=visitor, token=visitor_token
                )
                response = visitor_object.json()
                if response['success']:
                    room_rc = rocket.livechat_room(token=visitor_token)
                    if room_rc.json()['success']:
                        room = LiveChatRoom.objects.create(
                            connector=message.connector,
                            token=visitor_token,
                            room_id=room_rc.json()['room']['_id'],
                            open=True
                        )
            # deliver message to room
            if room:
                #
                # MEDIA MESSAGE
                #   
                if message.raw_message.get('isMedia', False):
                    mime = message.raw_message.get("mimetype")
                    extension = mimetypes.guess_extension(mime)
                    data = message.raw_message.get("body")
                    filedata = base64.b64decode(data)
                    with tempfile.NamedTemporaryFile(suffix=extension) as tmp:
                        tmp.write(filedata)
                        file_send = rocket.call_api_post(
                            "livechat/upload/" + room.room_id,
                        )
                        # file_send = rocket.rooms_upload(
                        #     rid=room.room_id,
                        #     file=tmp.name
                        # )
                        if file_send.ok:
                            message.delivered = True
                        # if caption, send it too
                        if message.raw_message.get("caption"):
                            deliver = rocket.chat_post_message(text=message.raw_message.get("caption"), room_id=room.room_id)
                            if deliver.ok:
                                message.delivered = True
                        message.save()
                
                #
                # TEXT ONLY MESSAGE
                #
                else:
                    deliver = rocket.livechat_message(
                        token=visitor_token,
                        rid=room.room_id,
                        msg=message.raw_message.get('body'),
                        _id=message.raw_message["id"]
                    )
                if deliver.ok:
                    message.deliverd = True
                    message.save()

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''

    def get_visitor(self, message):
        visitor_name = self.get_visitor_name(message)
        visitor_username = self.get_visitor_username(message)
        visitor_phone = self.get_visitor_phone(message)
        visitor_token = self.get_visitor_token(message)
        department = self.get_visitor_department(message)

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

    def get_visitor_token(self, message):
        visitor_token = "whatsapp:{0}@{1}".format(
            message.raw_message.get('chatId'),
            message.connector.token
        )
        return visitor_token

    def get_visitor_username(self, message):
        visitor_username = "whatsapp:{0}".format(
            message.raw_message.get('chatId')
        )
        return visitor_username

    def get_visitor_name(self, message):
        visitor_name = message.raw_message.get('chat').get('name')
        return visitor_name

    def get_visitor_phone(self, message):
        visitor_phone = message.raw_message.get('from').split("@")[0]
        return visitor_phone

    def get_visitor_department(self, message):
        visitor_department = message.connector.department
        return visitor_department
