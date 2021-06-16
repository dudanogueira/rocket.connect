import asyncio
import os

import requests
from panoramisk import Manager

ASTERISK_IP = os.environ["ASTERISK_IP"]
ASTERISK_PORT = os.environ["ASTERISK_PORT"]
ASTERISK_USER = os.environ["ASTERISK_USER"]
ASTERISK_PASSWORD = os.environ["ASTERISK_PASSWORD"]
ASTERISK_CONNECTOR_ENDPOINT = os.environ["ASTERISK_CONNECTOR_ENDPOINT"]


def fire(message):
    requests.post(ASTERISK_CONNECTOR_ENDPOINT, json=dict(message.items()))


def main():
    """Função principal da aplicação."""
    manager = Manager(
        loop=asyncio.get_event_loop(),
        host=ASTERISK_IP,
        port=ASTERISK_PORT,
        username=ASTERISK_USER,
        secret=ASTERISK_PASSWORD,
    )

    @manager.register_event("AgentCalled")
    @manager.register_event("AgentConnect")
    @manager.register_event("AgentComplete")
    @manager.register_event("AgentDump")
    @manager.register_event("AgentRingNoAnswer")
    # @manager.register_event('MessageWaiting')
    # @manager.register_event('UserEvent')
    async def callback_agent(manager, message):
        fire(message)

    @manager.register_event("Hangup")
    async def callback_hangup(manager, message):
        # hangup from queue
        if message.context == "ext-queues":
            fire(message)

    manager.connect()
    try:
        manager.loop.run_forever()
    except KeyboardInterrupt:
        manager.loop.close()


if __name__ == "__main__":
    main()
