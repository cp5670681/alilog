from __future__ import annotations

from unittest.mock import MagicMock

from alilog.client import AliyunSLSClient
from alilog.models import ContextCoordinates


def test_search_logs_builds_expected_request() -> None:
    client_mock = MagicMock()
    response = MagicMock()
    response.json.return_value = {"meta": {"count": 1}, "data": []}
    response.raise_for_status.return_value = None
    client_mock.post.return_value = response

    client = AliyunSLSClient(
        cookie="cookie=value",
        csrf_token="csrf-token",
        client=client_mock,
    )

    payload = client.search_logs(
        project="project-a",
        logstore="research",
        start=100,
        end=200,
        query="error | with_pack_meta",
    )

    assert payload["meta"]["count"] == 1
    _, kwargs = client_mock.post.call_args
    assert kwargs["data"]["ProjectName"] == "project-a"
    assert kwargs["data"]["LogStoreName"] == "research"
    assert kwargs["data"]["query"] == "error | with_pack_meta"
    assert kwargs["data"]["Reverse"] == "true"
    assert "/lognext/project/project-a/logsearch/research" \
        in kwargs["headers"]["Referer"]


def test_context_logs_builds_expected_request() -> None:
    client_mock = MagicMock()
    response = MagicMock()
    response.json.return_value = {"success": True, "data": {"logs": []}}
    response.raise_for_status.return_value = None
    client_mock.get.return_value = response

    client = AliyunSLSClient(cookie="cookie=value", client=client_mock)
    coords = ContextCoordinates("1", "cursor-value", "54", "6")

    client.context_logs(
        project="project-a",
        logstore="research",
        coords=coords,
        pack_id="PACK-ID",
        reserve=False,
    )

    _, kwargs = client_mock.get.call_args
    assert kwargs["params"]["ShardId"] == "1"
    assert kwargs["params"]["Cursor"] == "cursor-value"
    assert kwargs["params"]["PackNum"] == "54"
    assert kwargs["params"]["Offset"] == "6"
    assert kwargs["params"]["PackId"] == "PACK-ID"
    assert kwargs["params"]["Reserve"] == "false"
