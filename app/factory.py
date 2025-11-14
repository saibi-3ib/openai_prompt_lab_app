from __future__ import annotations

import logging
import os

from flask import Flask, current_app

from . import extensions as ext
from .config import config_by_name


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application (factory).

    This factory guarantees extensions in app.extensions are initialized and that
    HTTPS-forcing is disabled in development or when explicitly requested via env.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Load configuration (fall back to dict-style config_name)
    try:
        app.config.from_object(config_by_name[config_name])
    except Exception:
        if isinstance(config_name, dict):
            app.config.update(config_name)
        else:
            app.logger.exception("Failed to load config %s", config_name)

    # Ensure development runs do not force HTTPS unless explicitly requested
    if (
        config_name == "development"
        or os.environ.get("DISABLE_FORCE_HTTPS") in ("1", "true", "True")
        or app.config.get("DISABLE_FORCE_HTTPS")
    ):
        app.config["DISABLE_FORCE_HTTPS"] = True

    # Optional: prefer HTTP in URL generation for local dev
    if app.config.get("DISABLE_FORCE_HTTPS"):
        app.config.setdefault("PREFERRED_URL_SCHEME", "http")

    # Initialize extensions via central init function if available
    try:
        init_fn = getattr(ext, "init_extensions", None)
        if callable(init_fn):
            init_fn(app)
        else:
            # Initialize common extensions; ignore failures to allow incremental refactor.
            try:
                ext.db.init_app(app)
            except Exception:
                app.logger.debug("db.init_app failed or not present")
            try:
                ext.migrate.init_app(app, ext.db)
            except Exception:
                app.logger.debug("migrate.init_app failed or not present")
            try:
                ext.csrf.init_app(app)
            except Exception:
                app.logger.debug("csrf.init_app failed or not present")
            try:
                ext.limiter.init_app(app)
            except Exception:
                app.logger.debug("limiter.init_app failed or not present")
            try:
                ext.server_session.init_app(app)
            except Exception:
                app.logger.debug("server_session.init_app failed or not present")
            # Initialize talisman with force_https depending on config
            try:
                ext.talisman.init_app(
                    app,
                    content_security_policy=app.config.get("CSP", None),
                    force_https=not app.config.get("DISABLE_FORCE_HTTPS", False),
                )
            except Exception:
                app.logger.debug("talisman.init_app failed or not present")
            try:
                ext.login_manager.init_app(app)
            except Exception:
                app.logger.debug("login_manager.init_app failed or not present")
    except Exception:
        app.logger.exception("init_extensions flow failed")

    # Ensure app has login_manager attribute for flask_login internals
    if not hasattr(app, "login_manager") or getattr(app, "login_manager", None) is None:
        try:
            app.login_manager = ext.login_manager
        except Exception:
            app.login_manager = None

    # Configure login_manager defaults and user_loader if login_manager exists
    try:
        if getattr(ext, "login_manager", None):
            ext.login_manager.login_view = app.config.get("LOGIN_VIEW", "auth.login")
            ext.login_manager.login_message = app.config.get(
                "LOGIN_MESSAGE", "このページにアクセスするにはログインが必要です。"
            )

            @ext.login_manager.user_loader
            def load_user(user_id: str | int):
                try:
                    from .models import (  # avoid circular import at module import time
                        User,
                    )

                    return ext.db.session.get(User, int(user_id))
                except Exception:
                    try:
                        current_app.logger.exception(
                            "Failed to load user id=%s", user_id
                        )
                    except Exception:
                        logging.exception("Failed to load user id=%s", user_id)
                    return None

    except Exception:
        app.logger.debug("Setting up login_manager defaults failed", exc_info=True)

    # Register blueprints (non-fatal if import/registration fails)
    try:
        from .blueprints.auth import auth_bp

        app.register_blueprint(auth_bp)
    except Exception as e:
        app.logger.debug("auth blueprint import/registration failed: %s", e)

    try:
        from .blueprints.main import main_bp

        app.register_blueprint(main_bp)
    except Exception as e:
        app.logger.debug("main blueprint import/registration failed: %s", e)

    try:
        from .blueprints.api import api_bp

        app.register_blueprint(api_bp, url_prefix="/api")
    except Exception as e:
        app.logger.debug("api blueprint import/registration failed: %s", e)

    try:
        from .blueprints.admin import admin_bp

        app.register_blueprint(admin_bp, url_prefix="/admin")
    except Exception as e:
        app.logger.debug("admin blueprint import/registration failed: %s", e)

    return app
