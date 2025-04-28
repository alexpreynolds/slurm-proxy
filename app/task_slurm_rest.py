# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import subprocess
import requests
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
    SLURM_REST_SLURM_ENDPOINT_URL,
    SLURM_REST_SLURMDB_ENDPOINT_URL,
    SLURM_REST_JWT_EXPIRATION_TIME,
    SLURM_REST_GENERIC_USERNAME,
)
from typing import TypedDict
from typing_extensions import Unpack
from collections.abc import Callable

from jwt import JWT
from jwt.jwk import jwk_from_dict

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
        username=SLURM_REST_GENERIC_USERNAME,
        query_functor=query_slurm_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURM_ENDPOINT_URL,
        endpoint_key='diag',
        endpoint_method='GET',
    )


@task_slurm_rest.route("/jobs/", methods=["GET"])
def get_list_of_jobs() -> Response:
    """
    GET request handler for SLURM jobs information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with a list of jobs.
    """
    return run_query(
        username=SLURM_REST_GENERIC_USERNAME,
        query_functor=query_slurm_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURM_ENDPOINT_URL,
        endpoint_key='jobs',
        endpoint_method='GET',
    )


@task_slurm_rest.route("/job/<int:job_id>/", methods=["GET"])
def get_job_info_for_job_id(job_id: int) -> Response:
    """
    GET request handler for SLURM job information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with information about a specific job.
    """
    return run_query(
        username=SLURM_REST_GENERIC_USERNAME,
        query_functor=query_slurm_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURMDB_ENDPOINT_URL,
        endpoint_key='job',
        endpoint_method='GET',
        kwargs={
            'job_id': job_id,
        },
    )


def run_query(username: str, query_functor: Callable, endpoint_url: str, endpoint_key: str, endpoint_method:str, **kwargs: Unpack[QueryParams]) -> None:
    """
    Generic request handler for SLURM REST API.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response.
    """
    slurm_rest_auth_token = get_slurm_rest_jwt_token_via_env(username)
    if not slurm_rest_auth_token:
        print(" * Error: Failed to retrieve SLURM REST auth token", file=sys.stderr)
        return stream_json_response({"error": "Failed to retrieve SLURM REST auth token"}, 400)
    query_result = query_functor(slurm_rest_auth_token, endpoint_url, endpoint_key, endpoint_method, **(kwargs or {}))
    if not query_result:
        print(" * Error: Failed to retrieve query result", file=sys.stderr)
        return stream_json_response({"error": "Failed to retrieve SLURM diag"}, 400)
    return stream_json_response(
        {
            "SLURM_JWT": slurm_rest_auth_token,
            endpoint_url: endpoint_url,
            endpoint_method: endpoint_method,
            endpoint_key: query_result
        }, 200)


def get_slurm_rest_jwt_private_key_via_env() -> str:
    slurm_private_key = os.environ.get("SLURM_JWT_HS256_KEY_BASE64")
    if not slurm_private_key:
        print(" * Error: SLURM_JWT_HS256_KEY_BASE64 environment variable not set", file=sys.stderr)
        return None
    return slurm_private_key.strip()


def get_slurm_rest_jwt_token_via_env(username: str) -> str:
    priv_key = get_slurm_rest_jwt_private_key_via_env()
    signing_key = jwk_from_dict({
      'kty': 'oct',
      'k': priv_key,
    })
    message = {
        "exp": int(time.time() + SLURM_REST_JWT_EXPIRATION_TIME),
        "iat": int(time.time()),
        "sun": username,
    }
    a = JWT()
    compact_jws = a.encode(message, signing_key, alg='HS256')
    # print(f" * SLURM_JWT={compact_jws}", file=sys.stderr)
    return compact_jws


def get_slurm_rest_jwt_token_via_cli(username: str) -> str:
    cmd = f"eval $(ssh login-pvm02 scontrol token username={username} lifespan={SLURM_REST_JWT_EXPIRATION_TIME}) && echo -n $SLURM_JWT"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{cmd}' failed with error: {result.stderr}")
    return result.stdout.strip()


def get_slurm_rest_jwt_token_via_ssh(username: str) -> str:
    cmd = f"eval $(ssh login-pvm02 scontrol token username={username} lifespan={SLURM_REST_JWT_EXPIRATION_TIME}) && echo -n $SLURM_JWT"
    print(f" * Executing command: {cmd}", file=sys.stderr)
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_token = stdout.read().decode("utf-8")
        return slurm_rest_token.strip()
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None


def get_slurm_rest_query(endpoint_url: str, endpoint_key: str, **kwargs: Unpack[QueryParams]) -> str:
    args = ""
    kwargs = kwargs['kwargs'] if 'kwargs' in kwargs else kwargs
    if len(kwargs.keys()) > 0:
        for key, value in  kwargs.items():
            if key in QueryParams:
                args += f"/{value}"
    query_url = f"{endpoint_url}/{endpoint_key}/"
    if len(args) > 0:
        query_url = f"{endpoint_url}/{endpoint_key}/{args}/"
    return query_url


def query_slurm_endpoint_via_ssh(slurm_rest_auth_token: str, endpoint_url: str, endpoint_key: str, endpoint_method: str, **kwargs: Unpack[QueryParams]) -> str:
    query_url = get_slurm_rest_query(endpoint_url, endpoint_key, **kwargs)
    # print(f" * Querying SLURM endpoint: {endpoint_key} -> {query_url}", file=sys.stderr)
    cmd = f"curl -vs -k -vvvv -H X-SLURM-USER-TOKEN:{slurm_rest_auth_token} -X {endpoint_method} '{query_url}'"
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_diag = stdout.read().decode("utf-8")
        return json.loads(slurm_rest_diag)
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None


def query_slurm_endpoint_via_requests(slurm_rest_auth_token: str, endpoint_url: str, endpoint_key: str, endpoint_method: str, **kwargs: Unpack[QueryParams]) -> str:
    query_url = get_slurm_rest_query(endpoint_url, endpoint_key, **kwargs)
    # print(f" * Querying SLURM endpoint: {endpoint_key} -> {query_url}", file=sys.stderr)
    headers = {
        'X-SLURM-USER-TOKEN': slurm_rest_auth_token,
    }
    response = requests.request(endpoint_method, query_url, headers=headers)
    if response.status_code != 200:
        print(f" * Error: {response.status_code} - {response.text}", file=sys.stderr)
        return None
    return response.json()