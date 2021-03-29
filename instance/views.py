from django.shortcuts import render
from instance.models import Connector
from envelope.models import Message
# import it
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def connector_view(request, id):
    # get connector
    # connector = Connector.objects.get(id=id)
    # create message associated with connector
    raw_message = json.loads(request.body)
    message = Message.objects.create(
        connector_id=id,
        raw_message=raw_message
    )
    message.save()
    message.intake()
    return JsonResponse({})
