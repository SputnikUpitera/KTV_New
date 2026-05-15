# OperatorKTV Implementation Prompt Plan

This document contains the aligned multi-chat implementation plan for the
OperatorKTV changes. Each chat should stay inside its responsibility boundary and
use the shared header below.

## Global Header For Every Chat

```text
Project: W:\Projects\KTV_New.

Before making changes:
1. Read AGENTS.md in the project root.
2. Do a lightweight memory lookup in W:\Projects\2ndBRAIN for OperatorKTV context.
3. Keep the scope narrow and do not implement adjacent improvements.

Hard constraints:
- Do not add, recommend, or depend on python-vlc.
- Preserve the project's ordinary VLC playback approach.
- Do not change the daemon API bind address or port policy.
- Do not change password storage behavior.
- The old movie schedule is empty. Do not implement schedule data migration.
- Add or update tests for any changed non-trivial logic.
- Required verification: run compileall and pytest unless impossible; explain skipped checks.
```

## Recommended Execution Order

1. Test Infrastructure
2. Crash Diagnostics
3. Weekly Schedule Backend
4. Time Input UX
5. Single Clip Playlist
6. Weekly Movies UI
7. Linux Machine Time
8. No-Console Windows Launch
9. Integration QA

## Chat 1: Test Infrastructure

Start:

```text
Set up a minimal test foundation for the project. Add pytest-based tests that run on Windows without real VLC, PyQt GUI interaction, SSH, or Linux daemon access.

Scope:
- Add a small tests/ suite.
- Add a test requirements file if needed.
- Cover existing pure logic in ktv_paths.py.
- Cover remote_player.storage.database with temporary SQLite databases.
- Do not change runtime behavior except for minimal testability improvements.

Verification:
- python -m compileall -q operator_ktv remote_player build_offline_package.py ktv_paths.py view_logs.py
- python -m pytest
```

Continue:

```text
Continue test infrastructure cleanup. Ensure tests do not touch real user folders, /var/lib/ktv, ~/oktv, network, GUI, or VLC. Use tmp_path or in-memory databases. Document the confirmed test command in AGENTS.md only if it has been verified.
```

## Chat 2: Crash Diagnostics

Start:

```text
Diagnose why the Windows GUI may close unexpectedly. Add defensive crash diagnostics without changing business logic or the visible UI.

Focus:
- Add top-level exception logging for uncaught Python exceptions.
- Log exceptions from Qt slots and worker threads.
- Review QThread and QTimer lifecycle in main_window.py.
- Review disconnect, closeEvent, status polling, log fetching, terminal, and upload flows.
- Ensure failures are written to %USERPROFILE%\.operatorktv\operator_ktv.log instead of silently closing the app.

Tests:
- Add tests for any extracted crash/logging helper.
- Run compileall and pytest.
```

Continue:

```text
Continue crash diagnostics. Check every GUI QThread/QTimer path for premature object destruction, stale callbacks after disconnect, and exceptions escaping worker code. Produce a short report of likely crash causes and manual verification scenarios.
```

## Chat 3: Weekly Schedule Backend

Start:

```text
Replace the movie schedule backend from annual month/day recurrence to weekly weekday/hour/minute recurrence.

Scope:
- Use weekday convention 0=Monday through 6=Sunday and document it in code.
- Update SQLite schema. The old schedule is empty, so do not preserve old schedule rows.
- Update Database methods, Scheduler, daemon command handlers, CommandClient, ScheduleItem, and path helpers.
- Scheduler must run movie jobs weekly on the selected weekday and time.
- Add validation for weekday values and unsafe path/name input.

Tests:
- Database add/list/update/toggle/remove weekly schedules.
- Weekday validation.
- Weekly movie path build/parse.
- Scheduler day_of_week mapping.
- Daemon handlers with fakes where practical.

Verification:
- compileall
- pytest
```

Continue:

```text
Continue weekly backend work. Search for remaining month/day movie schedule usage and either remove it or convert it to weekday semantics. Check daemon, database, scheduler, command client, models, path helpers, installer docs, and README only where needed. Re-run compileall and pytest.
```

## Chat 4: Time Input UX

Start:

```text
Improve the schedule time input UX while keeping the current visual concept.

Requirements:
- Clicking the hour value selects the hour for quick replacement.
- Clicking the minute value selects the minute for quick replacement.
- Tab and Shift+Tab switch between hour and minute.
- Left/Right arrows switch between hour and minute.
- Up/Down arrows adjust the selected field.
- Numeric typing replaces the selected field predictably.
- Preserve existing dialog callers.

Primary file:
- operator_ktv/gui/schedule_dialog.py

Tests:
- Extract pure time normalization/field-selection logic if useful and test it.
- Cover boundaries: hours 00-23, minutes 00-59.
- Run compileall and pytest.
```

