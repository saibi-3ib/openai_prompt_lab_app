"""Admin blueprint to manually run worker.py with security checks, CSRF and logging."""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
import os
import sys
import subprocess
from pathlib import Path
import time
import logging

admin_bp = Blueprint("admin_worker", __name__, template_folder="templates")

# Paths for PID / logs (adjust if needed)
PID_FILE = Path("/tmp/worker_runner.pid")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "worker_run.log"
ADMIN_ACTION_LOG = LOG_DIR / "admin_actions.log"

# Setup logger for admin actions (app-level logging may already exist; this is supplemental)
logger = logging.getLogger("admin_worker")
if not logger.handlers:
    handler = logging.FileHandler(str(ADMIN_ACTION_LOG))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def is_worker_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False
    # POSIX check
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # process exists but we can't signal it
        return True
    return True


def require_admin_or_abort():
    # Replace this check with your project's admin check if different
    if not (current_user and getattr(current_user, "is_authenticated", False) and getattr(current_user, "is_admin", False)):
        abort(403)


@admin_bp.route("/admin/worker", methods=["GET", "POST"])
@login_required
def worker_settings():
    # ensure admin
    require_admin_or_abort()

    status = "running" if is_worker_running() else "stopped"
    pid = None
    try:
        pid = int(PID_FILE.read_text().strip()) if PID_FILE.exists() else None
    except Exception:
        pid = None

    if request.method == "POST":
        # CSRF is enforced by Flask-WTF CSRFProtect globally (see app init)
        action = request.form.get("action")
        confirm_phrase = request.form.get("confirm_phrase", "").strip()
        required_phrase = current_app.config.get("WORKER_CONFIRM_PHRASE", "RUN_WORKER")

        if action == "start_worker":
            if is_worker_running():
                flash("Worker is already running.", "warning")
                logger.info("start_worker attempted but worker already running (user=%s)", getattr(current_user, "id", None))
                return redirect(url_for(".worker_settings"))

            # confirm phrase check (extra human safety)
            if confirm_phrase != required_phrase:
                flash("Confirmation phrase is incorrect.", "danger")
                logger.warning("start_worker confirmation phrase mismatch (user=%s)", getattr(current_user, "id", None))
                return redirect(url_for(".worker_settings"))

            # Build command: same python executable
            cmd = [sys.executable, "worker.py", "--run-once", "--seed-test"]

            # Working directory: prefer app root_path if worker.py in package; otherwise cwd
            cwd = current_app.root_path if (Path(current_app.root_path) / "worker.py").exists() else os.getcwd()

            # Start detached process and log output
            try:
                with open(LOG_FILE, "ab") as out:
                    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, cwd=cwd, env=os.environ.copy())
                PID_FILE.write_text(str(proc.pid))
                flash(f"Worker started (pid {proc.pid}). Logs: {LOG_FILE}", "success")
                logger.info("Worker started by user=%s pid=%s cmd=%s", getattr(current_user, "id", None), proc.pid, " ".join(cmd))
            except Exception as e:
                flash(f"Failed to start worker: {e}", "danger")
                logger.exception("Failed to start worker (user=%s): %s", getattr(current_user, "id", None), e)
            return redirect(url_for(".worker_settings"))

        if action == "stop_worker":
            if not is_worker_running():
                flash("No worker running.", "info")
                logger.info("stop_worker called but no worker running (user=%s)", getattr(current_user, "id", None))
                return redirect(url_for(".worker_settings"))
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, 15)  # SIGTERM
                time.sleep(1)
                if is_worker_running():
                    os.kill(pid, 9)  # SIGKILL
                try:
                    PID_FILE.unlink()
                except Exception:
                    pass
                flash("Worker stopped.", "success")
                logger.info("Worker stopped by user=%s pid=%s", getattr(current_user, "id", None), pid)
            except Exception as e:
                flash(f"Failed to stop worker: {e}", "danger")
                logger.exception("Failed to stop worker (user=%s): %s", getattr(current_user, "id", None), e)
            return redirect(url_for(".worker_settings"))

    # Render GET: create ephemeral csrf token is handled by Flask-WTF; template should include {{ csrf_token() }}
    return render_template("admin/worker_settings.html", status=status, pid=pid, log_file=str(LOG_FILE), required_phrase=current_app.config.get("WORKER_CONFIRM_PHRASE", "RUN_WORKER"))