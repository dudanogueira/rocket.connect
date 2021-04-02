import tempfile
import base64
import mimetypes
from io import BytesIO
import qrcode
import zbarlight
from PIL import Image

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

    def outcome_qrbase64(self, connector, qrbase64):
        '''
        this method will send the qrbase64 image to the connector managers at RocketChat
        '''
        print("OUTCOME qr to outcome", qrbase64)
        server = connector.server
        # send message as bot
        rocket = server.get_rocket_client(bot=True)
        # create im for managers
        managers = connector.get_managers()
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
