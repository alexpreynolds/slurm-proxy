# dt-slurm-proxy

This Flask application provides endpoints for submitting and monitoring 
jobs sent to a SLURM scheduler, for the purpose of integration with a
defined set of CLI tools.

## Python

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

## Docker container

For forwarding SSH key data on macOS:

```
cd docker
docker image build -t dt-slurm-proxy-docker --build-context parent=../ .. -f Dockerfile
CONTAINER_ID=$(docker run -p 5001:5001 --mount type=bind,source=/Users/areynolds,target=/Users/areynolds,readonly -d dt-slurm-proxy-docker)
docker logs --follow ${CONTAINER_ID}
```

Or via Docker compose:

```
docker compose -f docker-compose-dt-slurm-proxy.yml build
docker compose -f docker-compose-dt-slurm-proxy.yml up
...
docker compose -f docker-compose-dt-slurm-proxy.yml down
```

## "Hello, world!" test request

Note the use of the `hpcz-test` queue, which refers to the new cluster:

```
wget -O- --post-data='{"task":{"uuid":"123e4567-e89b-12d3-a456-426614174000", "slurm":{"job_name":"dt-slurm-proxy.hello_world","output":"dt-slurm-proxy.hello_world.output.txt","error":"dt-slurm-proxy.hello_world.error.txt","time":"00:30:00","nodes":1,"ntasks_per_node":1,"cpus_per_task":1,"mem":"1G","partition":"hpcz-test"}, "name":"echo_hello_world", "params":["-e", "\"hello, world!\t(sent to $USER)\""], "dirs":{"input":"/home/areynolds/dt-slurm-proxy/input","output":"/home/areynolds/dt-slurm-proxy/output","error":"/home/areynolds/dt-slurm-proxy/error"}}}' --header="Content-Type:application/json" 127.0.0.1:5001/submit/
```