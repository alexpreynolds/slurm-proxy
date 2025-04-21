# dt-slurm-proxy

This Flask application provides endpoints for submitting and monitoring 
jobs sent to a SLURM scheduler, for the purpose of integration with a
defined set of CLI tools.

## Python

```
virtualenv --python=python3.9 .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Docker container

For forwarding SSH key data on macOS:

```
docker image build -t dt-slurm-proxy-docker .
CONTAINER_ID=$(docker run -p 5001:5001 --mount type=bind,source=/Users/areynolds,target=/Users/areynolds,readonly -d dt-slurm-proxy-docker)
docker logs --follow ${CONTAINER_ID}
```

## "Hello, world!" test request

```
wget -O- --post-data='{"task":{"uuid":"123e4567-e89b-12d3-a456-426614174000", "slurm":{"job_name":"dt-slurm-proxy.hello_world","output":"dt-slurm-proxy.hello_world.output.txt","error":"dt-slurm-proxy.hello_world.error.txt","time":"00:30:00","nodes":1,"ntasks_per_node":1,"cpus_per_task":1,"mem":"1G","partition":"queue1"}, "name":"echo_hello_world", "params":["-e", "\"hello, world!\t(sent to $USER)\""], "dirs":{"input":"/home/areynolds/dt-slurm-proxy/input","output":"/home/areynolds/dt-slurm-proxy/output","error":"/home/areynolds/dt-slurm-proxy/error"}}}' --header="Content-Type:application/json" 127.0.0.1:5001/submit/
```