from django.shortcuts import render
from instance.models import Connector
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
            print(raw_message)
        # todo, create task here
        connector.intake(raw_message)
    return JsonResponse({})
