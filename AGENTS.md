# Project Instructions

## Scope
- Keep changes narrowly focused on the requested task.
- Do not introduce unrelated refactors or tooling changes.

## Commands
- Document verified setup, run, build, and test commands here as they are confirmed.
- Compile check: `python -m compileall -q operator_ktv remote_player build_offline_package.py ktv_paths.py view_logs.py`
- Test suite: `python -m pytest`

## Constraints
- Preserve existing project structure unless a task explicitly requires changing it.
- Treat deployment/offline packaging scripts as production-sensitive.

## Definition of Done
- The relevant command or manual verification path is run when feasible.
- Any skipped verification is called out with the reason.
