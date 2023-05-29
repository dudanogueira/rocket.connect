import datetime
import json
import uuid

import pytz
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDay
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt
from envelope.models import LiveChatRoom
from instance.forms import NewConnectorForm, NewServerForm
from instance.models import Connector, Server

from .forms import NewChatwootConnectorForm, NewChatwootServerForm, NewInboundForm


@csrf_exempt
def connector_endpoint(request, connector_id):
    connector = get_object_or_404(
        Connector, external_token=connector_id, enabled=True, server__enabled=True
    )
    return_response = connector.intake(request)
    if not (return_response):
        return JsonResponse(
            {"connector_name": connector.name, "connector_id": connector.external_token}
        )
    return return_response


@csrf_exempt
def connector_inbound_endpoint(request, connector_id):
    connector = get_object_or_404(
        Connector, external_token=connector_id, enabled=True, server__enabled=True
    )
    return_response = connector.inbound_intake(request)
    if not return_response:
        return HttpResponse("No inbound return.", status=404)
    # it can request a redirect
    if return_response.get("redirect"):
        return redirect(return_response["redirect"])
    if return_response.get("notfound"):
        return HttpResponse(return_response.get("notfound"), status=404)
    return JsonResponse(return_response)


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
    if server.type == "rocketchat":
        # default_messages check
        if request.GET.get("default_messages"):
            return JsonResponse(server.default_messages, safe=False)
        # unauthorized access
        # if no server.secret_token, allow unprotected access
        if (
            server.secret_token
            and request.headers.get("X-Rocketchat-Livechat-Token")
            != server.secret_token
        ):
            # alert manager channel
            server.multiple_connector_admin_message(
                ":warning:  Rocket.Chat Omnichannel Connection Test was Received."
                + "It was *not successfull*, as the secret token is different"
            )
            return HttpResponse(
                "Unauthorized. No X-Rocketchat-Livechat-Token provided.", status=401
            )
        # income message, we have a body
        if request.body:
            raw_message = json.loads(request.body)
            if settings.DEBUG:
                print("DEBUG: NEW SERVER PAYLOAD: ", raw_message)

            #
            # roketchat test message
            #
            if raw_message.get("_id") == "fasd6f5a4sd6f8a4sdf":
                message_sent = server.multiple_connector_admin_message(
                    ":white_check_mark:  Rocket.Chat Omnichannel Connection Test was Received. This is the response."
                )
                if message_sent:
                    return JsonResponse({})
                else:
                    return HttpResponse(
                        "Unauthorized. No X-Rocketchat-Livechat-Token provided.",
                        status=401,
                    )
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
                    room = LiveChatRoom.objects.filter(
                        room_id=raw_message["_id"]
                    ).first()

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
                        "RUNING SECONDARY CONNECTOR *{}* WITH BODY {}:".format(
                            sconnector.connector, request.body
                        )
                    )
                    sconnector.ingoing()
    if server.type == "chatwoot":
        # for chatwoot, the outgoing messages will also be sent to the connector
        # here we only will receive the ROCKETCONNECT INBOX payalods
        # so we need to find the connector, based on source_id
        print("INCOMING ON CHATWOOT", request.body)
        raw_message = json.loads(request.body).get("conversation")
        source_id = raw_message.get("contact_inbox", {}).get("source_id")
        if raw_message.get("messages", {}):
            content = raw_message.get("messages", {})[0].get("content")
            connector_instance = server.connectors.get(external_token=source_id)
            Connectorcls = connector_instance.get_connector_class()
            connector = Connectorcls(
                connector_instance, request.body, "ingoing", request
            )
            if content == "status":
                status_session = connector.status_session()
                connector.outcome_admin_message(status_session)
            if content == "start":
                initialize = connector.initialize()
                connector.outcome_admin_message(initialize)
            if content == "close":
                status_session = connector.status_session()
                close = connector.close_session()
                connector.outcome_admin_message(close)

    return JsonResponse({})


@csrf_exempt
def server_messages_endpoint(request, server_id):
    server = get_object_or_404(Server, external_token=server_id, enabled=True)
    messages = server.get_custom_messages(term=request.GET.get("term"))
    return JsonResponse(list(messages), safe=False)


