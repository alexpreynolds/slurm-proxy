# -*- coding: utf-8 -*-

import sys
import pymongo
import paramiko
from flask import (
    Blueprint,
    request,
    Response,
    Flask,
)
from app.helpers import (
    stream_json_response,
)
from app.constants import (
    APP_NAME,
    SLURM_STATE,
    SLURM_STATE_UNKNOWN,
    SLURM_STATE_END_STATES,
    SLURM_TEST_JOB_ID,
    SLURM_TEST_JOB_STATUS,
    SLURM_REST_GENERIC_USERNAME,
    TASK_METADATA,
    SlurmCommunicationMethods,
)
from app.task_notification import NotificationMethod
from app.task_ssh_client import ssh_client_connection_singleton
from app.task_mongodb_client import mongodb_connection_singleton


ssh_connection = ssh_client_connection_singleton
mongodb_connection = mongodb_connection_singleton
app = Flask(APP_NAME)

SLURM_STATES_ALLOWED = SLURM_STATE.keys()
SLURM_COMMUNICATION_METHOD = SlurmCommunicationMethods.REST

task_monitoring = Blueprint("task_monitoring", __name__)

"""
This module defines a Flask blueprint for task monitoring, which maintains job state via
a MongoDB database and communicates with a SLURM scheduler to generate updated job status.
"""


@task_monitoring.route("/", methods=["POST"], strict_slashes=False)
def post() -> Response:
    """
    POST request to add a new job to the monitor database.
    The request body should contain a JSON object with the job information.
    """
    request_info = request.get_json(force=True)
    job = request_info.get("job")
    if not job:
        app.logger.error("No job provided to be monitored")
        return {"error": "No job provided to be monitored"}, 400
    response = (
        stream_json_response(job, 200)
        if monitor_new_slurm_job(job)
        else stream_json_response({"error": "Failed to monitor job"}, 400)
    )
    return response


@task_monitoring.route(
    "/slurm_job_id/<slurm_job_id>", methods=["GET"], strict_slashes=False
)
def get_job_metadata_by_slurm_job_id(slurm_job_id: str) -> Response:
    """
    GET request to retrieve job metadata from the monitor database using the SLURM job ID.
    The job ID is passed as a URL parameter.

    Args:
        slurm_job_id (str): The SLURM job ID.

    Returns:
        Response: A Flask Response object containing the job metadata in JSON format.
    """
    slurm_username = request.args.get("username")
    if not slurm_username:
        slurm_username = SLURM_REST_GENERIC_USERNAME
    slurm_job_id = int(slurm_job_id)
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id,
        slurm_username,
    )
    # if not slurm_job_status_metadata:
    # job not found in SLURM scheduler for specified ID and username
    # return {"error": "Job information not found"}, 404
    monitor_db_job_metadata = get_job_metadata_from_monitor_db_by_slurm_job_id(
        slurm_job_id
    )
    if not slurm_job_status_metadata and not monitor_db_job_metadata:
        app.logger.error(
            f"get_job_metadata_by_slurm_job_id | Job {slurm_job_id} not found in SLURM scheduler or monitor database"
        )
        return {"error": "Job and monitor information not found"}, 404
    slurm_job_state = (
        slurm_job_status_metadata["state"]
        if slurm_job_status_metadata
        else SLURM_STATE_UNKNOWN
    )
    slurm_username_from_slurmdb = (
        slurm_job_status_metadata["user"]
        if slurm_job_status_metadata
        else slurm_username
    )
    response_data = {
        "slurm": {
            "job_username": slurm_username_from_slurmdb,
            "job_id": slurm_job_id,
            "job_state": slurm_job_state,
        },
        "monitor": monitor_db_job_metadata,
    }
    response = stream_json_response(response_data, 200)
    return response


