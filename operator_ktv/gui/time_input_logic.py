"""Pure helpers for schedule time field editing."""

from typing import Literal

TimeField = Literal["hour", "minute"]

HOUR_FIELD: TimeField = "hour"
MINUTE_FIELD: TimeField = "minute"

_FIELD_MAX = {
    HOUR_FIELD: 23,
    MINUTE_FIELD: 59,
}


def normalize_time_field(field: TimeField, value: int) -> int:
    """Clamp a time field value to its valid range."""
    return max(0, min(int(value), _FIELD_MAX[field]))


def normalize_time_parts(hour: int, minute: int) -> tuple[int, int]:
    """Clamp hour and minute values to a valid HH:mm time."""
    return (
        normalize_time_field(HOUR_FIELD, hour),
        normalize_time_field(MINUTE_FIELD, minute),
    )


def next_time_field(current: TimeField, reverse: bool = False) -> TimeField:
    """Move between the two editable time fields."""
    if current == HOUR_FIELD:
        return MINUTE_FIELD if not reverse else MINUTE_FIELD
    return HOUR_FIELD


def adjust_time_parts(
    hour: int,
    minute: int,
    field: TimeField,
    delta: int,
) -> tuple[int, int]:
    """Adjust one time field, wrapping inside that field's range."""
    hour, minute = normalize_time_parts(hour, minute)
    maximum = _FIELD_MAX[field]

    if field == HOUR_FIELD:
        hour = (hour + delta) % (maximum + 1)
    else:
        minute = (minute + delta) % (maximum + 1)

    return hour, minute


def apply_numeric_time_input(
    hour: int,
    minute: int,
    field: TimeField,
    pending_digits: str,
    digit: str,
) -> tuple[int, int, str]:
    """Replace the selected field with one or two typed digits.

    The first digit immediately replaces the selected value. A second digit
    completes a two-digit replacement. Out-of-range two-digit input is clamped
    to the field maximum.
    """
    if len(digit) != 1 or not digit.isdigit():
        raise ValueError("digit must be a single numeric character")

    hour, minute = normalize_time_parts(hour, minute)
    maximum = _FIELD_MAX[field]
    digits = (pending_digits[-1:] + digit) if pending_digits else digit
    value = int(digits)

    if len(digits) == 2:
        value = min(value, maximum)
        pending_digits = ""
    else:
        pending_digits = digits

    if field == HOUR_FIELD:
        hour = value
    else:
        minute = value

    return hour, minute, pending_digits
