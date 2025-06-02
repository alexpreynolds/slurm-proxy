# -*- coding: utf-8 -*-

import os
from flask import (
    Blueprint,
    request,
    Response,
)
from typing import Tuple
from app.helpers import (
    stream_json_response,
    get_dict_from_streamed_json_response,
    get_slurm_proxy_app,
)
from app.constants import (
    TASK_METADATA,
    BAD_SLURM_JOB_ID,
    SLURM_STATE_UNKNOWN,
    SlurmCommunicationMethods,
)
from app.task_monitoring import (
    get_job_metadata_from_monitor_db_by_query,
    monitor_new_slurm_job,
)
from app.task_ssh_client import ssh_client_connection_singleton
from app.task_metadata_monitor_job_summary import MonitorJobSummary

ssh_connection = ssh_client_connection_singleton

SLURM_COMMUNICATION_METHOD = SlurmCommunicationMethods.REST

task_submission = Blueprint("task_submission", __name__)

"""
This module defines a Flask blueprint for task submission. 

The task is submitted via a POST request containing a JSON object with
information about the task to be submitted, including directories for input,
output, and error files, as well as SLURM parameters and the task name and
its parameters.
"""


@task_submission.route("/", methods=["POST"], strict_slashes=False)
def post() -> Response:
    """
    POST request handler for task submission.
    This function receives a JSON object containing task information,
    validates the task, and submits it to the SLURM scheduler.
    """
    app = get_slurm_proxy_app()
    request_info = request.get_json(force=True)
    if not request_info:
        app.logger.error(f"No JSON data received for job submission")
        return stream_json_response({"error": "Invalid JSON format"}, 400)
    task = request_info.get("task")
    if not task:
        app.logger.error(f"JSON data received for job submission does not contain task")
        return stream_json_response({"error": "No task provided"}, 400)
    if not is_task_valid(task):
        app.logger.error(
            f"JSON data received for job submission does not contain a valid task description"
        )
        return stream_json_response({"error": "Invalid task format"}, 400)
    (submit_job_id, submit_job_msg) = submit_slurm_job(task, SLURM_COMMUNICATION_METHOD)
    if submit_job_id == BAD_SLURM_JOB_ID:
        app.logger.error(f"Could not submit task to monitor and/or SLURM scheduler | {submit_job_msg}")
        return stream_json_response({"error": f"Failed to submit task | {submit_job_msg}"}, 400)
    # if successful, submit job metadata to the monitor service
    job = MonitorJobSummary(
        slurm_username=task["username"],
        slurm_job_id=submit_job_id,
        slurm_job_state=SLURM_STATE_UNKNOWN,
        task=task,
    )
    if not monitor_new_slurm_job(job):
        app.logger.error(f"Failed to monitor job")
        return stream_json_response({"error": "Failed to monitor job"}, 400)
    # return the task uuid back to the client
    return stream_json_response(
        {"uuid": task["uuid"], "slurm_job_id": submit_job_id}, 200
    )


def submit_slurm_job(task: dict, submit_method: str) -> Tuple[int, str]:
    """
    Submit a task to the SLURM scheduler.
    This function constructs the command to create the necessary directories
    for input, output, and error files, and then constructs the SLURM command
    using the parameters provided in the task dictionary. Finally, it sends
    the command to the SLURM scheduler using SSH.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.
        submit_method (str): The method to be used for task submission. Currently,
            only SSH is supported.

    Returns a tuple of:
        int: The job ID of the submitted task, or BAD_SLURM_JOB_ID if the submission
            failed.
        str: A message indicating the result of the submission.
    """
    app = get_slurm_proxy_app()
    if submit_method == SlurmCommunicationMethods.SSH:
        (job_id, msg) = submit_slurm_job_via_ssh(task)
        return (job_id, msg)
    elif submit_method == SlurmCommunicationMethods.REST:
        (job_id, msg) = submit_slurm_job_via_rest(task)
        return (job_id, msg)
    else:
        msg = f"Unsupported task submit method: {submit_method}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)


