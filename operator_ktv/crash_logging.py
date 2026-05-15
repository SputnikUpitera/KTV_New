"""
Crash diagnostics helpers for the OperatorKTV GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import logging
import os
from pathlib import Path
import sys
import threading
from types import TracebackType
from typing import Callable, Optional, TypeVar


F = TypeVar("F", bound=Callable)


def get_operator_log_path() -> Path:
    """Return the Windows operator log path, with a cross-platform fallback."""
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".operatorktv" / "operator_ktv.log"


def ensure_operator_log_dir() -> Path:
    """Ensure the operator log directory exists and return the log file path."""
    log_file = get_operator_log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return log_file


def is_current_callback_source(active_source: object, callback_source: object) -> bool:
    """Return whether a callback belongs to the currently active source object."""
    return callback_source is active_source


def log_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Optional[TracebackType],
    logger: Optional[logging.Logger] = None,
) -> None:
    """Write an uncaught exception traceback to the application log."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    target_logger = logger or logging.getLogger("operator_ktv.crash")
    target_logger.critical(
        "Uncaught Python exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def log_thread_exception(args: threading.ExceptHookArgs, logger: Optional[logging.Logger] = None) -> None:
    """Write an uncaught threading exception traceback to the application log."""
    target_logger = logger or logging.getLogger("operator_ktv.crash")
    thread_name = getattr(args.thread, "name", None) or "<unknown>"
    target_logger.critical(
        "Uncaught exception in thread %s",
        thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def log_qt_slot_exceptions(slot: F, *, context: Optional[str] = None,
                           logger: Optional[logging.Logger] = None) -> F:
    """Wrap a Qt slot so unhandled exceptions are logged before Qt handles them."""
    target_logger = logger or logging.getLogger("operator_ktv.crash")
    slot_name = context or getattr(slot, "__qualname__", repr(slot))

    @wraps(slot)
    def wrapper(*args, **kwargs):
        try:
            return slot(*args, **kwargs)
        except Exception:
            target_logger.exception("Unhandled exception in Qt slot: %s", slot_name)
            raise

    return wrapper  # type: ignore[return-value]


@dataclass
class ExceptionHookInstallation:
    previous_sys_excepthook: Callable
    previous_threading_excepthook: Optional[Callable]

    def restore(self) -> None:
        sys.excepthook = self.previous_sys_excepthook
        if self.previous_threading_excepthook is not None:
            threading.excepthook = self.previous_threading_excepthook


def install_exception_hooks(logger: Optional[logging.Logger] = None) -> ExceptionHookInstallation:
    """Install process-wide exception hooks and return a handle for tests."""
    target_logger = logger or logging.getLogger("operator_ktv.crash")
    previous_sys_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def sys_hook(exc_type, exc_value, exc_traceback):
        log_uncaught_exception(exc_type, exc_value, exc_traceback, target_logger)
        if not issubclass(exc_type, KeyboardInterrupt):
            previous_sys_hook(exc_type, exc_value, exc_traceback)

    def thread_hook(args):
        log_thread_exception(args, target_logger)
        if previous_thread_hook is not None:
            previous_thread_hook(args)

    sys.excepthook = sys_hook
    if previous_thread_hook is not None:
        threading.excepthook = thread_hook

    return ExceptionHookInstallation(previous_sys_hook, previous_thread_hook)
