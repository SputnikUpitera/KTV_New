import pytest

from PyQt6.QtWidgets import QApplication

from operator_ktv.gui.main_window import (
    LINUX_TIME_DISCONNECTED_TEXT,
    LINUX_TIME_UNAVAILABLE_TEXT,
    MainWindow,
    format_linux_time,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    instance = MainWindow()
    instance.startup_timer.stop()
    yield instance
    instance.close()
    instance._wait_for_background_threads(timeout_ms=100)


class FakeCommandClient:
    def __init__(self):
        self.calls = []

    def toggle_play_pause(self):
        self.calls.append("toggle_play_pause")
        return True, {"playlist": {"has_files": True, "transport_available": True}}, ""

    def stop_playback(self):
        self.calls.append("stop_playback")
        return True, {"playlist": {"has_files": True, "transport_available": True, "paused": True}}, ""

    def next_clip(self):
        self.calls.append("next_clip")
        return True, {"playlist": {"has_files": True, "transport_available": True}}, ""

    def toggle_shuffle(self):
        self.calls.append("toggle_shuffle")
        return True, {"playlist": {"has_files": True, "transport_available": True, "shuffle_enabled": True}}, ""


class FakeStatusThread:
    def __init__(self, running=True):
        self.running = running
        self.quit_calls = 0
        self.wait_calls = 0
        self.delete_later_calls = 0

    def isRunning(self):
        return self.running

    def quit(self):
        self.quit_calls += 1

    def wait(self, _timeout_ms):
        self.wait_calls += 1
        return not self.running

    def deleteLater(self):
        self.delete_later_calls += 1


class FakeCloseEvent:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


def test_format_linux_time_uses_daemon_status_field():
    assert format_linux_time(
        {
            "linux_time": {
                "iso": "2026-05-15T12:34:56+03:00",
                "timezone": "MSK",
            }
        }
    ) == "Linux time: 2026-05-15 12:34:56 MSK"


def test_format_linux_time_prefers_daemon_display_value():
    assert format_linux_time(
        {"linux_time": {"iso": "2026-05-15T12:34:56+03:00", "display": "2026-05-15 12:34:56 EEST"}}
    ) == "Linux time: 2026-05-15 12:34:56 EEST"


def test_format_linux_time_handles_missing_time():
    assert format_linux_time({}) == LINUX_TIME_UNAVAILABLE_TEXT


def test_removed_playlist_selector_leaves_schedule_with_wider_splitter(window):
    assert not hasattr(window.clips_tab, "playlist_list")
    assert window.main_splitter.widget(0) is window.movies_tab
    assert window.main_splitter.widget(1) is window.clips_tab
    assert window.main_splitter.sizes()[0] > window.main_splitter.sizes()[1]


def test_transport_controls_disabled_for_empty_clip_list(window):
    window._apply_playback_status(
        {
            "player": {},
            "playlist": {"has_files": False, "transport_available": False},
            "current_playback": {"source": None, "filename": None},
            "next_clip": {"filename": None},
        }
    )

    assert not window.play_pause_btn.isEnabled()
    assert not window.stop_btn.isEnabled()
    assert not window.next_btn.isEnabled()
    assert not window.shuffle_btn.isEnabled()


def test_linux_time_label_updates_from_playback_status(window):
    window._apply_playback_status(
        {
            "linux_time": {
                "iso": "2026-05-15T12:34:56+03:00",
                "timezone": "MSK",
            },
            "player": {},
            "playlist": {"has_files": False, "transport_available": False},
            "current_playback": {"source": None, "filename": None},
            "next_clip": {"filename": None},
        }
    )

    assert window.linux_time_label.text() == "Linux time: 2026-05-15 12:34:56 MSK"


def test_linux_time_label_clears_when_disconnected(window):
    window.linux_time_label.setText("Linux time: 2026-05-15 12:34:56 MSK")
    window.cmd_client = None

    window.refresh_playback_status()

    assert window.linux_time_label.text() == LINUX_TIME_DISCONNECTED_TEXT


def test_safe_action_discards_qaction_checked_argument(window):
    calls = []

    wrapped = window._safe_action(lambda: calls.append("called"))
    wrapped(False)
    wrapped(True)

    assert calls == ["called", "called"]


def test_status_refresh_failure_keeps_window_connected_until_thread_finishes(window):
    thread = FakeStatusThread(running=False)
    window.cmd_client = FakeCommandClient()
    window.status_thread = thread
    window.status_request_pending = True

    window._status_fetch_finished(thread, False, {}, "daemon unavailable")

    assert window.cmd_client is not None
    assert window.status_thread is thread
    assert window.status_request_pending
    assert window.linux_time_label.text() == LINUX_TIME_UNAVAILABLE_TEXT
    assert not window.play_pause_btn.isEnabled()

    window._status_thread_finished(thread)

    assert window.status_thread is None
    assert not window.status_request_pending
    assert thread.delete_later_calls == 1


def test_stale_status_response_after_disconnect_is_ignored(window):
    stale_thread = FakeStatusThread(running=False)
    window.linux_time_label.setText(LINUX_TIME_DISCONNECTED_TEXT)
    window.status_thread = None
    window.status_request_pending = False

    window._status_fetch_finished(
        stale_thread,
        True,
        {
            "linux_time": {"iso": "2026-05-15T12:34:56+03:00", "timezone": "MSK"},
            "player": {},
            "playlist": {"has_files": True, "transport_available": True},
            "current_playback": {"source": "clip", "filename": "clip.mp4"},
            "next_clip": {"filename": None},
        },
        "",
    )

    assert window.linux_time_label.text() == LINUX_TIME_DISCONNECTED_TEXT
    assert not window.status_request_pending


def test_disconnect_detaches_status_worker_without_waiting(window):
    thread = FakeStatusThread(running=True)
    window.cmd_client = FakeCommandClient()
    window.connected = True
    window.status_thread = thread
    window.status_request_pending = True
    window.status_timer.start()

    window.disconnect()

    assert window.status_thread is None
    assert not window.status_request_pending
    assert not window.status_timer.isActive()
    assert thread.quit_calls == 1
    assert thread.wait_calls == 0
    assert thread in window._background_threads
    assert window.linux_time_label.text() == LINUX_TIME_DISCONNECTED_TEXT


def test_status_thread_finished_releases_detached_worker(window):
    thread = FakeStatusThread(running=False)
    window._background_threads.append(thread)

    window._status_thread_finished(thread)

    assert thread not in window._background_threads
    assert thread.delete_later_calls == 1


def test_close_event_stops_status_updates_and_detaches_worker(window):
    thread = FakeStatusThread(running=True)
    event = FakeCloseEvent()
    window.cmd_client = FakeCommandClient()
    window.connected = True
    window.status_thread = thread
    window.status_request_pending = True
    window.status_timer.start()

    window.closeEvent(event)

    assert event.accepted
    assert window._closing
    assert not window.status_timer.isActive()
    assert window.status_thread is None
    assert not window.status_request_pending
    assert thread.quit_calls == 1
    assert thread.wait_calls == 1
    assert thread in window._background_threads


def test_transport_controls_enable_for_available_clip_list(window):
    window._apply_playback_status(
        {
            "player": {},
            "playlist": {
                "has_files": True,
                "transport_available": True,
                "has_active_clip": False,
                "paused": False,
                "shuffle_enabled": False,
            },
            "current_playback": {"source": None, "filename": None},
            "next_clip": {"filename": "next.mp4"},
        }
    )

    assert window.play_pause_btn.isEnabled()
    assert not window.stop_btn.isEnabled()
    assert window.next_btn.isEnabled()
    assert window.shuffle_btn.isEnabled()
    assert window.next_clip_label.text() == "Следующий клип: next.mp4"


def test_transport_controls_reflect_playing_and_shuffle_states(window):
    window._apply_playback_status(
        {
            "player": {"is_paused": False},
            "playlist": {
                "has_files": True,
                "transport_available": True,
                "has_active_clip": True,
                "paused": False,
                "shuffle_enabled": True,
            },
            "current_playback": {"source": "clip", "filename": "clip.mp4"},
            "next_clip": {"filename": "hidden.mp4"},
        }
    )

    assert window.play_pause_btn.isEnabled()
    assert window.stop_btn.isEnabled()
    assert window.next_btn.isEnabled()
    assert window.shuffle_btn.isEnabled()
    assert window.shuffle_btn.isChecked()
    assert not window.next_clip_label.isVisible()
    assert window.current_playback_label.text() == "Клип: clip.mp4"


def test_transport_buttons_dispatch_to_command_client(window):
    client = FakeCommandClient()
    window.cmd_client = client
    window.toggle_play_pause()
    window.stop_playback()
    window.next_clip()
    window.toggle_shuffle()

    assert client.calls == [
        "toggle_play_pause",
        "stop_playback",
        "next_clip",
        "toggle_shuffle",
    ]