def define_sbatch_cmd_for_task_via_ssh(task: dict) -> str:
    """
    Construct the sbatch command for the task.
    This function creates the command to create the necessary directories
    for input, output, and error files, and then constructs the sbatch command
    using the parameters provided in the task dictionary.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.

    Returns:
        str: The full sbatch command to be executed.
    """
    # app = get_slurm_proxy_app()
    cmd_comps = []
    # construct the command to create the directories holding the input, output, and error files
    dir_comps = task["dirs"]
    dir_cmd_comps = []
    dir_cmd_comps.append(f'mkdir -p {dir_comps["input"]}')
    dir_cmd_comps.append(f'mkdir -p {dir_comps["output"]}')
    dir_cmd_comps.append(f'mkdir -p {dir_comps["error"]}')
    dir_cmd = " ; ".join(dir_cmd_comps)
    cmd_comps.append(dir_cmd)
    # construct the sbatch command
    slurm_comps = task["slurm"]
    slurm_cmd_comps = []
    slurm_cmd_comps.append(f"sbatch")
    slurm_cmd_comps.append(f"--parsable")
    slurm_cmd_comps.append(f"--job-name={slurm_comps['job_name']}")
    slurm_cmd_comps.append(
        f"--output={os.path.join(dir_comps['output'], slurm_comps['output'])}"
    )
    slurm_cmd_comps.append(
        f"--error={os.path.join(dir_comps['error'], slurm_comps['error'])}"
    )
    slurm_cmd_comps.append(f"--nodes={slurm_comps['nodes']}")
    slurm_cmd_comps.append(f"--mem={slurm_comps['mem']}")
    slurm_cmd_comps.append(f"--cpus-per-task={slurm_comps['cpus_per_task']}")
    slurm_cmd_comps.append(f"--ntasks-per-node={slurm_comps['ntasks_per_node']}")
    slurm_cmd_comps.append(f"--partition={slurm_comps['partition']}")
    if slurm_comps["time"]:
        slurm_cmd_comps.append(f"--time={slurm_comps['time']}")
    task_cmd = define_task_cmd(task["name"], task.get("cmd", None), task.get("params", []))
    if not task_cmd:
        return None
    slurm_cmd_comps.append(f"--wrap='{task_cmd}'")
    slurm_cmd = " ".join(slurm_cmd_comps)
    cmd_comps.append(slurm_cmd)
    # construct and return the full set of commands
    cmd = " ; ".join(cmd_comps)
    # app.logger.debug(f" * Debug: {current_filename} | sbatch command: {cmd}")
    return cmd


def define_task_cmd(task_name: str, task_cmd: str, additional_task_params: list) -> str:
    """
    Construct the command for the task.
    This function retrieves the command template for the specified task
    and appends the parameters provided in the task dictionary.

    Args:
        task_name (str): The name of the task.
        task_cmd (str): The command for the task, if specified.
        additional_task_params (list): Additional parameters for the command
            that are not provided as default parameters.

    Returns:
        str: The full command for the task, or None if the task is not defined.
    """
    app = get_slurm_proxy_app()
    if task_name not in TASK_METADATA:
        app.logger.error(f"Task {task_name} is invalid")
        return None
    cmd = [task_cmd if task_cmd else TASK_METADATA[task_name].get("cmd", None)]
    if not cmd[0]:
        app.logger.error(f"Task command for {task_name} is unspecified")
        return None
    for default_param in TASK_METADATA[task_name].get("default_params", []):
        cmd.append(default_param)
    for additional_param in additional_task_params:
        cmd.append(additional_param)
    cmd = " ".join(cmd)
    return cmd


