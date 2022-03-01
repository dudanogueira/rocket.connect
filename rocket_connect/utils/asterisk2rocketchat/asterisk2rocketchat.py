import asyncio

import requests
from panoramisk import Manager

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
#
# you need to create the above webhook in Rocket.Chat
# and paste the Script from incoming.webhook.Rocket.Chat.js
# this is the webhook url
incoming_endpoint = (
    "http://localhost:3000/hooks/"
    + "620e9615701ffe000986a1c8/8fRecuRk5Muyf3mtsGtDGFgJDkZ8wuEjm5qNqNFqxuCLaErE"
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
        print(payload)
        requests.post(incoming_endpoint, json=payload)


def main():
    manager.connect()
    try:
        manager.loop.run_forever()
    except KeyboardInterrupt:
        manager.loop.close()


if __name__ == "__main__":
    main()
