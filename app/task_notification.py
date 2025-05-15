# -*- coding: utf-8 -*-

import sys
from enum import Enum
from functools import partial


class NotificationCallbacks(Enum):
    EMAIL = partial(
        lambda sender, recipient, subject, body: NotificationMethods.notify_via_email(
            sender, recipient, subject, body
        )
    )
    GMAIL = partial(
        lambda sender, recipient, subject, body: NotificationMethods.notify_via_gmail(
            sender, recipient, subject, body
        )
    )
    RABBITMQ = partial(
        lambda queue, exchange, routing_key, body: NotificationMethods.notify_via_rabbitmq(
            queue, exchange, routing_key, body
        )
    )
    SLACK = partial(
        lambda msg, channel: NotificationMethods.notify_via_slack(msg, channel)
    )
    TEST = partial(lambda msg: NotificationMethods.notify_via_test(msg))


class NotificationMethods:
    @staticmethod
    def notify_via_email(sender, recipient, subject, body):
        """
        Sends an email notification.

        Args:
            sender (str): The sender's email address.
            recipient (str): The recipient's email address.
            subject (str): The subject of the email.
            body (str): The body of the email.
        """
        print(
            f" * Sending email to {recipient} with subject '{subject}' and body '{body}'"
        )
        import re
        import smtplib
        from email.mime.text import MIMEText
        from app.constants import (
            NOTIFICATIONS_SMTP_SERVER,
            NOTIFICATIONS_SMTP_PORT,
            NOTIFICATIONS_SMTP_USERNAME,
            NOTIFICATIONS_SMTP_PASSWORD,
        )

        email_pattern = r"^\S+@\S+\.\S+$"
        if not re.match(email_pattern, sender):
            print(" * Error: Invalid sender email address.", file=sys.stderr)
            return
        if not re.match(email_pattern, recipient):
            print(" * Error: Invalid recipient email address.", file=sys.stderr)
            return
        if not subject or subject.strip() == "":
            print(" * Error: Invalid email subject.", file=sys.stderr)
            return
        if not body or body.strip() == "":
            print(" * Error: Invalid email body.", file=sys.stderr)
            return
        message = MIMEText(body)
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        try:
            with smtplib.SMTP(
                NOTIFICATIONS_SMTP_SERVER, NOTIFICATIONS_SMTP_PORT
            ) as server:
                server.starttls()
                server.login(NOTIFICATIONS_SMTP_USERNAME, NOTIFICATIONS_SMTP_PASSWORD)
                server.sendmail(sender, recipient, message.as_string())
        except Exception as err:
            print(f" * Failed to send email: {err}", file=sys.stderr)

    @staticmethod
    def notify_via_gmail(sender, recipient, subject, body):
        """
        Sends a Gmail notification.

        Args:
            sender (str): The sender's email address.
            recipient (str): The recipient's email address.
            subject (str): The subject of the email.
            body (str): The body of the email.
        """
        print(
            f" * Sending Gmail to {recipient} with subject '{subject}' and body '{body}'"
        )
        import re
        import base64
        from email.message import EmailMessage
        from google.auth import load_credentials_from_file
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from app.constants import (
            NOTIFICATIONS_GMAIL_CREDENTIALS_PATH,
        )

        email_pattern = r"^\S+@\S+\.\S+$"
        if not re.match(email_pattern, sender):
            print(" * Error: Invalid sender email address.", file=sys.stderr)
            return
        if not re.match(email_pattern, recipient):
            print(" * Error: Invalid recipient email address.", file=sys.stderr)
            return
        if not subject or subject.strip() == "":
            print(" * Error: Invalid email subject.", file=sys.stderr)
            return
        if not body or body.strip() == "":
            print(" * Error: Invalid email body.", file=sys.stderr)
            return

        credentials, _ = load_credentials_from_file(
            NOTIFICATIONS_GMAIL_CREDENTIALS_PATH
        )

        try:
            service = build("gmail", "v1", credentials=credentials)
            message = EmailMessage()
            message.set_content(body)
            message["To"] = recipient
            message["From"] = sender
            message["Subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            create_message = {"message": {"raw": raw_message}}
            send_message = (
                service.users()
                .messages()
                .send(userId="me", body=create_message)
                .execute()
            )
            print(f" * Gmail sent successfully: {send_message['id']}", file=sys.stderr)
        except HttpError as err:
            print(f" * Gmail error occurred: {err}", file=sys.stderr)
            send_message = None

    @staticmethod
    def notify_via_rabbitmq(
        queue="hello", exchange="", routing_key="hello", body="Hello World!"
    ):
        """
        Sends a message to a RabbitMQ queue.

        Args:
            queue (str): The name of the queue.
            exchange (str): The exchange to use.
            routing_key (str): The routing key for the message.
            body (str): The body of the message.
        """
        from app.constants import (
            NOTIFICATIONS_RABBITMQ_HOST,
            NOTIFICATIONS_RABBITMQ_PORT,
            NOTIFICATIONS_RABBITMQ_USERNAME,
            NOTIFICATIONS_RABBITMQ_PASSWORD,
            NOTIFICATIONS_RABBITMQ_PATH,
        )
        import pika

        credentials = pika.PlainCredentials(
            NOTIFICATIONS_RABBITMQ_USERNAME, NOTIFICATIONS_RABBITMQ_PASSWORD
        )
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                NOTIFICATIONS_RABBITMQ_HOST,
                NOTIFICATIONS_RABBITMQ_PORT,
                NOTIFICATIONS_RABBITMQ_PATH,
                credentials,
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue)
        channel.basic_publish(exchange, routing_key, body)
        connection.close()

    @staticmethod
    def notify_via_slack(msg, channel):
        """
        Sends a notification to a Slack channel.
        """
        if not msg:
            print(" * Error: Empty Slack message", file=sys.stderr)
            return
        from app.constants import (
            NOTIFICATIONS_SLACK_BOT_TOKEN,
            NOTIFICATIONS_SLACK_CHANNEL,
        )
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError

        try:
            client = WebClient(token=NOTIFICATIONS_SLACK_BOT_TOKEN)
            channel = NOTIFICATIONS_SLACK_CHANNEL if not channel else channel
            response = client.chat_postMessage(channel, text=msg)
            # print(f" * Slack message sent successfully: {response['message']['text']}", file=sys.stderr)
        except SlackApiError as err:
            print(
                f" * Error: Failed to send Slack message: {err.response['error']}",
                file=sys.stderr,
            )

    @staticmethod
    def notify_via_test(msg):
        """
        Sends a test notification.

        Args:
            msg (str): The message to be sent.
        """
        print(f" * {msg}", file=sys.stderr)