def submit_slurm_job_via_ssh(task: dict) -> Tuple[int, str]:
    """
    Send the sbatch command to the SLURM scheduler via SSH.
    This function connects to the SLURM scheduler using SSH and executes
    the sbatch command. It returns the job ID of the submitted task.
    If the command fails, it returns BAD_SLURM_JOB_ID.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.

    Returns a tuple of:
        int: The job ID of the submitted task, or BAD_SLURM_JOB_ID if the submission
            failed.
        str: A message indicating the result of the submission.
    """
    app = get_slurm_proxy_app()
    cmd = define_sbatch_cmd_for_task_via_ssh(task)
    if not cmd:
        msg = f"Failed to define sbatch command; validate task parameters"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)
    try:
        (stdin, stdout, stderr) = ssh_connection.ssh_client_exec(cmd)
        # use of '--parsable' option in sbatch command means that
        # the job id (integer) is the only thing sent to standard output
        job_id = int(stdout.read().decode("utf-8"))
        # if there is any output sent to standard error, log it as a failure
        stderr_val = stderr.read().decode("utf-8")
        if stderr_val:
            msg = f"Failed sbatch submit: {stderr_val}"
            app.logger.error(msg)
            return (BAD_SLURM_JOB_ID, msg)
    except ValueError as err:
        msg = f"submit_slurm_job_via_ssh - {err}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)
    return (job_id, "Successfully submitted SLURM job via SSH")


def submit_slurm_job_via_rest(task: dict) -> Tuple[int, str]:
    """
    Send the job to the SLURM scheduler via RESTful request.

    This function submits a preliminary job to the SLURM scheduler using a RESTful
    request, which generates directories for input, output, and error files. The
    job id that results is used as a dependency for the actual (main) job.

    This function then constructs the equivalent sbatch command using the
    parameters provided in the task dictionary and sends it to the SLURM
    scheduler via REST API.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.

    Returns a tuple of:
        int: The job ID of the submitted task, or BAD_SLURM_JOB_ID if the submission
            failed.
        str: A message indicating the result of the submission.
    """
    from app.task_slurm_rest import submit_job_via_params
    app = get_slurm_proxy_app()

    job_metadata = get_job_metadata_from_monitor_db_by_query({'task.uuid': task["uuid"]})
    if job_metadata:
        msg = f"Task UUID {task['uuid']} already exists in monitor database - {job_metadata}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)

    preliminary_payload = get_preliminary_slurm_rest_payload_for_task(task)
    if not preliminary_payload:
        msg = f"Failed to define preliminary REST payload for submission; validate task parameters"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)
    preliminary_response = submit_job_via_params(preliminary_payload)
    if preliminary_response.status_code != 200:
        try:
            preliminary_response_text = preliminary_response.text
            msg = f"{preliminary_response.status_code} - Preliminary submit step failed - {preliminary_response_text}"
            app.logger.error(msg)
            return (BAD_SLURM_JOB_ID, msg)
        except AttributeError as err:
            msg = f"{preliminary_response.status_code} - Preliminary submit step failed - {err}"
            app.logger.error(msg)
            return (BAD_SLURM_JOB_ID, msg)
    response = get_dict_from_streamed_json_response(preliminary_response)
    preliminary_job_id = response["response"].get("job_id", BAD_SLURM_JOB_ID)

    if preliminary_job_id == BAD_SLURM_JOB_ID:
        msg = f"Failed to create preliminary job - {response}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)

    # construct the command payload for the main job
    main_payload = get_main_slurm_rest_payload_for_task(task, preliminary_job_id)
    if not main_payload:
        msg = f"Failed to define main REST payload for submission; validate task parameters"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)
    main_response = submit_job_via_params(main_payload)
    if main_response.status_code != 200:
        msg = f"get_main_slurm_rest_payload_for_task: {main_response.status_code} - {main_response.text}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)
    response = get_dict_from_streamed_json_response(main_response)
    main_job_id = response["response"].get("job_id", BAD_SLURM_JOB_ID)
    if main_job_id == BAD_SLURM_JOB_ID:
        msg = f"Failed to create main job - {response}"
        app.logger.error(msg)
        return (BAD_SLURM_JOB_ID, msg)

    # main_job_id is what needs to be returned to the client for monitoring
    return (main_job_id, "Successfully submitted SLURM job via REST")


