import json

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt
from envelope.models import LiveChatRoom
from instance.models import Connector, Server


@csrf_exempt
def connector_endpoint(request, connector_id):
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


# Custom decorator
def must_be_yours(func):
    def check_and_call(request, *args, **kwargs):
        server_id = kwargs["server_id"]
        servers_owned = request.user.servers.all().values_list(
            "external_token", flat=True
        )
        if not (server_id in servers_owned):
            return redirect(reverse("home"))
        return func(request, *args, **kwargs)

    return check_and_call


@csrf_exempt
def server_endpoint(request, server_id):
    server = get_object_or_404(Server, external_token=server_id, enabled=True)
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
        #
        # roketchat test message
        #
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


@login_required(login_url="/accounts/login/")
@must_be_yours
def server_detail_view(request, server_id):
    server = get_object_or_404(Server.objects, external_token=server_id)
    # try to get the client
    try:
        client = server.get_rocket_client()
        alive = True
        info = client.info().json()
    except requests.ConnectionError:
        alive = False
        info = None
    if request.GET.get("force_connector_delivery"):
        connector = get_object_or_404(
            server.connectors,
            external_token=request.GET.get("force_connector_delivery"),
        )
        # TODO: display message
        # TODO: do as task
        connector.force_delivery()

    connectors = server.connectors.distinct().annotate(
        undelivered_messages=Count(
            "messages__id",
            Q(messages__delivered=False) | Q(messages__delivered=None),
            distinct=True,
        ),
        total_messages=Count("messages__id", distinct=True),
        open_rooms=Count("rooms__id", Q(rooms__open=True), distinct=True),
        total_rooms=Count("rooms__id", distinct=True),
        last_message=Max("messages__created"),
    )
    context = {"server": server, "connectors": connectors, "alive": alive, "info": info}
    return render(request, "instance/server_detail_view.html", context)
