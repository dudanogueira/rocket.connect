
from .base import Connector as ConnectorBase

class Connector(ConnectorBase):
    '''
        how to run wa-automate:
        npx @open-wa/wa-automate    -w 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    -e 'http://127.0.0.1:8000/connector/4333bd76-519f-4fe8-b51a-a228b29a4e19' \
                                    --session-id 'test-session' \
                                    --kill-client-on-logout \
                                    --event-mode
    '''

    def incoming(self, connector, message):
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
        if message.get('namespace'):
            if message.get('namespace') == 'qr':
                text = "SESSION ID: {0}".format(message.get('sessionId')) 
                self.outcome_qr(connector,  message.get('data'))
            else:
                text_message = "SESSION {0} > NAMESPACE {1}: {2} ".format(
                    message.get('sessionId'),
                    message.get('namespace'),
                    message.get('data')
                )
                self.outcome_admin_message(connector, text_message)

        
    def outcoming():
        '''
        this method will process the outcoming messages
        comming from Rocketchat, and deliver to the connector
        '''