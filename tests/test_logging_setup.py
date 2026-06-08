from __future__ import annotations

import io
import json
import logging

from jobforge.logging_setup import (
    _JsonFormatter,
    get_logger,
    get_request_id,
    new_request_id,
    set_request_id,
    setup_logging,
)


def test_new_request_id_is_short_hex() -> None:
    rid = new_request_id()
    assert len(rid) == 12
    assert all(c in "0123456789abcdef" for c in rid)
    assert get_request_id() == rid


def test_set_request_id_is_readable() -> None:
    set_request_id("custom-id")
    assert get_request_id() == "custom-id"


def test_setup_logging_is_idempotent() -> None:
    setup_logging()
    n1 = len(logging.getLogger().handlers)
    setup_logging()
    n2 = len(logging.getLogger().handlers)
    assert n1 == n2


def test_json_formatter_emits_parseable_json_with_request_id() -> None:
    set_request_id("rid-123")
    rec = logging.LogRecord(
        name="jobforge.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    rec.profile_id = 7  # arbitrary extra
    out = _JsonFormatter().format(rec)
    payload = json.loads(out)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "jobforge.test"
    assert payload["msg"] == "hello world"
    assert payload["request_id"] == "rid-123"
    assert payload["profile_id"] == 7


def test_logger_writes_request_id_through_extra() -> None:
    # Attach our own buffered handler so we don't depend on pytest's capsys/caplog
    # interception (caplog steals handler output before capsys sees it).
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_JsonFormatter())
    log = get_logger("jobforge.test.endtoend")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        set_request_id("end-to-end-rid")
        log.info("emit", extra={"k": "v"})
        line = buf.getvalue().strip()
        payload = json.loads(line)
        assert payload["request_id"] == "end-to-end-rid"
        assert payload["k"] == "v"
        assert payload["msg"] == "emit"
    finally:
        log.removeHandler(handler)
