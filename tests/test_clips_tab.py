import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from operator_ktv.gui.clips_tab import ClipsTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeSSHClient:
    def __init__(self, files=None, list_success=True, error="missing"):
        self.files = files or []
        self.list_success = list_success
        self.error = error
        self.deleted = []

    def get_remote_daemon_config(self):
        return {"clips_folder": "~/oktv/clips"}

    def get_remote_home(self):
        return "/home/operator"

    def list_directory(self, remote_path):
        self.listed_path = remote_path
        if not self.list_success:
            return False, [], self.error
        return True, list(self.files), ""

    def delete_file(self, remote_path):
        self.deleted.append(remote_path)
        return True, ""


class FakeCommandClient:
    def __init__(self):
        self.played = []
        self.sync_calls = 0

    def sync_playlists(self):
        self.sync_calls += 1
        return True, {}, ""

    def play_clip_file(self, filename):
        self.played.append(filename)
        return True, {}, ""


def item_payload(widget):
    item = widget.files_list.currentItem()
    return item.data(Qt.ItemDataRole.UserRole) if item else None


def test_disconnected_clips_tab_has_placeholder_and_disabled_actions(app):
    widget = ClipsTab()

    assert not widget.files_list.isEnabled()
    assert not widget.add_file_btn.isEnabled()
    assert not widget.play_file_btn.isEnabled()
    assert not widget.delete_file_btn.isEnabled()
    assert widget.files_list.item(0).text() == "Нет подключения"


def test_refresh_clips_shows_empty_list_state(app):
    widget = ClipsTab(FakeSSHClient(files=[]), FakeCommandClient())

    widget.refresh_clips()

    assert widget.files_list.item(0).text() == "Файлы пока не добавлены"
    assert item_payload(widget) is None
    assert widget.add_file_btn.isEnabled()
    assert not widget.play_file_btn.isEnabled()
    assert not widget.delete_file_btn.isEnabled()


def test_refresh_clips_shows_missing_folder_state(app):
    ssh = FakeSSHClient(list_success=False, error="No such file")
    widget = ClipsTab(ssh, FakeCommandClient())

    widget.refresh_clips()

    assert ssh.listed_path == "/home/operator/oktv/clips"
    assert "Не удалось прочитать каталог" in widget.files_list.item(0).text()
    assert item_payload(widget) is None
    assert widget.add_file_btn.isEnabled()
    assert not widget.play_file_btn.isEnabled()
    assert not widget.delete_file_btn.isEnabled()


def test_refresh_clips_filters_video_files_and_unsafe_names(app):
    widget = ClipsTab(
        FakeSSHClient(files=["b.webm", "notes.txt", "../bad.mp4", "a.MP4", "nested/bad.mkv"]),
        FakeCommandClient(),
    )

    widget.refresh_clips()

    assert [widget.files_list.item(index).text() for index in range(widget.files_list.count())] == [
        "a.MP4",
        "b.webm",
    ]
    assert widget.play_file_btn.isEnabled()
    assert widget.delete_file_btn.isEnabled()


def test_play_selected_file_uses_single_clip_command(app):
    cmd = FakeCommandClient()
    widget = ClipsTab(FakeSSHClient(files=["clip.mp4"]), cmd)
    widget.refresh_clips()

    widget.play_selected_file()

    assert cmd.played == ["clip.mp4"]
    assert cmd.sync_calls == 1


def test_refresh_clips_can_sync_daemon_clip_list(app):
    cmd = FakeCommandClient()
    widget = ClipsTab(FakeSSHClient(files=["clip.mp4"]), cmd)

    widget.refresh_clips(do_sync=True)

    assert cmd.sync_calls == 1


def test_delete_selected_file_removes_default_clip_path(app, monkeypatch):
    ssh = FakeSSHClient(files=["clip.mp4"])
    widget = ClipsTab(ssh, FakeCommandClient())
    widget.refresh_clips()
    monkeypatch.setattr(
        "operator_ktv.gui.clips_tab.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    widget.delete_selected_file()

    assert ssh.deleted == ["/home/operator/oktv/clips/clip.mp4"]
