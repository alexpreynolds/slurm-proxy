# -*- coding: utf-8 -*-

import sys
import pika
import unittest
from pathlib import Path

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))

from app.constants import (
    NOTIFICATIONS_RABBITMQ_HOST,
    NOTIFICATIONS_RABBITMQ_PORT,
    NOTIFICATIONS_RABBITMQ_USERNAME,
    NOTIFICATIONS_RABBITMQ_PASSWORD,
    NOTIFICATIONS_RABBITMQ_PATH,
)


class TestGetSlurmJobCompletionMessaging(unittest.TestCase):
    def test_rabbitmq_connection(self):
        # Setup RabbitMQ connection parameters
        rq_credentials = pika.PlainCredentials(
            NOTIFICATIONS_RABBITMQ_USERNAME, NOTIFICATIONS_RABBITMQ_PASSWORD
        )
        rq_connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                NOTIFICATIONS_RABBITMQ_HOST,
                NOTIFICATIONS_RABBITMQ_PORT,
                NOTIFICATIONS_RABBITMQ_PATH,
                rq_credentials,
            )
        )
        rq_channel = rq_connection.channel()

        # Publish a message
        rq_channel.basic_publish(exchange="", routing_key="hello", body="Hello World!")

        # Close the connection
        rq_connection.close()


if __name__ == "__main__":
    unittest.main()
