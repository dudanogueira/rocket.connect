How To
======================================================================

Run the development stack
----------------------------------------------------------------------

To run the development stack, you must haver docker and docker compose properly installed. You should run
    ::
    
        docker-compose -f local.yml up -d


We have created a nice management command to setup everything for you:

    ::
    
        docker-compose -f local.yml run --rm django python manage.py dev_settings

If everything went fine, you should have the following running services and exposed ports:

* http://localhost:8000/admin - Rocket Connect Admin User/Password: admin/admin
* http://localhost:3000 - Rocket Chat Server. User/Password: admin/admin or agent1/agent1 or manager1/manager1
* http://localhost:5555 - Flower, where you see how the tasks are running. User/Password: admin/admin
* http://localhost:8025 - Mailhog - A nice mailserver. The stack is configured to deliver emails there
* http://localhost:3010 - BrowserLess - A Browserless chrome instance
* http://localhost:8002/api-docs/ - WA-AUTOMATE API DOCS - Only Available after QR SCANNING

Scanning WA-AUTOMATE QR CODE
----------------------------------------------------------------------

If you access Rocket Chat, as admin, you should see new direct messages popping with the launch status of the WA-AUTOMATE CLient.

.. figure:: wa-launch-messages.png

At the end, you should see the QR CODE, that should be scanned with the device you want to PAIR.


Inside RocketChat
----------------------------------------------------------------------

To receive medias, its necessary to change the URL inside RocketChat.

Go to:
Administration -> General -> Site URL and put your IP address or valid URL.



Configuring Facebook Messenger
----------------------------------------------------------------------

By default, the dev_settings will set up a facebook endpoint for you with the verify_token set as, well, "verify_token". You will need to set up Facebook Messenger APP to this endpoint, and set up the verification token as... verify_token. You can run a ngrok to help do that. Like this:

    ::
    
        ngrok http 8000

You will get a temporarily hostname, that points to it. My case here:

https://e2515ac03068.ngrok.io

you setup like that at your facebook messenger configuration

.. figure:: facebook_messenger_dev_config.png

If everything went fine, will receive a message like this at Rocket.Chat

.. figure:: facebook_success_verification.png

you will also need to generate a token, in order to send back messages and get more informations about the visitor.after getting this token, change the connector conigurations at: http://127.0.0.1:8000/admin/instance/connector/

you need to change the "generate this" with the token facebook will give you.


.. figure:: facebook_connector_config.png


After that messages to your facebook account should be connected to RocketChat. If something goes wrong, facebook will stop sending messages for a while. That's normal. 

TroubleShooting
----------------------------------------------------------------------

The dev environment should work fine, unles somethigs break :) For testing, 
we will always try to deliver all clients to test with.

For WA-AUTOMATE, the dev environment has two wa-automate containers, using the same browser container. This command will restart all that stack, and kick off the initialize settings
    ::
    
        docker-compose -f local.yml restart waautomate1 waautomate2 browsert

