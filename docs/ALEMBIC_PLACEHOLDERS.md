# Temporary Alembic placeholders and merge revisions

This repository contains temporary placeholder and merge Alembic migrations that were added to recover from a missing migration file during deployment.

Files added temporarily:
- alembic/versions/66054e00253c_missing_placeholder.py
- alembic/versions/merge_66054e00253c_c3c244e4539d.py
- other merge files created to unify heads

Reason:
- A missing Alembic revision caused `alembic upgrade head` to fail on Render.
- Temporary placeholder and merge revisions were created to allow the revision graph to be built and to complete the upgrade.

Action items:
1. Try to recover the original migration file for revision `66054e00253c` from history, forks, or other branches.
2. If the original file is recovered, replace the placeholder file with the original content and remove these temporary files with a PR.
3. If the original cannot be recovered, keep these files but document them clearly (this file) and schedule a follow-up to avoid confusion.

If you need help restoring or removing placeholders, follow-up steps are documented in the repository issue tracker.