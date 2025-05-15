import sys
import unittest
from pathlib import Path

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))

import app

class TestLogConfiguration(unittest.TestCase):
    
    def test_INFO__level_log(self):
        """
        Verify log for INFO level
        """
        self.app = app.create_app()
        self.client = self.app.test_client

        with self.assertLogs() as log:
            user_logs = self.client().get('/ping')
            self.assertEqual(len(log.output), 1)
            self.assertEqual(len(log.records), 1)
            self.assertIn('ping > pong', log.output[0])