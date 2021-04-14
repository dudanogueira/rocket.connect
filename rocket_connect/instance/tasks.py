import requests

from config import celery_app


@celery_app.task(
    retry_kwargs={"max_retries": 7, "countdown": 5},
    autoretry_for=(requests.ConnectionError,),
)
def intake_unread_messages(connector_id):
    """Reintake the Unread Messages of a given Connector"""
    from instance.models import Connector

    connector = Connector.objects.get(id=connector_id)
    Connector = connector.get_connector_class()
    c = Connector(connector, {}, type="incoming")
    unread = c.intake_unread_messages()
    return unread
