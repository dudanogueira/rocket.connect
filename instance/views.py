from django.shortcuts import render, get_object_or_404
from instance.models import Connector, Server
from envelope.models import LiveChatRoom
# import it
from django.http import JsonResponse
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json

@csrf_exempt
def connector_view(request, connector_id):
    connector = Connector.objects.get(external_token=connector_id)
    # income message
    if request.body:
        raw_message = json.loads(request.body)
        if settings.DEBUG == True:
            print("INCOMING", raw_message)
        # todo, create task here
        connector.intake(raw_message)
    return JsonResponse({})


@csrf_exempt
def server_view(request, server_id):
    server = get_object_or_404(Server, external_token=server_id)
    # unauthorized access
    # if no server.secret_token, allow unprotected access
    if server.secret_token and request.headers.get('X-Rocketchat-Livechat-Token') != server.secret_token:
        return HttpResponse('Unauthorized', status=401)
    # income message, we have a body
    if request.body:
        raw_message = json.loads(request.body)
        if settings.DEBUG == True:
            print("INGOING", raw_message)
        # roketchat test message
        if raw_message['_id'] == "fasd6f5a4sd6f8a4sdf":
            return JsonResponse({})        
        else:
            # process ingoing message
            try:
                room = LiveChatRoom.objects.get(
                    room_id=raw_message['_id']
                )
                print("Got Room:", room.id)
                Connector = room.connector.get_connector_class()
                connector = Connector(room.connector, raw_message, "ingoing")
                connector.room = room
                # todo: create task to out go message
                connector.ingoing()
            except LiveChatRoom.DoesNotExist():
                # todo: try to get the room from rocketchat, and recreated it
                # maybesomething happened here.
                return HttpResponse('Room Not Found', status=404)

    return JsonResponse({})
