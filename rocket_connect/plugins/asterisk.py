import datetime

import pytz
from django.conf import settings
from django.http import JsonResponse
from django.template import Context, Template

from asterisk.models import Call

from .base import Connector as ConnectorBase

# TODO:
# - count how many transfers occurred
# - Detect unanswered direct calls
# - Detect voice mail


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
        caller_leave_message = self.call.messages.create(json=self.message)
        print("DEBUG! CREATING CALL MESSAGE: ", self.message)
        print("DEBUG! call message id ", caller_leave_message.id)
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
            waitseconds = (
                datetime.datetime.now(pytz.timezone(self.timezone)) - self.call.created
            )
            # render the temaplate with the call info
            enriched_message = self.message
            enriched_message["now"] = datetime.datetime.now(
                pytz.timezone(self.timezone)
            )
            enriched_message["call_initiated"] = local_dt
            enriched_message["waitseconds"] = waitseconds
            context = Context(enriched_message)
            template = Template(self.config.get("queue_notify_template"))
            rendered_template = template.render(context)
            for notify in notify_map:
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
                    if post.json.get("error") == "error-not-allowed":
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
                    room_id = room.json()["room"]["rid"]
                    self.rocket.chat_post_message(
                        channel=room_id, text=rendered_template
                    )
