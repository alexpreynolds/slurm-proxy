# -*- coding: utf-8 -*-

import os
import json
import time
import subprocess
import requests
from flask import (
    Blueprint,
    Response,
    request,
)
from app.helpers import (
    stream_json_response,
    get_slurm_proxy_app,
)
from app.constants import (
    SLURM_REST_SLURM_ENDPOINT_URL,
    SLURM_REST_SLURMDB_ENDPOINT_URL,
    SLURM_REST_JWT_EXPIRATION_TIME,
    SLURM_REST_GENERIC_USERNAME,
)
from app.task_ssh_client import ssh_client_connection_singleton
from typing import TypedDict
from typing_extensions import Unpack
from collections.abc import Callable

from jwt import JWT
from jwt.jwk import jwk_from_dict

"""
https://slurm.schedmd.com/SLUG23/REST-API-SLUG23.pdf
"""

ssh_connection = ssh_client_connection_singleton


class QueryParams(TypedDict, total=False):
    """
    TypedDict for query parameters. All fields are optional
    and it is up to the calling function to ensure that the
    parameters are valid and complete.
    """

    job_id: int
    update_time: int


task_slurm_rest = Blueprint("task_slurm_rest", __name__)


@task_slurm_rest.route("/diag/", methods=["GET"], strict_slashes=False)
def get_diag() -> Response:
    """
    GET request handler for SLURM diag information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with a diagnostic JSON object.

    ref. https://slurm.schedmd.com/rest_api.html#slurmV0042GetDiag (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_diag_resp (response)
    """
    username = request.args.get("username")
    if not username:
        username = SLURM_REST_GENERIC_USERNAME
    return run_query(
        username=username,
        query_functor=query_slurm_get_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURM_ENDPOINT_URL,
        endpoint_key="diag",
        endpoint_method="GET",
    )


@task_slurm_rest.route("/jobs/<int:update_time>", methods=["GET"], strict_slashes=False)
def get_list_of_jobs(update_time: int) -> Response:
    """
    GET request handler for SLURM jobs information updated since update_time.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with a list of jobs.

    ref. https://slurm.schedmd.com/rest_api.html#slurmdbV0042GetJobs (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_slurmdbd_jobs_resp (response)
    """
    username = request.args.get("username")
    if not username:
        username = SLURM_REST_GENERIC_USERNAME
    return run_query(
        username=username,
        query_functor=query_slurm_get_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURMDB_ENDPOINT_URL,
        endpoint_key="jobs",
        endpoint_method="GET",
        kwargs={
            "update_time": update_time,
        },
    )


@task_slurm_rest.route("/job/<int:job_id>/", methods=["GET"], strict_slashes=False)
def get_job_info_for_job_id(job_id: int) -> Response:
    """
    GET request handler for SLURM job information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with information about a specific job.

    ref. https://slurm.schedmd.com/rest_api.html#slurmdbV0042GetJob (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_slurmdbd_jobs_resp (response)
    """
    username = request.args.get("username")
    if not username:
        username = SLURM_REST_GENERIC_USERNAME
    return run_query(
        username=username,
        query_functor=query_slurm_get_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURMDB_ENDPOINT_URL,
        endpoint_key="job",
        endpoint_method="GET",
        kwargs={
            "job_id": job_id,
        },
    )


def get_job_info_for_job_id_via_params(job_id: int, username: str) -> Response:
    """
    GET request handler for SLURM job information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with information about a specific job.

    ref. https://slurm.schedmd.com/rest_api.html#slurmdbV0042GetJob (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_slurmdbd_jobs_resp (response)
    """
    app = get_slurm_proxy_app()
    if not username:
        username = SLURM_REST_GENERIC_USERNAME

    endpoint_url = SLURM_REST_SLURMDB_ENDPOINT_URL
    endpoint_key = "job"
    endpoint_method = "GET"
    kwargs = {"job_id": job_id}
    query_url = get_slurm_rest_query(endpoint_url, endpoint_key, **kwargs)
    slurm_rest_auth_token = get_slurm_rest_jwt_token_for_username(username)
    if not slurm_rest_auth_token:
        app.logger.error(
            f"get_job_info_for_job_id_via_params | Failed to retrieve SLURM REST auth token for username: {username}"
        )
        return (
            stream_json_response(
                {"error": "Failed to retrieve SLURM REST auth token"}, 400
            ),
            400,
            query_url,
        )
    headers = {
        "X-SLURM-USER-TOKEN": slurm_rest_auth_token,
    }
    response = requests.request(endpoint_method, query_url, headers=headers)
    if response.status_code != 200:
        app.logger.error(
            f"get_job_info_for_job_id_via_params | {response.status_code} - {response.text}"
        )
    response_content = ""
    for chunk in response.iter_content(chunk_size=None):
        response_content += chunk.decode("utf-8")
    try:
        response_json_content = json.loads(response_content)
    except json.JSONDecodeError as err:
        app.logger.error(
            f"get_job_info_for_job_id_via_params | JSON decoding failed - {err}"
        )
    return response_json_content, response.status_code, query_url


