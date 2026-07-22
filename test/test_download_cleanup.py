import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from m3u8_downloader import M3U8Downloader


class DownloadCleanupTests(unittest.TestCase):
    @staticmethod
    def _playlist():
        return {
            "segments": [
                {
                    "url": "https://cdn.example/segment.ts",
                    "index": 0,
                    "duration": 10.0,
                }
            ],
            "encryption": None,
        }

    @staticmethod
    def _write_downloaded_segment(_segments, temp_dir, _encryption, _progress):
        segment_path = os.path.join(temp_dir, "segment_000000.ts")
        with open(segment_path, "wb") as segment_file:
            segment_file.write(b"\x47" * (188 * 12))
        return [segment_path]

    def test_success_publishes_output_atomically_and_removes_workspace(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "video.mp4")
            downloader = M3U8Downloader()
            downloader.ffmpeg_merger.available = False

            with patch.object(
                downloader.parser,
                "parse_m3u8",
                return_value=self._playlist(),
            ), patch.object(
                downloader,
                "_download_segments",
                side_effect=self._write_downloaded_segment,
            ):
                success = downloader.download(
                    "https://cdn.example/index.m3u8",
                    output_path,
                )

            self.assertTrue(success)
            self.assertTrue(os.path.isfile(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)
            self.assertEqual(
                [name for name in os.listdir(output_dir) if name.endswith(".part")],
                [],
            )
            self.assertTrue(downloader.cleanup_incomplete_artifacts())
            self.assertTrue(os.path.isfile(output_path))

    def test_cancelled_merge_removes_partial_workspace_and_final_output_is_absent(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "video.mp4")
            downloader = M3U8Downloader()

            def interrupted_merge(_segment_files, staged_output):
                with open(staged_output, "wb") as partial_file:
                    partial_file.write(b"partial")
                downloader._stop_flag.set()
                raise InterruptedError("合并已取消")

            with patch.object(
                downloader.parser,
                "parse_m3u8",
                return_value=self._playlist(),
            ), patch.object(
                downloader,
                "_download_segments",
                side_effect=self._write_downloaded_segment,
            ), patch.object(
                downloader,
                "_merge_segments",
                side_effect=interrupted_merge,
            ):
                success = downloader.download(
                    "https://cdn.example/index.m3u8",
                    output_path,
                )

            self.assertFalse(success)
            self.assertFalse(os.path.exists(output_path))
            self.assertEqual(os.listdir(output_dir), [])

    def test_cleanup_only_removes_downloader_owned_workspace(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "video.mp4")
            sibling_path = os.path.join(output_dir, "keep.txt")
            with open(sibling_path, "w", encoding="utf-8") as sibling_file:
                sibling_file.write("keep")

            downloader = M3U8Downloader()
            _, temp_dir, staged_output = downloader._prepare_workspace(output_path)
            with open(staged_output, "wb") as partial_file:
                partial_file.write(b"partial")

            self.assertTrue(downloader.cleanup_incomplete_artifacts())
            self.assertFalse(os.path.exists(temp_dir))
            self.assertTrue(os.path.isfile(sibling_path))
            self.assertFalse(os.path.exists(output_path))

    def test_cleanup_refuses_path_outside_recorded_workspace_boundary(self):
        with tempfile.TemporaryDirectory() as output_dir:
            keep_dir = os.path.join(output_dir, ".keep.part")
            os.makedirs(keep_dir)
            downloader = M3U8Downloader()
            downloader._current_temp_dir = keep_dir
            downloader._current_temp_parent = os.path.join(output_dir, "different")

            self.assertFalse(downloader.cleanup_incomplete_artifacts())
            self.assertTrue(os.path.isdir(keep_dir))

    def test_aes_playlist_logs_detection_and_preloads_key(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "encrypted.mp4")
            downloader = M3U8Downloader()
            downloader.ffmpeg_merger.available = False
            playlist = self._playlist()
            playlist["encryption"] = {
                "method": "AES-128",
                "uri": "https://cdn.example/key.bin",
            }
            progress_messages = []
            log_output = io.StringIO()

            with patch.object(
                downloader.parser,
                "parse_m3u8",
                return_value=playlist,
            ), patch.object(
                downloader.decryptor,
                "get_key",
                return_value=b"0" * 16,
            ) as get_key, patch.object(
                downloader,
                "_download_segments",
                side_effect=self._write_downloaded_segment,
            ), redirect_stdout(log_output):
                success = downloader.download(
                    "https://cdn.example/encrypted.m3u8",
                    output_path,
                    lambda data: progress_messages.append(data.get("message", "")),
                )

            self.assertTrue(success)
            get_key.assert_called_once_with(
                "https://cdn.example/key.bin",
                dict(downloader.session.headers),
            )
            self.assertIn("已自动识别到 AES-128 加密的 M3U8", log_output.getvalue())
            self.assertIn("AES 解密 Key 已自动加载", log_output.getvalue())
            self.assertTrue(any("自动加载 Key" in message for message in progress_messages))
            self.assertTrue(any("Key 已加载" in message for message in progress_messages))


if __name__ == "__main__":
    unittest.main()
