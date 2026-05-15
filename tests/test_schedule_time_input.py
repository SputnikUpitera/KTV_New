import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QTime, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDateTimeEdit

from operator_ktv.gui.schedule_dialog import ScheduleTimeEdit
from operator_ktv.gui.time_input_logic import (
    HOUR_FIELD,
    MINUTE_FIELD,
    adjust_time_parts,
    apply_numeric_time_input,
    next_time_field,
    normalize_time_field,
    normalize_time_parts,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def press_key(widget, key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
    QApplication.sendEvent(widget, event)


def test_normalize_time_parts_clamps_to_valid_boundaries():
    assert normalize_time_parts(-1, -1) == (0, 0)
    assert normalize_time_parts(0, 0) == (0, 0)
    assert normalize_time_parts(23, 59) == (23, 59)
    assert normalize_time_parts(24, 60) == (23, 59)


def test_normalize_time_field_rejects_values_outside_hour_and_minute_bounds():
    assert normalize_time_field(HOUR_FIELD, -10) == 0
    assert normalize_time_field(HOUR_FIELD, 24) == 23
    assert normalize_time_field(MINUTE_FIELD, -10) == 0
    assert normalize_time_field(MINUTE_FIELD, 60) == 59


def test_next_time_field_switches_between_hour_and_minute():
    assert next_time_field(HOUR_FIELD) == MINUTE_FIELD
    assert next_time_field(MINUTE_FIELD) == HOUR_FIELD
    assert next_time_field(HOUR_FIELD, reverse=True) == MINUTE_FIELD
    assert next_time_field(MINUTE_FIELD, reverse=True) == HOUR_FIELD


def test_adjust_time_parts_wraps_hours_at_boundaries():
    assert adjust_time_parts(23, 15, HOUR_FIELD, 1) == (0, 15)
    assert adjust_time_parts(0, 15, HOUR_FIELD, -1) == (23, 15)


def test_adjust_time_parts_wraps_minutes_at_boundaries():
    assert adjust_time_parts(12, 59, MINUTE_FIELD, 1) == (12, 0)
    assert adjust_time_parts(12, 0, MINUTE_FIELD, -1) == (12, 59)


def test_numeric_typing_replaces_hour_with_one_or_two_digits():
    hour, minute, pending = apply_numeric_time_input(12, 34, HOUR_FIELD, "", "2")
    assert (hour, minute, pending) == (2, 34, "2")

    hour, minute, pending = apply_numeric_time_input(hour, minute, HOUR_FIELD, pending, "3")
    assert (hour, minute, pending) == (23, 34, "")


def test_numeric_typing_replaces_minute_with_one_or_two_digits():
    hour, minute, pending = apply_numeric_time_input(12, 34, MINUTE_FIELD, "", "5")
    assert (hour, minute, pending) == (12, 5, "5")

    hour, minute, pending = apply_numeric_time_input(hour, minute, MINUTE_FIELD, pending, "9")
    assert (hour, minute, pending) == (12, 59, "")


def test_numeric_typing_keeps_single_digit_ready_for_a_second_digit():
    assert apply_numeric_time_input(12, 34, HOUR_FIELD, "", "9") == (9, 34, "9")
    assert apply_numeric_time_input(12, 34, MINUTE_FIELD, "", "6") == (12, 6, "6")


def test_numeric_typing_clamps_out_of_range_two_digit_hour():
    assert apply_numeric_time_input(12, 34, HOUR_FIELD, "2", "4") == (23, 34, "")
    assert apply_numeric_time_input(12, 34, HOUR_FIELD, "9", "9") == (23, 34, "")


def test_numeric_typing_clamps_out_of_range_two_digit_minute():
    assert apply_numeric_time_input(12, 34, MINUTE_FIELD, "6", "5") == (12, 59, "")


def test_numeric_typing_requires_one_digit():
    with pytest.raises(ValueError, match="single numeric"):
        apply_numeric_time_input(12, 34, HOUR_FIELD, "", "12")


def test_time_edit_left_right_and_tab_switch_between_fields(app):
    edit = ScheduleTimeEdit()
    edit.setDisplayFormat("HH:mm")
    edit.setTime(QTime(12, 34))

    press_key(edit, Qt.Key.Key_Right)
    assert edit.currentSection() == QDateTimeEdit.Section.MinuteSection

    press_key(edit, Qt.Key.Key_Left)
    assert edit.currentSection() == QDateTimeEdit.Section.HourSection

    press_key(edit, Qt.Key.Key_Tab)
    assert edit.currentSection() == QDateTimeEdit.Section.MinuteSection

    press_key(edit, Qt.Key.Key_Backtab, modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert edit.currentSection() == QDateTimeEdit.Section.HourSection


def test_time_edit_up_down_wrap_selected_field(app):
    edit = ScheduleTimeEdit()
    edit.setDisplayFormat("HH:mm")
    edit.setTime(QTime(23, 59))

    press_key(edit, Qt.Key.Key_Up)
    assert (edit.time().hour(), edit.time().minute()) == (0, 59)

    press_key(edit, Qt.Key.Key_Right)
    press_key(edit, Qt.Key.Key_Up)
    assert (edit.time().hour(), edit.time().minute()) == (0, 0)

    press_key(edit, Qt.Key.Key_Down)
    assert (edit.time().hour(), edit.time().minute()) == (0, 59)


def test_time_edit_numeric_keys_replace_selected_field_and_clamp(app):
    edit = ScheduleTimeEdit()
    edit.setDisplayFormat("HH:mm")
    edit.setTime(QTime(12, 34))

    press_key(edit, Qt.Key.Key_9, "9")
    assert (edit.time().hour(), edit.time().minute()) == (9, 34)

    press_key(edit, Qt.Key.Key_9, "9")
    assert (edit.time().hour(), edit.time().minute()) == (23, 34)

    press_key(edit, Qt.Key.Key_Right)
    press_key(edit, Qt.Key.Key_6, "6")
    assert (edit.time().hour(), edit.time().minute()) == (23, 6)

    press_key(edit, Qt.Key.Key_5, "5")
    assert (edit.time().hour(), edit.time().minute()) == (23, 59)
