from types import SimpleNamespace

from operator_ktv.gui.movie_schedule_logic import (
    format_schedule_item_label,
    group_schedules_by_weekday,
)


def schedule(weekday, hour, minute, filename, enabled=True):
    return SimpleNamespace(
        weekday=weekday,
        hour=hour,
        minute=minute,
        filename=filename,
        enabled=enabled,
    )


def test_group_schedules_by_weekday_returns_all_days_sorted_by_time_and_name():
    monday_late = schedule(0, 18, 0, "B.mp4")
    monday_early = schedule(0, 9, 30, "z.mp4")
    monday_same_time = schedule(0, 9, 30, "A.mp4")
    sunday = schedule(6, 23, 59, "Sunday.mp4")
    invalid = schedule(7, 12, 0, "ignored.mp4")

    grouped = group_schedules_by_weekday(
        [monday_late, sunday, invalid, monday_early, monday_same_time]
    )

    assert list(grouped) == list(range(7))
    assert grouped[0] == [monday_same_time, monday_early, monday_late]
    assert grouped[1] == []
    assert grouped[6] == [sunday]
    assert invalid not in grouped[0]
    assert invalid not in grouped[6]


def test_format_schedule_item_label_includes_state_time_and_filename():
    enabled = schedule(2, 7, 5, "Morning Movie.mp4", enabled=True)
    disabled = schedule(4, 21, 45, "Night Movie.mkv", enabled=False)

    assert format_schedule_item_label(enabled) == "[on] 07:05  Morning Movie.mp4"
    assert format_schedule_item_label(disabled) == "[off] 21:45  Night Movie.mkv"
    assert (
        format_schedule_item_label(disabled, enabled_text="[enabled]", disabled_text="[disabled]")
        == "[disabled] 21:45  Night Movie.mkv"
    )
