# -*- coding: utf-8 -*-

import os
import sys
import pymongo
import paramiko
from flask import (
    Response,
    json,
    stream_with_context,
)
from socket import gaierror


def ssh_client() -> paramiko.SSHClient:
    """
    Create an SSH client to connect to the SLURM scheduler.
    This function uses the Paramiko library to create an SSH client
    and sets the missing host key policy to automatically add the host key.

    Returns:
        paramiko.SSHClient: An SSH client object configured to connect to the SLURM scheduler.
    """
    ssh_client = paramiko.SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return ssh_client


def ssh_client_exec(ssh_client: paramiko.SSHClient, cmd: str) -> tuple:
    """
    Execute a command on the SLURM scheduler via SSH. 
    
    The private key for the SSH connection is obtained via the SSH agent.

    This function uses the provided SSH client to execute a command on
    the SLURM scheduler and returns the output and error streams.

    Args:
        ssh_client (paramiko.SSHClient): The SSH client used to connect to the SLURM scheduler.
        cmd (str): The command to be executed on the SLURM scheduler.

    Returns:
        tuple: A tuple containing the output and error streams of the executed command.
    """
    from app.constants import (
        SSH_HOSTNAME,
        SSH_USERNAME,
        SSH_PRIVATE_KEY,
    )

    try:
        ssh_client.connect(
            hostname=SSH_HOSTNAME,
            username=SSH_USERNAME,
            pkey=SSH_PRIVATE_KEY,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        return ssh_client.exec_command(cmd)
    except gaierror as err:
        print(f" * SSH connection failed: {err}", file=sys.stderr)
        # print(f" * SSH_AUTH_SOCK={os.environ.get('SSH_AUTH_SOCK')}", file=sys.stderr)
        # sys.exit(-1)
    except paramiko.SSHException as err:
        print(f" * SSH connection failed: {err}", file=sys.stderr)
        # print(f" * SSH_AUTH_SOCK={os.environ.get('SSH_AUTH_SOCK')}", file=sys.stderr)
        sys.exit(-1)
    except paramiko.AuthenticationException as err:
        print(f" * SSH authentication failed: {err}", file=sys.stderr)
        sys.exit(-1)


def init_mongodb() -> None:
    """
    Initialize the MongoDB client and ping it to check if it is connected.
    """
    from app.constants import (
        MONGODB_CLIENT,
        MONGODB_URI,
    )

    ping_mongodb_client(MONGODB_CLIENT, MONGODB_URI)


def ping_mongodb_client(client: pymongo.MongoClient, uri: str) -> None:
    """
    Ping the MongoDB client to check if it is connected.
    This function attempts to ping the MongoDB client and raises an exception
    if the connection fails.

    Args:
        client (pymongo.MongoClient): The MongoDB client to be pinged.
        uri (str): The URI used to connect to the MongoDB client.

    Raises:
        Exception: If the MongoDB client cannot be pinged.
    """
    try:
        client.admin.command("ping")
        print(f" * MongoDB running on {uri}", file=sys.stderr)
    except pymongo.errors.ConnectionFailure as err:
        print(f" * MongoDB connection failed - is the server running?\nError: {err}", file=sys.stderr)
        sys.exit(-1)


def stream_json_response(data: dict, status_code: int = 200) -> Response:
    """
    Stream a JSON response with the given data and status code.

    Args:
        data (dict): The data to be included in the JSON response.
        status_code (int): The HTTP status code for the response.

    Returns:
        Response: A Flask Response object with the streamed JSON data.
    """

    def generate():
        yield json.dumps(data, indent=4)
        yield "\n"

    response = Response(
        stream_with_context(generate()),
        mimetype="application/json",
        status=status_code,
    )
    response.headers["Content-Type"] = "application/json"
    return response
