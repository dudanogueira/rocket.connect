
class Connector(object):

    def incoming(self, message):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        print(
            "INTAKING. PLUGIN BASE, CONNECTOR {0}, MESSAGE ID {1}".format(
                message.connector.name,
                message.id
            )
        )

    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''
