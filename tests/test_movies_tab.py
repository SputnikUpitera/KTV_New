from pathlib import PurePosixPath

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from operator_ktv.gui.movies_tab import MoviesTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_message_boxes(monkeypatch):
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.QMessageBox.critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )


class FakeSSHClient:
    def __init__(self):
        self.deleted = []
        self.uploaded = []

    def get_remote_home(self):
        return "/home/operator"

    def delete_file(self, path):
        self.deleted.append(path)
        return True, ""


class FakeCommandClient:
    def __init__(self, schedules=None):
        self.schedules = list(schedules or [])
        self.calls = []
        self.next_id = 100

    def sync_schedules(self):
        self.calls.append(("sync_schedules",))
        return True, {}, ""

    def list_schedules(self, enabled_only=False, category=None):
        self.calls.append(("list_schedules", enabled_only, category))
        return True, list(self.schedules), ""

    def add_schedule(self, **params):
        self.calls.append(("add_schedule", params))
        schedule_id = self.next_id
        self.next_id += 1
        self.schedules.append({"id": schedule_id, **params, "enabled": True})
        return True, schedule_id, ""

    def update_schedule(self, schedule_id, weekday, hour, minute):
        self.calls.append(("update_schedule", schedule_id, weekday, hour, minute))
        for schedule in self.schedules:
            if schedule["id"] == schedule_id:
                schedule.update({"weekday": weekday, "hour": hour, "minute": minute})
        return True, {}, ""

    def toggle_schedule(self, schedule_id, enabled):
        self.calls.append(("toggle_schedule", schedule_id, enabled))
        for schedule in self.schedules:
            if schedule["id"] == schedule_id:
                schedule["enabled"] = enabled
        return True, ""

    def remove_schedule(self, schedule_id):
        self.calls.append(("remove_schedule", schedule_id))
        self.schedules = [schedule for schedule in self.schedules if schedule["id"] != schedule_id]
        return True, ""


class FakeScheduleDialog:
    slot = (0, 12, 0)

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def exec(self):
        return True

    def get_schedule_slot(self):
        return self.slot


class FakeUrl:
    def __init__(self, local_file):
        self.local_file = local_file

    def toLocalFile(self):
        return self.local_file


class FakeMimeData:
    def __init__(self, files):
        self.files = files

    def hasUrls(self):
        return True

    def urls(self):
        return [FakeUrl(file) for file in self.files]


class FakeDropEvent:
    def __init__(self, files):
        self.files = files
        self.accepted = False

    def mimeData(self):
        return FakeMimeData(self.files)

    def acceptProposedAction(self):
        self.accepted = True


def movie_schedule(
    schedule_id=1,
    weekday=0,
    hour=9,
    minute=30,
    filename="movie.mp4",
    enabled=True,
):
    return {
        "id": schedule_id,
        "weekday": weekday,
        "hour": hour,
        "minute": minute,
        "filepath": str(PurePosixPath("/home/operator/oktv/weekly") / str(weekday) / f"{hour:02d}-{minute:02d}" / filename),
        "filename": filename,
        "enabled": enabled,
        "category": "movies",
    }


def select_first_item(widget, weekday):
    schedule_list = widget.weekday_lists[weekday]
    schedule_list.setCurrentRow(0)
    return schedule_list.currentItem()


def test_disconnected_movies_tab_disables_weekly_schedule_actions(app):
    widget = MoviesTab()

    assert not widget.week_grid.isEnabled()
    assert not widget.refresh_btn.isEnabled()
    assert not widget.edit_btn.isEnabled()
    assert not widget.toggle_btn.isEnabled()
    assert not widget.delete_btn.isEnabled()
    assert all(not widgets["button"].isEnabled() for widgets in widget.weekday_columns.values())
    assert all(widget.weekday_lists[weekday].count() == 0 for weekday in range(7))


def test_refresh_lists_weekly_movies_and_leaves_empty_weekdays_blank(app):
    long_name = "Very Long Movie Filename That Should Remain Visible In The Schedule Column 2026.mp4"
    cmd = FakeCommandClient(
        [
            movie_schedule(schedule_id=1, weekday=2, hour=21, minute=5, filename=long_name, enabled=False),
            movie_schedule(schedule_id=2, weekday=0, hour=8, minute=0, filename="morning.mp4"),
            movie_schedule(schedule_id=3, weekday=0, hour=7, minute=30, filename="early.mp4"),
        ]
    )
    widget = MoviesTab(FakeSSHClient(), cmd)

    widget.refresh_schedules(do_sync=True)

    assert ("sync_schedules",) in cmd.calls
    assert ("list_schedules", False, "movies") in cmd.calls
    assert widget.weekday_lists[0].count() == 2
    assert widget.weekday_lists[0].item(0).text().endswith("07:30  early.mp4")
    assert widget.weekday_lists[0].item(1).text().endswith("08:00  morning.mp4")
    assert widget.weekday_lists[1].count() == 0
    assert widget.weekday_lists[2].count() == 1
    assert long_name in widget.weekday_lists[2].item(0).text()
    assert widget.weekday_lists[2].item(0).toolTip().endswith(long_name)