@task_monitoring.route("/task_uuid/<task_uuid>", methods=["GET"], strict_slashes=False)
def get_job_metadata_by_task_uuid(task_uuid: str) -> Response:
    """
    GET request to retrieve job metadata from the monitor database using the
    task UUID. The UUID is passed as a URL parameter.

    Args:
        task_uuid (str): The task UUID of the job.

    Returns:
        Response: A Flask Response object containing the job metadata in JSON format.
    """
    if not task_uuid:
        app.logger.error("get_job_metadata_by_task_uuid | No task UUID provided")
        return {"error": "No task UUID provided"}, 400
    monitor_db_job_metadata = get_job_metadata_from_monitor_db_by_task_uuid(task_uuid)
    if not monitor_db_job_metadata:
        app.logger.error(
            f"get_job_metadata_by_task_uuid | Job {task_uuid} not found in monitor database"
        )
        return {"error": "Job monitor information not found"}, 404
    slurm_job_id = monitor_db_job_metadata["slurm_job_id"]
    slurm_username = monitor_db_job_metadata["task"].get(
        "username", SLURM_REST_GENERIC_USERNAME
    )
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id,
        slurm_username,
    )
    if not slurm_job_status_metadata:
        app.logger.error(
            f"get_job_metadata_by_task_uuid | Job {task_uuid} not found with Slurm scheduler metadata"
        )
        return {"error": "Job Slurm metadata not found"}, 404
    slurm_job_state = (
        slurm_job_status_metadata["state"]
        if slurm_job_status_metadata
        else SLURM_STATE_UNKNOWN
    )
    slurm_username_from_slurmdb = (
        slurm_job_status_metadata["user"]
        if slurm_job_status_metadata
        else slurm_username
    )
    response_data = {
        "slurm": {
            "job_username": slurm_username_from_slurmdb,
            "job_id": slurm_job_id,
            "job_state": slurm_job_state,
        },
        "monitor": monitor_db_job_metadata,
    }
    response = stream_json_response(response_data, 200)
    return response


@task_monitoring.route(
    "/slurm_job_state/<slurm_job_state>", methods=["GET"], strict_slashes=False
)
def get_by_slurm_job_state(slurm_job_state: str) -> Response:
    """
    GET request to retrieve job metadata from the monitor database using the SLURM job state.
    The job state is passed as a URL parameter.

    Args:
        slurm_job_state (str): The SLURM job state.

    Returns:
        Response: A Flask Response object containing the job metadata in JSON format.
    """
    if slurm_job_state not in SLURM_STATES_ALLOWED:
        app.logger.error(
            f"get_by_slurm_job_state | Invalid SLURM job state: {slurm_job_state}"
        )
        return {"error": "Invalid state key"}, 400
    # also query the database for jobs with the given state, for comparison
    jobs = get_slurm_jobs_metadata_by_slurm_job_state(slurm_job_state)
    response = stream_json_response(jobs, 200)
    return response


