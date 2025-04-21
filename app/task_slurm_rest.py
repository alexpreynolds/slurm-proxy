import json
from flask import (
    Blueprint,
    Response,
)
from app.helpers import (
    ssh_client,
    ssh_client_exec,
    stream_json_response,
)

"""
https://slurm.schedmd.com/SLUG23/REST-API-SLUG23.pdf
"""

SSH_CLIENT = ssh_client()

task_slurm_rest = Blueprint("task_slurm_rest", __name__)

@task_slurm_rest.route("/diag/", methods=["GET"])
def get_diag() -> Response:
    """
    GET request handler for SLURM diag information.
    This function retrieves the SLURM REST token from the request headers
    and returns it in the response, along with a diagnostic JSON object.
    """
    slurm_rest_auth_token = get_slurm_rest_token_via_ssh()
    if not slurm_rest_auth_token:
        return stream_json_response({"error": "Failed to retrieve SLURM REST auth token"}, 400)
    slurm_diag = get_slurm_diag_via_ssh(slurm_rest_auth_token)
    if not slurm_diag:
        return stream_json_response({"error": "Failed to retrieve SLURM diag"}, 400)
    return stream_json_response({"SLURM_JWT": slurm_rest_auth_token, "diag": slurm_diag}, 200)


def get_slurm_rest_token_via_ssh() -> str:
    cmd = "eval $(ssh login-pvm02 scontrol token) && echo -n $SLURM_JWT"
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_token = stdout.read().decode("utf-8")
        return slurm_rest_token.strip()
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None


def get_slurm_diag_via_ssh(slurm_rest_auth_token: str) -> str:
    cmd = f"curl -vs -k -vvvv -H X-SLURM-USER-TOKEN:{slurm_rest_auth_token} -X GET 'http://login-pvm02:6820/slurm/v0.0.42/diag'"
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        slurm_rest_diag = stdout.read().decode("utf-8")
        return json.loads(slurm_rest_diag)
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return None