import copy
import uuid

import unittest

import sys
from pathlib import Path

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))

from app.task_submission import task_submission
from app.helpers import (
    get_slurm_proxy_app,
)

test_data_base = {
    "task": {
        "dirs": {
            "parent": "/home/areynolds/dt-slurm-proxy",
            "error": "/home/areynolds/dt-slurm-proxy/error",
            "input": "/home/areynolds/dt-slurm-proxy/input",
            "output": "/home/areynolds/dt-slurm-proxy/output",
        },
        "slurm": {
            "cpus_per_task": 1,
            "error": "dt-slurm-proxy.hello_world.error.txt",
            "job_name": "dt-slurm-proxy.hello_world",
            "mem": 1000,
            "nodes": 1,
            "ntasks_per_node": 1,
            "output": "dt-slurm-proxy.hello_world.output.txt",
            "partition": "hpcz-test",
            "time": 5,
        },
        "name": "echo_hello_world",
        "cmd": "echo",
        "params": [
            "-e",
            "\"hello, world! (ran $SLURM_JOB_ID for $SLURM_JOB_USER at `date`)\"",
        ],
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "username": "areynolds",
        "cwd": "/home/areynolds",
    }
}

class TestTaskSubmission(unittest.TestCase):
    def setUp(self):
        self.app = get_slurm_proxy_app()
        self.client = self.app.test_client()

    def tearDown(self):
        pass

    def test_index_with_duplicate_uuid(self):
        test_data_existing_uuid = copy.deepcopy(test_data_base)
        response = self.client.post("/submit", json=test_data_existing_uuid)
        self.assertEqual(response.status_code, 400)

    def test_index_with_unique_uuid(self):
        test_data_with_unique_uuid = copy.deepcopy(test_data_base)
        test_data_with_unique_uuid["task"]["uuid"] = uuid.uuid4()
        response = self.client.post("/submit", json=test_data_with_unique_uuid)
        self.assertEqual(response.status_code, 200)

    def test_index_without_data(self):
        # Send a POST request without any JSON data
        response = self.client.post("/submit")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
