import logging
import io
import runpy
from pathlib import Path

from operator_ktv import main as operator_main


def close_handlers(handlers):
    for handler in handlers:
        handler.close()


def test_no_console_launcher_sets_project_root_and_imports_existing_main(monkeypatch, tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)

    namespace = runpy.run_path(
        str(project_root / "OperatorKTV.pyw"),
        run_name="operator_ktv_launcher_test",
    )

    assert Path.cwd() == project_root
    assert namespace["main"] is operator_main.main


def test_logging_handlers_skip_console_when_stderr_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(operator_main.sys, "stderr", None)

    handlers = operator_main._build_logging_handlers(tmp_path / "operator_ktv.log")
    try:
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.FileHandler)
    finally:
        close_handlers(handlers)


def test_logging_handlers_keep_console_when_stderr_exists(monkeypatch, tmp_path):
    stderr = io.StringIO()
    monkeypatch.setattr(operator_main.sys, "stderr", stderr)

    handlers = operator_main._build_logging_handlers(tmp_path / "operator_ktv.log")
    try:
        assert any(isinstance(handler, logging.FileHandler) for handler in handlers)
        assert any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
            for handler in handlers
        )
    finally:
        close_handlers(handlers)
