import dateutil.parser
import requests
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
    server_id, seconds_last_message, notification_target, notification_template
):
    """alert open messages"""

    # get server
    server = Server.objects.get(external_token=server_id)
    # get rocket
    rocket = server.get_rocket_client()
    # list all open messages
    open_rooms = server.get_open_rooms()
    # process
    alerted_rooms = []
    now = timezone.now()
    for room in open_rooms:
        if room.get("lastMessage"):
            last_message = room["lastMessage"]
            ts = dateutil.parser.parse(last_message["ts"])
            delta = now - ts
            if delta.total_seconds() >= seconds_last_message:
                alerted_rooms.append(room["_id"])
                # render notification_template
                # context = {}
                for target in notification_target.split(","):
                    manager_channel_message = rocket.chat_post_message(
                        text=notification_template, channel=target.replace("#", "")
                    )
                    print(manager_channel_message)

    # alert
    return {
        "alerted_rooms": alerted_rooms,
        "now": str(now),
        "seconds_last_message": seconds_last_message,
        "notification_target": notification_target,
    }