def get_main_slurm_rest_payload_for_task(task: dict, preliminary_job_id: int) -> dict:
    """
    Construct the payload for the SLURM RESTful request.
    This function creates the payload to be sent to the SLURM scheduler
    via REST API. It includes the necessary directories for input, output,
    and error files, as well as the SLURM parameters and task command.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.
        preliminary_job_id (int): The job ID of the preliminary job that was created
            to create the necessary directories.

    Returns:
        dict: The payload for the SLURM RESTful request.
    """
    app = get_slurm_proxy_app()
    try:
        dir_comps = task["dirs"]
        # parent_dir = dir_comps["parent"]
        output_dir = dir_comps["output"]
        error_dir = dir_comps["error"]
        task_cmd = define_task_cmd(
            task["name"], task.get("cmd", None), task.get("params", [])
        )
        slurm_cmd = f"#!/bin/bash\nsrun /bin/bash -c '{task_cmd};'"
        slurm_obj = {
            "username": task["username"],
            "job": {
                "script": slurm_cmd,
                "environment": [task["slurm"].get("environment", "PATH=/bin/:/usr/bin/:/sbin/")],
                "current_working_directory": f"{task['cwd']}",
                "name": f"hpc-proxy-{task['name']}-{task['uuid']}-main",
                "partition": task["slurm"]["partition"],
                "cpus_per_task": task["slurm"]["cpus_per_task"],
                "memory_per_cpu": {"set": True, "number": task["slurm"]["mem"]},
                "time_limit": {"set": True, "number": task["slurm"]["time"]},
                "standard_output": f'{output_dir}/{task["slurm"]["output"]}',
                "standard_error": f'{error_dir}/{task["slurm"]["error"]}',
                "dependency": f"afterok:{preliminary_job_id}",
            },
        }
        # app.logger.debug(f"SLURM main payload: {slurm_obj}")
        return slurm_obj
    except KeyError as err:
        app.logger.error(f"Missing keys from task - {task} - {err}")
        return None


def get_preliminary_slurm_rest_payload_for_task(task: dict) -> dict:
    """
    Construct the payload for the SLURM RESTful request.
    This function creates the payload to be sent to the SLURM scheduler
    via REST API. It includes the necessary directories for input, output,
    and error files, as well as the SLURM parameters and task command.

    Args:
        task (dict): The task dictionary containing information about the task
            to be submitted.

    Returns:
        dict: The payload for the SLURM RESTful request.
    """
    app = get_slurm_proxy_app()
    try:
        dir_comps = task["dirs"]
        parent_dir = dir_comps["parent"]
        input_dir = dir_comps["input"]
        output_dir = dir_comps["output"]
        error_dir = dir_comps["error"]
        mkdir_cmds = []
        mkdir_cmds.append(f"mkdir -p {parent_dir}")
        mkdir_cmds.append(f"mkdir -p {input_dir}")
        mkdir_cmds.append(f"mkdir -p {output_dir}")
        mkdir_cmds.append(f"mkdir -p {error_dir}")
        mkdir_cmd = " ; ".join(mkdir_cmds)
        slurm_cmd = f"#!/bin/bash\nsrun /bin/bash -c '{mkdir_cmd};'"
        slurm_obj = {
            "username": task["username"],
            "job": {
                "script": slurm_cmd,
                "environment": ["PATH=/bin/:/usr/bin/:/sbin/"],
                "current_working_directory": f"{task['cwd']}",
                "name": f"hpc-proxy-preliminary-{task['name']}-{task['uuid']}-preliminary",
                "partition": task["slurm"]["partition"],
                "cpus_per_task": 1,
                "memory_per_cpu": {"set": True, "number": 100},
                "time_limit": {"set": True, "number": 100},
                "standard_output": "/dev/null",
                "standard_error": "/dev/null",
            },
        }
        # app.logger.debug(f"SLURM preliminary payload: {slurm_obj}")
        return slurm_obj
    except KeyError as err:
        app.logger.error(f"Missing keys from task - {task} - {err}")
        return None


def is_task_valid(task: dict) -> bool:
    """
    Validate the task dictionary.
    This function checks if the task dictionary contains all the required
    top-level keys.

    Args:
        task (dict): The task dictionary to be validated.

    Returns:
        bool: True if the task is valid, False otherwise.
    """
    tests = [
        k in task
        for k in ["name", "username", "cwd", "uuid", "slurm", "dirs"]
    ]
    return all(tests)