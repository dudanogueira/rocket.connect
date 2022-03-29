import asyncio
import datetime
import re

import requests
from panoramisk import Manager

# CONFIG ##
#
headers = {
    "X-Auth-Token": "4abyk1ebvE34XzftyyW1e4tPlC3KBBAb1gryYD7VYRp",
    "X-User-Id": "avmX38wqkezv55obK",
}
rocketchat_url = "http://rocketchat:3000"
room_id = "GENERAL"
#
#


def from_payload_to_message(payload):
    text = [
        ":passport_control: *Queue*: " + payload.get("Queue"),
        ":calling: *Caller Number:*: " + payload.get("CallerIDNum"),
        ":alarm_clock: *Hold Time*: " + payload.get("HoldTime") + "s",
        ":vertical_traffic_light: *Entered at position* "
        + payload.get("OriginalPosition")
        + ". Abandoned at "
        + payload.get("Position"),
    ]
    return "\n".join(text)


def get_default_payload(payload, room_id=None):
    return {
        "message": {
            # "msg": from_payload_to_message(payload),
            "alias": "Telephony",
            "rid": room_id,
            "emoji": ":no_mobile_phones:",
            "attachments": [
                {
                    "color": "#ff0000",
                    "collapsed": True,
                    "title": "Abandoned Call from "
                    + payload.get("CallerIDNum")
                    + " at Queue "
                    + payload.get("Queue"),
                    # "text": "Telefonia alert",
                    "fields": [
                        {
                            "short": True,
                            "title": ":passport_control: Queue",
                            "value": payload.get("Queue"),
                        },
                        {
                            "short": True,
                            "title": ":calling: Caller Number",
                            "value": payload.get("CallerIDNum"),
                        },
                        {
                            "short": True,
                            "title": ":alarm_clock: Hold Time",
                            "value": payload.get("HoldTime") + "s",
                        },
                        {
                            "short": False,
                            "title": ":vertical_traffic_light: Position",
                            "value": "Entered at position "
                            + payload.get("OriginalPosition")
                            + ". Abandoned at "
                            + payload.get("Position"),
                        },
                    ],
                }
            ],
        }
    }


def get_grouper_id(payload):
    """
    this will return how we want to group messages by
    """
    n = re.sub("[^0-9]", "", payload.get("CallerIDNum"))
    return str(datetime.date.today()) + "_" + n  # + '_' + payload.get("Queue")


def send_message_or_thread(payload, room_id, base_url="http://rocketchat:3000"):
    grouper_id = get_grouper_id(payload)
    # search message
    url_search = base_url + "/api/v1/chat.getThreadMessages?tmid={0}".format(grouper_id)
    response = requests.get(url_search, headers=headers)
    # discussion already open
    payload = get_default_payload(payload, room_id)
    if response.ok:
        # we already have a grouper
        payload["message"]["tmid"] = grouper_id
    else:
        # no previous message
        payload["message"]["_id"] = grouper_id

    url_send_message = base_url + "/api/v1/chat.sendMessage"
    new_message = requests.post(url_send_message, json=payload, headers=headers)
    return new_message


payload = {
    "Event": "QueueCallerAbandon",
    "Privilege": "agent,all",
    "Channel": "SIP/123123123-00003841",
    "ChannelState": "6",
    "ChannelStateDesc": "Up",
    "CallerIDNum": "+553335222332",
    "CallerIDName": "CO:+55353522123123",
    "ConnectedLineNum": "<unknown>",
    "ConnectedLineName": "<unknown>",
    "Language": "pt_BR",
    "AccountCode": "",
    "Context": "ext-queues",
    "Exten": "2001",
    "Priority": "40",
    "Uniqueid": "1648498996.318653",
    "Linkedid": "1648498996.318653",
    "Queue": "2001",
    "Position": "1",
    "OriginalPosition": "4",
    "HoldTime": "168",
    "content": "",
}

a = send_message_or_thread(payload, room_id)

#
# AMI CONF in ASTERISK
#
# add this below, adapting permit and deny accordingly
# to /etc/asterisk/manager_custom.conf
# [queue_alert_user]
# secret=queue_alert_pwd
# deny=0.0.0.0/0.0.0.0
# permit=0.0.0.0/0.0.0.0
# read = all
# eventfilter=Event: QueueCallerAbandon


manager = Manager(
    loop=asyncio.get_event_loop(),
    host="localhost",
    username="queue_alert_user",
    secret="queue_alert_pwd",
)


# this is an example.
# you can filter the callback by different method
# or inside the method, using message.event
# you can also duplicate the code below, and send different
# events to differents webhooks / channels / users


@manager.register_event("QueueCallerAbandon")
def callback(manager, message):
    if "FullyBooted" not in message.event:
        """This will print every event, but the FullyBooted events as these
        will continuously spam your screen"""
        # event = message.event
        # if event == "QueueCallerAbandon":
        # if event == "OtherEvent":
        payload = dict(message.items())
        send_message_or_thread(
            payload,
            room_id,
        )


def main():
    manager.connect()
    try:
        manager.loop.run_forever()
    except KeyboardInterrupt:
        manager.loop.close()


if __name__ == "__main__":
    main()
