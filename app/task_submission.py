# -*- coding: utf-8 -*-

import os
import sys
from flask import (
    Blueprint,
    request,
    Response,
)
from app.helpers import (
    ssh_client,
    ssh_client_exec,
    stream_json_response,
)
from app.constants import (
    TASK_METADATA,
    BAD_SLURM_JOB_ID,
    SLURM_STATE_UNKNOWN,
    TaskCommunicationMethods,
)
from app.task_monitoring import monitor_new_slurm_job

SSH_CLIENT = ssh_client()

task_submission = Blueprint("task_submission", __name__)

"""
This module defines a Flask blueprint for task submission. 

The task is submitted via a POST request containing a JSON object with
information about the task to be submitted, including directories for input,
output, and error files, as well as SLURM parameters and the task name and
its parameters.
"""


@task_submission.route("/", methods=["POST"])
def post() -> Response:
    """
    POST request handler for task submission.
    This function receives a JSON object containing task information,
    validates the task, and submits it to the SLURM scheduler.
    """
    request_info = request.get_json(force=True)
    task = request_info.get("task")
    if not task:
        return stream_json_response({"error": "No task provided"}, 400)
    if not is_task_valid(task):
        return stream_json_response({"error": "Invalid task format"}, 400)
    submit_job_id = submit_slurm_task(task, TaskCommunicationMethods.SSH)
    if submit_job_id == BAD_SLURM_JOB_ID:
        return stream_json_response({"error": "Failed to submit task"}, 400)
    # if successful, submit job metadata to the monitor service
    job = {
        "slurm_job_id": submit_job_id,
        "slurm_job_state": SLURM_STATE_UNKNOWN,
        "task": task,
    }
    if not monitor_new_slurm_job(job):
        return stream_json_response({"error": "Failed to monitor job"}, 400)
    # return the task uuid back to the client
    return stream_json_response({"uuid": task["uuid"]}, 200)


def submit_slurm_task(task: dict, submit_method: str) -> int:
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

    Returns:
        int: The job ID of the submitted task, or BAD_SLURM_JOB_ID if the submission
            failed.
    """
    if submit_method == TaskCommunicationMethods.SSH:
        cmd = define_sbatch_cmd_for_task_via_ssh(task)
        if not cmd:
            print(" * Failed to define sbatch command", file=sys.stderr)
            return BAD_SLURM_JOB_ID
        job_id = send_sbatch_cmd_via_ssh(cmd) if cmd else BAD_SLURM_JOB_ID
        return job_id
    elif submit_method == TaskCommunicationMethods.REST:
        print(f" * Unsupported task submit method: {submit_method}", file=sys.stderr)
        return BAD_SLURM_JOB_ID
    else:
        print(f" * Unsupported task submit method: {submit_method}", file=sys.stderr)
        return BAD_SLURM_JOB_ID


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
    task_cmd = define_task_cmd(task["name"], task["params"])
    if not task_cmd:
        return None
    slurm_cmd_comps.append(f"--wrap='{task_cmd}'")
    slurm_cmd = " ".join(slurm_cmd_comps)
    cmd_comps.append(slurm_cmd)
    # construct and return the full set of commands
    cmd = " ; ".join(cmd_comps)
    # print(f" * sbatch command: {cmd}", file=sys.stderr)
    return cmd


def define_task_cmd(task_name: str, task_params: list) -> str:
    """
    Construct the command for the task.
    This function retrieves the command template for the specified task
    and appends the parameters provided in the task dictionary.

    Args:
        task_name (str): The name of the task.
        task_params (list): The parameters for the task.

    Returns:
        str: The full command for the task, or None if the task is not defined.
    """
    if task_name not in TASK_METADATA:
        print(f" * Task {task_name} is not defined", file=sys.stderr)
        return None
    task_cmd = [TASK_METADATA[task_name]["cmd"]]
    for default_param in TASK_METADATA[task_name]["default_params"]:
        task_cmd.append(default_param)
    for additional_param in task_params:
        task_cmd.append(additional_param)
    task_cmd = " ".join(task_cmd)
    return task_cmd


def send_sbatch_cmd_via_ssh(cmd: str) -> int:
    """
    Send the sbatch command to the SLURM scheduler via SSH.
    This function connects to the SLURM scheduler using SSH and executes
    the sbatch command. It returns the job ID of the submitted task.
    If the command fails, it returns BAD_SLURM_JOB_ID.

    Args:
        cmd (str): The sbatch command to be executed.

    Returns:
        int: The job ID of the submitted task, or BAD_SLURM_JOB_ID if the submission
            failed.
    """
    if not cmd:
        print(f" * sbatch command is empty", file=sys.stderr)
        return BAD_SLURM_JOB_ID
    (stdin, stdout, stderr) = ssh_client_exec(SSH_CLIENT, cmd)
    try:
        # use of '--parsable' option in sbatch command means that
        # the job id (integer) is the only thing sent to standard output
        job_id = int(stdout.read().decode("utf-8"))
        # if there is any output sent to standard error, log it as a failure
        stderr_val = stderr.read().decode("utf-8")
        if stderr_val:
            print(f" * Failed sbatch submit: {stderr_val}", file=sys.stderr)
            return BAD_SLURM_JOB_ID
    except ValueError as err:
        print(f" * Error: {err}", file=sys.stderr)
        return BAD_SLURM_JOB_ID
    return job_id


def is_task_valid(task: dict) -> bool:
    """
    Validate the task dictionary.
    This function checks if the task dictionary contains all the required
    keys and if the values are of the expected types.

    Args:
        task (dict): The task dictionary to be validated.

    Returns:
        bool: True if the task is valid, False otherwise.
    """
    return all([k in task for k in ["name", "params", "uuid", "slurm", "dirs"]])