@login_required(login_url="/accounts/login/")
@must_be_yours
def active_chat(request, server_id):
    server = get_object_or_404(Server.objects, external_token=server_id)
    form = NewInboundForm(request.POST or None, server=server)
    # get online agents and departments
    rocket = server.get_rocket_client()
    departments_raw = rocket.call_api_get("livechat/department").json()
    departments_choice = [
        ("@" + d["name"], "Department: " + d["name"])
        for d in departments_raw["departments"]
    ]
    destinations = departments_choice
    # now get online agents
    agents = rocket.livechat_get_users(user_type="agent").json()
    available_agents = [
        agent["username"]
        for agent in agents["users"]
        if agent["status"] == "online" and agent["statusLivechat"] == "available"
    ]
    print(available_agents)
    for agent in available_agents:
        destinations.append(("@" + agent, "Agent: " + agent))

    form.fields["destination"].choices = destinations
    if form.is_valid():
        pass
    context = {"server": server, "form": form}
    return render(request, "instance/active_chat.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def server_detail_view(request, server_id):
    server = get_object_or_404(Server.objects, external_token=server_id)
    room_sync = None
    delivered_messages_to_delete = None
    # get server status
    status = server.status()
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
                    "Sucess! Message #{} was delivered at connector {}".format(
                        message.id, message.connector.name
                    ),
                )
            else:
                messages.error(
                    request,
                    "Error! Could not deliver Message #{} at connector {}".format(
                        message.id, message.connector.name
                    ),
                )

        return redirect(reverse("instance:server_detail", args=[server.external_token]))

    if request.GET.get("check-room-sync"):
        room_sync = server.room_sync()
        if request.GET.get("do-check-room-sync"):
            room_sync = server.room_sync(execute=True)
            messages.success(request, "Sync Executed!")
            room_sync = server.room_sync()

    if request.GET.get("delete-delivered-messages"):
        if request.GET.get("do-delete-delivered-messages"):
            delivered_messages_to_delete = server.delete_delivered_messages(
                age=10, execute=True
            )
            messages.success(
                request, f"Delivered messages deleted: {delivered_messages_to_delete}"
            )
        else:
            delivered_messages_to_delete = server.delete_delivered_messages(age=10)

    if request.GET.get("install-default-tasks"):
        added_tasks = server.install_server_tasks()
        for added_task in added_tasks:
            messages.success(request, f"Added task {added_task} to this server")
        if added_tasks:
            messages.info(request, "All tasks are created disabled. Edit it to enable.")

        return redirect(reverse("instance:server_detail", args=[server.external_token]))

    if request.POST.get("custom-messages-import"):
        import_messages = request.POST.get("custom-messages-import")
        if import_messages:
            try:
                server.import_custom_messages(import_messages)
                messages.success(request, "messages imported")
            except IndexError:
                messages.error(request, "Error importing custom messages")
        else:
            messages.info(request, "No Custom Messages to Import")

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
    tasks = server.tasks.order_by("-enabled")
    context = {
        "base_uri": base_uri,
        "server": server,
        "connectors": connectors,
        "status": status,
        "room_sync": room_sync,
        "delivered_messages_to_delete": delivered_messages_to_delete,
        "tasks": tasks,
    }
    return render(request, "instance/server_detail_view.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def connector_analyze(request, server_id, connector_id):
    connector = get_object_or_404(
        Connector.objects, server__external_token=server_id, external_token=connector_id
    )
    # get base uri
    uri = request.build_absolute_uri()
    base_uri = uri.replace(request.get_full_path(), "")
    # get status session
    connector_action_response = {}
    connector_action_response["status_session"] = connector.status_session()
    undelivered_messages = None
    date = None
    room_sync = None

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
                        "Success! Message #{} was delivered at connector {}".format(
                            message.id, connector.name
                        ),
                    )
                else:
                    messages.error(
                        request,
                        "Error! Could not deliver Message #{} at connector {}".format(
                            message.id, connector.name
                        ),
                    )
        if request.GET.get("action") == "mark_as_delivered":
            undelivered_messages.update(delivered=True)
            for um in undelivered_messages:
                messages.success(request, f"Message #{um.id} marked as delivered")
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

    if request.GET.get("check-room-sync"):
        room_sync = connector.room_sync()
        if request.GET.get("do-check-room-sync"):
            room_sync = connector.room_sync(execute=True)
            messages.success(request, "Sync Executed!")
            room_sync = connector.room_sync()

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
            messages.success(request, f"Configurations changed for {connector.name}")
    else:
        if config_form:
            config_form = config_form(connector=connector)

    context = {
        "connector": connector,
        "messages_undelivered_by_date": messages_undelivered_by_date,
        "undelivered_messages": undelivered_messages,
        "date": date,
        "room_sync": room_sync,
        "connector_action_response": connector_action_response,
        "config_form": config_form,
        "base_uri": base_uri,
    }
    return render(request, "instance/connector_analyze.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def new_rocketchat_connector(request, server_id):
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
            messages.success(request, f"New connector {new_connector.name} created.")
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
    return render(request, "instance/new_rocketchat_connector.html", context)


@login_required(login_url="/accounts/login/")
@must_be_yours
def new_chatwoot_connector(request, server_id):
    server = get_object_or_404(Server, external_token=server_id)
    form = NewChatwootConnectorForm(request.POST or None, server=server)
    if request.POST:
        if form.is_valid():
            new_connector = form.save(commit=False)
            new_connector.server = server
            new_connector.config = {}
            if form.cleaned_data.get("custom_connector_type"):
                new_connector.connector_type = form.cleaned_data[
                    "custom_connector_type"
                ]
            new_connector.save()
            # make sure we have the default form values
            form = NewChatwootConnectorForm(instance=new_connector, server=server)
            if form.is_valid():
                new_connector = form.save()
            messages.success(request, f"New connector {new_connector.name} created.")
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
    return render(request, "instance/new_chatwoot_connector.html", context)


@login_required(login_url="/accounts/login/")
def new_server(request):
    context = {}
    return render(request, "instance/new_server.html", context)


@login_required(login_url="/accounts/login/")
def new_server_rocket_chat(request):
    form = NewServerForm(request.POST or None)
    form.fields["admin_user_id"].required = True
    form.fields["url"].initial = "http://rocketchat:3000"
    form.fields["secret_token"].initial = str(uuid.uuid4()).upper()
    form.fields["admin_user_token"].required = True
    if form.is_valid():
        server = form.save(commit=False)
        server.bot_user_id = server.admin_user_id
        server.bot_user_token = server.admin_user_token
        status = server.status()
        if status["alive"] and not status["auth_error"]:
            server.save()
            server.owners.add(request.user)
            messages.success(request, "Server Created!")
            aditional_tasks = {}
            # add omnichannel
            if request.POST.get("install_omnichannel_webhooks"):
                i = server.install_omnichannel_webhook()
                aditional_tasks["install_omnichannel_webhooks"] = i
            # add default wppconnect
            if request.POST.get("install_default_wppconnect"):
                i = server.install_default_wppconnect()
                aditional_tasks["install_default_wppconnect"] = i
            # add default tasks
            if request.POST.get("add_default_server_tasks"):
                i = server.install_server_tasks()
                aditional_tasks["add_default_server_tasks"] = i

            if aditional_tasks:
                messages.success(
                    request,
                    "Additional tasks after server creation: {}".format(
                        aditional_tasks
                    ),
                )
            return redirect(
                reverse("instance:server_detail", args=[server.external_token])
            )
        else:
            messages.error(request, f"Error {status}")
    context = {"form": form}
    return render(request, "instance/new_server_rocketchat.html", context)


@login_required(login_url="/accounts/login/")
def new_server_chatwoot(request):
    form = NewChatwootServerForm(request.POST or None)
    form.fields["secret_token"].label = "ApiKey"
    form.fields["secret_token"].help_text = "ApiKey for this server"
    if form.is_valid():
        server = form.save(commit=False)
        server.type = "chatwoot"
        server.save()
        server.owners.add(request.user)
        return redirect(reverse("instance:server_detail", args=[server.external_token]))
    context = {"form": form}
    return render(request, "instance/new_server_chatwoot.html", context)


@login_required(login_url="/accounts/login/")
def server_monitor_view(request, server_id):
    server = get_object_or_404(Server.objects, external_token=server_id)
    order = request.GET.get("order", "agent")
    if order == "agent":
        open_rooms = server.get_open_rooms(sort='{"servedBy.username": 1, "lm": 1}')
    else:
        open_rooms = server.get_open_rooms(sort='{"department.name": 1, "lm": 1}')
    # enhance open_rooms dates
    if open_rooms:
        open_rooms = open_rooms["rooms"]
        for idx, room in enumerate(open_rooms):
            lm = datetime.datetime.strptime(room["lm"], "%Y-%m-%dT%H:%M:%S.%fZ")
            ts = datetime.datetime.strptime(room["ts"], "%Y-%m-%dT%H:%M:%S.%fZ")
            open_rooms[idx]["lm_datetime"] = pytz.utc.localize(lm)
            open_rooms[idx]["ts_datetime"] = pytz.utc.localize(ts)
    context = {"server": server, "open_rooms": open_rooms, "order": order}
    return render(request, "instance/server_monitor.html", context)
