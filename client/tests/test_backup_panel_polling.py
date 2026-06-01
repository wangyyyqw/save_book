import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.backup_panel import BackupPanel


class FakeClient:
    def __init__(self):
        self.calls = 0

    def get_task(self, task_id):
        self.calls += 1
        return {
            "bookName": "Book",
            "bookId": "1",
            "status": "running",
            "totalChapters": 10,
            "completedChapters": 1,
            "failedChapters": 0,
        }


class BackupPanelPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_server_task_starts_timer(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.load_task(123, server_crawl=True)
        self.assertTrue(panel._polling)
        self.assertTrue(panel._poll_timer.isActive())
        panel._poll_timer.stop()


if __name__ == "__main__":
    unittest.main()