@task_monitoring.route(
    "/slurm_job_id/<slurm_job_id>", methods=["DELETE"], strict_slashes=False
)
def delete_by_slurm_job_id(slurm_job_id: int) -> Response:
    """
    DELETE request to remove a job from the monitor database using the SLURM job ID.
    The job ID is passed as a URL parameter.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        Response: A Flask Response object indicating the success or failure of the operation.
    """
    response = None
    # check if job was already in the monitor database
    slurm_job_id = int(slurm_job_id)
    job_metadata = get_job_metadata_from_monitor_db_by_slurm_job_id(slurm_job_id)
    if job_metadata:
        try:
            # delete the job from SLURM queue
            cmd = " ".join(
                [
                    str(x)
                    for x in [
                        "scancel",
                        str(slurm_job_id),
                    ]
                ]
            )
            (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                app.logger.error(
                    f'delete_by_slurm_job_id | Failed to delete job from SLURM: {stderr.read().decode("utf-8")}'
                )
                response = stream_json_response(
                    {"error": "Job could not be deleted from SLURM scheduler"}, 400
                )
                return response
        except paramiko.SSHException as err:
            app.logger.error(
                f"delete_by_slurm_job_id | Failed to delete job from SLURM via SSH client: {err}"
            )
            response = stream_json_response(
                {"error": f"Failed to delete job from SLURM: {err}"}, 500
            )
            return response
        except Exception as err:
            app.logger.error(f"delete_by_slurm_job_id | Unexpected error: {err}")
            response = stream_json_response({"error": f"Unexpected error: {err}"}, 500)
            return response
    else:
        # job not found in the database
        app.logger.error(
            f"delete_by_slurm_job_id | Job {slurm_job_id} not found in monitor database"
        )
        response = stream_json_response(
            {"error": f"Job not found in monitor database"}, 404
        )
        return response
    # delete the job from the database
    deleted_job = remove_and_return_job_from_monitor_db_by_slurm_job_id(slurm_job_id)
    # return the job object
    response = stream_json_response(deleted_job, 200)
    return response


"""
CRUD operations for the job monitoring database.
"""


def monitor_new_slurm_job(job: dict) -> bool:
    """
    Monitor a new SLURM job by adding it to the database.
    The job dictionary should contain the SLURM job ID and task information.
    The SLURM job state is retrieved from the SLURM scheduler.

    Args:
        job (dict): A dictionary containing the SLURM job ID and task information.
    Returns:
        bool: True if the job was successfully monitored, False otherwise.
    """
    try:
        slurm_job_id = int(job["slurm_job_id"])
    except TypeError as err:
        app.logger.error(f"monitor_new_slurm_job | {job['slurm_job_id']} {err}")
        return False
    slurm_username = job["task"]["username"]
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id,
        slurm_username,
    )
    if not slurm_job_status_metadata:
        return False
    slurm_job_state = (
        slurm_job_status_metadata["state"]
        if slurm_job_status_metadata
        or slurm_job_status_metadata["state"] in SLURM_STATE_END_STATES
        else SLURM_STATE_UNKNOWN
    )
    slurm_job_task_metadata = job["task"]
    result = add_job_to_monitor_db(
        slurm_job_id, slurm_job_state, slurm_job_task_metadata, slurm_username
    )
    # if the job is already completed, we send a notification msg
    if slurm_job_state in SLURM_STATE_END_STATES:
        process_job_state_change(slurm_job_id, SLURM_STATE_UNKNOWN, slurm_job_state)
    return result


def add_job_to_monitor_db(
    slurm_job_id: int,
    slurm_job_state: str,
    slurm_job_task_metadata: dict,
    slurm_username: str,
) -> bool:
    """
    Add a new job to the monitor database, only if its SLURM job ID and task
    UUID are not already present in the database.

    The job dictionary should contain the SLURM job ID and task information.
    The SLURM job status is retrieved from the SLURM scheduler.

    Args:
        slurm_job_id (int): The SLURM job ID.
        slurm_job_state (str): The SLURM job state.
        slurm_job_task_metadata (dict): The task metadata for the job.
        slurm_username (str): The SLURM job username.

    Returns:
        bool: True if the job was successfully added to the monitor database, False otherwise.
    """
    if slurm_job_state == SLURM_STATE_UNKNOWN:
        current_slurm_job_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
            slurm_job_id,
            slurm_username,
        )
        if current_slurm_job_metadata:
            slurm_job_state = current_slurm_job_metadata["state"]
    job = {
        "slurm_job_id": slurm_job_id,
        "slurm_job_state": slurm_job_state,
        "task": slurm_job_task_metadata,
    }
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        if not jobs_coll.find_one(
            {"slurm_job_id": slurm_job_id}
        ) and not jobs_coll.find_one({"task.uuid": slurm_job_task_metadata["uuid"]}):
            jobs_coll.insert_one(job)
        return True
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"add_job_to_monitor_db | Error adding job to monitor database: {err}"
        )
        return False


def get_job_metadata_from_monitor_db_by_slurm_job_id(slurm_job_id: int) -> dict:
    """
    Get job metadata from the monitor database using the SLURM job ID.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.find_one({"slurm_job_id": slurm_job_id})
        if result:
            job_metadata = {
                "slurm_job_id": result["slurm_job_id"],
                "slurm_job_state": result["slurm_job_state"],
                "task": result["task"],
            }
            return job_metadata
        else:
            return None
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"get_job_metadata_from_monitor_db_by_slurm_job_id | Error retrieving job information from monitor database: {err}"
        )
        return None


def get_job_metadata_from_monitor_db_by_task_uuid(task_uuid: int) -> dict:
    """
    Get job metadata from the monitor database using the task UUID.

    Args:
        task_uuid (int): The SLURM job ID.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.find_one({"task.uuid": task_uuid})
        if result:
            job_metadata = {
                "slurm_job_id": result["slurm_job_id"],
                "slurm_job_state": result["slurm_job_state"],
                "task": result["task"],
            }
            return job_metadata
        else:
            return None
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"get_job_metadata_from_monitor_db_by_task_uuid | Error retrieving job information from monitor database: {err}"
        )
        return None


