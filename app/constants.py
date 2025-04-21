# -*- coding: utf-8 -*-

import os
import pymongo
import paramiko
from enum import Enum
from app.task_notification import NotificationCallbacks

"""
Application name and port
"""
APP_NAME = os.environ.get("NAME", "dt-slurm-proxy")
APP_PORT = os.environ.get("PORT", 5001)

"""
These parameters are used to define the tasks that can be submitted to the SLURM scheduler
through this proxy. 

The `cmd` parameter is the command that will be executed on the host submitting a job to 
the SLURM scheduler. 

The `description` parameter is a short summary of the task. 

The `default_params` parameter is a list of default parameters that will be passed to the
command.

The `notification_queue` parameter is the name of the RabbitMQ queue that will be used to
send notifications about a completed task. This queue name should be specific to the task.
"""
TASK_METADATA = {
    "echo_hello_world": {
        "cmd": "echo",
        "default_params": [],
        "description": "Prints a generic hello world! message",
        "notification": {
            "methods": [
                NotificationCallbacks.TEST,
                NotificationCallbacks.EMAIL,
                NotificationCallbacks.SLACK,
                NotificationCallbacks.RABBITMQ,
            ],
            "params": {
                "test": None,
                "email": {
                    "sender": "areynolds@altius.org",
                    "recipient": "areynolds@altius.org",
                    "subject": "Hello World",
                    "body": "Hello World!",
                },
                "slack": {
                    "msg": "Hello World!",
                    "channel": "general",
                },
                "rabbitmq": {
                    "queue": "hello_world_queue",
                    "exchange": "",
                    "routing_key": "hello_world",
                    "body": "Hello World!",
                },
            },
        },
    },
}

"""
Task submission methods
"""


class TaskCommunicationMethods(Enum):
    SSH = 1
    REST = 2


"""
RabbitMQ connection parameters

The defaults point to a local instance of a test RabbitMQ server, which is only
for test use.

Specific parameters should be passed in as environment variables, which reflect
the configuration of the organization's RabbitMQ server. Please see: 
https://github.com/Altius/messaging for more details on host, port, username,
password, path and other parameters.
"""
NOTIFICATIONS_RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
NOTIFICATIONS_RABBITMQ_PORT = os.environ.get("RABBITMQ_PORT", 5672)
NOTIFICATIONS_RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "guest")
NOTIFICATIONS_RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
NOTIFICATIONS_RABBITMQ_PATH = os.environ.get("RABBITMQ_PATH", "/")

"""
SMTP service parameters

If smtp.gmail.com is used, the username and password should be set to the
Gmail account used to send the email. The password should be an app password or token
generated for the account. See https://support.google.com/accounts/answer/185201?hl=en
for more details on how to generate an app password.
"""
NOTIFICATIONS_SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.example.com")
NOTIFICATIONS_SMTP_PORT = os.environ.get("SMTP_PORT", 587)
NOTIFICATIONS_SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "username@example.com")
NOTIFICATIONS_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "api_token")

"""
Slack service parameters

Tokens should be created for the bot user that will be used to send messages to the Slack
channel. The channel should be the name of the channel that the bot user is a member of.
The token should be a bot token, which can be created in the Slack API console, described
here: https://api.slack.com/tutorials/tracks/getting-a-token
"""
NOTIFICATIONS_SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "api_token")
NOTIFICATIONS_SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "channel_name")

"""
These parameters are used to connect to the SLURM scheduler via SSH. A private key is
used to authenticate the connection. The `SSH_USERNAME` is the username used to connect
to the SLURM scheduler, and the `SSH_HOSTNAME` is the hostname of the SLURM scheduler.
"""
SSH_USERNAME = os.environ.get("SSH_USERNAME", "areynolds")
SSH_HOSTNAME = os.environ.get("SSH_HOSTNAME", "tools0.altiusinstitute.org")
SSH_PRIVATE_KEY_PATH = os.path.expanduser(f"/Users/{SSH_USERNAME}/.ssh/id_ed25519")
try:
    SSH_KEY = paramiko.Ed25519Key.from_private_key_file(SSH_PRIVATE_KEY_PATH)
except FileNotFoundError as err:
    print(f" * SSH key not found: {err}", file=sys.stderr)
    SSH_KEY = None

