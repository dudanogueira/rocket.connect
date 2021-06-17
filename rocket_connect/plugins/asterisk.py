import datetime

from django.conf import settings
from django.http import JsonResponse
from django.template import Context, Template

from asterisk.models import Call

from .base import Connector as ConnectorBase

# TODO:
# - register and relate transfered calls (previous calls)
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
                call.answered = datetime.datetime.now()
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
                call, created = self.get_call()
                call.hangup = datetime.datetime.now()
                # abandoned call
                if self.message.get("Event") == "QueueCallerLeave":
                    call.caller_left_queue = True
                    self.hook_queue_caller_leave()
                call.save()
                # register message
                call.messages.create(json=self.message)
        # user eventsQUEUE LEFT C
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
        self.call, created = Call.objects.get_or_create(unique_id=unique_id)
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
            notify_map = list(set(notify_map))
            # render the temaplate with the call info
            self.message["now"] = datetime.datetime.now
            context = Context(self.message)
            template = Template(self.config.get("queue_notify_template"))
            rendered_template = template.render(context)
            # get rocket client at self.rocket
            self.get_rocket_client(bot=True)
            for notify in notify_map:
                # send to a channel
                if notify[0] == "#":
                    if settings.DEBUG:
                        print("NOTIFYING CHANNEL CALLER LEFT QUEUE: ", self.message)
                    # notify a channel
                    # self.rocket.
                else:
                    if settings.DEBUG:
                        print("NOTIFYING USER CALLER LEFT QUEUE: ", self.message)
                    # notify a user
                    # self.rocket.

                print(rendered_template)
