import datetime
import json

import pytz
from asterisk.models import Call
from django.conf import settings
from django.http import JsonResponse
from django.template import Context, Template

from .base import Connector as ConnectorBase

# TODO:
# - count how many transfers occurred
# - Detect unanswered direct calls


class Connector(ConnectorBase):
    def incoming(self):
        # create call
        unique_id = self.message.get("Uniqueid")
        # only for agents calls and connections
        if unique_id and self.message.get("Event") in [
            "AgentCalled",
            "AgentConnect",
            "UserEvent",
        ]:
            call, created = self.get_call()
            # if AgentConnect, it got answered
            if self.message.get("Event") == "AgentConnect":
                call.answered = datetime.datetime.now(pytz.timezone(self.timezone))
                # remove hangup
                # call.hangup = None
                call.save()
                # register message
                call.messages.create(json=self.message)
        # hangups
        if unique_id and self.message.get("Event") in [
            "Hangup",
            "AgentDump",
            "AgentComplete",
            "QueueCallerLeave",
        ]:
            # only for queues
            if self.message.get("Queue"):  # in ["ext-queues", "macro-blkvm-clr"]:
                self.get_call()
                self.call.hangup = datetime.datetime.now(pytz.timezone(self.timezone))
                # abandoned call
                if (
                    self.message.get("Event") == "QueueCallerLeave"
                    and self.message.get("ConnectedLineNum") == "<unknown>"
                ):
                    self.call.caller_left_queue = True
                    self.hook_queue_caller_leave()
                self.call.save()

        # user events
        if self.message.get("Event") == "UserEvent":
            if self.message.get("Context") in self.config.get(
                "userevent_context_filter"
            ):
                call, created = self.get_call()
                # register message
                call.messages.create(json=self.message)

        # voicemail
        if unique_id and self.message.get("Event") in [
            "MessageWaiting",
        ]:
            # only of caller id
            if self.message.get("CallerIDNum"):
                self.hook_voicemail()

        return JsonResponse({})

    def get_call(self):
        unique_id = self.message.get("Uniqueid")
        linked_id = self.message.get("Linkedid")
        self.call, created = Call.objects.get_or_create(unique_id=unique_id)
        if created:
            # check if the recently created call has a linked one
            if unique_id != linked_id:
                try:
                    linked_call = Call.objects.get(unique_id=linked_id)
                    self.call.previous_call = linked_call
                except Call.objects.DoesNotExist:
                    pass

        self.call.caller = self.message.get("CallerIDNum")
        # if call is from queue, register the queue
        if self.message.get("Event") in ["AgentCalled", "AgentConnect"]:
            self.call.queue = self.message.get("Queue")
        # if event is agent connect, register agent
        if self.message.get("Event") in ["AgentConnect"]:
            self.call.agent = self.message.get("ConnectedLineNum")
        self.call.save()
        return self.call, created

    def hook_queue_caller_leave(self):
        """
        This method will get the the queue_notify_map from the conector config,
        and notify users or channels accordingly when a caller leave a queue
        """
        # identify the notify list

        notify_map = []
        self.call.messages.create(json=self.message)
        if self.connector.config.get("queue_notify_map"):
            queue = self.message.get("Queue")
            # wild card
            if self.config.get("queue_notify_map").get("*"):
                notify_map.extend(
                    self.config.get("queue_notify_map").get("*").split(",")
                )
            # queue map
            if self.config.get("queue_notify_map").get(queue):
                notify_map.extend(
                    self.config.get("queue_notify_map").get(queue).split(",")
                )
            # get unique list of notifies
            notify_map = list(set(notify_map))
            # calculate wait time
            local_tz = pytz.timezone(self.timezone)
            call_epoch = int(self.message.get("Uniqueid").split(".")[0])
            utc_dt = datetime.datetime.utcfromtimestamp(call_epoch).replace(
                tzinfo=pytz.utc
            )
            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            waitseconds = datetime.datetime.now(pytz.timezone(self.timezone)).replace(
                microsecond=0
            ) - self.call.created.replace(microsecond=0)
            # render the temaplate with the call info
            enriched_message = self.message
            enriched_message["now"] = datetime.datetime.now(
                pytz.timezone(self.timezone)
            )
            enriched_message["call_initiated"] = local_dt
            enriched_message["waitseconds"] = waitseconds
            context = Context(enriched_message)
            template = Template(self.config.get("notify_abandoned_queue_template"))
            rendered_template = template.render(context)
            for notify in notify_map:
                print("DEBUG! NOTIFY LOOK:, ", notify)
                # get rocket client at self.rocket as bot
                self.get_rocket_client(bot=True)

                # send to a channel
                if notify[0] == "#":
                    if settings.DEBUG:
                        print(
                            "NOTIFYING CHANNEL {0} CALLER LEFT QUEUE: ".format(notify),
                            self.message,
                        )
                    # notify a channel
                    post = self.rocket.chat_post_message(
                        channel=notify, text=rendered_template
                    )
                    if post.json().get("error") == "error-not-allowed":
                        # bot may not be at the channel. Send as admin
                        rocket = self.get_rocket_client(bot=True)
                        post = rocket.chat_post_message(
                            channel=notify, text=rendered_template
                        )
                else:
                    if settings.DEBUG:
                        print(
                            "NOTIFYING USER {0} CALLER LEFT QUEUE: ".format(notify),
                            self.message,
                        )
                    room = self.rocket.im_create(username=notify)
                    if room:
                        room_id = room.json()["room"]["rid"]
                        self.rocket.chat_post_message(
                            channel=room_id, text=rendered_template
                        )

    def hook_voicemail(self):
        extension = self.message.get("Mailbox").split("@")[0]
        # get user extension custom field
        extension_field = self.config.get("extension_user_custom_field", "ramal")
        self.get_rocket_client(bot=True)
        # search user by extension
        query = {"customFields": {extension_field: extension}}
        users_with_extension = self.rocket.users_list(query=json.dumps(query))
        # render the template message
        enriched_message = self.message
        enriched_message["extension"] = extension
        enriched_message["now"] = datetime.datetime.now(pytz.timezone(self.timezone))
        context = Context(enriched_message)
        default_template = (
            "You've got a new Voicemail from Caller {{CallerIDNum}} at extension {{extension}} and "
            + "time {{now|date:'SHORT_DATETIME_FORMAT'}}. You have now {{New}} new message{{New|pluralize}} and {{Old}}"
            + " old{{New|pluralize}}"
        )
        template = Template(
            self.config.get("notify_voicemail_template", default_template)
        )
        rendered_template = template.render(context)
        users_found = users_with_extension.json().get("users")
        if users_found:
            # send message to user, if found any
            for user in users_found:
                room = self.rocket.im_create(username=user["username"])
                room_id = room.json()["room"]["rid"]
                print("ROOM ID ", room_id)
                self.rocket.chat_post_message(channel=room_id, text=rendered_template)
