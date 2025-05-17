import unittest
from unittest.mock import patch, MagicMock
from flask import Flask, json

import sys
from pathlib import Path

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))
from app.task_monitoring import (
    task_monitoring,
    get_current_slurm_job_metadata_by_slurm_job_id,
    monitor_new_slurm_job,
)
from app.constants import SLURM_TEST_JOB_ID
import app.helpers

# Language: python

# Absolute import from the namespace package


class TestGetSlurmJobMetadataById(unittest.TestCase):
    @patch("helpers.paramiko.SSHClient")
    @patch("helpers.paramiko.Ed25519Key")
    def test_get_slurm_job_metadata_success(self, mock_ed25519key, mock_sshclient):
        # Setup dummy ssh key and SSHClient instance.
        dummy_key = MagicMock()
        mock_ed25519key.from_private_key_file.return_value = dummy_key

        dummy_ssh_instance = MagicMock()
        mock_sshclient.return_value = dummy_ssh_instance

        # Create dummy SLURM output
        dummy_output = b"123|abcd1234|COMPLETED|username|partition|UNLIMITED|2025-04-14T08:57:46|2025-04-14T11:00:44|02:02:58"
        dummy_stdout = MagicMock()
        dummy_stdout.read.return_value = dummy_output
        dummy_ssh_instance.exec_command.return_value = (None, dummy_stdout, None)

        # Call the function under test.
        result = get_current_slurm_job_metadata_by_slurm_job_id(SLURM_TEST_JOB_ID)
        expected_keys = [
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
        expected_values = [
            "123",
            "abcd1234",
            "COMPLETED",
            "username",
            "partition",
            "UNLIMITED",
            "2025-04-14T08:57:46",
            "2025-04-14T11:00:44",
            "02:02:58",
        ]
        expected = dict(zip(expected_keys, expected_values))
        self.assertEqual(result, expected)

    @patch("helpers.paramiko.SSHClient")
    @patch("helpers.paramiko.Ed25519Key")
    def test_get_slurm_job_metadata_failure(self, mock_ed25519key, mock_sshclient):
        # Setup dummy ssh key and SSHClient instance.
        dummy_key = MagicMock()
        mock_ed25519key.from_private_key_file.return_value = dummy_key

        dummy_ssh_instance = MagicMock()
        mock_sshclient.return_value = dummy_ssh_instance

        # Return empty stdout to simulate missing job status.
        dummy_stdout = MagicMock()
        dummy_stdout.read.return_value = b""
        dummy_ssh_instance.exec_command.return_value = (None, dummy_stdout, None)

        result = get_current_slurm_job_metadata_by_slurm_job_id(0)
        self.assertIsNone(result)


class TestPostRequest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(task_monitoring, url_prefix="/")
        self.client = self.app.test_client()

    def tearDown(self):
        pass

    @patch("task_monitoring.monitor_new_slurm_job")
    def test_post_success(self, mock_monitor_job):
        # Set monitor_job to return True.
        mock_monitor_job.return_value = True

        # Create dummy job payload with required keys.
        job_payload = {"slurm_job_id": 123, "task": {"key": "value"}}
        data = {"job": job_payload}

        response = self.client.post("/", json=data)
        self.assertEqual(response.status_code, 200)
        # Expect the echoed JSON to match the provided job payload.
        self.assertEqual(response.get_json(), job_payload)

    def test_post_failure_no_job(self):
        # Payload without 'job' key.
        response = self.client.post("/", json={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
