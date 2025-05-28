# -*- coding: utf-8 -*-

import copy
import pymongo
import paramiko
from flask import (
    Blueprint,
    request,
    Response,
)
from app import helpers
from app.constants import (
    SLURM_STATE,
    SLURM_STATE_UNKNOWN,
    SLURM_STATE_END_STATES,
    SLURM_TEST_JOB_ID,
    SLURM_TEST_JOB_STATUS,
    SLURM_REST_GENERIC_USERNAME,
    TASK_METADATA,
    SlurmCommunicationMethods,
    MONGODB_MONITOR_JOB_CREATED_AT_MAX_AGE,
)
from app.task_notification import (
    NotificationMethod,
    NotificationCallbackFactory,
)
from app.task_ssh_client import ssh_client_connection_singleton
from app.task_mongodb_client import mongodb_connection_singleton
from app.task_metadata_monitor_job_summary import MonitorJobSummary
from app.task_metadata_slurm_job_summary import SlurmJobSummary
from app.task_metadata_job_summary import JobSummary

ssh_connection = ssh_client_connection_singleton
mongodb_connection = mongodb_connection_singleton

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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    request_info = request.get_json(force=True)
    request_monitor_job = request_info.get("monitor", None)
    if not request_monitor_job:
        app.logger.error("No job provided to be monitored")
        return {"error": "No job provided to be monitored"}, 400
    job = MonitorJobSummary(
        slurm_username=request_monitor_job.get("task", {}).get("username", SLURM_REST_GENERIC_USERNAME),
        slurm_job_id=request_monitor_job.get("slurm_job_id"),
        slurm_job_state=request_monitor_job.get("slurm_job_state", SLURM_STATE_UNKNOWN),
        task=request_monitor_job.get("task", {}),
    )
    response = (
        helpers.stream_json_response(job, 200)
        if monitor_new_slurm_job(job)
        else helpers.stream_json_response({"error": "Failed to monitor job"}, 400)
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    slurm_username = request.args.get("username")
    if not slurm_username:
        slurm_username = SLURM_REST_GENERIC_USERNAME
    slurm_job_id = int(slurm_job_id)
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id,
        slurm_username,
    )
    monitor_db_job_metadata = get_job_metadata_from_monitor_db(slurm_job_id)
    if not slurm_job_status_metadata or not monitor_db_job_metadata:
        app.logger.error(
            f"get_job_metadata_by_slurm_job_id | Job {slurm_job_id} not found in SLURM scheduler or monitor database"
        )
        return {"error": "Job scheduler or monitor information not found"}, 404
    # package up a job summary object
    job_summary = JobSummary(slurm_summary=slurm_job_status_metadata, monitor_summary=monitor_db_job_metadata)
    response = helpers.stream_json_response(job_summary, 200)
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
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
    response_data = JobSummary(slurm_summary=slurm_job_status_metadata, monitor_summary=monitor_db_job_metadata)
    response = helpers.stream_json_response(response_data, 200)
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    if slurm_job_state not in SLURM_STATES_ALLOWED:
        app.logger.error(
            f"get_by_slurm_job_state | Invalid SLURM job state: {slurm_job_state}"
        )
        return {"error": "Invalid state key"}, 400
    # also query the database for jobs with the given state, for comparison
    jobs = get_slurm_jobs_metadata_by_slurm_job_state_via_ssh(slurm_job_state)
    response = helpers.stream_json_response(jobs, 200)
    return response


