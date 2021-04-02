import tempfile
import base64
import mimetypes


class Connector(object):

    def incoming(self, connector, message):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        print(
            "INTAKING. PLUGIN BASE, CONNECTOR {0}, MESSAGE {1}".format(
                connector.name,
                message
            )
        )

    def outcome_qr(self, connector, qrbase64):
        '''
        this method will send the qrbase64 image to the connector managers at RocketChat
        '''
        server = connector.server
        # send message as bot
        rocket = server.get_rocket_client(bot=True)
        # create im for managers
        managers = connector.get_managers()
        im_room = rocket.im_create(username="", usernames=managers)
        response = im_room.json()
        if response['success']:
            # send qrcode
            data = qrbase64.split(',')[1]
            imgdata = base64.b64decode(data)
            with tempfile.NamedTemporaryFile(suffix='.png') as tmp:
                tmp.write(imgdata)
                rocket.rooms_upload(
                    rid=response['room']['rid'],
                    file=tmp.name
                )
 
    def outcome_admin_message(self, connector, message):
        rocket = connector.server.get_rocket_client(bot=True)
        managers = connector.get_managers()
        im_room = rocket.im_create(username="", usernames=managers)
        response = im_room.json()
        text_message = ":rocket:CONNECT {0} > {1}".format(
            connector.name,
            message
        )
        if response['success']:
            rocket.chat_post_message(text=text_message, room_id=response['room']['rid'])

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
        pass
