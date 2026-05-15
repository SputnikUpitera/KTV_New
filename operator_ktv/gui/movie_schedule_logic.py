"""Pure helpers for the weekly movie schedule view."""


def group_schedules_by_weekday(schedules):
    """Group schedules into Monday=0 through Sunday=6 buckets sorted by time."""
    grouped = {weekday: [] for weekday in range(7)}
    sorted_schedules = sorted(
        schedules,
        key=lambda item: (
            item.weekday,
            item.hour,
            item.minute,
            item.filename.lower(),
        ),
    )
    for schedule in sorted_schedules:
        if 0 <= schedule.weekday <= 6:
            grouped[schedule.weekday].append(schedule)
    return grouped


def format_schedule_item_label(schedule, enabled_text="[on]", disabled_text="[off]"):
    """Format one schedule row with state, HH:mm time, and filename."""
    state = enabled_text if schedule.enabled else disabled_text
    return f"{state} {schedule.hour:02d}:{schedule.minute:02d}  {schedule.filename}"
