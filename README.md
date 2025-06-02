# slurm-proxy

This Flask application provides endpoints for submitting and monitoring 
jobs sent to a SLURM scheduler, for the purpose of integration with a
defined set of CLI tools.

## API

### Public endpoints

#### Job submission

##### `https://slurm-proxy/submit` | `POST`

A authenticated job may be submitted as a `POST` request on behalf of any user who can access the new compute cluster. 

Submitted jobs contain Slurm-specific as well as task-specific metadata, described below. 

Here is an example of a request:

```json
{
    "task": {
        "dirs": {
            "parent": "/home/someone/slurm-proxy-hello-world",
            "error": "/home/someone/slurm-proxy-hello-world/error",
            "input": "/home/someone/slurm-proxy-hello-world/input",
            "output": "/home/someone/slurm-proxy-hello-world/output",
        },
        "slurm": {
            "cpus_per_task": 1,
            "error": "slurm-proxy.hello_world.error.txt",
            "job_name": "slurm-proxy.hello_world",
            "mem": 1000,
            "nodes": 1,
            "ntasks_per_node": 1,
            "output": "slurm-proxy.hello_world.output.txt",
            "partition": "hpcz-test",
            "time": 5,
            "environment": "PATH=/bin/:/usr/bin/:/sbin/",
        },
        "name": "generic",
        "cmd": "echo",
        "params": [
            "-e",
            "\"hello, world! (ran $SLURM_JOB_ID for $SLURM_JOB_USER at `date`)\"",
        ],
        "notification": {
            "methods": ["email"],
            "params": {
                "email": {
                    "sender": "administrator@example.com",
                    "recipient": "someone@example.com",
                    "subject": "Generic task completed",
                    "body": "Generic task has completed successfully.",
                }
            },
        },
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "username": "someone",
        "cwd": "/home/someone",
    }
}
```

**Required parameters**

1. `task.name` - Should be `generic` or `echo_hello_world` (defined in `app/constants.py` in `TASK_METADATA`). The `generic` task name requires that `task.notification` methods and metadata are defined for the `task` in order for notifications to be sent upon job completion. The `generic` task also requires that `cmd` and `params` are set to run a particular command and any supplied command-line parameters. If desired, additional task names can be added with default specifications for notification, etc.

2. `task.username` - Set this to the organization username, which is an account that is able to submit jobs to the specified cluster partition. Note that the output of the job is entirely owned by the specified `task.username`, and so that account must have write file permissions to paths specified in `task.dirs` and `task.cwd` (defined below).

3. `task.cwd` - Set this to the working directory of the job being executed. This does not need to be `/home/someone` but should be specified as a directory where temporary files are written. The `task.username` must have write permissions to this path.

4. `task.uuid` - Set this to a unique usage identifier (e.g., with `uuid.uuid4()` etc.). This must be unique, as it identifies the submitted job in the monitor database. Using a duplicate identifier will raise an error.

5. `task.slurm` - Set this to define the Slurm-specific parameters for the job. At this time, the following parameters are supported:

 - `output` - (string) filename storing standard output from executing `task.cmd` (or the command specified in `TASK_METADATA`)
 - `error` - (string) filename storing standard error from executing `task.cmd` (or the command specified in `TASK_METADATA`)
 - `job_name` - (string) name of the job, as stored in the Slurm scheduler database
 - `mem` - (integer) number of megabytes allocated to the scheduled job
 - `cpus_per_task` - (integer) number of CPUs dedicated to the job (useful for multithreading)
 - `nodes` - (integer) number of cores allocated (useful for MPI or OpenMPI tasks)
 - `partition` - (string) name of the cluster partition the job is assigned to
 - `time` - (integer) sets the job time limit in hours, which the `partition` must permit
 - `environment` - (string) sets the runtime environment for the job (if not specified, set to a default of `"PATH=/bin/:/usr/bin/:/sbin/"`)

6. `task.dirs` - Set the `task.dirs.parent`, `task.dirs.error`, `task.dirs.input`, `task.dirs.output` to strings defining paths on the cluster-accessible filesystem where output files are written. The `task.username` must have write permissions to these paths.
 
**Optional parameters**

1. `task.notification` - This object defines what notifications occur when the Slurm scheduler is queried for a status update on a running job, when that job completes (successfully or not).

 - `task.notification.methods` - This list contains one or more of `email`, `gmail`, `slack`, or `rabbithq`. For each method, `task.notification.params` must have a property for that method, which contains metadata for how the response should be processed. See `TASK_METADATA.echo_hello_world.notification.params` in `app/constants.py` for an example of canned responses for each method, and duplicate and modify these as needed.
 
Note: Accordingly, the `slurm-proxy` container itself must be configured to talk to the respective services defined in these methods; see `NOTIFICATIONS_RABBITMQ_*`, `NOTIFICATIONS_SMTP_*`, `NOTIFICATIONS_GMAIL_*` and `NOTIFICATIONS_SLACK_*` in `app/constants.py` to set their definitions (typically done via `.env` or similar environment variables).

**Response**

| Status Code      | Description                                      |
| ---------------- | ------------------------------------------------ |
| 200              | OK                                               |
| 400              | General error; check error message for specifics |

Upon successful submission of a job, relevant job metadata is automatically sent to the job monitoring service (i.e., a separate request to the monitoring service is not required).

#### Job monitoring

A job is monitored automatically, if submitted through the submission endpoints. 