def update_job_state_in_monitor_db(slurm_job_id: int, new_slurm_job_state: str) -> bool:
    """
    Update the job state key in the monitor database.
    The job dictionary should contain the SLURM job ID and task information.
    The SLURM job state is retrieved from the SLURM scheduler.

    Args:
        slurm_job_id (int): The SLURM job ID.
        new_slurm_job_state (str): The new SLURM job state.

    Returns:
        bool: True if the job state was successfully updated, False otherwise.
    """
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.update_one(
            {"slurm_job_id": slurm_job_id},
            {"$set": {"slurm_job_state": new_slurm_job_state}},
        )
        if result.modified_count == 0:
            return False
        return True
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"update_job_state_in_monitor_db | Error updating job state in monitor database: {err}"
        )
        return False


def remove_job_from_monitor_db_by_slurm_job_id(slurm_job_id: int) -> bool:
    """
    Remove a job from the monitor database using the SLURM job ID.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        bool: True if the job was successfully removed, False otherwise.
    """
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.delete_one({"slurm_job_id": slurm_job_id})
        if result.deleted_count == 0:
            return False
        return True
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"remove_job_from_monitor_db_by_slurm_job_id | Error removing job from monitor database: {err}"
        )
        return False


def remove_and_return_job_from_monitor_db_by_slurm_job_id(slurm_job_id: int) -> dict:
    """
    Remove a job from the monitor database and return the job metadata.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.find_one_and_delete({"slurm_job_id": slurm_job_id})
        return result
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"remove_and_return_job_from_monitor_db_by_slurm_job_id | Error removing job from monitor database: {err}"
        )
        return None


def get_current_slurm_job_metadata_by_slurm_job_id(
    slurm_job_id: int, slurm_username: str
) -> dict:
    if SLURM_COMMUNICATION_METHOD == SlurmCommunicationMethods.SSH:
        return get_current_slurm_job_metadata_by_slurm_job_id_via_ssh(
            slurm_job_id, slurm_username
        )
    elif SLURM_COMMUNICATION_METHOD == SlurmCommunicationMethods.REST:
        return get_current_slurm_job_metadata_by_slurm_job_id_via_rest(
            slurm_job_id, slurm_username
        )


def get_current_slurm_job_metadata_by_slurm_job_id_via_rest(
    slurm_job_id: int, slurm_username: str
) -> dict:
    if not slurm_job_id:
        return None
    if not slurm_username:
        slurm_username = SLURM_REST_GENERIC_USERNAME
    # test case
    if slurm_job_id == SLURM_TEST_JOB_ID:
        return SLURM_TEST_JOB_STATUS
    # REST API call to get the job status
    from app.task_slurm_rest import get_job_info_for_job_id_via_params

    (
        job_status_response,
        job_status_response_code,
        query_url,
    ) = get_job_info_for_job_id_via_params(slurm_job_id, slurm_username)
    if not job_status_response or job_status_response_code != 200:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_rest | No job status information found for job ID {slurm_job_id} and user {slurm_username} | {job_status_response_code} | {query_url}"
        )
        return None
    job_status_jobs = job_status_response.get("jobs", None)
    if not job_status_jobs or len(job_status_jobs) == 0:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_rest | No job status information found for job ID {slurm_job_id} and user {slurm_username}"
        )
        return None
    job_status_job_instance = job_status_jobs[0]
    # ref. https://slurm.schedmd.com/rest_api.html#v0.0.42_openapi_slurmdbd_jobs_resp
    try:
        result = {"state": SLURM_STATE_UNKNOWN, "user": slurm_username}
        if job_status_job_instance["state"]["current"][0] not in SLURM_STATES_ALLOWED:
            result["state"] = SLURM_STATE_UNKNOWN
        else:
            result["state"] = job_status_job_instance["state"]["current"][0]
        if job_status_job_instance["user"] != slurm_username:
            result["user"] = job_status_job_instance["user"]
            app.logger.warning(
                f"get_current_slurm_job_metadata_by_slurm_job_id_via_rest | Job {slurm_job_id} is not owned by user {slurm_username}"
            )
            # raise NameError(
            #     f"Job {slurm_job_id} is not owned by user {slurm_username}"
            # )
        return result
    except TypeError as err:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_rest | Error: {err} | {job_status_job_instance}"
        )
        return None
    except NameError as err:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_rest | Error: {err} | {job_status_job_instance}"
        )
        return None


def get_current_slurm_job_metadata_by_slurm_job_id_via_ssh(
    slurm_job_id: int, slurm_username: str
) -> dict:
    """
    Get the current SLURM job metadata by job ID via SSH.

    Args:
        slurm_job_id (int): The SLURM job ID.
        slurm_username (str): The SLURM job username.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    if not slurm_job_id:
        return None
    # test case
    if slurm_job_id == SLURM_TEST_JOB_ID:
        return SLURM_TEST_JOB_STATUS
    # SSH command to get the job status
    cmd = " ".join(
        [
            str(x)
            for x in [
                "sacct",
                "-j",
                slurm_job_id,
                "--format=JobID,Jobname%-128,state,User,partition,time,start,end,elapsed",
                "--noheader",
                "--parsable2",
            ]
        ]
    )
    try:
        (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
        job_status_str = stdout.read().decode("utf-8").strip()
        if not job_status_str:
            return None
        job_status_components = job_status_str.split("\n")[0].split("|")
        job_status_keys = [
            "job_id",
            "job_name",
            "state",
            "user",
            "partition",
            "time",
            "start",
            "end",
            "elapsed",
        ]
        job_status = dict(zip(job_status_keys, job_status_components))
        if job_status["state"] not in SLURM_STATES_ALLOWED:
            job_status["state"] = SLURM_STATE_UNKNOWN
        if job_status["user"] != slurm_username:
            app.logger.error(
                f"get_current_slurm_job_metadata_by_slurm_job_id_via_ssh | Job {slurm_job_id} is not owned by user {slurm_username}"
            )
            raise NameError(f"Job {slurm_job_id} is not owned by user {slurm_username}")
        return job_status
    except TypeError as err:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_ssh | Error: {err}"
        )
        return None
    except NameError as err:
        app.logger.error(
            f"get_current_slurm_job_metadata_by_slurm_job_id_via_ssh | Error: {err}"
        )
        return None