@task_slurm_rest.route("/job/submit/", methods=["POST"], strict_slashes=False)
def submit_job() -> Response:
    """
    POST request handler for submitting a job to SLURM.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with the job submission result.

    ref. https://slurm.schedmd.com/rest_api.html#slurmV0042PostJobSubmit (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_job_submit_response (response)
    """
    if request.is_json:
        job = request.get_json()
    username = job["username"]
    if not username:
        username = SLURM_REST_GENERIC_USERNAME
    return run_query(
        username=username,
        query_functor=query_slurm_post_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURM_ENDPOINT_URL,
        endpoint_key="job/submit",
        endpoint_method="POST",
        kwargs={
            "job": job,
        },
    )


def submit_job_via_params(job: dict) -> Response:
    """
    Submit a job to SLURM using the provided task parameters.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with the job submission result.

    ref. https://slurm.schedmd.com/rest_api.html#slurmV0042PostJobSubmit (request)
    ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_job_submit_response (response)
    """
    username = job["username"]
    if not username:
        username = SLURM_REST_GENERIC_USERNAME
    return run_query(
        username=username,
        query_functor=query_slurm_post_endpoint_via_requests,
        endpoint_url=SLURM_REST_SLURM_ENDPOINT_URL,
        endpoint_key="job/submit",
        endpoint_method="POST",
        kwargs={
            "job": job,
        },
    )


def run_query(
    username: str,
    query_functor: Callable,
    endpoint_url: str,
    endpoint_key: str,
    endpoint_method: str,
    **kwargs: Unpack[QueryParams],
) -> None:
    """
    Generic request handler for SLURM REST API.
    This function retrieves the SLURM REST token from the request headers
    and returns it with the response from the called query_functor.

    Args:
        username (str): The username for SLURM authentication.
        query_functor (Callable): The function to call for querying SLURM.
        endpoint_url (str): The base URL for the SLURM REST API.
        endpoint_key (str): The specific endpoint key for the query.
        endpoint_method (str): The HTTP method for the query (GET, POST, etc.).
        **kwargs: Additional parameters for the query function.

    Returns:
        Response: The response from the SLURM REST API.
    """
    app = get_slurm_proxy_app()
    slurm_rest_auth_token = get_slurm_rest_jwt_token_for_username(username)
    if not slurm_rest_auth_token:
        # print(" * Error: Failed to retrieve SLURM REST auth token", file=sys.stderr)
        app.logger.error(f"run_query | Failed to retrieve SLURM REST auth token")
        return stream_json_response(
            {"error": "Failed to retrieve SLURM REST auth token"}, 400
        )
    query_result, query_url = query_functor(
        slurm_rest_auth_token,
        endpoint_url,
        endpoint_key,
        endpoint_method,
        **(kwargs or {}),
    )
    if not query_result:
        app.logger.error(f"run_query | Failed to retrieve query result")
        return stream_json_response({"error": "Failed to retrieve SLURM data"}, 400)
    return stream_json_response(
        {
            "slurm_query_username": username,
            "slurm_query_url": query_url,
            "response": query_result,
        },
        200,
    )


def get_slurm_rest_jwt_private_key_via_env() -> str:
    app = get_slurm_proxy_app()
    slurm_private_key = os.environ.get("SLURM_JWT_HS256_KEY_BASE64")
    if not slurm_private_key:
        # print(" * Error: SLURM_JWT_HS256_KEY_BASE64 environment variable not set", file=sys.stderr)
        app.logger.error(
            f"get_slurm_rest_jwt_private_key_via_env | SLURM_JWT_HS256_KEY_BASE64 environment variable not set"
        )
        return None
    return slurm_private_key.strip()


def get_slurm_rest_jwt_token_for_username(username: str) -> str:
    # if not username or username == SLURM_REST_GENERIC_USERNAME:
    #     return None
    app = get_slurm_proxy_app()
    if not username:
        app.logger.warning(
            f"get_slurm_rest_jwt_token_for_username | Username not provided"
        )
        username = SLURM_REST_GENERIC_USERNAME
    priv_key = get_slurm_rest_jwt_private_key_via_env()
    if not priv_key:
        # print(" * Error: Failed to retrieve SLURM JWT private key", file=sys.stderr)
        app.logger.error(
            f"get_slurm_rest_jwt_token_for_username | Failed to retrieve SLURM JWT private key"
        )
        return None
    signing_key = jwk_from_dict(
        {
            "kty": "oct",
            "k": priv_key,
        }
    )
    message = {
        "exp": int(time.time() + SLURM_REST_JWT_EXPIRATION_TIME),
        "iat": int(time.time()),
        "sun": username,
    }
    a = JWT()
    compact_jws = a.encode(message, signing_key, alg="HS256")
    app.logger.debug(
        f"get_slurm_rest_jwt_token_for_username | SLURM_JWT={compact_jws} | username={username}"
    )
    return compact_jws


