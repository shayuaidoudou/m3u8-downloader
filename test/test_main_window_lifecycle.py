import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QDialog

from app.main_window_lifecycle import MainWindowLifecycleMixin


class LifecycleHarness(MainWindowLifecycleMixin):
    def __init__(self, tasks):
        self.download_tasks = tasks
        self.is_closing = False
        self.quit_called = False
        self.minimize_called = False

    def quit_application(self):
        self.quit_called = True

    def minimize_to_tray(self):
        self.minimize_called = True


class MainWindowCloseTests(unittest.TestCase):
    def test_empty_queue_closes_without_prompt(self):
        window = LifecycleHarness([])
        event = Mock()

        with patch("app.main_window_lifecycle.CustomMessageBox") as message_box:
            window.closeEvent(event)

        message_box.assert_not_called()
        self.assertTrue(window.quit_called)
        event.accept.assert_called_once_with()
        event.ignore.assert_not_called()

    def test_non_empty_queue_keeps_close_prompt(self):
        window = LifecycleHarness([object()])
        event = Mock()
        dialog = Mock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.result_index = 0

        with patch("app.main_window_lifecycle.CustomMessageBox", return_value=dialog) as message_box:
            window.closeEvent(event)

        message_box.assert_called_once()
        self.assertFalse(window.quit_called)
        self.assertTrue(window.minimize_called)
        event.ignore.assert_called_once_with()

    def test_shutdown_stops_workers_before_cleaning_incomplete_artifacts(self):
        task = Mock()
        window = LifecycleHarness([task])

        MainWindowLifecycleMixin._shutdown_all_download_workers(window)

        task.shutdown_worker.assert_called_once_with(wait_ms=5000)
        task.cleanup_incomplete_artifacts.assert_called_once_with()
        self.assertLess(
            task.method_calls.index(unittest.mock.call.shutdown_worker(wait_ms=5000)),
            task.method_calls.index(unittest.mock.call.cleanup_incomplete_artifacts()),
        )


if __name__ == "__main__":
    unittest.main()
