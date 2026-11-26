import os
import unittest
from datetime import datetime, timedelta

from app.api.translation import (
    _task_started_at,
    _task_updated_at,
    _translation_task_stall_timeout_seconds,
    _translation_task_timeout_seconds,
)


class TranslationTaskTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.saved_timeout = os.environ.pop("TRANSLATION_TASK_TIMEOUT_MINUTES", None)
        self.saved_stall = os.environ.pop("TRANSLATION_TASK_STALL_TIMEOUT_SECONDS", None)

    def tearDown(self):
        for key, value in (
            ("TRANSLATION_TASK_TIMEOUT_MINUTES", self.saved_timeout),
            ("TRANSLATION_TASK_STALL_TIMEOUT_SECONDS", self.saved_stall),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_deadline_is_five_minutes_not_thirty(self):
        self.assertEqual(_translation_task_timeout_seconds(), 300)

    def test_deadline_can_be_configured(self):
        os.environ["TRANSLATION_TASK_TIMEOUT_MINUTES"] = "2"
        self.assertEqual(_translation_task_timeout_seconds(), 120)

    def test_default_stall_timeout_is_two_minutes(self):
        self.assertEqual(_translation_task_stall_timeout_seconds(), 120)

    def test_task_timestamps_are_parsed(self):
        now = datetime.utcnow()
        task = {
            "started_at": (now - timedelta(minutes=3)).isoformat(),
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        }
        self.assertIsNotNone(_task_started_at(task))
        self.assertIsNotNone(_task_updated_at(task))
        self.assertLess(_task_updated_at(task), _task_started_at(task) + timedelta(minutes=3))


if __name__ == "__main__":
    unittest.main()
