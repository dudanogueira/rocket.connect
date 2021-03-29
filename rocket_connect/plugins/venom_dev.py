
import tempfile
import base64

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
        if message.raw_message['topic'] == 'qrcode':
            # send message as bot
            rocket = message.connector.server.get_rocket_client(bot=True)
            # create im for managers
            managers = message.connector.server.managers.split(',')
            managers.append(message.connector.server.bot_user)
            im_room = rocket.im_create(username="", usernames=",".join(managers))
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

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