@task_monitoring.route(
    "/slurm_job_id/<slurm_job_id>", methods=["DELETE"], strict_slashes=False
)
def delete_by_slurm_job_id_via_ssh(slurm_job_id: int) -> Response:
    """
    DELETE request to remove a job from the monitor database using the SLURM job ID.
    The job ID is passed as a URL parameter.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        Response: A Flask Response object indicating the success or failure of the operation.
    """
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    response = None
    # check if job was already in the monitor database
    slurm_job_id = int(slurm_job_id)
    job_metadata = get_job_metadata_from_monitor_db(slurm_job_id)
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
                response = helpers.stream_json_response(
                    {"error": "Job could not be deleted from SLURM scheduler"}, 400
                )
                return response
        except paramiko.SSHException as err:
            app.logger.error(
                f"delete_by_slurm_job_id | Failed to delete job from SLURM via SSH client: {err}"
            )
            response = helpers.stream_json_response(
                {"error": f"Failed to delete job from SLURM: {err}"}, 500
            )
            return response
        except Exception as err:
            app.logger.error(f"delete_by_slurm_job_id | Unexpected error: {err}")
            response = helpers.stream_json_response({"error": f"Unexpected error: {err}"}, 500)
            return response
    else:
        # job not found in the database
        app.logger.error(
            f"delete_by_slurm_job_id | Job {slurm_job_id} not found in monitor database"
        )
        response = helpers.stream_json_response(
            {"error": f"Job not found in monitor database"}, 404
        )
        return response
    # delete the job from the database
    deleted_job = remove_and_return_job_from_monitor_db_by_slurm_job_id(slurm_job_id)
    # return the job object
    response = helpers.stream_json_response(deleted_job, 200)
    return response


"""
CRUD operations for the job monitoring database.
"""


def monitor_new_slurm_job(job: MonitorJobSummary) -> bool:
    """
    Monitor a new SLURM job by adding it to the database.
    The job dictionary should contain the SLURM job ID and task information.
    The SLURM job state is retrieved from the SLURM scheduler.

    Args:
        job (dict): A dictionary containing the SLURM job ID and task information.
    Returns:
        bool: True if the job was successfully monitored, False otherwise.
    """
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    try:
        slurm_job_id = job.get_slurm_job_id()
    except TypeError as err:
        app.logger.error(f"monitor_new_slurm_job | {job['slurm_job_id']} {err}")
        return False
    slurm_username = job.get_slurm_username()
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id,
        slurm_username,
    )
    if not slurm_job_status_metadata:
        return False
    slurm_job_state = (
        slurm_job_status_metadata.get_job_state()
        if slurm_job_status_metadata
        or slurm_job_status_metadata.get_job_state() in SLURM_STATE_END_STATES
        else SLURM_STATE_UNKNOWN
    )
    slurm_job_task_metadata = job.get_task()
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    if slurm_job_state == SLURM_STATE_UNKNOWN:
        current_slurm_job_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
            slurm_job_id,
            slurm_username,
        )
        if current_slurm_job_metadata:
            slurm_job_state = current_slurm_job_metadata["state"]
    job = MonitorJobSummary(
        slurm_username=slurm_username,
        slurm_job_id=slurm_job_id,
        slurm_job_state=slurm_job_state,
        task=slurm_job_task_metadata,
    )
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        if not jobs_coll.find_one(
            {"slurm_job_id": slurm_job_id}
        ) and not jobs_coll.find_one({"task.uuid": slurm_job_task_metadata["uuid"]}):
            jobs_coll.insert_one(job.to_dict())
        return True
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"add_job_to_monitor_db | Error adding job to monitor database: {err}"
        )
        return False


