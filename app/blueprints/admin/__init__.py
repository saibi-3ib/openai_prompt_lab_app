"""
Admin blueprint wrapper.

If you have an existing top-level admin_worker.py (produced earlier),
this module will try to reuse its `admin_bp`. If not found, it creates
a minimal admin blueprint so app startup doesn't fail. Replace this
wrapper by moving admin_worker into app/blueprints/admin if you prefer.
"""
from importlib import import_module
from flask import Blueprint, current_app

admin_bp = None

# Try to import admin_blueprint from app.admin_worker (if you moved it),
# else try top-level admin_worker module (legacy location).
for mod_name in ("app.admin_worker", "admin_worker"):
    try:
        mod = import_module(mod_name)
        admin_bp = getattr(mod, "admin_bp", None)
        if admin_bp is not None:
            current_app and current_app.logger.debug(f"admin blueprint loaded from {mod_name}")
            break
    except Exception:
        # import failure is fine here; we'll fallback to placeholder
        pass

if admin_bp is None:
    # Fallback: create a minimal admin blueprint (so create_app won't error)
    admin_bp = Blueprint("admin", __name__, template_folder="templates")

    @admin_bp.route("/worker", methods=["GET"])
    def _admin_worker_placeholder():
        return "Admin worker UI placeholder (no admin blueprint module found)", 200