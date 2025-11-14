from flask import current_app, render_template
from flask_login import login_required

from ...extensions import db

# Adjust import path if needed
from ...models import CollectedPost, TargetAccount
from . import main_bp


@main_bp.route("/")
@login_required
def index():
    # existing index implementation
    try:
        posts = (
            db.session.query(CollectedPost)
            .order_by(CollectedPost.id.desc())
            .limit(50)
            .all()
        )
    except Exception:
        current_app.logger.debug(
            "No CollectedPost model or DB access; returning empty list"
        )
        posts = []
    return render_template("index.html", posts=posts)


@main_bp.route("/manage")
@login_required
def manage():
    # Placeholder: list settings / controls
    try:
        settings = (
            db.session.query().execute("SELECT key, value FROM settings")
            if False
            else []
        )
    except Exception:
        settings = []
    return render_template("manage.html", settings=settings)


@main_bp.route("/accounts")
@login_required
def accounts():
    # show linked target accounts
    try:
        accounts = (
            db.session.query(TargetAccount).order_by(TargetAccount.id.desc()).all()
        )
    except Exception:
        current_app.logger.debug(
            "No TargetAccount model or DB access; returning empty list"
        )
        accounts = []
    return render_template("accounts.html", accounts=accounts)


@main_bp.route("/history")
@login_required
def history():
    # placeholder: recent analysis results
    try:
        results = (
            db.session.execute(
                "SELECT * FROM analysis_results ORDER BY analyzed_at DESC LIMIT 50"
            ).fetchall()
            if False
            else []
        )
    except Exception:
        results = []
    return render_template("history.html", results=results)


@main_bp.route("/_debug_login_manager")
def _debug_login_manager():
    from flask import current_app

    from app import extensions as ext

    info = {
        "current_app_repr": repr(current_app._get_current_object()),
        "hasattr_login_manager_on_current_app": hasattr(
            current_app._get_current_object(), "login_manager"
        ),
        "current_app_login_manager_is_ext": getattr(
            current_app._get_current_object(), "login_manager", None
        )
        is getattr(ext, "login_manager", None),
        "ext_login_manager_repr": repr(getattr(ext, "login_manager", None)),
        "current_app_login_manager_repr": repr(
            getattr(current_app._get_current_object(), "login_manager", None)
        ),
    }
    # Log for server console as well
    current_app.logger.info("_debug_login_manager: %s", info)
    return info
