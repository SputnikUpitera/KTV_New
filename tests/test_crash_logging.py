import logging
from types import SimpleNamespace
import sys
import threading

import pytest

from operator_ktv import crash_logging


def test_operator_log_path_uses_userprofile(monkeypatch, tmp_path):
    home = tmp_path / "profile"
    monkeypatch.setenv("USERPROFILE", str(home))

    log_path = crash_logging.ensure_operator_log_dir()

    assert log_path == home / ".operatorktv" / "operator_ktv.log"
    assert log_path.parent.exists()


def test_current_callback_source_uses_identity():
    active = object()
    matching = active
    stale = object()

    assert crash_logging.is_current_callback_source(active, matching)
    assert not crash_logging.is_current_callback_source(active, stale)
    assert not crash_logging.is_current_callback_source(None, stale)


def test_qt_slot_wrapper_logs_and_reraises(caplog):
    def failing_slot():
        raise RuntimeError("slot failed")

    wrapped = crash_logging.log_qt_slot_exceptions(failing_slot, context="test-slot")

    with caplog.at_level(logging.ERROR, logger="operator_ktv.crash"):
        with pytest.raises(RuntimeError, match="slot failed"):
            wrapped()

    assert "Unhandled exception in Qt slot: test-slot" in caplog.text
    assert "RuntimeError: slot failed" in caplog.text


def test_uncaught_exception_logger_records_traceback(caplog):
    try:
        raise ValueError("top-level failure")
    except ValueError as exc:
        with caplog.at_level(logging.CRITICAL, logger="operator_ktv.crash"):
            crash_logging.log_uncaught_exception(type(exc), exc, exc.__traceback__)

    assert "Uncaught Python exception" in caplog.text
    assert "ValueError: top-level failure" in caplog.text


def test_thread_exception_logger_includes_thread_name(caplog):
    args = SimpleNamespace(
        exc_type=RuntimeError,
        exc_value=RuntimeError("thread failed"),
        exc_traceback=None,
        thread=SimpleNamespace(name="status-worker"),
    )

    with caplog.at_level(logging.CRITICAL, logger="operator_ktv.crash"):
        crash_logging.log_thread_exception(args)

    assert "Uncaught exception in thread status-worker" in caplog.text
    assert "RuntimeError: thread failed" in caplog.text


def test_install_exception_hooks_chains_and_restores(monkeypatch, caplog):
    calls = []

    def previous_sys_hook(exc_type, exc_value, exc_traceback):
        calls.append(("sys", exc_type, str(exc_value)))

    def previous_thread_hook(args):
        calls.append(("thread", args.exc_type, str(args.exc_value)))

    monkeypatch.setattr(sys, "excepthook", previous_sys_hook)
    monkeypatch.setattr(threading, "excepthook", previous_thread_hook)

    hook = crash_logging.install_exception_hooks()
    try:
        assert sys.excepthook is not previous_sys_hook
        assert threading.excepthook is not previous_thread_hook

        with caplog.at_level(logging.CRITICAL, logger="operator_ktv.crash"):
            sys.excepthook(ValueError, ValueError("hooked"), None)
            threading.excepthook(
                SimpleNamespace(
                    exc_type=RuntimeError,
                    exc_value=RuntimeError("thread hooked"),
                    exc_traceback=None,
                    thread=SimpleNamespace(name="worker"),
                )
            )
    finally:
        hook.restore()

    assert sys.excepthook is previous_sys_hook
    assert threading.excepthook is previous_thread_hook
    assert ("sys", ValueError, "hooked") in calls
    assert ("thread", RuntimeError, "thread hooked") in calls
    assert "Uncaught Python exception" in caplog.text
    assert "Uncaught exception in thread worker" in caplog.text
