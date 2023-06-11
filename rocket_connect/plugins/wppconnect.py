import base64
import datetime
import json
import time
import urllib.parse as urlparse

import pytz
import requests
import urllib3
import vobject
from django import forms
from django.conf import settings
from django.core import validators
from django.http import JsonResponse
from django.utils import timezone
from instance import tasks

from .base import BaseConnectorConfigForm
from .base import Connector as ConnectorBase


class Connector(ConnectorBase):
    """ """

    def populate_config(self):
        self.connector.config = {
            "webhook": "http://127.0.0.1:8000/connector/WPP_EXTERNAL_TOKEN/",
            "endpoint": "http://wppconnect:8080",
            "secret_key": "My53cr3tKY",
            "instance_name": "test",
        }
        self.save()

    def generate_token(self):
        # generate token
        endpoint = "{}/api/{}/{}/generate-token".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
            self.config.get("secret_key"),
        )
        token = requests.post(endpoint, timeout=1)
        if token.ok:
            token = token.json()
            self.connector.config["token"] = token
            self.connector.save()
            return token
        # TODO: here may fail if wppconnect secret token
        # is differnet. It  would be nice to alert this
        return False

    def status_session(self):
        # generate token
        status = {}
        if self.config.get("endpoint", None):
            endpoint = "{}/api/{}/status-session".format(
                self.config.get("endpoint"),
                self.config.get("instance_name"),
            )
            session = self.get_request_session()
            try:
                status_req = session.get(endpoint, timeout=1)
                if status_req.ok:
                    status = status_req.json()
                    # if connected, get battery and host device
                    if status.get("status") == "CONNECTED":
                        # host device
                        endpoint = "{}/api/{}/host-device".format(
                            self.config.get("endpoint"),
                            self.config.get("instance_name"),
                        )
                        host_device = session.get(endpoint, timeout=1).json()
                        status["host_device"] = host_device["response"]
                else:
                    status = {"success": False, **status_req.json()}
            except urllib3.exceptions.ReadTimeoutError as e:
                status = {"success": False, "message": str(e)}
        if status.get("status") in ["CLOSED", "CONNECTED"]:
            if status.get("qrcode"):
                del status["qrcode"]
            if status.get("urlcode"):
                del status["urlcode"]
        return status

    def close_session(self):
        # generate token
        endpoint = "{}/api/{}/close-session".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )
        token = self.config.get("token", {}).get("token")
        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        status_req = requests.post(endpoint, headers=headers)
        if status_req.ok:
            status = status_req.json()
            return status
        return False

    def livechat_manager(self, payload):
        """
        options:
        rc livechat forward 30d alice Consultas - This will *forward* all messages created 30+ minutes
        ago with the user alice to department Consultas',
        rc livechat forward 30m * Consultas - Same as above, but for all agents
        rc livechat close 30d alice - This will *close* all messages created 30+ days ago served by the user alice',
        rc livechat close 30m - This will *close* all messages created 30+ minutes ago,'

        """
        text = payload.get("text")
        parts = text.split(" ")
        messages = ["server return: " + text]
        minutes = None
        days = None
        try:
            time = parts[3]
            minutes = int(time)
        except ValueError:
            time = parts[3]
            try:
                if time.endswith("m"):
                    minutes = int(time[:-1])
                if time.endswith("d"):
                    days = int(time[:-1])
            except ValueError:
                messages.append(
                    "Invalid time. It must be, ex: 30m for 30 minutes, or 10d for 10 days"
                )
                return {"success": False, "message": "\n".join(messages)}
        if minutes or minutes == 0:
            date_created_ago = timezone.now() - datetime.timedelta(minutes=minutes)
        if days or days == 0:
            date_created_ago = timezone.now() - datetime.timedelta(days=days)

        kwargs = {
            "open": "true",
            "createdAt": '{"end": "'
            + date_created_ago.isoformat().replace("+00:00", "Z")
            + '"}',
        }

        if parts[2] == "close":
            local_time = date_created_ago.replace(tzinfo=pytz.utc).astimezone(
                pytz.timezone(self.timezone)
            )
            messages.append(
                "Closing rooms created before: {}".format(
                    str(local_time),
                )
            )
            # defining agent
            try:
                agent = parts[4]
                if agent != "*":
                    kwargs["agents"] = [agent]
                serving_agent = agent if agent else "ALL"
                msg = f"Rooms with agent serving: {serving_agent}"
                messages.append(msg)
            except IndexError:
                # the close action may not have agent
                pass

        if parts[2] == "forward":
            messages.append(
                "Forwarding open rooms created before: " + date_created_ago.isoformat()
            )
            # defining agent
            try:
                agent = parts[4]
                if agent != "*":
                    kwargs["agents"] = [agent]
                serving_agent = agent if agent else "ALL"
                msg = f"Rooms with agent serving: {serving_agent}"
                messages.append(msg)
            except IndexError:
                messages.append("ERROR! No Agent Provided.")
                return {"success": False, "message": "\n".join(messages)}
            # defining department

        self.get_rocket_client()

        rooms = self.rocket.livechat_rooms(**kwargs).json()
        messages.append("Rooms found:" + str(len(rooms["rooms"])))
        for room in rooms["rooms"]:
            if parts[2] == "close":
                room_id = room["_id"]
                close = self.rocket.call_api_post(
                    "livechat/room.close", rid=room_id, token=room["v"]["token"]
                )
                room_url = "{}/omnichannel/current/{}/room-info".format(
                    self.connector.server.external_url, room_id
                )
                if close.ok:
                    messages.append(
                        ":heavy_check_mark: [Room closed: {}]({})".format(
                            room_id, room_url
                        )
                    )
                else:
                    messages.append(
                        ":stop_sign: (ERROR CLOSING ROOM: {}]({})".format(
                            room_id, room_url
                        )
                    )
        return {"success": True, "message": "\n".join(messages)}

    def check_number_status(self, number):
        endpoint = "{}/api/{}/check-number-status/{}".format(
            self.config.get("endpoint"), self.config.get("instance_name"), number
        )

        token = self.config.get("token", {}).get("token")

        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        data = {"webhook": self.config.get("webhook")}
        try:
            start_session_req = requests.get(endpoint, headers=headers, json=data)
            self.logger.info(f"CHECKING NUMBER: {number}: {start_session_req.json()}")
            return start_session_req.json()
        except requests.ConnectionError:
            return {"success": False, "message": "Could not connect to wppconnect"}

    def check_number_info(self, number, augment_message=False):
        """
        this method will get infos from the contact api and insert
        into self message
        """
        endpoint = "{}/api/{}/contact/{}".format(
            self.config.get("endpoint"), self.config.get("instance_name"), number
        )

        token = self.config.get("token", {}).get("token")

        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")

        headers = {"Authorization": "Bearer " + token}
        number_info_req = requests.get(endpoint, headers=headers)
        number_info = number_info_req.json()
        self.logger.info(f"CHECKING CONTACT INFO FOR  NUMBER {number}: {number_info}")
        if augment_message:
            if not self.message.get("sender"):
                self.message["sender"] = {}
            name_order = self.config.get(
                "name_extraction_order", "pushname,name,shortName"
            )
            if number_info.get("response"):
                for order in name_order.split(","):
                    if number_info.get("response", {}).get(order, False):
                        self.message["sender"][order] = number_info.get(
                            "response", {}
                        ).get(order)

        return number_info_req.json()

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
        if not check_number.get("response", {}).get("numberExists", False):
            alert = f"COULD NOT SEND ACTIVE MESSAGE TO *{self.connector.name}*"
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
        if check_number.get("response", {}).get("canReceiveMessage", False):
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
                self.message["chatId"] = number
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
                    return {"success": True, "message": "MESSAGE SENT"}
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

    def start_session(self):
        endpoint = "{}/api/{}/start-session".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )

        token = self.config.get("token", {}).get("token")

        if not token:
            self.generate_token()
            token = self.config.get("token", {}).get("token")
            # could not generate token, return error
            return {
                "success": False,
                "message": "Could not generate token. Check secret key",
            }

        headers = {"Authorization": "Bearer " + token}
        data = {"webhook": self.config.get("webhook")}
        start_session_req = requests.post(endpoint, headers=headers, json=data)
        if start_session_req.ok:
            start_session = start_session_req.json()
            if start_session.get("status") == "CLOSED":
                if start_session.get("qrcode"):
                    del start_session["qrcode"]
                if start_session.get("urlcode"):
                    del start_session["urlcode"]
            return start_session
        return False

    def initialize(self):
        """
        c = Connector.objects.get(pk=12)
        cls = c.get_connector_class()
        ci = cls(connector=c, message={}, type="incoming")
        """
        # generate token
        try:
            self.generate_token()
        except requests.ConnectionError:
            return {"success": False, "message": "ConnectionError"}
        # start session
        return self.start_session()

    def incoming(self):
        """
        this method will process the incoming messages
        and ajust what necessary, to output to rocketchat
        """
        message = json.dumps(self.message)
        self.logger_info(f"INCOMING MESSAGE: {message}")
        # qr code

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

        if self.message.get("event") == "qrcode":
            base64_fixed_code = self.message.get("qrcode")
            self.outcome_qrbase64(base64_fixed_code)

        # admin message
        if self.message.get("event") == "status-find":
            text = "Session: {}. Status: {}".format(
                self.message.get("session"), self.message.get("status")
            )
            if self.message.get("status") in ["isLogged", "inChat", "qrReadSuccess"]:
                text = text + " ✅ ✅ ✅ " + "SUCESS!!! ✅ ✅ ✅ "
                # call intake unread task
                if self.config.get("process_unread_messages_on_start", False):
                    tasks.intake_unread_messages.delay(self.connector.id)
            self.outcome_admin_message(text)

        if self.message.get("event") == "incomingcall":
            # handle incoming call
            self.get_rocket_client()
            message, created = self.register_message()
            room = self.get_room()
            self.handle_incoming_call()

        # message
        if self.message.get("event") in ["onmessage", "unreadmessages"]:
            department = None
            if self.message.get("event") == "unreadmessages":
                self.logger_info(f"PROCESSING UNREAD MESSAGE. PAYLOAD {self.message}")
                # if it's a message from Me, ignore:
                if self.message.get("id", {}).get("fromMe"):
                    self.handle_ack_fromme_message()
                    return JsonResponse({})
                # adapt unread messages to intake like a regular message
                pass
            # direct messages only
            if not self.message.get(
                "isGroupMsg", False
            ) and "status@broadcast" not in self.message.get("from"):
                # register message
                message, created = self.register_message()
                if not message.delivered:
                    # get rocket client
                    # self.get_rocket_client()
                    # if not self.rocket:
                    #     return HttpResponse("Rocket Down!", status=503)
                    # department triage is enabled
                    if self.config.get("department_triage"):
                        # message has no department, always
                        # outcome department_triage_payload
                        # if it's not a button reply
                        # there is not room
                        room = self.get_room(department, create=False)
                        if not room:
                            # get departments and buttons
                            buttons = []
                            departments = self.rocket.call_api_get(
                                "livechat/department"
                            ).json()
                            department_triage_to_ignore = self.config.get(
                                "department_triage_to_ignore", ""
                            ).split(",")
                            for department in departments.get("departments"):
                                if department.get("enabled"):
                                    if (
                                        department.get("_id")
                                        not in department_triage_to_ignore
                                    ):
                                        button = {
                                            "id": department.get("_id"),
                                            "text": department.get("name"),
                                        }
                                        buttons.append(button)
                            # the message is a button reply. we now register the room
                            # with the choosen department and return
                            if self.message.get("type") == "template_button_reply":
                                # the department text is body
                                choosen_department = self.message.get("body")
                                department_map = {}
                                for b in buttons:
                                    department_map[b["text"]] = b["buttonId"]
                                department = department_map[choosen_department]
                            else:
                                # add destination phone
                                payload = self.config.get("department_triage_payload")
                                if not payload.get("options"):
                                    payload["options"] = {"buttons": []}
                                if not payload.get("options").get("buttons"):
                                    payload["options"]["buttons"] = []
                                payload["phone"] = self.get_visitor_id()
                                payload_buttons = payload["options"]["buttons"]
                                # limit to 3 department buttons, otherwise will not work
                                payload["options"]["buttons"] = (
                                    buttons[:3] + payload_buttons
                                )
                                payload["options"]["buttons"] = payload["options"][
                                    "buttons"
                                ][:5]
                                # payload["options"]["buttons"] = buttons
                                # outcome buttons
                                message = {"msg": json.dumps(payload)}
                                self.outgo_text_message(message)
                                return JsonResponse(
                                    {
                                        "sucess": True,
                                        "message": "Departments triage button list sent",
                                    }
                                )
                    # get room
                    room = self.get_room(department)
                    #
                    # no room was generated
                    #
                    if not room:
                        return JsonResponse({"message": "no room generated"})

                    #
                    # type uknown
                    #
                    if self.message.get("type") == "unknown":
                        # in case it has message object attached
                        if not self.message_object.delivered:
                            self.message_object.delivered = True
                            self.message_object.save()
                        return JsonResponse({"message": "uknown type"})

                    #
                    # process different type of messages
                    #
                    # text type or dynamic button press
                    if self.message.get("type") == "chat" or self.message.get(
                        "quotedMsg", {}
                    ).get("isDynamicReplyButtonsMsg"):
                        # pre define the message to be delivered
                        message = self.get_message_body()
                        # Quoted Message in chat message and not a reply to a button
                        if self.message.get("quotedMsgId") and not self.message.get(
                            "quotedMsg", {}
                        ).get("isDynamicReplyButtonsMsg"):
                            quote_type = self.message.get("quotedMsg").get("type")
                            # type of message quoted is text
                            if quote_type == "chat":
                                quoted_body = self.message.get("quotedMsg").get("body")
                                if self.connector.config.get(
                                    "outcome_message_with_quoted_message", True
                                ):
                                    message = ":arrow_forward:  IN RESPONSE TO: {0} \n:envelope: {1}"
                                    message = message.format(
                                        quoted_body,
                                        self.get_message_body(),
                                    )
                            # type of message is others
                            elif quote_type in ["document", "image", "ptt"]:
                                message = "DOCUMENT RESENT:\n {}".format(
                                    self.get_message_body()
                                )
                                mime = self.message.get("quotedMsg").get("mimetype")
                                # THE QUOTED BODY SEEMS CORRUPT
                                # body = self.message.get("quotedMsg").get("body")
                                # LETS GET THE ORIGINAL
                                # session = self.get_request_session()
                                # endpoint = "{0}/api/{1}/message-by-id/{2}".format(
                                #     self.config.get("endpoint"),
                                #     self.config.get("instance_name"),
                                #     self.message.get("quotedMsgId")
                                # )
                                # session = self.get_request_session()
                                # quoted_message = session.get(endpoint).json()
                                # file_to_send = self.message.get("quotedMsg").get("body")
                                # none of the above worked.
                                # will need to get original content from rocket.connect
                                try:
                                    quoted_message = self.connector.messages.get(
                                        envelope_id=self.message.get("quotedMsgId")
                                    )
                                    file_to_send = quoted_message.raw_message["body"]
                                except self.connector.messages.model.DoesNotExist:
                                    file_to_send = None
                                if file_to_send:
                                    filename = self.message.get("filename")
                                    file_sent = self.outcome_file(
                                        file_to_send,
                                        room.room_id,
                                        mime,
                                        filename=filename,
                                        description=self.message.get("quotedMsg").get(
                                            "caption", None
                                        ),
                                    )

                        # deliver text message
                        if room:
                            deliver = self.outcome_text(room.room_id, message)
                            if settings.DEBUG:
                                self.logger_info(
                                    f"DELIVER OF TEXT MESSAGE: {deliver.ok}"
                                )
                    # location type
                    elif self.message.get("type") == "location":
                        lat = self.message.get("lat")
                        lng = self.message.get("lng")
                        link = "https://www.google.com/maps/search/?api=1&query={}+{}".format(
                            lat, lng
                        )
                        text = "Lat:{}, Long:{}: Link: {}".format(
                            lat,
                            lng,
                            link,
                        )
                        self.outcome_text(
                            room.room_id, text, message_id=self.get_message_id()
                        )

                    elif self.message.get("type") == "vcard":
                        content = self.message.get("content")
                        vcard = vobject.readOne(content)
                        import sys
                        from io import StringIO

                        buffer = StringIO()
                        sys.stdout = buffer
                        vcard.prettyPrint()
                        print_output = buffer.getvalue()
                        sys.stdout = sys.__stdout__
                        self.outcome_text(
                            room.room_id, print_output, message_id=self.get_message_id()
                        )

                    # upload type
                    else:
                        body = self.message.get("body")
                        if self.message.get("type") == "ptt":
                            self.handle_ptt()
                        if self.message.get("type") in ["poll_creation"]:
                            return JsonResponse({})
                            # download the media file
                            # NOT WORKING FOR NOW
                            # session = self.get_request_session()
                            # endpoint = "{0}/api/{1}/get-media-by-message/{2}".format(
                            #     self.config.get("endpoint"),
                            #     self.config.get("instance_name"),
                            #     self.message.get("id")
                            # )
                            # # payload = {
                            # #     "messageId": self.message.get("id")
                            # # }
                            # payload = None
                            # media = session.get(endpoint, json=payload).json()

                        # media type
                        mime = self.message.get("mimetype")
                        filename = self.message.get("filename")
                        if body:
                            file_sent = self.outcome_file(
                                body,
                                room.room_id,
                                mime,
                                description=self.message.get("caption", None),
                                filename=filename,
                            )
                            if file_sent.ok:
                                self.message_object.delivered = True
                                self.message_object.save()
                        else:
                            # COULD NOT SEND MESSAGE WITHOUT BODY. MARK AS DELIVERED
                            self.message_object.delivered = True
                            self.message_object.save()

                else:
                    self.logger_info(
                        "Message Object {} Already delivered. Ignoring".format(
                            message.id
                        )
                    )

        # handle ack fromme
        if self.message.get("event") == "onack":
            self.handle_ack_fromme_message()

        # unread messages - just logging
        if self.message.get("event") == "unreadmessages":
            if "status@broadcast" not in self.message.get(
                "from"
            ) and not self.message.get("id", {}).get("fromMe", False):
                self.logger_info(f"PROCESSED UNREAD MESSAGE. PAYLOAD {self.message}")

        # message removed
        if self.message.get("event") == "onrevokedmessage":
            # get ref id
            ref_id = self.message.get("refId")
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

        # reaction to a message
        if self.message.get("event") == "onreactionmessage":
            self.get_rocket_client()
            room = self.get_room()
            ref_id = self.message.get("msgId").get("_serialized")
            msg = self.rocket.chat_get_message(msg_id=ref_id)
            reaction = self.message.get("reactionText")
            if msg.ok:
                new_message = "{} {}".format(reaction, msg.json()["message"]["msg"])
            else:
                # message may be from previous chats.
                # lets get from wppconnect
                message = self.get_message(message_id=ref_id)
                new_message = "{} {}".format(
                    reaction, message.get("response").get("data").get("body")
                )
                print(new_message)
            room = self.get_room()
            self.outcome_text(
                room_id=room.room_id, text=new_message, message_id=self.get_message_id()
            ).json()

        # webhook active chat integration
        if self.config.get("active_chat_webhook_integration_token"):
            if self.message.get("token") == self.config.get(
                "active_chat_webhook_integration_token"
            ):
                self.logger_info("active_chat_webhook_integration_token triggered")
                # message, created = self.register_message()
                req = self.active_chat()
                return JsonResponse(req)

        return JsonResponse({})

    def intake_unread_messages(self):
        """
        intake unread messages
        """
        endpoint = "{}/api/{}/unread-messages".format(
            self.config.get("endpoint"),
            self.config.get("instance_name"),
        )
        session = self.get_request_session()
        unread_contacts = session.get(endpoint)
        if unread_contacts.ok:
            self.logger_error(
                "PROCESSING UNREAD {} CONTACTS ON START".format(
                    len(unread_contacts.get("response"))
                )
            )
            unread_contacts = unread_contacts.json()
            for contact in unread_contacts.get("response"):
                for message in contact["messages"]:
                    message["event"] = "onmessage"
                    message["chatId"] = message["from"]
                    self.logger_error(f"PROCESSING UNREAD MESSAGE {message}")
                    self.message = message
                    self.type = "incoming"
                    self.incoming()
        else:
            self.logger_error("COULD NOT CONNECT TO WPP SERVER TO GET UNREAD MESSAGES")

        return False

    def get_incoming_message_id(self):
        # unread messages has a different structure
        if self.message.get("event") in ["unreadmessages", "onreactionmessage"]:
            return self.message.get("id", {}).get("_serialized")
        if self.message.get("type") == "active_chat":
            return self.message.get("message_id")
        if self.message.get("event") == "onack":
            return self.message.get("id", {}).get("id")
        return self.message.get("id")

    def get_incoming_visitor_id(self):
        if self.message.get("event") == "incomingcall":
            visitor_id = self.message.get("peerJid")
        if self.message.get("event") == "onreactionmessage":
            visitor_id = self.message.get("id").get("remote")
        if self.message.get("event") == "onack":
            if self.message.get("id", {}).get("fromMe"):
                visitor_id = self.message.get("id").get("remote")
        else:
            if self.message.get("event") in ["unreadmessages", "onrevokedmessage"]:
                return self.message.get("from")
            else:
                visitor_id = self.message.get("chatId")

        if not self.config.get("append_connector_to_visitor_id"):
            return visitor_id
        else:
            return str(visitor_id) + "|" + self.connector.external_token

    def get_visitor_name(self):
        # get name order
        name_order = self.config.get("name_extraction_order", "pushname,name,shortName")
        message = self.message
        order = name_order.split(",")
        name = None
        # try each attribute
        for attribute in order:
            if not name:
                name = message.get("sender", {}).get(attribute)
        # get the fallback name
        if not name:
            name = message.get("chatId")
        return name

    def get_visitor_phone(self):
        visitor_phone = None
        if self.message.get("event") == "incomingcall":
            visitor_phone = self.message.get("peerJid").split("@")[0]
        else:
            if self.message.get("from"):
                visitor_phone = self.message.get("from").split("@")[0]
        return visitor_phone

    def get_visitor_username(self):
        if self.message.get("event") == "incomingcall":
            visitor_username = "whatsapp:{}".format(
                # works for wa-automate
                self.message.get("peerJid")
            )
        else:
            visitor_username = "whatsapp:{}".format(self.message.get("from"))
        return visitor_username

    def get_visitor_avatar_url(self):
        if self.message.get("sender", {}).get("profilePicThumbObj", {}).get("img"):
            return (
                self.message.get("sender", {}).get("profilePicThumbObj", {}).get("img")
            )

    def get_message_body(self):
        return self.message.get("body")

    def get_request_session(self):
        s = requests.Session()
        s.headers = {"content-type": "application/json"}
        if self.connector.config.get("token", {}):
            token = self.connector.config.get("token", {}).get("token")
            if token:
                s.headers.update({"Authorization": f"Bearer {token}"})
        return s

    def outgo_text_message(self, message, agent_name=None):
        sent = False
        if type(message) == str:
            content = message
        else:
            content = message["msg"]
        url = self.connector.config["endpoint"] + "/api/{}/send-message".format(
            self.connector.config["instance_name"]
        )
        try:
            # mesangem é um json
            payload = json.loads(content)
            # if payload is integer or other json loadable content
            if type(payload) != dict:
                raise ValueError
            if payload.get("buttons"):
                if not payload.get("phone"):
                    payload["phone"] = self.get_visitor_id()
                url = self.connector.config["endpoint"] + "/api/{}/send-buttons".format(
                    self.connector.config["instance_name"]
                )
                self.logger_info(
                    f"OUTGOING BUTTON MESSAGE. URL: {url}. PAYLOAD {payload}"
                )
        except (ValueError, TypeError):
            content = self.joypixel_to_unicode(content)
            # message may not have an agent
            if agent_name:
                content = self.render_message_agent_template(content, agent_name)
                # content = "*[" + agent_name + "]*\n" + content

            payload = {
                "phone": self.get_visitor_id(),
                "message": content,
                "isGroup": False,
            }
            self.logger_info(f"OUTGOING TEXT MESSAGE. URL: {url}. PAYLOAD {payload}")
        # SEND MESSAGE
        session = self.get_request_session()
        # TODO: Simulate typing
        # See: https://github.com/wppconnect-team/wppconnect-server/issues/59

        timestamp = int(time.time())
        try:
            self.logger_info(f"OUTGOING TEXT MESSAGE: URL and PAYLOAD {url} {payload}")
            sent = session.post(url, json=payload)
            if self.message_object and sent.ok:
                self.message_object.delivered = sent.ok
                self.message_object.response[timestamp] = sent.json()
                if not self.message_object.response.get("id"):
                    self.message_object.response["id"] = [
                        sent.json()["response"][0]["id"]
                    ]
                else:
                    self.message_object.response["id"].append(
                        sent.json()["response"][0]["id"]
                    )

            if sent.ok:
                self.logger_info(f"OUTGOING TEXT MESSAGE SUCCESS: {sent.json()}")
            else:
                self.logger_info(f"OUTGOING TEXT MESSAGE ERROR: {sent.json()}")

        except requests.ConnectionError:
            if self.message_object:
                self.message_object.delivered = False
                self.logger_info(f"CONNECTOR DOWN: {self.connector}")
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()
        return sent

    def outgo_file_message(self, message, file_url=None, mime=None, agent_name=None):
        # if its audio, treat different
        # ppt = False
        # if message["file"]["type"] == "audio/mpeg":
        #     ppt = True

        # to avoid some networking problems,
        # we use the same url as the configured one, as some times
        # the url to get the uploaded file may be different
        # eg: the publicFilePath is public, but waautomate is running inside
        # docker
        if not file_url:
            file_url = (
                self.connector.server.url
                + message["attachments"][0]["title_link"]
                + "?"
                + urlparse.urlparse(message["fileUpload"]["publicFilePath"]).query
            )
        content = base64.b64encode(requests.get(file_url).content).decode("utf-8")
        if not mime:
            mime = self.message["messages"][0]["fileUpload"]["type"]
        payload = {
            "phone": self.get_visitor_id(),
            "base64": f"data:{mime};base64,{content}",
            "isGroup": False,
        }

        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/api/{}/send-file-base64".format(
            self.connector.config["instance_name"]
        )
        if settings.DEBUG:
            print("PAYLOAD OUTGOING FILE: ", payload)
        sent = session.post(url, json=payload)
        if settings.DEBUG:
            print("PAYLOAD OUTGOING FILE RESPONSE: ", sent.json())

        if sent.ok:
            timestamp = int(time.time())
            if settings.DEBUG:
                self.logger.info(f"RESPONSE OUTGOING FILE: {sent.json()}")
            self.message_object.payload[timestamp] = payload
            self.message_object.delivered = True
            self.message_object.response[timestamp] = sent.json()
            self.message_object.save()
            # self.send_seen()

    def outgo_vcard(self, payload):
        session = self.get_request_session()
        url = self.connector.config["endpoint"] + "/api/{}/contact-vcard".format(
            self.connector.config["instance_name"]
        )
        self.logger_info(f"OUTGOING VCARD. URL: {url}. PAYLOAD {payload}")
        timestamp = int(time.time())
        try:
            # replace destination phone
            payload["phone"] = self.get_visitor_phone()
            sent = session.post(url, json=payload)
            self.message_object.delivered = sent.ok
            self.message_object.response[timestamp] = sent.json()
        except requests.ConnectionError:
            self.message_object.delivered = False
            self.logger_info(f"CONNECTOR DOWN: {self.connector}")
        # save message object
        if self.message_object:
            self.message_object.payload[timestamp] = payload
            self.message_object.save()

    def handle_inbound(self, request):
        if request.GET.get("phone"):
            check = self.check_number_status(request.GET.get("phone"))
            if check["response"]["numberExists"]:
                serialized_id = check.get("response").get("id").get("_serialized")
                # get proper number
                proper_number = check["response"]["id"]["user"]

                department = request.GET.get("department", None)
                if not department:
                    department = self.config.get("default_inbound_department", None)

                self.message = {
                    "from": serialized_id,
                    "chatId": serialized_id,
                    "id": self.message.get("message_id"),
                    "visitor": {"token": "whatsapp:" + serialized_id},
                }
                self.check_number_info(proper_number, augment_message=True)
                self.message["visitor"] = {"token": "whatsapp:" + serialized_id}
                self.get_rocket_client()
                room = self.get_room(department, allow_welcome_message=False)
                if room:
                    # outcome message
                    if request.GET.get("text"):
                        # send message to channel
                        self.rocket.chat_post_message(
                            text=request.GET.get("text"), room_id=room.room_id
                        )
                    external_url = room.get_room_url()
                    return {"success": True, "redirect": external_url}
            else:
                return {
                    "success": False,
                    "notfound": f"{request.GET.get('phone')} was not found",
                }

            self.logger_info(f"INBOUND MESSAGE. {request.GET}")

        trigger_word = self.config.get("default_fromme_ack_department_trigger")
        if trigger_word:
            # here we will return the last message that has the trigger word
            # for a triggered phone
            if request.GET.get("trigger_id"):
                trigger_id = request.GET.get("trigger_id")
                phone = trigger_id.split("@")[0]
                if "whatsapp" in phone:
                    phone = phone.replace("whatsapp:", "")

                # get the last triggered message
                session = self.get_request_session()
                url = self.connector.config[
                    "endpoint"
                ] + "/api/{}/all-messages-in-chat/{}".format(
                    self.connector.config["instance_name"], phone
                )
                last_messages_req = session.get(url).json()
                last_messages = last_messages_req["response"]
                if not last_messages_req["response"]:
                    output = {
                        "success": False,
                        "notfound": f"{trigger_id} trigger id was not found",
                    }
                    return output
                # as the message may be recent, this can save some processing
                last_messages.reverse()
                # find the trigger message
                trigger_message = None
                for message in last_messages:
                    if trigger_word in message["body"]:
                        trigger_message = message
                        break
                # enhance trigger_message with external_url
                trigger_message["external_url"] = self.connector.server.external_url
                return trigger_message

        if request.GET.get("check-phone"):
            return self.check_number_status(request.GET.get("check-phone"))

    def handle_ack_fromme_message(self):
        # activate this if default_fromme_ack_department is set
        if self.config.get("default_fromme_ack_department") and self.config.get(
            "default_fromme_ack_department_trigger"
        ):
            if self.config.get(
                "default_fromme_ack_department_trigger"
            ) in self.message.get("body"):
                self.get_rocket_client()
                # lets force it to transfer if room is open
                if self.config.get("fromme_ack_department_force_transfer"):
                    force_transfer = self.config.get("default_fromme_ack_department")
                else:
                    # no forcing, leave it at the department
                    force_transfer = None
                # get the room
                room_response = self.get_room(
                    department=self.config.get("default_fromme_ack_department"),
                    allow_welcome_message=False,
                    check_if_open=True,
                    force_transfer=force_transfer,
                )
                # if reply trigger, emulate the message as the visitor message
                if self.config.get("fromme_reply_trigger_message"):
                    message = (
                        ":mailbox: *SENT TO THE USER WITH TRIGGER*\n"
                        + self.message.get("body")
                    )
                    self.outcome_text(room_id=room_response.room_id, text=message)
                self.logger_info(
                    "HANDLING ACK FROMME MESSAGE TRIGGER."
                    + f"PAYLOAD {json.dumps(self.message)}"
                    + f"room response: {room_response}"
                )
        # ack receipt
        if (
            self.config.get("enable_ack_receipt")
            and self.connector.server.type == "rocketchat"
        ):
            # get the sent message
            self.get_rocket_client()
            message_id = self.message.get("id", {}).get("_serialized")
            self.logger_info(f"enable_ack_receipt for {message_id}")
            for message in self.connector.messages.filter(
                response__id__contains=message_id
            ):
                # or add only the white check
                original_message = self.rocket.chat_get_message(
                    msg_id=message.envelope_id
                )
                body = original_message.json()["message"]["msg"]
                # remove previous markers
                body = body.replace(":ballot_box_with_check:", "")
                body = body.replace(":white_check_mark:", "")
                if self.message["ack"] == 1:
                    mark = ":ballot_box_with_check:"
                else:
                    mark = ":white_check_mark:"

                self.rocket.chat_update(
                    room_id=message.room.room_id,
                    msg_id=message.envelope_id,
                    text=f"{mark} {body}",
                )
                message.ack = True
                message.save()

    def get_message(self, message_id):
        session = self.get_request_session()
        endpoint = "{}/api/{}/message-by-id/{}".format(
            self.config.get("endpoint"), self.config.get("instance_name"), message_id
        )
        message = session.get(endpoint).json()
        return message