def get_slurm_jobs_metadata_by_slurm_job_state(slurm_job_state: str) -> dict:
    """
    Get SLURM job metadata by job state.
    The job state is passed as a URL parameter.

    Args:
        slurm_job_state (str): The SLURM job state.

    Returns:
        dict: A dictionary containing the job metadata for the given state.
    """
    if not slurm_job_state:
        return None
    cmd = " ".join(
        [
            str(x)
            for x in [
                "sacct",
                "--state",
                slurm_job_state,
                "--format=JobID,Jobname%-128,state,User,partition,time,start,end,elapsed",
                "--noheader",
                "--parsable2",
            ]
        ]
    )
    (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
    job_status_strs = stdout.read().decode("utf-8").strip()
    if not job_status_strs:
        return None
    jobs_status = {"jobs": []}
    for job_status_str in job_status_strs.split("\n"):
        job_status_components = job_status_str.split("|")
        job_status_keys = [
            "job_id",
            "job_name",
            "state",
            "user",
            "partition",
            "time",
            "start",
            "end",
            "elapsed",
        ]
        job_status_instance = dict(zip(job_status_keys, job_status_components))
        if job_status_instance["state"] not in SLURM_STATES_ALLOWED:
            job_status_instance["state"] = SLURM_STATE_UNKNOWN
        jobs_status["jobs"].append(job_status_instance)
    return jobs_status


def poll_slurm_jobs() -> None:
    """
    Poll the SLURM scheduler periodically for job status updates. Timer value is set
    in constants.MONITOR_POLLING_INTERVAL.

    This function checks the status of all jobs in the monitor database and updates
    the job status if there are any changes. If a job is marked as finished, a state
    change event is triggered.
    """
    # app.logger.debug("poll_slurm_jobs | Polling SLURM jobs...")
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        jobs = jobs_coll.find()
        for job in jobs:
            slurm_job_id = int(job["slurm_job_id"])
            monitor_db_job_state = job["slurm_job_state"]
            slurm_username = job["task"].get("username", SLURM_REST_GENERIC_USERNAME)
            # app.logger.debug(f"poll_slurm_jobs | Testing {slurm_job_id} | {monitor_db_job_state}")
            if monitor_db_job_state in SLURM_STATE_END_STATES:
                # job is already completed, therefore no need to check its state
                continue
            slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
                slurm_job_id,
                slurm_username,
            )
            if not slurm_job_status_metadata:
                # job not found in SLURM scheduler for specified ID and username
                continue
            current_slurm_job_state = slurm_job_status_metadata["state"]
            if monitor_db_job_state != current_slurm_job_state:
                new_slurm_job_state = (
                    current_slurm_job_state
                    if current_slurm_job_state in SLURM_STATES_ALLOWED
                    else SLURM_STATE_UNKNOWN
                )
                if new_slurm_job_state in SLURM_STATE_END_STATES:
                    process_job_state_change(
                        slurm_job_id, monitor_db_job_state, new_slurm_job_state
                    )
                update_job_state_in_monitor_db(slurm_job_id, new_slurm_job_state)
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"poll_slurm_jobs | Error polling SLURM jobs in monitor db: {err}"
        )


