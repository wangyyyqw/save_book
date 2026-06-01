import os
import unittest
from unittest.mock import patch

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

    def test_switching_to_local_task_stops_server_poll_timer(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.load_task(123, server_crawl=True)
        self.assertTrue(panel._poll_timer.isActive())

        with patch.object(panel, "_start_local_crawl"):
            panel.load_task(456, server_crawl=False)

        self.assertFalse(panel._polling)
        self.assertFalse(panel._poll_timer.isActive())

    def test_poll_task_spawns_worker_thread_instead_of_calling_api_inline(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.task_id = 123
        panel._polling = True

        with patch("qidian_save.desktop.panels.backup_panel.threading.Thread") as thread_cls:
            panel._poll_task()

        self.assertTrue(thread_cls.called)
        self.assertEqual(client.calls, 0)

    def test_stale_poll_response_is_rejected(self):
        """返回旧任务的结果不覆盖新任务状态"""
        client = FakeClient()
        panel = BackupPanel(client)
        panel.load_task(1, server_crawl=True)
        gen1 = panel._poll_gen

        # 模拟切换到任务 2
        panel.load_task(2, server_crawl=True)
        self.assertGreater(panel._poll_gen, gen1)

        # 用旧 generation 调用 _on_poll_status — 应被拒绝
        status = {"bookName": "Old", "bookId": "1", "status": "completed",
                  "totalChapters": 5, "completedChapters": 5, "failedChapters": 0}
        panel._on_poll_status(1, gen1, status)

        # UI 不应被旧结果覆盖
        self.assertEqual(panel.task_id, 2)
        self.assertNotIn("Old", panel.label_book.text())
        self.assertTrue(panel._polling, "旧 completed 不应停止当前任务轮询")


if __name__ == "__main__":
    unittest.main()
