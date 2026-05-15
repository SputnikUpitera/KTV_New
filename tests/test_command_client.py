from operator_ktv.network.commands import CommandClient


class CapturingCommandClient(CommandClient):
    def __init__(self):
        super().__init__(ssh_client=None)
        self.calls = []

    def send_command(self, command, params=None):
        self.calls.append((command, params or {}))
        if command == "add_schedule":
            return True, {"schedule_id": 42}, ""
        if command == "update_schedule":
            return True, {"success": True}, ""
        return True, {}, ""


def test_command_client_add_schedule_sends_weekday_contract():
    client = CapturingCommandClient()

    success, schedule_id, error = client.add_schedule(
        weekday=4,
        hour=14,
        minute=5,
        filepath="/remote/oktv/weekly/4/14-05/movie.mp4",
        filename="movie.mp4",
    )

    assert (success, schedule_id, error) == (True, 42, "")
    assert client.calls == [
        (
            "add_schedule",
            {
                "weekday": 4,
                "hour": 14,
                "minute": 5,
                "filepath": "/remote/oktv/weekly/4/14-05/movie.mp4",
                "filename": "movie.mp4",
                "category": "movies",
            },
        )
    ]


def test_command_client_update_schedule_sends_weekday_contract():
    client = CapturingCommandClient()

    success, result, error = client.update_schedule(10, weekday=6, hour=23, minute=59)

    assert (success, result, error) == (True, {"success": True}, "")
    assert client.calls == [
        (
            "update_schedule",
            {
                "schedule_id": 10,
                "weekday": 6,
                "hour": 23,
                "minute": 59,
            },
        )
    ]


def test_command_client_play_clip_file_uses_single_clip_command():
    client = CapturingCommandClient()

    success, result, error = client.play_clip_file("clip.mp4")

    assert (success, result, error) == (True, {}, "")
    assert client.calls == [("play_clip_file", {"filename": "clip.mp4"})]


def test_command_client_sync_playlists_uses_single_clip_list_command():
    client = CapturingCommandClient()

    success, result, error = client.sync_playlists()

    assert (success, result, error) == (True, {}, "")
    assert client.calls == [("sync_playlists", {})]
