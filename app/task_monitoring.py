# -*- coding: utf-8 -*-

import sys
import pymongo
import paramiko
from flask import (
    Blueprint,
    request,
    Response,
)
from app.helpers import ssh_client, ssh_client_exec, stream_json_response
from app.constants import (
    SLURM_STATE,
    SLURM_STATE_UNKNOWN,
    SLURM_STATE_END_STATES,
    SLURM_TEST_JOB_ID,
    SLURM_TEST_JOB_STATUS,
    MONGODB_JOBS_COLLECTION,
    TASK_METADATA,
)
from app.task_notification import NotificationCallbacks

SSH_CLIENT = ssh_client()

SLURM_STATES_ALLOWED = SLURM_STATE.keys()

task_monitoring = Blueprint("task_monitoring", __name__)

"""
This module defines a Flask blueprint for task monitoring, which maintains job state via
a MongoDB database and communicates with a SLURM scheduler to generate updated job status.
"""


@task_monitoring.route("/", methods=["POST"])
def post() -> Response:
    """
    POST request to add a new job to the monitor database.
    The request body should contain a JSON object with the job information.
    """
    request_info = request.get_json(force=True)
    job = request_info.get("job")
    if not job:
        return {"error": "No job provided"}, 400
    response = (
        stream_json_response(job, 200)
        if monitor_new_slurm_job(job)
        else stream_json_response({"Error": "Failed to monitor job"}, 400)
    )
    return response


@task_monitoring.route("/slurm_job_id/<slurm_job_id>", methods=["GET"])
def get_job_metadata_by_slurm_job_id(slurm_job_id: str) -> Response:
    """
    GET request to retrieve job metadata from the monitor database using the SLURM job ID.
    The job ID is passed as a URL parameter.

    Args:
        slurm_job_id (str): The SLURM job ID.

    Returns:
        Response: A Flask Response object containing the job metadata in JSON format.
    """
    slurm_job_id = int(slurm_job_id)
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id
    )
    monitor_db_job_metadata = get_job_metadata_from_monitor_db(slurm_job_id)
    if not slurm_job_status_metadata and not monitor_db_job_metadata:
        return {"error": "Job information not found"}, 404
    slurm_job_state = (
        slurm_job_status_metadata["state"]
        if slurm_job_status_metadata
        else SLURM_STATE_UNKNOWN
    )
    response_data = {
        "slurm": {
            "job_id": slurm_job_id,
            "job_state": slurm_job_state,
        },
        "monitor": monitor_db_job_metadata,
    }
    response = stream_json_response(response_data, 200)
    return response


@task_monitoring.route("/slurm_job_state/<slurm_job_state>", methods=["GET"])
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
        return {"error": "Invalid state key"}, 400
    # also query the database for jobs with the given state, for comparison
    jobs = get_slurm_jobs_metadata_by_slurm_job_state(slurm_job_state)
    response = stream_json_response(jobs, 200)
    return response


@task_monitoring.route("/slurm_job_id/<slurm_job_id>", methods=["DELETE"])
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
            (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                response = stream_json_response(
                    {"error": "Job could not be deleted from SLURM scheduler"}, 400
                )
                return response
        except paramiko.SSHException as err:
            response = stream_json_response(
                {"error": f"Failed to delete job from SLURM: {err}"}, 500
            )
            return response
        except Exception as err:
            response = stream_json_response({"error": f"Unexpected error: {err}"}, 500)
            return response
    else:
        # job not found in the database
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
    slurm_job_id = int(job["slurm_job_id"])
    slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
        slurm_job_id
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
    # print(f" * Adding job to monitor database: {slurm_job_id} | {slurm_job_state}", file=sys.stderr)
    result = add_job_to_monitor_db(
        slurm_job_id, slurm_job_state, slurm_job_task_metadata
    )
    # if the job is already completed, we send a notification msg
    if slurm_job_state in SLURM_STATE_END_STATES:
        process_job_state_change(slurm_job_id, SLURM_STATE_UNKNOWN, slurm_job_state)
    return result


def add_job_to_monitor_db(
    slurm_job_id: int, slurm_job_state: str, slurm_job_task_metadata: dict
) -> bool:
    """
    Add a new job to the monitor database.
    The job dictionary should contain the SLURM job ID and task information.
    The SLURM job status is retrieved from the SLURM scheduler.

    Args:
        slurm_job_id (int): The SLURM job ID.
        slurm_job_state (str): The SLURM job state.
        slurm_job_task_metadata (dict): The task metadata for the job.

    Returns:
        bool: True if the job was successfully added to the monitor database, False otherwise.
    """
    if slurm_job_state == SLURM_STATE_UNKNOWN:
        current_slurm_job_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
            slurm_job_id
        )
        if current_slurm_job_metadata:
            slurm_job_state = current_slurm_job_metadata["state"]
    job = {
        "slurm_job_id": slurm_job_id,
        "slurm_job_state": slurm_job_state,
        "task": slurm_job_task_metadata,
    }
    try:
        jobs_coll = MONGODB_JOBS_COLLECTION
        if not jobs_coll.find_one({"slurm_job_id": slurm_job_id}):
            jobs_coll.insert_one(job)
        return True
    except pymongo.errors.PyMongoError as err:
        print(f" * Error adding job to monitor database: {err}", file=sys.stderr)
        return False


