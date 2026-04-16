from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from alilog import cli


class ParsePackMetaTests(unittest.TestCase):
    def test_parse_pack_meta(self) -> None:
        coords = cli.parse_pack_meta("1|cursor-value|54|6")

        self.assertEqual(coords.shard_id, "1")
        self.assertEqual(coords.cursor, "cursor-value")
        self.assertEqual(coords.pack_num, "54")
        self.assertEqual(coords.offset, "6")

    def test_parse_pack_meta_rejects_invalid_value(self) -> None:
        with self.assertRaises(cli.AliLogError):
            cli.parse_pack_meta("1|cursor-only")


class AuthConfigTests(unittest.TestCase):
    def test_save_and_load_auth_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".alilog.json"

            cli.save_auth_config(
                path,
                cli.AuthConfig(cookie="cookie=value", csrf_token="csrf-token"),
            )

            loaded = cli.load_auth_config(path)
            self.assertEqual(loaded.cookie, "cookie=value")
            self.assertEqual(loaded.csrf_token, "csrf-token")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["cookie"],
                "cookie=value",
            )

    def test_resolve_auth_uses_config_when_cli_empty(self) -> None:
        resolved = cli.resolve_auth(
            None,
            None,
            cli.AuthConfig(cookie="cookie=value", csrf_token="csrf-token"),
        )

        self.assertEqual(resolved.cookie, "cookie=value")
        self.assertEqual(resolved.csrf_token, "csrf-token")


class TimeParsingTests(unittest.TestCase):
    def test_parse_time_value_accepts_seconds_timestamp(self) -> None:
        self.assertEqual(
            cli.parse_time_value("1776352860", "Asia/Shanghai"),
            1776352860,
        )

    def test_parse_time_value_accepts_milliseconds_timestamp(self) -> None:
        self.assertEqual(
            cli.parse_time_value("1776352860000", "Asia/Shanghai"),
            1776352860,
        )

    def test_parse_time_value_accepts_datetime_string(self) -> None:
        self.assertEqual(
            cli.parse_time_value("2026-04-16 23:21:00", "Asia/Shanghai"),
            1776352860,
        )

    def test_resolve_search_window_supports_last(self) -> None:
        window = cli.resolve_search_window(
            start=None,
            end="2026-04-16 23:21:00",
            last="15m",
            timezone_name="Asia/Shanghai",
        )

        self.assertEqual(window.start, 1776351960)
        self.assertEqual(window.end, 1776352860)
        self.assertEqual(window.timezone_name, "Asia/Shanghai")


class ClientRequestTests(unittest.TestCase):
    def test_search_logs_builds_expected_request(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {"meta": {"count": 1}, "data": []}
        response.raise_for_status.return_value = None
        session.post.return_value = response

        client = cli.AliyunSLSClient(
            cookie="cookie=value",
            csrf_token="csrf-token",
            session=session,
        )

        payload = client.search_logs(
            project="project-a",
            logstore="research",
            start=100,
            end=200,
            query="error | with_pack_meta",
        )

        self.assertEqual(payload["meta"]["count"], 1)
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["data"]["ProjectName"], "project-a")
        self.assertEqual(kwargs["data"]["LogStoreName"], "research")
        self.assertEqual(kwargs["data"]["query"], "error | with_pack_meta")
        self.assertEqual(kwargs["data"]["Reverse"], "true")
        self.assertIn(
            "/lognext/project/project-a/logsearch/research",
            kwargs["headers"]["Referer"],
        )

    def test_context_logs_builds_expected_request(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {"success": True, "data": {"logs": []}}
        response.raise_for_status.return_value = None
        session.get.return_value = response

        client = cli.AliyunSLSClient(cookie="cookie=value", session=session)
        coords = cli.ContextCoordinates("1", "cursor-value", "54", "6")

        client.context_logs(
            project="project-a",
            logstore="research",
            coords=coords,
            pack_id="PACK-ID",
            reserve=False,
        )

        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["params"]["ShardId"], "1")
        self.assertEqual(kwargs["params"]["Cursor"], "cursor-value")
        self.assertEqual(kwargs["params"]["PackNum"], "54")
        self.assertEqual(kwargs["params"]["Offset"], "6")
        self.assertEqual(kwargs["params"]["PackId"], "PACK-ID")
        self.assertEqual(kwargs["params"]["Reserve"], "false")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_auth_save_writes_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".alilog.json"
            result = self.runner.invoke(
                cli.cli,
                [
                    "--config",
                    str(config_path),
                    "auth",
                    "save",
                    "--cookie",
                    "cookie=value",
                    "--csrf-token",
                    "csrf-token",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["cookie"], "cookie=value")
            self.assertEqual(saved["csrf_token"], "csrf-token")
            self.assertIn(str(config_path), result.output)

    def test_auth_clear_removes_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".alilog.json"
            config_path.write_text('{"cookie":"cookie=value"}', encoding="utf-8")

            result = self.runner.invoke(
                cli.cli,
                ["--config", str(config_path), "auth", "clear"],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse(config_path.exists())

    def test_context_both_calls_prev_and_next(self) -> None:
        fake_client = MagicMock()
        fake_client.context_logs.side_effect = [
            {
                "data": {
                    "packId": "PACK-ID",
                    "prePackId": "PREV-PACK",
                    "packMeta": "1|cursor|54|6",
                    "prePackMeta": "0|cursor-prev|24|0",
                    "logs": [
                        {"__index_number__": "-1", "__time__": 1776352587, "content": "prev log"}
                    ],
                }
            },
            {
                "data": {
                    "packId": "PACK-ID",
                    "prePackId": "PACK-ID",
                    "packMeta": "1|cursor|54|36",
                    "prePackMeta": "1|cursor|54|6",
                    "logs": [
                        {"__index_number__": "+1", "__time__": 1776352588, "content": "next log"}
                    ],
                }
            },
        ]

        with patch("alilog.cli.get_client", return_value=fake_client):
            result = self.runner.invoke(
                cli.cli,
                [
                    "--cookie",
                    "cookie=value",
                    "--config",
                    "/tmp/ignored.json",
                    "context",
                    "--project",
                    "project-a",
                    "--logstore",
                    "research",
                    "--pack-meta",
                    "1|cursor|54|6",
                    "--pack-id",
                    "PACK-ID",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(fake_client.context_logs.call_count, 2)
        self.assertIn("[prev]", result.output)
        self.assertIn("[next]", result.output)

    def test_search_accepts_human_time_and_last(self) -> None:
        fake_client = MagicMock()
        fake_client.search_logs.return_value = {"meta": {"count": 0}, "data": []}

        with patch("alilog.cli.get_client", return_value=fake_client):
            result = self.runner.invoke(
                cli.cli,
                [
                    "--cookie",
                    "cookie=value",
                    "search",
                    "--project",
                    "project-a",
                    "--logstore",
                    "research",
                    "--to",
                    "2026-04-16 23:21:00",
                    "--last",
                    "15m",
                    "--query",
                    "error",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        _, kwargs = fake_client.search_logs.call_args
        self.assertEqual(kwargs["start"], 1776351960)
        self.assertEqual(kwargs["end"], 1776352860)
        self.assertIn("range=", result.output)


if __name__ == "__main__":
    unittest.main()
