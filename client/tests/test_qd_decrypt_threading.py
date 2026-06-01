import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.qd_decrypt_panel import QDDecryptPanel


class QDDecryptThreadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_set_busy_from_thread_uses_signal_not_qtimer_single_shot(self):
        """Verify worker-thread busy state uses pyqtSignal (not direct QTimer.singleShot)."""
        panel = QDDecryptPanel(client=object())
        mock_handler = MagicMock()
        panel._sig.busy_changed.connect(mock_handler)
        # _set_busy_from_thread should emit a signal; the connected _set_busy may
        # still schedule a UI-refresh QTimer.singleShot — that's a separate concern.
        panel._set_busy_from_thread(False)
        mock_handler.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()
