import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class FakeCronTrigger:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeBackgroundScheduler:
    def __init__(self):
        self.jobs = []

    def start(self):
        pass

    def shutdown(self, wait=False):
        pass

    def remove_all_jobs(self):
        self.jobs.clear()

    def add_job(self, **kwargs):
        self.jobs.append(kwargs)
        return SimpleNamespace(id=kwargs["id"], name=kwargs["name"], next_run_time=None)

    def get_jobs(self):
        return []


@pytest.fixture
def scheduler_module(monkeypatch):
    background_module = types.ModuleType("apscheduler.schedulers.background")
    background_module.BackgroundScheduler = FakeBackgroundScheduler
    cron_module = types.ModuleType("apscheduler.triggers.cron")
    cron_module.CronTrigger = FakeCronTrigger

    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", background_module)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers", types.ModuleType("apscheduler.triggers"))
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.cron", cron_module)
    sys.modules.pop("remote_player.scheduler", None)
    module = importlib.import_module("remote_player.scheduler")
    yield module
    sys.modules.pop("remote_player.scheduler", None)


def test_scheduler_day_of_week_mapping_uses_monday_zero_convention(scheduler_module):
    scheduler = scheduler_module.Scheduler(database=None, player=None)

    scheduler._add_schedule_job(
        {
            "id": 10,
            "weekday": 6,
            "hour": 23,
            "minute": 59,
            "filepath": "/tmp/movie.mp4",
            "filename": "movie.mp4",
        }
    )

    added_job = scheduler.scheduler.jobs[0]
    assert added_job["trigger"].kwargs == {
        "day_of_week": 6,
        "hour": 23,
        "minute": 59,
    }
    assert "weekday 6" in added_job["name"]


def test_scheduler_rejects_invalid_weekday(scheduler_module):
    with pytest.raises(ValueError, match="weekday"):
        scheduler_module.Scheduler._cron_day_of_week(7)
