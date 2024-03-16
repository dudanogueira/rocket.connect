Connectors
======================================================================


WPPCONNECT
----------------------------------------------------------------------

https://wppconnect-team.github.io/

Features:

* Active Chat
* One Instance, multiple sessions
* Automatically mark as read
* Automatically send unread messages on startup
* Many more

EVOLUTION
----------------------------------------------------------------------

https://github.com/EvolutionAPI/evolution-api

Features:

* Active Chat
* One Instance, multiple sessions
* Automatically mark as read
* Automatically send unread messages on startup
* Many more


FACEBOOK
----------------------------------------------------------------------

https://developers.facebook.com/docs/messenger-platform/reference/send-api/


ASTERISK (DEPRECATED)
----------------------------------------------------------------------

The idea of the Asterisk Connector is, for now, to be able to alert Rocketchat users and channels whenever a Caller left a Queue unanswered, or a new voice mail is left. 

We also plan to provide the necessary APIs to create a new Omnichannel Room for a Caller.

This connector was tested with Issabel, but should work fine with other asterisk flavours as well.

In order to deploy, you will have to create an Asterisk AMI's user, run the AMI Client, and point it to the Asterisk Endpoint at Rocket Connect.

Add this to you /etc/asterisk/manager.conf (you can restrict access configure the permit directive)::

    [rocketconnect]
    secret=asterisk_manager_password
    deny=0.0.0.0/0.0.0.0
    permit=0.0.0.0/0.0.0.0
    read=all
    eventfilter=Event: QueueCallerLeave
    eventfilter=Event: AgentCalled
    eventfilter=Event: AgentConnect
    eventfilter=Event: AgentComplete
    eventfilter=Event: AgentDump
    eventfilter=Event: UserEvent
    eventfilter=Event: MessageWaiting
    eventfilter=Event: Hangup


Now, you need to run the Asterisk Script, that will connect to Asterisk AMI and send the events to the Asterisk Endpoint at Rocket Connect::

    docker compose -f local.yml run --rm django python rocket_connect/utils/clients/asterisk.py


note that a few environment variables are necessary::

    ASTERISK_IP=my.asterisk.ip
    ASTERISK_PORT=5038
    ASTERISK_USER=rocketconnect
    ASTERISK_PASSWORD=asterisk_manager_password
    ASTERISK_CONNECTOR_ENDPOINT=http://django:8000/connector/ASTERISK_CONNECTOR/

If everything is configured properly, you should see the queue calls being registered at http://127.0.0.1:8000/admin/asterisk/call/

Now, you can configure the connector do your environment, defining the queue_notify_map, that will send the messages as configured at notify_abandoned_queue_template.