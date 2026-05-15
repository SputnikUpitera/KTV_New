import sqlite3

import pytest

from remote_player.storage.database import Database


@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "nested" / "schedule.db"))


def test_database_initializes_schema_and_creates_parent_directory(tmp_path):
    db_path = tmp_path / "data" / "schedule.db"

    db = Database(str(db_path))

    assert str(db.db_path).startswith(str(tmp_path))
    assert db_path.exists()
    with db.get_connection() as conn:
        table_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"schedule", "playlists", "settings"}.issubset(table_names)


def test_schedule_crud_filtering_and_time_lookup(database):
    disabled_id = database.add_schedule(
        0,
        3,
        4,
        "/test-media/oktv/weekly/0/03-04/disabled.mp4",
        "disabled.mp4",
    )
    movie_id = database.add_schedule(
        0,
        3,
        4,
        "/test-media/oktv/weekly/0/03-04/movie.mp4",
        "movie.mp4",
    )
    clip_id = database.add_schedule(
        0,
        3,
        5,
        "/test-media/oktv/clips/morning/clip.mp4",
        "clip.mp4",
        category="clips",
    )

    assert database.toggle_schedule(disabled_id, False)
    assert database.update_schedule(
        movie_id,
        6,
        23,
        59,
        "/test-media/oktv/weekly/6/23-59/movie-new.mp4",
        "movie-new.mp4",
    )

    movie = database.get_schedule(movie_id)
    assert movie["filename"] == "movie-new.mp4"
    assert movie["weekday"] == 6
    assert movie["enabled"] == 1

    enabled_filenames = {
        row["filename"] for row in database.list_schedules(enabled_only=True)
    }
    assert enabled_filenames == {"clip.mp4", "movie-new.mp4"}
    assert [row["id"] for row in database.list_schedules(category="clips")] == [clip_id]
    assert database.get_schedules_for_time(0, 3, 4) == []
    assert [row["id"] for row in database.get_schedules_for_time(6, 23, 59)] == [
        movie_id
    ]

    assert database.remove_schedule(disabled_id)
    assert database.get_schedule(disabled_id) is None
    assert not database.remove_schedule(disabled_id)


def test_weekday_validation_is_enforced(database):
    with pytest.raises(ValueError, match="weekday"):
        database.add_schedule(
            7,
            0,
            0,
            "/test-media/oktv/weekly/7/00-00/movie.mp4",
            "movie.mp4",
        )


def test_old_annual_schedule_schema_is_dropped_without_migration(tmp_path):
    db_path = tmp_path / "schedule.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                minute INTEGER NOT NULL,
                filepath TEXT NOT NULL,
                filename TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                category TEXT DEFAULT 'movies',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO schedule (month, day, hour, minute, filepath, filename)
            VALUES (1, 2, 3, 4, '/old.mp4', 'old.mp4')
            """
        )
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO settings (key, value) VALUES ('volume', '80')")

    db = Database(str(db_path))

    assert db.list_schedules() == []
    assert db.get_setting("volume") == "80"
    with db.get_connection() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(schedule)").fetchall()
        }
    assert "weekday" in columns
    assert "month" not in columns
    assert "day" not in columns


def test_playlist_crud_active_playlist_and_ensure(database):
    first_id, created = database.ensure_playlist("morning", "/clips/morning")
    assert created
    second_id = database.create_playlist("evening", "/clips/evening")

    existing_id, created = database.ensure_playlist("morning", "/clips/morning")
    assert (existing_id, created) == (first_id, False)

    with pytest.raises(ValueError, match="Playlist folder mismatch"):
        database.ensure_playlist("morning", "/clips/new-morning")

    aligned_id, created = database.ensure_playlist(
        "morning",
        "/clips/new-morning",
        folder_aligned=True,
    )
    assert (aligned_id, created) == (first_id, False)
    assert database.get_playlist(first_id)["folder_path"] == "/clips/new-morning"

    assert database.set_active_playlist(first_id)
    assert database.get_active_playlist()["id"] == first_id
    assert database.set_active_playlist(second_id)
    assert database.get_active_playlist()["id"] == second_id
    assert database.get_playlist(first_id)["active"] == 0

    assert [row["name"] for row in database.list_playlists()] == ["evening", "morning"]
    assert database.delete_playlist(first_id)
    assert database.get_playlist_by_name("morning") is None
    assert not database.delete_playlist(first_id)


def test_settings_round_trip(database):
    assert database.get_setting("missing") is None
    assert database.get_setting("missing", default="fallback") == "fallback"

    database.set_setting("volume", "75")
    database.set_setting("display_mode", "fullscreen")
    database.set_setting("volume", "80")

    assert database.get_setting("volume") == "80"
    assert database.get_all_settings() == {
        "display_mode": "fullscreen",
        "volume": "80",
    }
