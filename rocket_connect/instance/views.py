import datetime
import json

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDay
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt
from envelope.models import LiveChatRoom
from instance.forms import NewConnectorForm
from instance.models import Connector, Server
from rocketchat_API.APIExceptions.RocketExceptions import RocketAuthenticationException


@csrf_exempt
def connector_endpoint(request, connector_id):
    connector = get_object_or_404(
        Connector, external_token=connector_id, enabled=True, server__enabled=True
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
        #
        # roketchat test message
        #
        if raw_message.get("_id") == "fasd6f5a4sd6f8a4sdf":
            return JsonResponse({})
        else:
            # process ingoing message
            try:
                room = LiveChatRoom.objects.get(room_id=raw_message["_id"])
            except LiveChatRoom.DoesNotExist:
                # todo: Alert Admin that there was an attempt to message a non existing room
                # todo: register this message somehow. RCHAT will try to deliver it a few times
                # do not answer 404 as rocketchat will keep trying do deliver
                return HttpResponse("Room Not Found", status=200)
            except LiveChatRoom.MultipleObjectsReturned:
                # this situation hangs RocketChat forever
                room = LiveChatRoom.objects.filter(room_id=raw_message["_id"]).first()

            # now, with a room, or at least one of them, let's keep it going
            Connector = room.connector.get_connector_class()
            connector = Connector(room.connector, request.body, "ingoing", request)
            connector.room = room
            # call primary connector
            connector.ingoing()
            # call secondary connectors for ingoing
            for secondary_connector in room.connector.secondary_connectors.all():
                SConnector = secondary_connector.get_connector_class()
                sconnector = SConnector(
                    secondary_connector, request.body, "ingoing", request
                )
                connector.logger_info(
                    "RUNING SECONDARY CONNECTOR *{0}* WITH BODY {1}:".format(
                        sconnector.connector, request.body
                    )
                )
                sconnector.ingoing()

    return JsonResponse({})


@login_required(login_url="/accounts/login/")
@must_be_yours
def server_detail_view(request, server_id):
    server = get_object_or_404(Server.objects, external_token=server_id)
    # try to get the client
    auth_error = False
    alive = False
    info = None
    try:
        client = server.get_rocket_client()
        alive = True
        info = client.info().json()
    except (requests.ConnectionError, json.JSONDecodeError):
        alive = False
    except RocketAuthenticationException:
        auth_error = True
    if request.GET.get("force_connector_delivery"):
        connector = get_object_or_404(
            server.connectors,
            external_token=request.GET.get("force_connector_delivery"),
        )
        # TODO: do as task
        undelivered_messages = connector.messages.filter(delivered=False)
        for message in undelivered_messages:
            message.force_delivery()
            if message.delivered:
                messages.success(
                    request,
                    "Sucess! Message #{0} was delivered at connector {1}".format(
                        message.id, message.connector.name
                    ),
                )
            else:
                messages.error(
                    request,
                    "Error! Could not deliver Message #{0} at connector {1}".format(
                        message.id, message.connector.name
                    ),
                )

        return redirect(reverse("instance:server_detail", args=[server.external_token]))

    connectors = (
        server.connectors.distinct()
        .annotate(
            undelivered_messages=Count(
                "messages__id",
                Q(messages__delivered=False) | Q(messages__delivered=None),
                distinct=True,
            ),
            # total_messages=Count("messages__id", distinct=True),
            # open_rooms=Count("rooms__id", Q(rooms__open=True), distinct=True),
            # total_rooms=Count("rooms__id", distinct=True),
            last_message=Max("messages__created"),
            # total_visitors=Count("rooms__token", distinct=True),
        )
        .order_by("-id")
    )
    uri = request.build_absolute_uri()
    base_uri = uri.replace(request.get_full_path(), "")
    context = {
        "base_uri": base_uri,
        "server": server,
        "connectors": connectors,
        "alive": alive,
        "info": info,
        "auth_error": auth_error,
    }
    return render(request, "instance/server_detail_view.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def connector_analyze(request, server_id, connector_id):
    connector = get_object_or_404(
        Connector.objects, server__external_token=server_id, external_token=connector_id
    )
    # get status session
    connector_action_response = {}
    connector_action_response["status_session"] = connector.status_session()
    undelivered_messages = None
    date = None

    if request.GET.get("connector_action") == "status_session":
        connector_action_response["status_session"] = connector.status_session()

    if request.GET.get("connector_action") == "initialize":
        connector_action_response["initialize"] = connector.initialize()

    if request.GET.get("connector_action") == "close_session":
        connector_action_response["close_session"] = connector.close_session()
        connector_action_response["status_session"] = connector.status_session()

    if request.GET.get("date") or request.GET.get("action") or request.GET.get("id"):
        # select messages to action
        if request.GET.get("date"):
            date = datetime.datetime.strptime(request.GET.get("date"), "%Y-%m-%d")
            undelivered_messages = connector.messages.filter(
                created__date=date, delivered=False
            )
        if request.GET.get("id"):
            undelivered_messages = connector.messages.filter(
                id=request.GET.get("id"), delivered=False
            )
        # act on messages
        if request.GET.get("action") == "force_delivery":
            for message in undelivered_messages:
                delivery_happened = message.force_delivery()
                if delivery_happened:
                    messages.success(
                        request,
                        "Success! Message #{0} was delivered at connector {1}".format(
                            message.id, connector.name
                        ),
                    )
                else:
                    messages.error(
                        request,
                        "Error! Could not deliver Message #{0} at connector {1}".format(
                            message.id, connector.name
                        ),
                    )
        if request.GET.get("action") == "mark_as_delivered":
            undelivered_messages.update(delivered=True)
            for um in undelivered_messages:
                messages.success(
                    request, "Message #{0} marked as delivered".format(um.id)
                )
        if request.GET.get("action") == "show":
            # we want to show the messages, so just pass
            # as the other actions will redirect
            pass
        else:
            return redirect(
                reverse(
                    "instance:connector_analyze",
                    args=[connector.server.external_token, connector.external_token],
                )
            )

    messages_undelivered_by_date = (
        connector.messages.filter(delivered=False)
        .annotate(date=TruncDay("created"))
        .values("date")
        .annotate(created_count=Count("id"))
        .annotate(room_count=Count("room__room_id", distinct=True))
        .order_by("-date")
    )

    # get form
    config_form = connector.get_connector_config_form()
    # process or render
    if request.POST:
        config_form = config_form(request.POST or None, connector=connector)
        if config_form.is_valid():
            # TODO: better save here
            config_form.save()
            messages.success(
                request, "Configurations changed for {0}".format(connector.name)
            )
    else:
        if config_form:
            config_form = config_form(connector=connector)

    context = {
        "connector": connector,
        "messages_undelivered_by_date": messages_undelivered_by_date,
        "undelivered_messages": undelivered_messages,
        "date": date,
        "connector_action_response": connector_action_response,
        "config_form": config_form,
    }
    return render(request, "instance/connector_analyze.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def new_connector(request, server_id):
    server = get_object_or_404(Server, external_token=server_id)
    form = NewConnectorForm(request.POST or None, server=server)
    if request.POST:
        if form.is_valid():
            new_connector = form.save(commit=False)
            new_connector.server = server
            new_connector.config = {}
            if form.cleaned_data["custom_connector_type"]:
                new_connector.connector_type = form.cleaned_data[
                    "custom_connector_type"
                ]
            new_connector.save()
            # make sure we have the default form values
            form = NewConnectorForm(instance=new_connector, server=server)
            if form.is_valid():
                new_connector = form.save()
            messages.success(
                request, "New connector {0} created.".format(new_connector.name)
            )
            return redirect(
                reverse(
                    "instance:connector_analyze",
                    args=[
                        new_connector.server.external_token,
                        new_connector.external_token,
                    ],
                )
            )
    context = {"server": server, "form": form}
    return render(request, "instance/new_connector.html", context)
