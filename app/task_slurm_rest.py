# -*- coding: utf-8 -*-

import sys
import json
import subprocess
from flask import (
    Blueprint,
    Response,
)
from app.helpers import (
    ssh_client,
    ssh_client_exec,
    stream_json_response,
)
from app.constants import (
    SLURM_REST_URL,
)
from typing import TypedDict
from typing_extensions import Unpack
from collections.abc import Callable

"""
https://slurm.schedmd.com/SLUG23/REST-API-SLUG23.pdf
"""

SSH_CLIENT = ssh_client()

class QueryParams(TypedDict, total=False):
    """
    TypedDict for query parameters. All fields are optional
    and it is up to the calling function to ensure that the
    parameters are valid and complete.
    """
    job_id: int
    partition: str
    state: str

task_slurm_rest = Blueprint("task_slurm_rest", __name__)


@task_slurm_rest.route("/diag/", methods=["GET"])
def get_diag() -> Response:
    """
    GET request handler for SLURM diag information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with a diagnostic JSON object.
    """
    return run_query(
        query_functor=get_slurm_diag_via_ssh, 
        endpoint_key='diag',
        kwargs=None,
    )


def run_query(query_functor: Callable, endpoint_key: str, **kwargs: Unpack[QueryParams]) -> None:
    """
    Generic request handler for SLURM REST API.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response.
    """
    slurm_rest_auth_token = get_slurm_rest_jwt_token_via_cli()  # get_slurm_rest_jwt_token_via_ssh()
    if not slurm_rest_auth_token:
        print(" * Error: Failed to retrieve SLURM REST auth token", file=sys.stderr)
        return stream_json_response({"error": "Failed to retrieve SLURM REST auth token"}, 400)
    query_result = query_functor(slurm_rest_auth_token, **(kwargs or {}))
    if not query_result:
        print(" * Error: Failed to retrieve query result", file=sys.stderr)
        return stream_json_response({"error": "Failed to retrieve SLURM diag"}, 400)
    return stream_json_response({"SLURM_JWT": slurm_rest_auth_token, endpoint_key: query_result}, 200)


def get_slurm_rest_jwt_token_via_cli() -> str:
    cmd = f"eval $(ssh login-pvm02 scontrol token) && echo -n $SLURM_JWT"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{cmd}' failed with error: {result.stderr}")
    return result.stdout.strip()


def get_slurm_rest_jwt_token_via_ssh() -> str:
    cmd = f"eval $(ssh login-pvm02 scontrol token) && echo -n $SLURM_JWT"
    print(f" * Executing command: {cmd}", file=sys.stderr)
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_token = stdout.read().decode("utf-8")
        return slurm_rest_token.strip()
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None


def get_slurm_diag_via_ssh(slurm_rest_auth_token: str, **kwargs: Unpack[QueryParams]) -> str:
    cmd = f"curl -vs -k -vvvv -H X-SLURM-USER-TOKEN:{slurm_rest_auth_token} -X GET '{SLURM_REST_URL}/diag'"
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_diag = stdout.read().decode("utf-8")
        return json.loads(slurm_rest_diag)
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None