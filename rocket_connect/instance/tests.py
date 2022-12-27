import json

from django.test import TestCase
from instance.models import Server


class ServerTestCase(TestCase):
    def setUp(self):
        pass
        # create a test server
        self.server = Server.objects.create(name="TEST SERVER")
        # create a base connector
        self.connector = self.server.connectors.create(
            name="TEST CONNECTOR", connector_type="base"
        )
        # get connector_class
        self.ConnectorClass = self.connector.get_connector_class()
        # simulate payload
        self.payload = {"payload": "here"}

    def test_get_close_message(self):
        pass
        """The close message will be defined:
        1 - force_close_message without department
        2 - advanced_force_close_message depending on department

        follow force_close_message if defined, otherwise, follow advanced_close_message, respecting
        their departments
        """

        # set force message
        close_message = "A forced, generic, close message"
        self.connector.config["force_close_message"] = close_message
        self.connector.save()
        self.incoming = self.ConnectorClass(
            self.connector, json.dumps(self.payload), "incoming"
        )

        # test simple forced message
        self.assertEqual(close_message, self.incoming.get_close_message())

    def test_get_advanced_close_message(self):

        # test advanced forced message
        forced_dpto1 = "Forced Message for Dpto 1"
        forced_dpto2 = "Forced Message for Dpto 2"
        self.connector.config["advanced_force_close_message"] = {
            "department1": forced_dpto1,
            "department2": forced_dpto2,
        }
        self.connector.save()
        self.incoming = self.ConnectorClass(
            self.connector, json.dumps(self.payload), "incoming"
        )
        got_dpto1 = self.incoming.get_close_message(department="department1")
        got_dpto2 = self.incoming.get_close_message(department="department2")
        print("A!!!!", got_dpto1)
        print("B!!!!", got_dpto2)

        self.assertEqual(
            forced_dpto1, self.incoming.get_close_message(department="department1")
        )
        self.assertEqual(
            forced_dpto2, self.incoming.get_close_message(department="department2")
        )