def process_job_state_change(
    slurm_job_id: int, old_slurm_job_state: str, new_slurm_job_state: str
) -> None:
    """
    Handle the job state change here. This would be typically called when the
    job state becomes one of e.g., COMPLETED, FAILED, or CANCELLED.

    A state change event may be handled by sending a notification message to a
    RabbitMQ queue, for instance, and/or an email, and/or a Slack message to a
    particular channel, as defined in the TASK_METADATA object. Other methods
    may be exposed in task_notification.py.

    Args:
        slurm_job_id (int): The SLURM job ID.
        old_slurm_job_state (str): The old SLURM job state.
        new_slurm_job_state (str): The new SLURM job state.
    """
    # app.logger.debug(
    #     f"process_job_state_change | Processing job state change: {slurm_job_id}: {old_slurm_job_state} -> {new_slurm_job_state}"
    # )
    if new_slurm_job_state in SLURM_STATE_END_STATES:
        # app.logger.debug(f'process_job_state_change | Sending notification message for job {slurm_job_id}')
        try:
            jobs_coll = mongodb_connection.get_monitor_jobs_collection()
            result = jobs_coll.find_one({"slurm_job_id": slurm_job_id})
            if result:
                task = result["task"]
                task_name = task["name"]
                task_md = TASK_METADATA[task_name]
                task_notification = task_md["notification"]
                # get the notification methods
                task_notification_methods = task_notification["methods"]
                task_notification_params = task_notification["params"]
                msg = f"Sending test notification for: {slurm_job_id}!"
                for method in task_notification_methods:
                    # app.logger.debug(f'process_job_state_change | Sending notification message via method {method}')
                    if (
                        method == NotificationMethod.EMAIL
                        or method == NotificationMethod.GMAIL
                    ):
                        sender = task_notification_params["email"]["sender"]
                        recipient = task_notification_params["email"]["recipient"]
                        subject = task_notification_params["email"]["subject"]
                        body = msg
                        try:
                            method.value(sender, recipient, subject, body)
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not email or Gmail: {err}"
                            )
                    elif method == NotificationMethod.SLACK:
                        try:
                            method.value(
                                msg, task_notification_params["slack"]["channel"]
                            )
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not Slack message: {err}"
                            )
                    elif method == NotificationMethod.RABBITMQ:
                        try:
                            method.value(
                                task_notification_params["rabbitmq"]["queue"],
                                task_notification_params["rabbitmq"]["exchange"],
                                task_notification_params["rabbitmq"]["routing_key"],
                                msg,
                            )
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not RabbitMQ message: {err}"
                            )
                    elif method == NotificationMethod.TEST:
                        method.value(msg)
        except pymongo.errors.PyMongoError as err:
            app.logger.error(
                f"process_job_state_change | Error removing job from monitor database: {err}"
            )
            return None
