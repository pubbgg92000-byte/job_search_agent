"""Deterministic tests for jobforge.llm.client.

These tests stub the Anthropic SDK so we can verify behavior without network.
Cassette-based integration tests for the real wire format live elsewhere
(pytest-recording is wired up in pyproject for that).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    AuthenticationError,
    InternalServerError,
)

from jobforge.llm import client as llm_client


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    llm_client._client = None
    yield
    llm_client._client = None


def _fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _make_fake_create(responses: list[Any] | Any) -> tuple[list[dict[str, Any]], Any]:
    """Return (calls_log, fake_create_coroutine) — fake_create pops the next response per call."""
    if not isinstance(responses, list):
        responses = [responses]
    queue = list(responses)
    calls: list[dict[str, Any]] = []

    async def fake_create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return calls, fake_create


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, fake_create: Any) -> None:
    fake = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake)


def _tool_use_response(tool_name: str, payload: dict[str, Any]) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", name=tool_name, input=payload)
    return SimpleNamespace(content=[block])


def _text_response(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


async def test_call_structured_returns_tool_input_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, fake_create = _make_fake_create(_tool_use_response("emit_x", {"k": "v"}))
    _install_fake_client(monkeypatch, fake_create)

    out = await llm_client.call_structured(
        system="sys",
        user="usr",
        tool_name="emit_x",
        tool_description="desc",
        input_schema={"type": "object"},
    )

    assert out == {"k": "v"}
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "emit_x"}
    assert calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_call_structured_raises_when_no_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, fake_create = _make_fake_create(_text_response("oops"))
    _install_fake_client(monkeypatch, fake_create)

    with pytest.raises(RuntimeError, match="did not emit"):
        await llm_client.call_structured(
            system="sys",
            user="usr",
            tool_name="emit_x",
            tool_description="d",
            input_schema={"type": "object"},
        )
    assert len(calls) == 1  # No retry on RuntimeError — model error is non-transient.


async def test_call_structured_retries_on_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, fake_create = _make_fake_create(
        [
            APIConnectionError(request=_fake_request()),
            _tool_use_response("emit_x", {"k": 1}),
        ]
    )
    _install_fake_client(monkeypatch, fake_create)

    out = await llm_client.call_structured(
        system="s",
        user="u",
        tool_name="emit_x",
        tool_description="d",
        input_schema={"type": "object"},
    )
    assert out == {"k": 1}
    assert len(calls) == 2


async def test_call_structured_retries_on_5xx_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = httpx.Response(500, request=_fake_request())
    calls, fake_create = _make_fake_create(
        [
            InternalServerError("server error", response=resp, body=None),
            _tool_use_response("emit_x", {"ok": True}),
        ]
    )
    _install_fake_client(monkeypatch, fake_create)

    out = await llm_client.call_structured(
        system="s",
        user="u",
        tool_name="emit_x",
        tool_description="d",
        input_schema={"type": "object"},
    )
    assert out == {"ok": True}
    assert len(calls) == 2


async def test_call_structured_does_not_retry_auth_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = httpx.Response(401, request=_fake_request())
    calls, fake_create = _make_fake_create(
        AuthenticationError("bad key", response=resp, body=None)
    )
    _install_fake_client(monkeypatch, fake_create)

    with pytest.raises(AuthenticationError):
        await llm_client.call_structured(
            system="s",
            user="u",
            tool_name="emit_x",
            tool_description="d",
            input_schema={"type": "object"},
        )
    assert len(calls) == 1, "auth error should not be retried"


async def test_call_text_returns_concatenated_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hello "),
            SimpleNamespace(type="text", text="world"),
        ]
    )
    calls, fake_create = _make_fake_create(response)
    _install_fake_client(monkeypatch, fake_create)

    out = await llm_client.call_text(system="s", user="u")
    assert out == "Hello world"
    assert calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