class ConnectorConfigForm(BaseConnectorConfigForm):
    def __init__(self, *args, **kwargs):
        self.connector = kwargs.get("connector")
        super().__init__(*args, **kwargs)
        if self.connector.server.type == "rocketchat":
            # this is how we show only rocket.chat options
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
            self.fields["department_triage"] = forms.BooleanField(required=False)
            self.fields["department_triage_payload"] = forms.JSONField(required=False)
            self.fields["department_triage_to_ignore"] = forms.CharField(
                max_length=None, required=False
            )
            self.fields["session_management_token"] = forms.CharField(required=False)
            self.fields["default_fromme_ack_department"] = forms.CharField(
                required=False,
                help_text="This is a deparment where should be created a message sent from the mobile",
            )
            self.fields["fromme_ack_department_force_transfer"] = forms.BooleanField(
                help_text="Force the transfer if chat is already open with visitor",
                initial=True,
                required=False,
            )
            self.fields["default_fromme_ack_department_trigger"] = forms.CharField(
                required=False,
                help_text="This is trigger word a message must have in order to trigger the ack from me feature",
            )
            self.fields["fromme_reply_trigger_message"] = forms.BooleanField(
                required=False,
                help_text="When activated, it will reply the trigger message, emulating the visitor text",
            )
            self.fields["enable_ack_receipt"] = forms.BooleanField(
                required=False,
                help_text="This will update the ingoing message to show it was delivered and received",
            )
            self.fields["default_inbound_department"] = forms.CharField(
                required=False,
                help_text="This is the deparment that will be opened inbound active messages to by default",
            )
            self.fields["append_connector_to_visitor_id"] = forms.BooleanField(
                required=False,
                initial=False,
                help_text="EXPERIMENTAL!! This will append the connector_token to the user id."
                + "Its useful to make Rocket.Chat create different visitors per connector, "
                + "so their messages and history doesn't get mixed up.",
            )

    webhook = forms.CharField(
        help_text="Where WPPConnect will send the events",
        required=True,
    )
    endpoint = forms.CharField(
        help_text="Where your WPPConnect is installed",
        required=True,
        initial="http://wppconnect:21465",
    )
    secret_key = forms.CharField(
        help_text="The secret key for your WPPConnect instance",
        required=True,
    )
    instance_name = forms.CharField(
        help_text="WPPConnect instance name", validators=[validators.validate_slug]
    )

    name_extraction_order = forms.CharField(
        required=False,
        help_text="The prefered order to extract a visitor name",
        initial="name,shortName,pushname",
    )

    process_unread_messages_on_start = forms.BooleanField(initial=False, required=False)

    outcome_message_with_quoted_message = forms.BooleanField(required=False)

    # ORDERING

    field_order = [
        "webhook",
        "endpoint",
        "secret_key",
        "instance_name",
        "active_chat_webhook_integration_token",
        "active_chat_force_department_transfer",
        "session_management_token",
        "name_extraction_order",
        "process_unread_messages_on_start",
        "outcome_message_with_quoted_message",
        "department_triage",
        "department_triage_payload",
        "department_triage_to_ignore",
    ]
