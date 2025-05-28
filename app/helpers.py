# -*- coding: utf-8 -*-

import sys
import pymongo
from flask import (
    Response,
    json,
    stream_with_context,
)
from app.constants import (
    MONGODB_URI,
    MONGODB_MONITOR_JOB_CREATED_AT_MAX_AGE,
)
from app.task_mongodb_client import MongoDBConnection
from bson import json_util

mongodb_connection = MongoDBConnection()


def get_current_datetime():
    """
    Get the current date and time in ISO format.
    
    Returns:
        str: The current date and time in ISO format.
    """
    from datetime import (datetime, timezone)
    return datetime.now(timezone.utc)


def get_current_datetime_minus_interval(interval:int=MONGODB_MONITOR_JOB_CREATED_AT_MAX_AGE):
    """
    Get the current date and time minus a specified interval in seconds.

    Args:
        interval (int): The interval in seconds to subtract from the current time.

    Returns:
        datetime: The current date and time minus the specified interval.
    """
    from datetime import (datetime, timezone, timedelta)
    return datetime.now(timezone.utc) - timedelta(seconds=interval)


def get_slurm_proxy_app():
    """
    Get the SLURM proxy application singleton instance. Useful for logging.
    """
    from app import slurm_proxy_app
    slurm_proxy_app_singleton = slurm_proxy_app.SlurmProxyApp.app()
    return slurm_proxy_app_singleton


def ping_mongodb_client(
    client: pymongo.MongoClient = mongodb_connection.get_client(),
    uri: str = MONGODB_URI,
) -> None:
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
    app = get_slurm_proxy_app()
    try:
        client.admin.command("ping")
        app.logger.info(f"MongoDB running on {uri}")
    except pymongo.errors.ConnectionFailure as err:
        app.logger.error(
            f"MongoDB connection failed - is the server running?\nError: {err}"
        )
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
        yield json_util.dumps(data, indent=4, default=vars)
        yield "\n"

    response = Response(
        stream_with_context(generate()),
        mimetype="application/json",
        status=status_code,
    )
    response.headers["Content-Type"] = "application/json"
    return response


def get_dict_from_streamed_json_response(response_as_json: Response) -> dict:
    res = ""
    while True:
        try:
            res += next(response_as_json.response)
            # print(f'res: {res}')
        except StopIteration:
            break
    res = json.loads(res)
    return res