def get_job_metadata_from_monitor_db(slurm_job_id: int) -> dict:
    """
    Get job metadata from the monitor database using the SLURM job ID.

    Args:
        slurm_job_id (int): The SLURM job ID.

    Returns:
        dict: A dictionary containing the job metadata, or None if the job was not found.
    """
    try:
        jobs_coll = MONGODB_JOBS_COLLECTION
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
        print(f" * Error retrieving job information from monitor database: {err}", file=sys.stderr)
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
        jobs_coll = MONGODB_JOBS_COLLECTION
        result = jobs_coll.update_one(
            {"slurm_job_id": slurm_job_id},
            {"$set": {"slurm_job_state": new_slurm_job_state}},
        )
        if result.modified_count == 0:
            return False
        return True
    except pymongo.errors.PyMongoError as err:
        print(f" * Error updating job state in monitor database: {err}", file=sys.stderr)
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
        jobs_coll = MONGODB_JOBS_COLLECTION
        result = jobs_coll.delete_one({"slurm_job_id": slurm_job_id})
        if result.deleted_count == 0:
            return False
        return True
    except pymongo.errors.PyMongoError as err:
        print(f" * Error removing job from monitor database: {err}", file=sys.stderr)
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
        jobs_coll = MONGODB_JOBS_COLLECTION
        result = jobs_coll.find_one_and_delete({"slurm_job_id": slurm_job_id})
        return result
    except pymongo.errors.PyMongoError as err:
        print(f" * Error removing job from monitor database: {err}", file=sys.stderr)
        return None


def get_current_slurm_job_metadata_by_slurm_job_id(slurm_job_id: int) -> dict:
    """
    Get the current SLURM job metadata by job ID.

    Args:
        slurm_job_id (int): The SLURM job ID.

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
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
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
    return job_status


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
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
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
    print(" * Polling SLURM jobs...", file=sys.stderr)
    try:
        jobs_coll = MONGODB_JOBS_COLLECTION
        jobs = jobs_coll.find()
        for job in jobs:
            slurm_job_id = int(job["slurm_job_id"])
            monitor_db_job_state = job["slurm_job_state"]
            # print(f'poll: testing {slurm_job_id} | {monitor_db_job_state}', file=sys.stderr)
            if monitor_db_job_state in SLURM_STATE_END_STATES:
                # job is already completed, therefore no need to check its state
                continue
            slurm_job_status_metadata = get_current_slurm_job_metadata_by_slurm_job_id(
                slurm_job_id
            )
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
        print(f" * Error polling SLURM jobs: {err}", file=sys.stderr)


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
    print(
        f" * Processing job state change: {slurm_job_id}: {old_slurm_job_state} -> {new_slurm_job_state}",
        file=sys.stderr
    )
    if new_slurm_job_state in SLURM_STATE_END_STATES:
        # print(f" * Sending notification message for job {slurm_job_id}", file=sys.stderr)
        try:
            jobs_coll = MONGODB_JOBS_COLLECTION
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
                    # print(f" * Sending notification message via method {method}", file=sys.stderr)
                    if method == NotificationCallbacks.EMAIL:
                        sender = task_notification_params["email"]["sender"]
                        recipient = task_notification_params["email"]["recipient"]
                        subject = task_notification_params["email"]["subject"]
                        body = msg
                        try:
                            method.value(sender, recipient, subject, body)
                        except Exception as err:
                            pass
                    elif method == NotificationCallbacks.SLACK:
                        try:
                            method.value(msg, task_notification_params["slack"]["channel"])
                        except Exception as err:
                            pass
                    elif method == NotificationCallbacks.RABBITMQ:
                        try:
                            method.value(
                              task_notification_params["rabbitmq"]["queue"],
                              task_notification_params["rabbitmq"]["exchange"],
                              task_notification_params["rabbitmq"]["routing_key"],
                              msg,
                            )
                        except Exception as err:
                            pass
                    elif method == NotificationCallbacks.TEST:
                        method.value(msg)
        except pymongo.errors.PyMongoError as err:
            print(f" * Error removing job from monitor database: {err}", file=sys.stderr)
            return None