def get_job_metadata_from_monitor_db(slurm_job_id: int) -> dict:
    """
    Get job metadata from the monitor database using the SLURM job ID.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.find_one({"slurm_job_id": slurm_job_id})
        # clean MonitorJob object for JSON serialization
        result['_id'] = str(result['_id']) if result.get('_id') else None
        return result if result else None
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"get_job_metadata_from_monitor_db | Error retrieving job information from monitor database: {err}"
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.find_one({"task.uuid": task_uuid})
        result['_id'] = str(result['_id']) if result.get('_id') else None
        return result if result else None
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"get_job_metadata_from_monitor_db_by_task_uuid | Error retrieving job information from monitor database: {err}"
        )
        return None


def update_job_state_in_monitor_db(slurm_job_id: int, new_slurm_job_state: str) -> bool:
    """
    Update the job state key in the monitor database, as well as the updated
    timestamp.

    The job dictionary should contain the SLURM job ID and task information.
    
    The SLURM job state is retrieved from the SLURM scheduler.

    Args:
        slurm_job_id (int): The SLURM job ID.
        new_slurm_job_state (str): The new SLURM job state.

    Returns:
        bool: True if the job state was successfully updated, False otherwise.
    """
    from app.helpers import (
        get_slurm_proxy_app,
        get_current_datetime,
    )
    app = get_slurm_proxy_app()
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.update_one(
            {"slurm_job_id": slurm_job_id},
            {"$set": {
                "slurm_job_state": new_slurm_job_state,
                "updated_at": get_current_datetime(),
            }},
        )
        if result.modified_count == 0:
            app.logger.error(
                f"update_job_state_in_monitor_db | More than one job entry exists for Slurm job: {slurm_job_id}"
            )
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        result = jobs_coll.delete_one({"slurm_job_id": slurm_job_id})
        return False if result.deleted_count == 0 else True
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
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
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
) -> SlurmJobSummary:
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
) -> SlurmJobSummary:
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
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
        result = SlurmJobSummary(
            username=slurm_username,
            job_id=slurm_job_id,
            job_state=SLURM_STATE_UNKNOWN,
        )
        if job_status_job_instance["state"]["current"][0] not in SLURM_STATES_ALLOWED:
            result.set_job_state(SLURM_STATE_UNKNOWN)
        else:
            result.set_job_state(
                job_status_job_instance["state"]["current"][0]
            )
        if job_status_job_instance["user"] != slurm_username:
            result.set_username(job_status_job_instance["user"])
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
) -> SlurmJobSummary:
    """
    Get the current SLURM job metadata by job ID via SSH.

    Args:
        slurm_job_id (int): The SLURM job ID.
        slurm_username (str): The SLURM job username.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
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
        result = SlurmJobSummary(
            username=job_status["user"],
            job_id=slurm_job_id,
            job_state=job_status["state"],
        )
        return result
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


