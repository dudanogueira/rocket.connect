import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from envelope.models import LiveChatRoom
from instance.models import Connector, Server


@csrf_exempt
def connector_view(request, connector_id):
    connector = get_object_or_404(Connector, external_token=connector_id)
    if settings.DEBUG:
        if request.body:
            body = json.loads(request.body)
            print(
                "INCOMING > CONNECTOR NAME: REQUEST BODY: {0}: ".format(connector.name),
                body,
            )
    return_response = connector.intake(request)
    return return_response


@csrf_exempt
def server_view(request, server_id):
    server = get_object_or_404(Server, external_token=server_id)
    # unauthorized access
    # if no server.secret_token, allow unprotected access
    if (
        server.secret_token
        and request.headers.get("X-Rocketchat-Livechat-Token") != server.secret_token
    ):
        return HttpResponse("Unauthorized", status=401)
    # income message, we have a body
    if request.body:
        raw_message = json.loads(request.body)
        if settings.DEBUG is True:
            print("INGOING", request.body)
        # roketchat test message
        if raw_message["_id"] == "fasd6f5a4sd6f8a4sdf":
            return JsonResponse({})
        else:
            # process ingoing message
            try:
                room = LiveChatRoom.objects.get(room_id=raw_message["_id"])
                print("Got Room:", room.id)
                Connector = room.connector.get_connector_class()
                connector = Connector(room.connector, request.body, "ingoing", request)
                connector.room = room
                # todo: create task to out go message
                connector.ingoing()
            except LiveChatRoom.DoesNotExist:
                # todo: Alert Admin that there was an attempt to message a non existing room
                # todo: register this message somehow. RCHAT will try to deliver it a few times
                return HttpResponse("Room Not Found", status=404)

    return JsonResponse({})