"""
Mongodb connection
"""
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_CLIENT = pymongo.MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=1000,
)
MONGODB_MONITOR_DB = MONGODB_CLIENT["monitordb"]
MONGODB_JOBS_COLLECTION = MONGODB_MONITOR_DB["jobs"]

"""
How frequently to poll the SLURM scheduler for job status updates.
"""
MONITOR_POLLING_INTERVAL = os.environ.get("MONITOR_POLLING_INTERVAL", 1)  # in minutes

"""
SLURM test parameters
"""
BAD_SLURM_JOB_ID = -1
SLURM_TEST_JOB_ID = 123
SLURM_TEST_JOB_STATUS = {
    "job_id": "123",
    "job_name": "abcd1234",
    "state": "COMPLETED",
    "user": "username",
    "partition": "partition",
    "time": "UNLIMITED",
    "start": "2025-04-14T08:57:46",
    "end": "2025-04-14T11:00:44",
    "elapsed": "02:02:58",
}

"""
These parameters are used to define the SLURM job status codes and their explanations.
"""
SLURM_STATE = {
    "COMPLETED": {
        "code": "CD",
        "explanation": "The job has completed successfully.",
    },
    "COMPLETING": {
        "code": "CG",
        "explanation": "The job is finishing but some processes are still active.",
    },
    "FAILED": {
        "code": "F",
        "explanation": "The job terminated with a non-zero exit code and failed to execute.",
    },
    "PENDING": {
        "code": "PD",
        "explanation": "The job is waiting for resource allocation. It will eventually run.",
    },
    "PREEMPTED": {
        "code": "PR",
        "explanation": "The job was terminated because of preemption by another job.",
    },
    "RUNNING": {
        "code": "R",
        "explanation": "The job currently is allocated to a node and is running.",
    },
    "SUSPENDED": {
        "code": "S",
        "explanation": "A running job has been stopped with its cores released to other jobs.",
    },
    "STOPPED": {
        "code": "ST",
        "explanation": "A running job has been stopped with its cores retained.",
    },
    "TIMEOUT": {
        "code": "TO",
        "explanation": "The job has been terminated because it exceeded its time limit.",
    },
    "CANCELLED": {
        "code": "CA",
        "explanation": "The job has been cancelled by the user.",
    },
    "NODE_FAIL": {
        "code": "NF",
        "explanation": "The job has been terminated because one or more nodes failed.",
    },
    "BOOT_FAIL": {
        "code": "BF",
        "explanation": "The job has been terminated because the node failed to boot.",
    },
    "OUT_OF_MEMORY": {
        "code": "OOM",
        "explanation": "The job has been terminated because it exceeded its memory limit.",
    },
    "PREEMPTED": {
        "code": "PR",
        "explanation": "The job has been terminated because it was preempted by another job.",
    },
    "RESV_DEL_HOLD": {
        "code": "RD",
        "explanation": "The job has been held.",
    },
    "REQUEUE_FED": {
        "code": "RF",
        "explanation": "The job has been requeued by a federation.",
    },
    "REQUEUE_HOLD": {
        "code": "RH",
        "explanation": "Held job is being requeued.",
    },
    "RESIZING": {
        "code": "RS",
        "explanation": "The job is being resized.",
    },
    "REVOKED": {
        "code": "RV",
        "explanation": "Sibling was removed from cluster due to other cluster starting the job.",
    },
    "SIGNALING": {
        "code": "SI",
        "explanation": "The job is being signaled.",
    },
    "SPECIAL_EXIT": {
        "code": "SE",
        "explanation": "The job was requeued in a special state. This state can be set by users, typically in EpilogSlurmctld, if the job has terminated with a particular exit value.",
    },
    "STAGE_OUT": {
        "code": "SO",
        "explanation": "The job is being staged out.",
    },
    "DEADLINE": {
        "code": "DL",
        "explanation": "The job has been terminated because it exceeded its deadline.",
    },
}
SLURM_STATE_UNKNOWN = "UNKNOWN"
SLURM_STATE_END_STATES = ["COMPLETED", "FAILED", "CANCELLED", "SUSPENDED", "NODE_FAIL", "TIMEOUT", "DEADLINE"]
