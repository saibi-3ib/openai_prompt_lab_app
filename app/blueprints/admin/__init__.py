from flask import Blueprint

admin_bp = Blueprint(
    "admin", __name__, template_folder="templates", static_folder="static"
)

# ビューを登録するために import
from . import admin_worker  # noqa: E402,F401