If a job is submitted seperately (i.e., outside of the `slurm-proxy` submit endpoint) those jobs can still be monitored with information that is supplied manually via a `POST` request.

Additional `GET` endpoints are also offered to retrieve the current state of Slurm- and monitor-specific metadata, which include the task details themselves. This can facilitate quick, automated reconstruction of a job for parameter tweaks and resubmission.

##### `https://slurm-proxy/monitor` | `POST`

```json
{
    "monitor": {
        "task": { ... },
        "slurm_job_id": 123456,
    }
}
```

**Required parameters**

1. `task` - Should have at least `task.username` and `task.uuid`. The `task.uuid` parameter should be unique; if it already exists in the monitor database, an error will be thrown.

2. `slurm_job_id` - Should correspond to the Slurm job identifier.

**Optional parameters**

3. `slurm_job_state` - Should correspond to the Slurm job state keyword (`PENDING`, etc.), if specified.

**Response**

| Status Code      | Description                                                     |
| ---------------- | --------------------------------------------------------------- |
| 200              | OK; returns contents of `monitor`, with defaults if unspecified |
| 400              | General error; check error message for specifics                |

##### `https://slurm-proxy/monitor/slurm_job_id/<slurm_job_id>` | `GET`

**Required parameters**

1. `slurm_job_id` - Should correspond to the Slurm job identifier.

**Response**

| Status Code      | Description                                                       |
| ---------------- | ----------------------------------------------------------------- |
| 200              | OK; returns information from monitor database and Slurm scheduler |
| 400              | General error; check error message for specifics                  |

##### `https://slurm-proxy/monitor/task_uuid/<task_uuid>` | `GET`

**Required parameters**

1. `task_uuid` - Should correspond to the job's `task.uuid` parameter, which should have an associated record in the monitor database.

**Response**

| Status Code      | Description                                                       |
| ---------------- | ----------------------------------------------------------------- |
| 200              | OK; returns information from monitor database and Slurm scheduler |
| 400              | General error; check error message for specifics                  |

### Private endpoints

Endpoints are used internally for querying the Slurm REST service, are defined in `app/task_slurm_rest.py`, and are not documented here. Please see the routes in that file for more information.

## Runtime notes

This section describes logging and database storage usage for purposes of deciding storage.

### MongoDB

To plan out storage needs, a monitor job record stored in MongoDB takes an average of 38kB. Multiply this by the expected number of monitored tasks to determine the storage requirements for the monitor database.

The `docker/supervisord.conf` file defines log file size and rotation parameters, which are specified at five rotations of 10MB-size log files for standard output and error. The defaults provided therefore specify an additional 100MB.

## Development

### Python

For testing locally:

```
virtualenv --python=python3.9 .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

If the following error occurs or similar, start the local MongoDB service before starting the Flask application:

```
 * MongoDB connection failed - is the server running?
Error: localhost:27017: [Errno 61] Connection refused (configured timeouts: socketTimeoutMS: 20000.0ms, connectTimeoutMS: 20000.0ms), Timeout: 1.0s, Topology Description: <TopologyDescription id: 6807f7620a450d28e1335f35, topology_type: Unknown, servers: [<ServerDescription ('localhost', 27017) server_type: Unknown, rtt: None, error=AutoReconnect('localhost:27017: [Errno 61] Connection refused (configured timeouts: socketTimeoutMS: 20000.0ms, connectTimeoutMS: 20000.0ms)')>]>
```

### Docker container

For forwarding SSH key data on macOS:

```
cd docker
docker image build -t slurm-proxy --build-context parent=../ .. -f Dockerfile
CONTAINER_ID=$(docker run -p 5001:5001 --mount type=bind,source=/Users/areynolds,target=/Users/areynolds,readonly -d slurm-proxy)
docker logs --follow ${CONTAINER_ID}
```

Or via Docker compose:

```
docker compose -f docker-compose-slurm-proxy.yml build
docker compose -f docker-compose-slurm-proxy.yml up
...
docker compose -f docker-compose-slurm-proxy.yml down
```

### "Hello, world!" test request

Note the use of the `hpcz-test` queue, which refers to the new cluster:

```
wget -O- --post-data='{"task":{"uuid":"123e4567-e89b-12d3-a456-426614174000", "username":"areynolds", "cwd":"/home/areynolds", "cmd":"echo", "params":["-e", "\"hello, world! (sent job $SLURM_JOB_ID to $SLURM_JOB_USER at `date`)\""], "notification":{"methods":["email"],"params":{"email":{"sender":"username@gmail.com","recipient":"username@gmail.com","subject":"hello-world test job finished!","body":"hello!"}}}, "slurm":{"job_name":"slurm-proxy-test.generic","time":30,"nodes":1,"ntasks_per_node":1,"cpus_per_task":1,"mem":1000,"partition":"hpcz-test","output":"slurm-proxy-test.generic.output.txt","error":"slurm-proxy-test.generic.error.txt"}, "name":"generic", "dirs":{"parent":"/home/areynolds/slurm-proxy-test","input":"/home/areynolds/slurm-proxy-test/input","output":"/home/areynolds/slurm-proxy-test/output","error":"/home/areynolds/slurm-proxy-test/error"}}}' --header="Content-Type:application/json" 127.0.0.1:5001/submit/
```

Use the `cmd` and `params` properties to specify the command and a list of its parameters.