def get_slurm_jobs_metadata_by_slurm_job_state_via_ssh(slurm_job_state: str) -> dict:
    """
    Get SLURM job metadata by job state.
    The job state is passed as a URL parameter.

    Args:
        slurm_job_state (str): The SLURM job state.

    Returns:
        dict: A dictionary containing the job metadata for the given state.
    """
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
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
    in `constants.MONITOR_POLLING_INTERVAL`.

    This function checks the status of all jobs in the monitor database no older than
    the value of `constants.MONGODB_MONITOR_JOB_CREATED_AT_MAX_AGE` and updates the job
    state if there are any changes.
    
    If a job is marked as finished, a state change event is triggered.
    """
    from app.helpers import (
        get_slurm_proxy_app,
        get_current_datetime,
        get_current_datetime_minus_interval,
    )
    app = get_slurm_proxy_app()
    # app.logger.debug("poll_slurm_jobs | Polling SLURM jobs...")
    try:
        jobs_coll = mongodb_connection.get_monitor_jobs_collection()
        jobs = jobs_coll.find({
            "created_at": {
                "$lte": get_current_datetime(),
                "$gte": get_current_datetime_minus_interval(MONGODB_MONITOR_JOB_CREATED_AT_MAX_AGE),
            },
        })
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
            current_slurm_job_state = slurm_job_status_metadata.get_job_state()
            if monitor_db_job_state != current_slurm_job_state:
                new_slurm_job_state = (
                    current_slurm_job_state
                    if current_slurm_job_state in SLURM_STATES_ALLOWED
                    else SLURM_STATE_UNKNOWN
                )
                if new_slurm_job_state in SLURM_STATE_END_STATES:
                    result = process_job_state_change(
                        slurm_job_id, monitor_db_job_state, new_slurm_job_state
                    )
                    if not result:
                        app.logger.error(
                            f"poll_slurm_jobs | Failed to process job state change for job {slurm_job_id}"
                        )
                result = update_job_state_in_monitor_db(slurm_job_id, new_slurm_job_state)
                if not result:
                    app.logger.error(
                        f"poll_slurm_jobs | Failed to update job state in monitor database for job {slurm_job_id}"
                    )
    except pymongo.errors.PyMongoError as err:
        app.logger.error(
            f"poll_slurm_jobs | Error polling SLURM jobs in monitor db: {err}"
        )


def process_job_state_change(
    slurm_job_id: int, old_slurm_job_state: str, new_slurm_job_state: str
) -> bool:
    """
    Handle the job state change here. This would be typically called when the
    Slurm job state becomes one of e.g., COMPLETED, FAILED, or CANCELLED.

    A state change event may be handled by sending a notification message to a
    RabbitMQ queue, for instance, and/or an email, and/or a Slack message to a
    particular channel, as defined in the TASK_METADATA object. Other methods
    may be exposed in task_notification.py.

    Args:
        slurm_job_id (int): The SLURM job ID.
        old_slurm_job_state (str): The old SLURM job state.
        new_slurm_job_state (str): The new SLURM job state.

    Returns:
        bool: True if the job state change was successfully processed, False otherwise.
    """
    # print(
    #     f" * Processing job state change: {slurm_job_id}: {old_slurm_job_state} -> {new_slurm_job_state}",
    #     file=sys.stderr
    # )
    from app.helpers import (
        get_slurm_proxy_app,
    )
    app = get_slurm_proxy_app()
    app.logger.debug(
        f"process_job_state_change | Processing job state change: {slurm_job_id}: {old_slurm_job_state} -> {new_slurm_job_state}"
    )
    if new_slurm_job_state in SLURM_STATE_END_STATES:
        app.logger.debug(f'process_job_state_change | Sending notification message(s) for job {slurm_job_id}')
        try:
            jobs_coll = mongodb_connection.get_monitor_jobs_collection()
            result = jobs_coll.find_one({"slurm_job_id": slurm_job_id})
            if result:
                task = result["task"]
                task_name = task["name"]
                task_md = TASK_METADATA[task_name]
                task_md_notification = task_md["notification"]
                '''
                Get notification methods and params from TASK_METADATA
                '''
                task_md_notification_methods = task_md_notification["methods"]
                task_md_notification_params = task_md_notification["params"]
                task_notification_methods = task_md_notification_methods
                task_notification_params = task_md_notification_params
                '''
                If there are custom notification property data in the task itself, merge
                it with the built-in methods and parameters, where not already existing
                '''
                task_custom_notification = task.get("notification", None)
                if task_custom_notification:
                    task_custom_notification_methods = task_custom_notification.get("methods", [])
                    task_custom_notification_params = task_custom_notification.get("params", {})
                    for method in task_custom_notification_methods:
                        if method not in task_notification_methods and method in task_custom_notification_params:
                            task_notification_methods.append(method)
                            task_notification_params[method] = {}
                            for k, v in task_custom_notification_params[method].items():
                                task_notification_params[method][k] = copy.deepcopy(v)
                '''
                Process each method
                '''
                task_notification_method_factory = NotificationCallbackFactory()
                for method in task_notification_methods:
                    msg = f"Sending notification for: {slurm_job_id} using method: {method}"
                    app.logger.debug(f'process_job_state_change | Sending notification message for: {slurm_job_id} via method: {method}')
                    callback = task_notification_method_factory.create_callback_for_method(method)
                    if method == NotificationMethod.EMAIL.value or method == NotificationMethod.GMAIL.value:
                        sender = task_notification_params["email"]["sender"]
                        recipient = task_notification_params["email"]["recipient"]
                        subject = task_notification_params["email"]["subject"]
                        body = msg
                        try:
                            callback.notify(
                                sender,
                                recipient,
                                subject,
                                body,
                            )
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not message via email or Gmail: {err}"
                            )
                    elif method == NotificationMethod.SLACK.value:
                        try:
                            callback.notify(
                                msg, 
                                task_notification_params["slack"]["channel"],
                            )
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not message via Slack: {err}"
                            )
                    elif method == NotificationMethod.RABBITMQ.value:
                        try:
                            callback.notify(
                                task_notification_params["rabbitmq"]["queue"],
                                task_notification_params["rabbitmq"]["exchange"],
                                task_notification_params["rabbitmq"]["routing_key"],
                                msg,
                            )
                        except Exception as err:
                            app.logger.warning(
                                f"process_job_state_change | Could not message via RabbitMQ: {err}"
                            )
                    elif method == NotificationMethod.TEST.value:
                        callback.notify(msg)
                    else:
                        app.logger.error(f"process_job_state_change | Unknown or unimplemented notification method: {method}")
                        return False
        except pymongo.errors.PyMongoError as err:
            app.logger.error(
                f"process_job_state_change | Error handling job state change from monitor database query: {err}"
            )
            return False
    return True