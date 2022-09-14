import dateutil.parser
import requests
from django.apps import apps
from django.template import Context, Template
from django.utils import timezone
from instance.models import Server

from config import celery_app


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def intake_unread_messages(connector_id):
    """Reintake the Unread Messages of a given Connector"""
    from instance.models import Connector

    connector = Connector.objects.get(id=connector_id)
    Connector = connector.get_connector_class()
    c = Connector(connector, {}, type="incoming")
    unread = c.intake_unread_messages()
    return unread


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def alert_last_message_open_chat(
    server_token, seconds_last_message, notification_target, notification_template
):
    """alert open messages"""

    # get server
    server = Server.objects.get(external_token=server_token)
    # get rocket
    rocket = server.get_rocket_client()
    # list all open messages
    open_rooms = server.get_open_rooms()
    # process
    alerted_rooms = []
    now = timezone.now()
    # parse datetime strings to python objects

    for room in open_rooms.get("rooms", []):
        rendered_targets = []
        if room.get("lastMessage"):
            last_message = room["lastMessage"]
            ts = dateutil.parser.parse(last_message["ts"])
            delta = now - ts
            if delta.total_seconds() >= seconds_last_message:
                alerted_rooms.append(room["_id"])
                # adjust context dict
                room["id"] = room["_id"]
                room["lm_obj"] = dateutil.parser.parse(room["lm"])
                room["ts_obj"] = dateutil.parser.parse(room["ts"])
                # render notification_template
                context_dict = {
                    "room": room,
                    # "open_rooms": open_rooms,
                    "external_url": server.get_external_url(),
                }
                context = Context(context_dict)
                template = Template(notification_template)
                for target in notification_target.split(","):

                    # render message
                    message = template.render(context)
                    if target.startswith("#"):
                        rendered_targets.append(target)
                        sent = rocket.chat_post_message(
                            text=message, channel=target.replace("#", "")
                        )
                    else:

                        # target may contain variables
                        target_template = Template(target)
                        rendered_target = target_template.render(context)
                        rendered_targets.append(rendered_target)
                        dm = rocket.im_create(username=rendered_target)
                        if dm.ok:
                            room_id = dm.json()["room"]["rid"]
                            sent = rocket.chat_post_message(
                                text=message, room_id=room_id
                            )
                            print("SENT! ", sent)

    # return findings
    return {
        "alerted_rooms": alerted_rooms,
        "now": str(now),
        "seconds_last_message": seconds_last_message,
        "notification_target_unrendered": notification_target,
        "rendered_targets": rendered_targets,
    }


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def server_maintenance(server_token):
    """do all sorts of server maintenance"""
    server = Server.objects.get(external_token=server_token)
    response = {}
    # sync room
    response["room_sync"] = server.room_sync(execute=True)
    # return results
    return response


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def alert_open_rooms_generic_webhook(server_token, endpoint):
    """send a payload to a configured endpoint"""

    # get server
    server = Server.objects.get(external_token=server_token)
    # list all open messages
    open_rooms = server.get_open_rooms()
    # enhance payloads
    open_rooms["external_url"] = server.get_external_url()
    # process
    response = requests.post(endpoint, json=open_rooms)
    return response.ok


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def change_user_status(server_token, users, status, message=""):
    """send a payload to a configured endpoint"""

    # get server
    server = Server.objects.get(external_token=server_token)
    rocket = server.get_rocket_client()
    responses = []
    if type(users) == str:
        users = users.split(",")
    for user in users:
        r = rocket.users_set_status(username=user, status=status, message=message)
        responses.append(
            {"user": user, "status": status, "message": message, "return": r.json()}
        )
    return responses


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def close_abandoned_chats(
    server_token, last_message_users, last_message_seconds, closing_message=None
):
    """close all open rooms that the last message from last_message_users
    with more then last_message_seconds. before, send a closing_message.
    # TODO:
    optionally, alert a channel
    """
    # get server
    server = Server.objects.get(external_token=server_token)
    # get rocket
    rocket = server.get_rocket_client()
    # list all open messages
    open_rooms = server.get_open_rooms()
    if type(last_message_users) == str:
        last_message_users = last_message_users.split(",")
    # process
    now = timezone.now()
    # parse datetime strings to python objects

    closed_rooms = []
    if open_rooms:
        for room in open_rooms.get("rooms", []):
            if room.get("lastMessage", False):
                last_message = room["lastMessage"]
                if last_message["u"]["username"] in last_message_users:
                    ts = dateutil.parser.parse(last_message["ts"])
                    delta = now - ts
                    if delta.total_seconds() >= last_message_seconds:
                        if closing_message:
                            rocket.chat_post_message(
                                room_id=room["_id"], text=closing_message
                            ).json()
                        # close messages on this situation
                        room_close_options = {
                            "rid": room["_id"],
                            "token": room["v"]["token"],
                        }
                        close = rocket.call_api_post(
                            "livechat/room.close", **room_close_options
                        )
                        closed_rooms.append(close.json())

    # return findings
    return {
        "closed_rooms": closed_rooms,
        "now": str(now),
        "last_message_users": last_message_users,
        "last_message_seconds": last_message_seconds,
        "closing_message": closing_message,
    }


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def alert_undelivered_messages(
    server_token, notification_target, notification_template
):
    """
    - get all undelivered messages from server
    - render notification template
    - send to notification targets
    """
    server = Server.objects.get(external_token=server_token)
    rocket = server.get_rocket_client()
    Messages = apps.get_model(app_label="envelope", model_name="Message")
    undelivered_messages = Messages.objects.filter(delivered=False, server=server)
    context = {"undelivered_messages": undelivered_messages}
    context = Context(context)
    template = Template(notification_template)
    targets = []
    sent_messages = []
    for target in notification_target.split(","):
        # render message
        message = template.render(context)
        if target.startswith("#"):
            targets.append(target)
            sent = rocket.chat_post_message(
                text=message, channel=target.replace("#", "")
            )
        else:
            # target may contain variables
            targets.append(target)
            dm = rocket.im_create(username=target)
            if dm.ok:
                room_id = dm.json()["room"]["rid"]
                sent = rocket.chat_post_message(text=message, room_id=room_id)
        sent_messages.append(sent)

    responses = {"targets": targets, "sent_messages": sent_messages}
    return responses
