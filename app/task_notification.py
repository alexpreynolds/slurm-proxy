# -*- coding: utf-8 -*-

import re
import sys
import pika
import base64
import smtplib
from enum import Enum
from email.mime.text import MIMEText
from email.message import EmailMessage
from google.auth import load_credentials_from_file
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from abc import ABC, abstractmethod


class NotificationMethod(Enum):
    EMAIL = "email"
    GMAIL = "gmail"
    RABBITMQ = "rabbitmq"
    SLACK = "slack"
    TEST = "test"


class NotificationCallback(ABC):
    @abstractmethod
    def notify(self, *args, **kwargs):
        """
        Abstract method to send a notification.
        This method should be implemented by subclasses.
        """
        pass

    
class NotificationCallbackFactory:
    @staticmethod
    def create_callback_for_method(method:NotificationMethod) -> NotificationCallback:
        if not method:
            raise ValueError("Must specify notification method!")
        if method == NotificationMethod.EMAIL.value:
            return EmailNotificationCallback()
        elif method == NotificationMethod.GMAIL.value:
            return GmailNotificationCallback()
        elif method == NotificationMethod.RABBITMQ.value:
            return RabbitMQNotificationCallback()
        elif method == NotificationMethod.SLACK.value:
            return SlackNotificationCallback()
        elif method == NotificationMethod.TEST.value:
            return TestNotificationCallback()
        else:
            raise ValueError("Unknown notification method!")

    
class EmailNotificationCallback(NotificationCallback):
    def notify(self, sender, recipient, subject, body):
        NotificationMethodCallback.notify_via_email(sender, recipient, subject, body)


class GmailNotificationCallback(NotificationCallback):
    def notify(self, sender, recipient, subject, body):
        NotificationMethodCallback.notify_via_gmail(sender, recipient, subject, body)


class RabbitMQNotificationCallback(NotificationCallback):
    def notify(self, queue, exchange, routing_key, body):
        NotificationMethodCallback.notify_via_rabbitmq(queue, exchange, routing_key, body)


class SlackNotificationCallback(NotificationCallback):
    def notify(self, msg, channel):
        NotificationMethodCallback.notify_via_slack(msg, channel)


class TestNotificationCallback(NotificationCallback):
    def notify(self, msg):
        NotificationMethodCallback.notify_via_test(msg)


class NotificationMethodCallback:
    @staticmethod
    def validate_email_parameters(sender, recipient, subject, body):
        """
        Validates the email address.

        Args:
            email (str): The email address to validate.

        Returns:
            bool: True if valid, False otherwise.
        """
        from app.helpers import (
            get_slurm_proxy_app,
        )
        app = get_slurm_proxy_app()
        email_pattern = r"^\S+@\S+\.\S+$"
        if not re.match(email_pattern, sender):
            app.logger.error(
                "validate_email_parameters | Invalid sender email address."
            )
            return False
        if not re.match(email_pattern, recipient):
            app.logger.error(
                "validate_email_parameters | Invalid recipient email address."
            )
            return False
        if not subject or subject.strip() == "":
            app.logger.error("validate_email_parameters | Invalid email subject.")
            return False
        if not body or body.strip() == "":
            app.logger.error("validate_email_parameters | Invalid email body.")
            return False
        return True

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
        from app.helpers import (
            get_slurm_proxy_app,
        )
        from app.constants import (
            NOTIFICATIONS_SMTP_SERVER,
            NOTIFICATIONS_SMTP_PORT,
            NOTIFICATIONS_SMTP_USERNAME,
            NOTIFICATIONS_SMTP_PASSWORD,
        )
        app = get_slurm_proxy_app()
        app.logger.debug(
            f"notify_via_email | Sending email from {sender} to {recipient} with subject '{subject}' and body '{body}'"
        )
        if not NotificationMethodCallback.validate_email_parameters(
            sender, recipient, subject, body
        ):
            app.logger.error(
                "notify_via_email | Invalid email parameters. See error log."
            )
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
            app.logger.error(f"notify_via_email | Failed to send email: {err}")

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
        from app.constants import (
            NOTIFICATIONS_GMAIL_CREDENTIALS_PATH,
        )
        from app.helpers import (
            get_slurm_proxy_app,
        )
        app = get_slurm_proxy_app()
        app.logger.debug(
            f"Sending email from {sender} to {recipient} with subject '{subject}' and body '{body}'"
        )
        if not NotificationMethodCallback.validate_email_parameters(
            sender, recipient, subject, body
        ):
            app.logger.error(
                "notify_via_gmail | Invalid email parameters. See error log."
            )
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
            app.logger.debug(
                f"notify_via_gmail | Gmail sent successfully: {send_message['id']}"
            )
        except HttpError as err:
            app.logger.error(f"notify_via_gmail | Gmail error occurred: {err}")
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
        from app.helpers import (
            get_slurm_proxy_app,
        )
        app = get_slurm_proxy_app()
        try:
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
            app.logger.debug(
                f"notify_via_rabbitmq | Message sent to RabbitMQ queue '{queue}' with routing key '{routing_key}': {body}"
            )
        except pika.exceptions.AMQPConnectionError as err:
            app.logger.error(f"notify_via_rabbitmq | RabbitMQ connection error: {err}")
        except pika.exceptions.AMQPChannelError as err:
            app.logger.error(f"notify_via_rabbitmq | RabbitMQ channel error: {err}")
        except pika.exceptions.AMQPError as err:
            app.logger.error(f"notify_via_rabbitmq | RabbitMQ error: {err}")
        except Exception as err:
            app.logger.error(
                f"notify_via_rabbitmq | Failed to send RabbitMQ message: {err}"
            )

    @staticmethod
    def notify_via_slack(msg, channel):
        """
        Sends a notification to a Slack channel.
        """
        from app.constants import (
            NOTIFICATIONS_SLACK_BOT_TOKEN,
            NOTIFICATIONS_SLACK_CHANNEL,
        )
        from app.helpers import (
            get_slurm_proxy_app,
        )
        app = get_slurm_proxy_app()
        if not msg:
            app.logger.error("Error: Empty Slack message")
            return
        try:
            client = WebClient(token=NOTIFICATIONS_SLACK_BOT_TOKEN)
            channel = NOTIFICATIONS_SLACK_CHANNEL if not channel else channel
            response = client.chat_postMessage(channel=channel, text=msg)
            app.logger.debug(
                f"notify_via_slack | Slack message sent successfully: {response['message']['text']}"
            )
        except SlackApiError as err:
            app.logger.error(f"notify_via_slack | Slack API error occurred: {err}")
        except Exception as err:
            app.logger.error(f"notify_via_slack | Failed to send Slack message: {err}")

    @staticmethod
    def notify_via_test(msg):
        """
        Sends a test notification.

        Args:
            msg (str): The message to be sent.
        """
        print(f" * {msg}", file=sys.stderr)