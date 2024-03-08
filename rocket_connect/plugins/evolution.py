import base64
import json
import os
import time
import urllib.parse as urlparse
import datetime

import requests
from django import forms
from django.conf import settings
from django.core import validators
from django.http import JsonResponse

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    #
    # SESSION MANAGEMENT
    #
    def initialize(self):
        endpoint_create = "{}/instance/create".format(
            self.config.get("endpoint"),
        )
        secret_key = self.config.get("secret_key")
        webhook_url = self.config.get("webhook")
        instance_name = self.config.get("instance_name")
        headers = {"apiKey": secret_key, "Content-Type": "application/json"}
        # GET {{baseUrl}}/instance/create with { "instanceName": "codechat"}
        payload = {"instanceName": instance_name}
        headers = {"Content-Type": "application/json", "apikey": secret_key}

        create_instance_response = requests.request(
            "POST", endpoint_create, json=payload, headers=headers
        )
        output = {}
        output["instance_create"] = {
            "endpoint": endpoint_create,
            **create_instance_response.json(),
        }
        # GET {{baseUrl}}/instance/connect/{{instance}}

        endpoint_connect = "{}/instance/connect/{}".format(
            self.config.get("endpoint"), instance_name
        )
        connect_instance_response = requests.request(
            "GET", endpoint_connect, json=payload, headers=headers
        )
        output["instance_connect"] = {
            "endpoint": endpoint_connect,
            **connect_instance_response.json(),
        }
        # POST {{baseUrl}}/webhook/set/{{instance}}
        endpoint_webhook_set = "{}/webhook/set/{}".format(
            self.config.get("endpoint"), instance_name
        )
        
        #payload = {"enabled": True, "url": webhook_url}
        payload = {'enabled': True,
                                'events': ['APPLICATION_STARTUP',
                                           'QRCODE_UPDATED',
                                           'MESSAGES_SET',
                                           'MESSAGES_UPSERT',
                                           'MESSAGES_UPDATE',
                                           'MESSAGES_DELETE',
                                           'SEND_MESSAGE',
                                           'CHATS_SET',
                                           'CHATS_UPSERT',
                                           'CHATS_UPDATE',
                                           'CONNECTION_UPDATE',
                                           'CALL',
                                           'NEW_JWT_TOKEN'],
                                'url': webhook_url,
                                'webhook_base64': True}
        connect_instance_response = requests.request(
            "POST", endpoint_webhook_set, json=payload, headers=headers
        )
        output["instance_webhook"] = {
            "endpoint": endpoint_webhook_set,
            **connect_instance_response.json(),
        }
        return output

    def status_session(self):
        if self.config.get("endpoint", None):
            output = {}
            # GET {{baseUrl}}/instance/connectionState/{{instance}}
            secret_key = self.config.get("secret_key")
            instance_name = self.config.get("instance_name")
            headers = {"apiKey": secret_key, "Content-Type": "application/json"}

            endpoint_status = "{}/instance/connect/{}".format(
                self.config.get("endpoint"), instance_name
            )
            status_instance_response = requests.request(
                "GET", endpoint_status, headers=headers
            )
            # get webhook info
            endpoint_webhook_get_url = "{}/webhook/find/{}".format(
                self.config.get("endpoint"), instance_name
            )       
            endpoint_webhook_response = requests.request(
                "GET", endpoint_webhook_get_url, headers=headers
            )
            # fetch instances and filter for only this one
            endpoint_fetchinstances_get_url = "{}/instance/fetchInstances".format(
                self.config.get("endpoint")
            )       
            endpoint_fetchinstances_response = requests.request(
                "GET", endpoint_fetchinstances_get_url, headers=headers
            )
            if endpoint_fetchinstances_response.json():
                instance = [
                    i for i in endpoint_fetchinstances_response.json()
                    if i.get("instance").get("instanceName") == "rocketchat_evolution_test"
                ]
                if instance:
                    endpoint_fetchinstances_response = instance[0].get("instance")
            else:
                endpoint_fetchinstances_response = endpoint_fetchinstances_response.json()
                
              
            if status_instance_response:
                output = status_instance_response.json()
                output["webhook"] = endpoint_webhook_response.json()
            if endpoint_fetchinstances_response:
                output["instance"] = endpoint_fetchinstances_response
                return output
            return {"error": "no endpoint"}
        else:
            return {"error": "no endpoint"}

    def close_session(self):
        # DELETE {{baseUrl}}/instance/logout/{{instance}}
        secret_key = self.config.get("secret_key")
        instance_name = self.config.get("instance_name")
        headers = {"apiKey": secret_key, "Content-Type": "application/json"}
        endpoint_status = "{}/instance/logout/{}".format(
            self.config.get("endpoint"), instance_name
        )
        status_instance_response = requests.request(
            "DELETE", endpoint_status, headers=headers
        )
        endpoint_status = "{}/instance/delete/{}".format(
            self.config.get("endpoint"), instance_name
        )
        status_instance_response = requests.request(
            "DELETE", endpoint_status, headers=headers
        )        
        return {"success": status_instance_response.ok}


    #
    # MESSAGE HELPERS
    # 

    def get_message(self, message_id):
        
        endpoint = "{}/chat/findMessages/{}".format(
            self.config.get("endpoint"), self.config.get("instance_name")
        )
        
        payload = {
            "where": {
                "key": {
                    "id": message_id
                    }
            }
        }
        headers = {
            "apiKey": self.config.get("secret_key"),
            "Content-Type": "application/json",
        }
        response = requests.post(endpoint, headers=headers, json=payload)
        response_json = response.json()
        if len(response_json) >= 1:
            return response_json[0]
        return None


    def check_number_status(self, phone):
        
        endpoint = "{}/chat/whatsappNumbers/{}".format(
            self.config.get("endpoint"), self.config.get("instance_name")
        )
        
        payload = {
            "numbers": [
                phone
            ]
        }
        headers = {
            "apiKey": self.config.get("secret_key"),
            "Content-Type": "application/json",
        }
        response = requests.post(endpoint, headers=headers, json=payload)
        response_json = response.json()
        if len(response_json) >= 1:
            return response_json[0]
        return None


    def active_chat(self):
        """
        this method will be triggered when an active_chat needs to be places
        it has to interpret the active chat text, and do the necessary check and
        returns in order to provide.
        this method will provide options for:
        triggerword reference text
        reference can be:
            +5531111111@Department - opens a new chat at the selected department
            +5531111111@ Opens a new chat at the configured connector default department or None
        """
        # set the message type
        self.type = "active_chat"
        self.message["type"] = self.type
        department = False
        department_id = None
        transfer = False
        # get client
        self.get_rocket_client()
        now_str = datetime.datetime.now().replace(microsecond=0).isoformat()
        # get the number reference, room_id and message_id
        reference = self.message.get("text").split()[1]
        room_id = self.message.get("channel_id")
        msg_id = self.message.get("message_id")
        # get the number, or all
        number = reference.split("@")[0]
        # register number to get_visitor_id
        # emulating a regular ingoing message
        self.message["visitor"] = {"token": "whatsapp:" + number}
        check_number = self.check_number_status(number)
        # could not get number validation
        if not check_number.get("exists"):
            alert = f"COULD NOT SEND ACTIVE MESSAGE FROM *{self.connector.name}* to {number}. NUMBER INVALID OR DON'T EXISTS"
            self.logger_info(alert)
            self.rocket.chat_update(
                room_id=room_id,
                msg_id=msg_id,
                text=self.message.get("text") + f"\n:warning: {now_str} {alert}",
            )
            # return nothing
            return {"success": False, "message": "NO MESSAGE TO SEND"}
        # construct message
        texto = self.message.get("text")
        message_raw = " ".join(texto.split(" ")[2:])
        if not message_raw:
            self.rocket.chat_update(
                room_id=room_id,
                msg_id=msg_id,
                text=self.message.get("text")
                + "\n:warning: {} NO MESSAGE TO SEND. *SYNTAX: {} {} <TEXT HERE>*".format(
                    now_str, self.message.get("trigger_word"), reference
                ),
            )
            # return nothing
            return {"success": False, "message": "NO MESSAGE TO SEND"}

        # number checking
        if check_number.get("exists"):
            # can receive messages
            if "@" in reference:
                # a new room was asked to be created (@ included)
                try:
                    department = reference.split("@")[1]
                except IndexError:
                    # no department provided
                    department = None
                # check if department is valid
                if department:
                    department_check = self.rocket.call_api_get(
                        "livechat/department",
                        text=department,
                        onlyMyDepartments="false",
                    )
                    # departments found
                    departments = department_check.json().get("departments")

                    if not departments:
                        # maybe department is an online agent. let's check if
                        agents = self.rocket.livechat_get_users(
                            user_type="agent"
                        ).json()
                        available_agents = [
                            agent
                            for agent in agents["users"]
                            if agent["status"] == "online"
                            and agent["statusLivechat"] == "available"
                        ]
                        self.logger_info(
                            "NO DEPARTMENT FOUND. LOOKING INTO ONLINE AGENTS: {}".format(
                                available_agents
                            )
                        )
                        for agent in available_agents:
                            if agent.get("username").lower() == department.lower():
                                transfer = True
                                departments = ["AGENT-DIRECT:" + agent.get("_id")]
                        # transfer the room for the agent
                        if not transfer:
                            available_usernames = [
                                u["username"] for u in available_agents
                            ]
                            self.rocket.chat_update(
                                room_id=room_id,
                                msg_id=msg_id,
                                text=self.message.get("text")
                                + f"\n:warning: AGENT {department} NOT AVAILABLE OR ONLINE"
                                + f"\nAVAILABLE AGENTS {available_usernames}",
                            )
                            return {
                                "success": False,
                                "message": f"AGENT {department} NOT AVAILABLE OR ONLINE",
                                "available_agents": available_agents,
                            }
                    # > 1 departments found
                    if len(departments) > 1:
                        alert_message = "\n:warning: {} More than one department found. Try one of the below:".format(
                            now_str
                        )
                        for dpto in departments:
                            alert_message = alert_message + "\n*{}*".format(
                                self.message.get("text").replace(
                                    "@" + department, "@" + dpto["name"]
                                ),
                            )
                        self.rocket.chat_update(
                            room_id=room_id,
                            msg_id=msg_id,
                            text=self.message.get("text") + alert_message,
                        )
                        return {
                            "success": False,
                            "message": "MULTIPLE DEPARTMENTS FOUND",
                            "departments": departments,
                        }
                    # only one department, good to go.
                    if len(departments) == 1:
                        # direct chat to user
                        # override department, and get agent name
                        if "AGENT-DIRECT:" in departments[0]:
                            agent_id = departments[0].split(":")[1]
                            self.logger_info(f"AGENT-DIRECT TRIGGERED: {agent_id}")
                            department = None
                        else:
                            department = departments[0]["name"]
                            department_id = departments[0]["_id"]

                        # define message type
                        self.type = "active_chat"
                        # register message
                        message, created = self.register_message()
                        # do not send a sent message
                        if message.delivered:
                            return {
                                "success": False,
                                "message": "MESSAGE ALREADY SENT",
                            }
                        # create basic incoming new message, as payload
                        self.type = "incoming"
                        self.message = {
                            "from": check_number.get("response")
                            .get("id")
                            .get("_serialized"),
                            "chatId": check_number.get("response")
                            .get("id")
                            .get("_serialized"),
                            "id": self.message.get("message_id"),
                            "visitor": {
                                "token": "whatsapp:"
                                + check_number["response"]["id"]["_serialized"]
                            },
                        }
                        self.check_number_info(
                            check_number["response"]["id"]["user"], augment_message=True
                        )
                        self.logger_info(
                            f"ACTIVE MESSAGE PAYLOAD GENERATED: {self.message}"
                        )
                        # if force transfer for active chat, for it.

                        # register room
                        room = self.get_room(
                            department,
                            allow_welcome_message=False,
                            check_if_open=True,
                            force_transfer=department_id,
                        )
                        if room:
                            self.logger_info(f"ACTIVE CHAT GOT A ROOM {room}")
                            # send the message to the room, in order to be delivered to the
                            # webhook and go the flow
                            # send message_raw to the room
                            self.get_rocket_client(bot=True)
                            post_message = self.rocket.chat_post_message(
                                text=message_raw, room_id=room.room_id
                            )
                            # change the message with checkmark
                            if post_message.ok:
                                if transfer:
                                    payload = {
                                        "roomId": room.room_id,
                                        "userId": agent_id,
                                    }
                                    self.rocket.call_api_post(
                                        "livechat/room.forward", **payload
                                    )
                                self.rocket.chat_update(
                                    room_id=room_id,
                                    msg_id=msg_id,
                                    text=":white_check_mark: " + texto,
                                )
                                # register message delivered
                                if self.message_object:
                                    self.message_object.delivered = True
                                    self.message_object.save()
                                return {
                                    "success": True,
                                    "message": "MESSAGE SENT",
                                }
                            else:
                                return {
                                    "success": False,
                                    "message": "COULD NOT SEND MESSAGE",
                                }

                        else:
                            return {
                                "success": False,
                                "message": "COULD NOT CREATE ROOM",
                            }

                # register visitor

            else:
                # no department, just send the message
                self.message["event"] = "call"
                self.message["data"] = {"from": check_number.get("jid")}
                message = {"msg": message_raw}
                sent = self.outgo_text_message(message)
                if sent and sent.ok:
                    # return {
                    #     "text": ":white_check_mark: SENT {0} \n{1}".format(
                    #         number, message_raw
                    #     )
                    # }
                    # update message
                    self.rocket.chat_update(
                        room_id=room_id,
                        msg_id=msg_id,
                        text=":white_check_mark: " + self.message.get("text"),
                    )
                    return {"success": True, "message": "MESSAGE SENT", "data": sent.json()}
                else:
                    self.rocket.chat_update(
                        room_id=room_id,
                        msg_id=msg_id,
                        text=":warning: "
                        + self.message.get("text")
                        + "\n ERROR WHILE SENDING MESSAGE",
                    )
                    return {"success": False, "message": "ERROR WHILE SENDING MESSAGE"}

        # if cannot receive message, report
        else:
            # check_number failed, not a valid number
            # report back that it was not able to send the message
            # return {"text": ":warning:  INVALID NUMBER: {0}".format(number)}
            self.rocket.chat_update(
                room_id=room_id,
                msg_id=msg_id,
                text=self.message.get("text") + f"\n:warning: {now_str} INVALID NUMER",
            )
            return {"success": True, "message": "INVALID NUMBER"}



    #
    # INCOMING HANDLERS
    #

    def incoming(self):
        message = json.dumps(self.message)
        self.logger_info(f"INCOMING MESSAGE: {message}")

        # conector actions
        if self.message.get("action"):
            # check if session managemnt is active
            if self.config.get("session_management_token"):
                if self.message.get("session_management_token") != self.config.get(
                    "session_management_token"
                ):
                    output = {"success": False, "message": "INVALID TOKEN"}
                    return JsonResponse(output)
                else:
                    action = self.message.get("action")
                    output = {"action": action}
                    if action == "start":
                        response = self.connector.initialize()
                    if action == "status":
                        response = self.connector.status_session()
                    if action == "close":
                        response = self.connector.close_session()
                    if action == "livechat":
                        response = self.livechat_manager(self.message)

                    # return status
                    output = {**output, **response}
                    self.logger_info(f"RETURN OF ACTION MESSAGE: {output}")
                    return JsonResponse(output)

        # webhook active chat integration
        if self.config.get("active_chat_webhook_integration_token"):
            if self.message.get("token") == self.config.get(
                "active_chat_webhook_integration_token"
            ):
                self.logger_info("active_chat_webhook_integration_token triggered")
                message, created = self.register_message()
                req = self.active_chat()
                return JsonResponse(req)    

        #
        # qrcode reading
        #
        if self.message.get("event") == "qrcode.updated":
            base64 = self.message.get("data", {}).get("qrcode", {}).get("base64")
            if base64:
                self.outcome_qrbase64(base64)
            return JsonResponse({})
        #
        # connection update
        #
        if self.message.get("event") == "connection.update":
            data = self.message.get("data", {})
            text = "*CONNECTOR NAME:* {} > {}".format(
                self.connector.name, json.dumps(data)
            )
            if data.get("state") == "open":
                text = text + "\n" + " ✅ " * 6
            self.outcome_admin_message(text)
            return JsonResponse({})
        #
        # message upsert
        #
        if self.message.get("event") == "messages.upsert":                
            department = None
            message_obj, created = self.register_message()
            if not message_obj.delivered:
                message = self.message.get("data", {}).get("message", {})
                # get room
                room = self.get_room(department)
                if not room:
                    return JsonResponse({"message": "no room generated"})
                #
                # outcome if is a reaction
                #
                if self.message.get("data").get("messageType") == "reactionMessage":
                    
                    ref_message = self.message.get("data").get("message").get("reactionMessage")
                    ref_id = ref_message.get("key").get("id")
                    original_message = self.get_message(ref_id)
                    if not original_message:
                        # could not find message
                        self.message_object.delivered = True
                        self.message_object.save()
                        return JsonResponse({})
                    if original_message.get("message").get("extendedTextMessage"):
                        msg = original_message.get("message").get("extendedTextMessage").get("text")
                    elif original_message.get("message").get("imageMessage"):
                        msg = original_message.get("message").get("imageMessage").get("caption") + " Some Image"
                    else:
                        msg = "some message (audio, for example)"
                    reaction = ref_message.get("text")
                    new_message = "Reacted: {} to: {}".format(
                        reaction, msg
                    )
                    room = self.get_room()
                    self.outcome_text(
                        room_id=room.room_id, text=new_message, message_id=self.get_message_id()
                    ).json()
                    return JsonResponse({})
                #
                # oucome if text
                #
                if message.get("extendedTextMessage"):
                    text = (
                        self.message.get("data", {})
                        .get("message", {})
                        .get("extendedTextMessage")
                        .get("text")
                    )
                    deliver = self.outcome_text(room.room_id, text)
                    print(deliver)
                #
                # outcome if image
                #
                if (
                    message.get("imageMessage")
                    or message.get("audioMessage")
                    or message.get("videoMessage")
                    or message.get("stickerMessage")
                    or message.get("documentWithCaptionMessage")
                    or message.get("documentMessage")
                    or message.get("contactsArrayMessage")
                    or message.get("locationMessage")
                    or message.get("stickerMessage")
                ):
                    filename = None
                    caption = None
                    mime = None

                    # files that are actually text
                    if message.get("contactsArrayMessage"):
                        for contact in message.get("contactsArrayMessage").get(
                            "contacts"
                        ):
                            sent = self.outcome_text(
                                room_id=room.room_id,
                                text=f"{contact.get('displayName')}\n{contact.get('vcard')}",
                            )
                        if sent.ok:
                            self.message_object.delivered = True
                            self.message_object.save()
                        return JsonResponse({})

                    if message.get("locationMessage"):
                        message_type = "locationMessage"
                        text = (
                            f"Lat: {message.get(message_type).get('degreesLatitude')} "
                        )
                        +"Lon: {message.get(message_type).get('degreesLongitude')}"
                        self.outcome_text(room.room_id, text=text)
                        return JsonResponse({})

                    # "real" files
                    if message.get("imageMessage"):
                        message_type = "imageMessage"

                    if message.get("audioMessage"):
                        message_type = "audioMessage"
                        self.handle_ptt()

                    if message.get("videoMessage"):
                        message_type = "videoMessage"

                    if message.get("stickerMessage"):
                        # TODO: sticker not supported
                        return JsonResponse({})
                        message_type = "stickerMessage"

                    if message.get("documentWithCaptionMessage"):
                        message_type = "documentWithCaptionMessage"
                        filename = (
                            message.get(message_type)
                            .get("message")
                            .get("documentMessage")
                            .get("title")
                        )
                        caption = (
                            message.get(message_type)
                            .get("message")
                            .get("documentMessage")
                            .get("caption")
                        )
                        mime = (
                            message.get(message_type)
                            .get("message")
                            .get("documentMessage")
                            .get("mimetype")
                        )
                    if message.get("documentMessage"):
                        message_type = "documentMessage"
                        filename = message.get(message_type).get("title")
                        mime = message.get(message_type).get("mimetype")

                    if not caption:
                        # get default caption
                        caption = message.get(message_type, {}).get("caption")

                    if not mime:
                        mime = message.get(message_type).get("mimetype")

                    # payload = {
                    #     "key": {
                    #         "id": self.message.get("data", {}).get("key", {}).get("id")
                    #     }
                    # }
                    payload = {
                        "message": {
                            "key": {
                                "id": self.message.get("data", {}).get("key", {}).get("id")
                            }
                        },
                        "convertToMp4": False
                    }                        
                    url = self.connector.config[
                        "endpoint"
                    ] + "/chat/getBase64FromMediaMessage/{}".format(
                        self.connector.config["instance_name"]
                    )
                    headers = {
                        "apiKey": self.config.get("secret_key"),
                        "Content-Type": "application/json",
                    }
                    media_body = requests.post(url, headers=headers, json=payload)
                    
                    if media_body.ok:
                        body = media_body.json().get("base64")
                        filename = filename

                        file_sent = self.outcome_file(
                            body,
                            room.room_id,
                            mime,
                            description=caption,
                            filename=filename,
                        )
                        self.logger_info(
                            f"Outcoming message. url {url}, file sent: {file_sent.json()}"
                        )
                        if file_sent.ok:
                            self.message_object.delivered = True
                            self.message_object.save()
                    else:
                        self.logger_info(
                            f"GETTOMG message MEDIA ERROR. url {url}, file sent: {media_body.json()} media_body"
                        )

            else:
                self.logger_info(
                    f"Message Object {message.id} Already delivered. Ignoring"
                )
            return JsonResponse({})
        #
        # messages deletion
        #        
        if self.message.get("event") == "messages.delete":
            if self.connector.server.type == "rocketchat":
                # TODO: move this code do base?
                ref_id = self.message.get("data").get("id")
                if ref_id:
                    self.get_rocket_client()
                    msg = self.rocket.chat_get_message(msg_id=ref_id)
                    if msg:
                        new_message = ":warning:  DELETED: ~{}~".format(
                            msg.json()["message"]["msg"]
                        )
                        room = self.get_room()
                        self.rocket.chat_update(
                            room_id=room.room_id, msg_id=ref_id, text=new_message
                        )

        #
        # handle calls
        #
        if self.message.get("event") == "call":
            # handle incoming call
            self.get_rocket_client()
            message, created = self.register_message()
            if not message.delivered:
                room = self.get_room()
                self.handle_incoming_call()
            return JsonResponse({})
        #
        # handle sent and acks confirmation
        #
        if self.message.get("event") in ["send.message"] and \
                self.message.get("data", {}).get("key", {}).get("fromMe") == True:
            self.logger_info("ACK MESSAGE SENT")
            self.handle_ack_fromme_message()
            return JsonResponse({})        
        
        if self.message.get("event") in ["messages.update"] and \
                self.message.get("data", {}).get("fromMe") == True:
            self.logger_info("ACK MESSAGE RECEIVED")
            self.handle_ack_fromme_message()
            return JsonResponse({})


        return JsonResponse({})

    def handle_ack_fromme_message(self):
        # ack receipt
        if (
            self.config.get("enable_ack_receipt")
            and self.connector.server.type == "rocketchat"
        ):
            # get the message id from whatsapp, find rocket.chat message and update
            message_id = self.get_message_id()
            self.logger_info("Handling ack from me for message id: " + message_id)
            self.get_rocket_client()
            for message in self.connector.messages.filter(
                response__id__contains=message_id
            ):
                self.logger_info("Found message to handle ack: " + message.envelope_id)
                # or add only the white check
                original_message = self.rocket.chat_get_message(
                    msg_id=message.envelope_id
                )
                body = original_message.json()["message"]["msg"]
                # remove previous markers
                body = body.replace(":ballot_box_with_check:", "")
                body = body.replace(":white_check_mark:", "")
                if self.message.get("data", {}).get("status") == "DELIVERY_ACK":
                    mark = ":white_check_mark:"
                else:
                    mark = ":ballot_box_with_check:"
                self.rocket.chat_update(
                    room_id=message.room.room_id,
                    msg_id=message.envelope_id,
                    text=f"{mark} {body}",
                )
                message.ack = True
                message.save()

    #
    # OUTGO
    #

    def outgo_text_message(self, message, agent_name=None):
        if type(message) == str:
            content = message
        else:
            content = message["msg"]
        payload = {
            "number": self.get_ingoing_visitor_phone() or self.get_visitor_phone(),
            "options": {"delay": self.connector.config.get("send_message_delay", 1200)},
            "textMessage": {"text": content},
        }
        url = self.connector.config["endpoint"] + "/message/SendText/{}".format(
            self.connector.config["instance_name"]
        )
        headers = {
            "apiKey": self.config.get("secret_key"),
            "Content-Type": "application/json",
        }
        sent = requests.post(url, headers=headers, json=payload)
        sent_json = sent.json()
        self.logger_info(
            f"OUTGO TEXT MESSAGE. URL: {url}. PAYLOAD {payload} RESULT: {sent_json}. {sent}"
        )
        timestamp = int(time.time())
        if self.message_object and sent.ok:
            self.message_object.delivered = sent.ok
            self.message_object.response[timestamp] = sent.json()
            if not self.message_object.response.get("id"):
                self.message_object.response["id"] = [
                    sent.json()["key"]["id"]
                ]
            self.message_object.save()
        return sent

    def outgo_file_message(self, message, file_url=None, mime=None, agent_name=None):
        caption = None
        if not file_url:
            file_url = (
                self.connector.server.url
                + message["attachments"][0]["title_link"]
                + "?"
                + urlparse.urlparse(message["fileUpload"]["publicFilePath"]).query
            )
            caption = message["attachments"][0].get("description")
        content = base64.b64encode(requests.get(file_url).content).decode("utf-8")
        file_name = os.path.basename(file_url).split("?")[0]
        if not mime:
            mime = self.message["messages"][0]["fileUpload"]["type"]
        mediatype = mime.split("/")[0]
        if mediatype == "application":
            mediatype = "document"
        payload = {
            "number": self.get_ingoing_visitor_phone(),
            "options": {"delay": self.connector.config.get("send_message_delay", 1200)},
            "mediaMessage": {
                "mediatype": mediatype,
                "fileName": file_name,
                "media": content,
            },
        }
        if caption:
            payload["mediaMessage"]["caption"] = str(caption)
        url = self.connector.config["endpoint"] + "/message/SendMedia/{}".format(
            self.connector.config["instance_name"]
        )
        headers = {
            "apiKey": self.config.get("secret_key"),
            "Content-Type": "application/json",
        }
        sent = requests.post(url, headers=headers, json=payload)
        self.logger_info(
            f"OUTGOING FILE. URL: {url}. PAYLOAD {payload} response: {sent.json()}"
        )
        if sent.ok:
            # Audio doesnt have caption, so outgo as message
            if mediatype == "audio" and caption:
                self.outgo_text_message(caption)
            timestamp = int(time.time())
            if settings.DEBUG:
                self.logger.info(f"RESPONSE OUTGOING FILE to url {url}: {sent.json()}")
            self.message_object.payload[timestamp] = payload
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            self.message_object.save()
            # self.send_seen()
        return sent

    #
    # MESSAGE METADA DATA
    #
    def get_incoming_message_id(self):
        id = None
        if self.message.get("event") in ["messages.upsert", "send.message"]:
            id = self.message.get("data", {}).get("key", {}).get("id")
        elif self.message.get("event") in ["call", "messages.update"]:
            id = self.message.get("data", {}).get("id")
        return id

    def get_visitor_name(self):
        name = self.message.get("data", {}).get("pushName")
        if name:
            return name
        return None

    def get_visitor_phone(self):
        # the phone can come both as remoteJid or chatId, for when it
        if self.message.get("event") == "call":
            remoteJid = self.message.get("data", {}).get("from")
        elif self.message.get("event") == "messages.delete":
            remoteJid = self.message.get("data", {}).get("remoteJid")
        else:
            remoteJid = self.message.get("data", {}).get("key", {}).get("remoteJid")
        if remoteJid:
            return remoteJid.split("@")[0]
        return None

    def get_visitor_username(self):
        visitor_username = f"whatsapp:{self.get_visitor_phone()}@c.us"
        return visitor_username

    def get_incoming_visitor_id(self):
        return self.get_visitor_phone() + "@c.us"

    # def get_visitor_avatar_url(self):
    #     secret_key = self.config.get("secret_key")
    #     headers = {"apiKey": secret_key, "Content-Type": "application/json"}
    #     url = self.connector.config["endpoint"] + "/chat/fetchProfilePictureUrl/{}".format(
    #         self.connector.config["instance_name"]
    #     )
    #     payload = {
    #     "number": self.get_visitor_phone()
    #     }
    #     headers = {
    #         "apiKey": self.config.get("secret_key"),
    #         "Content-Type": "application/json",
    #     }
    #     profile_picture_request = requests.post(url, headers=headers, json=payload)
    #     if profile_picture_request.ok:
    #         profile_url = profile_picture_request.json().get("profilePictureUrl")
    #         self.logger_info(f"GOT PROFILE URL: {profile_url}")
    #         return profile_picture_request.json().get("profilePictureUrl")


