import datetime

from django.http import JsonResponse

from asterisk.models import Call

from .base import Connector as ConnectorBase


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
        ]:
            # only for queues
            if self.message.get("Queue"):  # in ["ext-queues", "macro-blkvm-clr"]:
                call, created = self.get_call()
                call.hangup = datetime.datetime.now()
                call.save()
                # register message
                call.messages.create(json=self.message)
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
        call, created = Call.objects.get_or_create(unique_id=unique_id)
        call.caller = self.message.get("CallerIDNum")
        # if call is from queue, register the queue
        if self.message.get("Event") in ["AgentCalled", "AgentConnect"]:
            call.queue = self.message.get("Queue")
        # if event is agent connect, register agent
        if self.message.get("Event") in ["AgentConnect"]:
            call.agent = self.message.get("ConnectedLineNum")
        call.save()
        return call, created
