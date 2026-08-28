import tempfile
import time
import unittest
from pathlib import Path

from data.database import Database
from managers.alarm_manager import AlarmManager
from managers.candidate_manager import CandidateManager
from managers.command_manager import CommandManager
from protocol import make_command


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self.database.close()
        self.temp_dir.cleanup()

    def test_candidate_lifecycle(self) -> None:
        manager = CandidateManager(self.database)
        item = manager.add({"candidate_id": "CAN-1", "latitude": 31.2, "status": "new"})
        self.assertEqual(item["candidate_id"], "CAN-1")
        self.assertEqual(len(manager.all()), 1)
        manager.delete(["CAN-1"])
        self.assertEqual(manager.all(), [])

    def test_alarm_transitions_are_deduplicated(self) -> None:
        manager = AlarmManager()
        self.assertIsNotNone(manager.evaluate("battery", True, "low battery"))
        self.assertIsNone(manager.evaluate("battery", True, "low battery"))
        recovered = manager.evaluate("battery", False, "low battery")
        self.assertIsNotNone(recovered)
        self.assertFalse(recovered.alarmed)

    def test_command_rtt_and_database(self) -> None:
        manager = CommandManager(self.database)
        command = make_command("ping")
        manager.sent(command)
        time.sleep(0.01)
        pending, rtt, status = manager.completed({"command_id": command["command_id"], "status": "success"})
        self.assertIsNotNone(pending)
        self.assertGreater(rtt, 0)
        self.assertEqual(status, "success")

    def test_telemetry_and_photo_persistence(self) -> None:
        self.database.save_telemetry({"timestamp": 1, "latitude": 31.2, "battery": 80})
        self.database.save_photo({"photo_id": "PHOTO-1", "timestamp": 2, "latitude": 31.2})
        telemetry = self.database.connection.execute("SELECT COUNT(*) FROM telemetry_snapshots").fetchone()[0]
        photos = self.database.connection.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        self.assertEqual((telemetry, photos), (1, 1))


if __name__ == "__main__":
    unittest.main()
