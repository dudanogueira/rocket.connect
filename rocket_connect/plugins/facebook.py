
from .base import Connector as ConnectorBase

from django.conf import settings

from django.http import JsonResponse
from django.http import HttpResponse
from django.http import HttpResponseForbidden

import json
import requests
import base64


class Connector(ConnectorBase):
    '''
        Facebook Connector.
    '''

    def populate_config(self):
        self.connector.config = {
            "verify_token": "verification-token"
        }
        self.save()

    def incoming(self):
        '''
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        '''
        mode = self.request.GET.get('hub.mode')
        verify_token = self.request.GET.get('hub.verify_token')

        # facebook subscription
        if self.request.GET:
            if mode == 'subscribe' and verify_token == self.connector.config.get('verify_token'):
                challenge = self.request.GET.get('hub.challenge')
                return HttpResponse(challenge)
            else:
                return HttpResponseForbidden()

        # POST REQUEST
        if self.message.get("object") == "page":
            # register message
            message, created = self.register_message()
            # get room
            room = self.get_room()
            if room:
                for entry in self.message.get("entry", []):
                    # register message
                    message, created = self.register_message()
                    # Gets the body of the webhook event
                    webhook_event = entry['messaging'][0]
                    sender_psid = webhook_event['sender']['id']
                    #
                    # TODO: Check differente type of messages.
                    # has attachments
                    if webhook_event['message'].get('attachments'):
                        for attachment in webhook_event['message'].get('attachments', []):
                            url = webhook_event['message']['attachments'][0]["payload"]['url']
                            r = requests.get(url)
                            base = base64.b64encode(r.content)
                            mime = r.headers['Content-Type']
                            self.outcome_file(base, room.room_id, mime)
                        if webhook_event['message'].get("text"):
                            deliver = self.room_send_text(
                                room.room_id, webhook_event['message'].get("text")
                            )
                        # RETURN 200
                        return HttpResponse("EVENT_RECEIVED")

                    if self.get_message_body():
                        deliver = self.room_send_text(
                            room.room_id, self.get_message_body()
                        )
                        if settings.DEBUG:
                            print("room_send_text, ", deliver.request.body)
                        if deliver.ok:
                            if settings.DEBUG:
                                print("message delivered ", self.message_object.id)
                            self.message_object.delivered = True
                            # return 200 Response
                            return HttpResponse("EVENT_RECEIVED")
                        else:
                            # room can be closed on RC and open here
                            r = deliver.json()
                            if r.get('error') == "room-closed":
                                self.room_close_and_reintake(room)
                            else:
                                print("ERRO AO ENTEGAR")
                    self.message_object.save()

        return JsonResponse({'ae': 1})

    def get_incoming_message_id(self):
        # rocketchat doesnt accept facebook original id
        return self.message["entry"][0]['messaging'][0]['message']['mid'][0:10]

    def get_incoming_visitor_id(self):
        return self.message["entry"][0]['messaging'][0]['sender']['id']

    def get_visitor_token(self):
        visitor_id = self.get_visitor_id()
        token = "facebook:{0}".format(visitor_id)
        return token

    def get_visitor_username(self):
        return "facebook:{0}".format(self.get_visitor_id())

    def get_visitor_json(self):
        # cal api to get more infos
        url = "https://graph.facebook.com/{0}?fields=first_name,last_name,profile_pic&access_token={1}"
        url = url.format(
            self.get_visitor_id(),
            self.connector.config['access_token']
        )
        data = requests.get(url)
        if settings.DEBUG:
            print("GETTING FACEBOOK CONTACT: ", url)
            print("GOT: ", )
        if data.ok:
            visitor_name = "{0} {1}".format(
                data.json()["first_name"],
                data.json()["last_name"]
            )
        visitor_username = self.get_visitor_username()
        visitor_phone = ''
        visitor_token = self.get_visitor_token()
        department = self.connector.department

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

    def get_message_body(self):
        message_body = self.message['entry'][0]['messaging'][0]['message']['text']
        return message_body

    def outgo_text_message(self, message):
        visitor_id = self.get_visitor_id()
        if message.get('u', {}):
            agent_name = message.get('u', {}).get('name', {})
        else:
            agent_name = None

        if agent_name:
            content = "*[" + agent_name + "]*\n" + message['msg']
        else:
            content = message['msg']
        # replace emojis
        content = self.joypixel_to_unicode(content)
        url = "https://graph.facebook.com/v2.6/me/messages?access_token={0}".format(
            self.connector.config['access_token']
        )
        payload = {
            "recipient": {"id": visitor_id},
            "message": {
                "text": content
            }
        }
        sent = requests.post(
            url=url,
            json=payload
        )
        # register outcome
        if sent.ok and self.message_object:
            self.message_object.delivered = True
        self.message_object.payload = payload
        self.message_object.response = sent.json()
        self.message_object.save()