def test_refresh_ignores_legacy_annual_schedule_rows(app):
    cmd = FakeCommandClient(
        [
            {
                "id": 99,
                "month": 5,
                "day": 15,
                "hour": 10,
                "minute": 30,
                "filepath": "/home/operator/oktv/05/15/legacy.mp4",
                "filename": "legacy.mp4",
                "enabled": True,
                "category": "movies",
            },
            movie_schedule(schedule_id=2, weekday=4, hour=20, minute=15, filename="weekly.mp4"),
        ]
    )
    widget = MoviesTab(FakeSSHClient(), cmd)

    widget.refresh_schedules()

    assert len(widget.schedules) == 1
    assert widget.schedules[0].filename == "weekly.mp4"
    assert widget.weekday_lists[4].count() == 1


def test_add_movie_uses_weekly_api_uploads_then_refreshes(app, tmp_path, monkeypatch):
    local_movie = tmp_path / "new_movie.mp4"
    local_movie.write_text("not real video")
    ssh = FakeSSHClient()
    cmd = FakeCommandClient()
    widget = MoviesTab(ssh, cmd)
    FakeScheduleDialog.slot = (3, 14, 25)
    monkeypatch.setattr("operator_ktv.gui.movies_tab.ScheduleDialog", FakeScheduleDialog)
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.QFileDialog.getOpenFileNames",
        lambda *args, **kwargs: ([str(local_movie)], ""),
    )
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.upload_file_with_progress",
        lambda parent, ssh_client, local_path, remote_path: (
            ssh.uploaded.append((local_path, remote_path)) is None,
            "",
        ),
    )

    widget.add_movie_for_weekday(3)

    expected_remote = "/home/operator/oktv/weekly/3/14-25/new_movie.mp4"
    assert ssh.uploaded == [(str(local_movie), expected_remote)]
    assert cmd.calls[0] == (
        "add_schedule",
        {
            "weekday": 3,
            "hour": 14,
            "minute": 25,
            "filepath": expected_remote,
            "filename": "new_movie.mp4",
            "category": "movies",
        },
    )
    assert cmd.calls[-1] == ("list_schedules", False, "movies")


def test_update_time_toggle_and_remove_use_weekly_api_then_refresh(app, monkeypatch):
    schedule = movie_schedule(schedule_id=42, weekday=1, hour=10, minute=0, filename="edit.mp4")
    ssh = FakeSSHClient()
    cmd = FakeCommandClient([schedule])
    widget = MoviesTab(ssh, cmd)
    widget.refresh_schedules()
    monkeypatch.setattr("operator_ktv.gui.movies_tab.ScheduleDialog", FakeScheduleDialog)
    monkeypatch.setattr(
        "operator_ktv.gui.movies_tab.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    FakeScheduleDialog.slot = (5, 18, 45)
    select_first_item(widget, 1)
    widget.edit_selected_schedule()

    select_first_item(widget, 5)
    widget.toggle_selected_schedule()

    select_first_item(widget, 5)
    widget.delete_selected()

    assert ("update_schedule", 42, 5, 18, 45) in cmd.calls
    assert ("toggle_schedule", 42, False) in cmd.calls
    assert ("remove_schedule", 42) in cmd.calls
    assert ssh.deleted == ["/home/operator/oktv/weekly/1/10-00/edit.mp4"]
    assert cmd.calls.count(("list_schedules", False, "movies")) == 4


def test_drag_drop_on_weekday_column_retains_add_flow(app, tmp_path, monkeypatch):
    local_movie = tmp_path / "drop.webm"
    local_movie.write_text("not real video")
    widget = MoviesTab(FakeSSHClient(), FakeCommandClient())
    added = []
    monkeypatch.setattr(widget, "add_file_to_schedule", lambda file_path, weekday: added.append((file_path, weekday)))
    event = FakeDropEvent([str(local_movie), str(tmp_path / "notes.txt")])

    widget.drop_event(event, 6)

    assert added == [(str(local_movie), 6)]
    assert event.accepted