def get_slurm_rest_jwt_token_cmd(username: str) -> str:
    return (
        f"eval $(ssh login-pvm02 scontrol token username={username} lifespan={SLURM_REST_JWT_EXPIRATION_TIME}) && echo -n $SLURM_JWT"
        if username
        else f"eval $(ssh login-pvm02 scontrol token lifespan={SLURM_REST_JWT_EXPIRATION_TIME}) && echo -n $SLURM_JWT"
    )


def get_slurm_rest_jwt_token_via_cli(username: str) -> str:
    app = get_slurm_proxy_app()
    cmd = get_slurm_rest_jwt_token_cmd(username)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        app.logger.error(
            f"get_slurm_rest_jwt_token_via_cli | Command '{cmd}' failed with error: {result.stderr}"
        )
        raise Exception(f"Command '{cmd}' failed with error: {result.stderr}")
    return result.stdout.strip()


def get_slurm_rest_jwt_token_via_ssh(username: str) -> str:
    app = get_slurm_proxy_app()
    cmd = get_slurm_rest_jwt_token_cmd(username)
    app.logger.debug(f"get_slurm_rest_jwt_token_via_ssh | Executing command '{cmd}'")
    (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
    try:
        slurm_rest_token = stdout.read().decode("utf-8")
        return slurm_rest_token.strip()
    except ValueError as err:
        app.logger.error(
            f"get_slurm_rest_jwt_token_via_ssh | Username: {username} | Error: {err}"
        )
        return None


def get_slurm_rest_query(
    endpoint_url: str, endpoint_key: str, **kwargs: Unpack[QueryParams]
) -> str:
    def args_from_values(kwargs: dict) -> str:
        args = ""
        for key, value in kwargs.items():
            if key in QueryParams.__annotations__.keys():
                args += f"{value}/"
        return args.rstrip("&")

    def args_from_keys(kwargs: dict) -> str:
        args = "?"
        if len(kwargs.keys()) > 0:
            for key, value in kwargs.items():
                if key in QueryParams.__annotations__.keys():
                    args += f"{key}={value}&"
        return args

    kwargs = kwargs["kwargs"] if "kwargs" in kwargs else kwargs
    if endpoint_key == "job":
        args = args_from_values(kwargs)
    elif endpoint_key == "jobs":
        args = args_from_keys(kwargs)
    query_url = f"{endpoint_url}/{endpoint_key}/"
    if len(args) > 0:
        query_url = f"{endpoint_url}/{endpoint_key}/{args}"
    return query_url


def query_slurm_endpoint_via_ssh(
    slurm_rest_auth_token: str,
    endpoint_url: str,
    endpoint_key: str,
    endpoint_method: str,
    **kwargs: Unpack[QueryParams],
) -> str:
    app = get_slurm_proxy_app()
    query_url = get_slurm_rest_query(endpoint_url, endpoint_key, **kwargs)
    cmd = f"curl -vs -k -vvvv -H X-SLURM-USER-TOKEN:{slurm_rest_auth_token} -X {endpoint_method} '{query_url}'"
    (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
    try:
        slurm_rest_diag = stdout.read().decode("utf-8")
        return json.loads(slurm_rest_diag), query_url
    except ValueError as err:
        app.logger.error(f"query_slurm_endpoint_via_ssh | Error: {err}")
        return None


def query_slurm_get_endpoint_via_requests(
    slurm_rest_auth_token: str,
    endpoint_url: str,
    endpoint_key: str,
    endpoint_method: str,
    **kwargs: Unpack[QueryParams],
) -> str:
    app = get_slurm_proxy_app()
    query_url = get_slurm_rest_query(endpoint_url, endpoint_key, **kwargs)
    headers = {
        "X-SLURM-USER-TOKEN": slurm_rest_auth_token,
    }
    response = requests.request(endpoint_method, query_url, headers=headers)
    if response.status_code != 200:
        app.logger.error(
            f"query_slurm_get_endpoint_via_requests | Error: {response.status_code} - {response.text}"
        )
        return None
    return response.json(), query_url


def query_slurm_post_endpoint_via_requests(
    slurm_rest_auth_token: str,
    endpoint_url: str,
    endpoint_key: str,
    endpoint_method: str,
    **kwargs: Unpack[QueryParams],
) -> str:
    app = get_slurm_proxy_app()
    query_url = f"{endpoint_url}/{endpoint_key}/"
    headers = {
        "X-SLURM-USER-TOKEN": slurm_rest_auth_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    job = kwargs["kwargs"]
    if "job" in job:
        job = job["job"]
    response = requests.request(endpoint_method, query_url, headers=headers, json=job)
    if response.status_code != 200:
        json_content = response.json()
        errors = json_content.get("errors", None)
        if errors:
            error = errors[0]
            error_message = f"Slurm error {error['error_number']}: {error['description']} - {error['error']}"
            username = job.get("username", SLURM_REST_GENERIC_USERNAME)
            app.logger.error(
                f"query_slurm_post_endpoint_via_requests | Username: {username} | Error: {response.status_code} - {error_message}"
            )
        else:
            app.logger.error(
                f"query_slurm_post_endpoint_via_requests | Error: {response.status_code} - {json_content}"
            )
        return None
    return response.json(), query_url