Continue:

```text
Continue time input UX. Manually reason through one-digit input, two-digit input, replacing selected values, Tab, Shift+Tab, Left/Right, Up/Down, and boundary wrapping or clamping. Fix only issues in this dialog and re-run checks.
```

## Chat 5: Single Clip Playlist

Start:

```text
Remove multi-playlist clip management. The system should expose one clip list only.

Scope:
- Remove the playlist selector from the GUI.
- Keep one clip list with add, delete, and play-selected actions.
- Backend should use one default clips folder/list.
- Do not delete existing clip files.
- No migration of old playlist records is required.
- Add validation against unsafe names and path traversal.

Files likely involved:
- operator_ktv/gui/clips_tab.py
- operator_ktv/gui/main_window.py
- remote_player/playlist_manager.py
- remote_player/daemon.py
- remote_player/storage/database.py
- ktv_paths.py

Tests:
- Default clip list behavior.
- Video extension filtering.
- Path validation rejects ../, absolute paths, and separators where unsafe.
- Transport controls with fake player where practical.
```

Continue:

```text
Continue single clip playlist work. Verify play/pause, stop, next, shuffle, play selected file, delete file, empty list, missing clips folder, and disconnected GUI states. Ensure the removed playlist selector frees layout space for the weekly movie schedule.
```

## Chat 6: Weekly Movies UI

Start:

```text
Redesign the movie schedule block for weekly scheduling.

Requirements:
- Replace month-based UI with seven columns: Monday through Sunday.
- Each day column has a "+" button.
- "+" opens video file selection, then the time selection dialog.
- Each day displays scheduled movies with time, filename, and enabled/disabled state.
- Remove month-based add flow.
- The movie schedule area should become the primary wide area of the window.

Tests:
- Extract and test pure grouping by weekday/time.
- Test schedule item label formatting.
- Run compileall and pytest.
- If full Qt UI tests are not added, provide a manual GUI checklist.
```

Continue:

```text
Continue weekly movies UI. Verify integration with weekly backend API: add, list, update time, toggle enabled, remove, refresh. Check disabled state without connection, empty weekdays, long filenames, and drag/drop if retained. Re-run compileall and pytest.
```

## Chat 7: Linux Machine Time

Start:

```text
Show the current Linux machine time at the bottom of the main Windows GUI.

Scope:
- Prefer adding the Linux time to daemon get_status.
- Display it in the bottom area of main_window.py.
- Update periodically without blocking the UI.
- On disconnect, clear it or show a disconnected state.
- If daemon is unavailable but SSH is connected, an SSH fallback is acceptable only if non-blocking.

Tests:
- Daemon status includes a stable time field.
- Any formatting helper is tested.
- Run compileall and pytest.
```

Continue:

```text
Continue Linux time display. Check that refresh failures do not block or close the GUI, no extra worker threads are leaked, and disconnect/closeEvent stops updates cleanly. Re-run checks.
```

## Chat 8: No-Console Windows Launch

Start:

```text
Make the Windows GUI launch without showing a Python console.

Scope:
- Inspect current launch paths in README, .vscode, scripts, and entry points.
- Add the smallest working no-console launcher, preferably a .pyw launcher or documented pythonw.exe command.
- Preserve debug launch with console/log visibility.
- Keep logging in %USERPROFILE%\.operatorktv\operator_ktv.log.

Tests:
- compileall for launcher and main entry.
- Verify imports work from the launcher.
- Do not change daemon or business logic.
```

Continue:

```text
Continue no-console launch work. Verify on Windows that the new launch method opens the GUI without a console, uses the correct working directory/import path, and still writes logs. Update README with normal launch, debug launch, and log location.
```

## Chat 9: Integration QA

Start:

```text
Integrate all completed task branches/changes:
- test infrastructure
- crash diagnostics
- weekly schedule backend
- time input UX
- single clip playlist
- weekly movies UI
- Linux time display
- no-console launcher

Rules:
- Resolve conflicts minimally.
- Do not add new features.
- Preserve all hard constraints from the global header.

Verification:
- python -m compileall -q operator_ktv remote_player build_offline_package.py ktv_paths.py view_logs.py
- python -m pytest
- Launch GUI to the startup window if possible.
- Check offline package build only if it does not require a long dependency download.
```

Continue:

```text
Continue integration QA. Validate end-to-end behavior: SSH connection, daemon ping/status, add movie to weekday/time, edit time, toggle, remove, clip add/delete/play/next/shuffle, Linux time display, clean app exit without lingering threads. Produce a concise Windows + Linux manual checklist and state what must be rebuilt or reinstalled on Linux.
```