class ConnectorConfigForm(BaseConnectorConfigForm):

    def __init__(self, *args, **kwargs):
        self.connector = kwargs.get("connector")
        super().__init__(*args, **kwargs)
        if self.connector.server.type == "rocketchat":
            self.fields["active_chat_webhook_integration_token"] = forms.CharField(
                required=False,
                help_text="Put here the same token used for the active chat integration",
                validators=[validators.validate_slug],
            )
            self.fields["active_chat_force_department_transfer"] = forms.BooleanField(
                help_text="If the Chat is already open, force the transfer to this department",
                required=False,
                initial=False,
            )

    webhook = forms.CharField(
        help_text="Where Evolution will send the events", required=True, initial=""
    )
    endpoint = forms.CharField(
        help_text="Where your Evolution is installed",
        required=True,
        initial="http://evolution:8084",
    )
    secret_key = forms.CharField(
        help_text="The secret ApiKey for your Evolution instance",
        required=True,
    )
    instance_name = forms.CharField(
        help_text="Evolution instance name", validators=[validators.validate_slug]
    ),

    send_message_delay = forms.IntegerField(
        help_text="Evolution delay to send message. Defaults to 1200", initial=1200
    ),

    enable_ack_receipt = forms.BooleanField(
        required=False,
        help_text="This will update the ingoing message to show it was delivered and received",
    )
    session_management_token = forms.CharField(required=False)

    field_order = [
        "webhook",
        "endpoint",
        "secret_key",
        "instance_name",
        "send_message_delay",
        "enable_ack_receipt",
        "session_management_token",
        "active_chat_webhook_integration_token",
        "active_chat_force_department_transfer",
    ]
