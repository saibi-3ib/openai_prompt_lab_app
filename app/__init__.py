import os
from flask import Flask, current_app
from .config import config_by_name
from .extensions import db, migrate, login_manager, csrf, talisman, limiter, server_session

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, static_folder="static", template_folder="templates")
    # load config object
    app.config.from_object(config_by_name[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Limiter storage: pass storage_uri via init_app for compatibility
    limiter.init_app(app, storage_uri=app.config.get("RATELIMIT_STORAGE_URI"))

    # Server-side sessions (optional)
    if app.config.get("SESSION_TYPE") == "redis":
        from redis import Redis
        redis_client = Redis.from_url(app.config.get("SESSION_REDIS_URL"))
        app.config["SESSION_REDIS"] = redis_client
        server_session.init_app(app)
    else:
        # filesystem/session default is fine for development
        server_session.init_app(app)

    # Talisman (CSP) - respects DISABLE_FORCE_HTTPS flag
    talisman.init_app(app, content_security_policy=app.config.get("CSP", None),
                      force_https=not app.config.get("DISABLE_FORCE_HTTPS", False))

    # Login manager config
    login_manager.login_view = "auth.login"
    login_manager.login_message = "このページにアクセスするにはログインが必要です。"

    # Blueprint registration hooks: import if present; avoid hard failure
    try:
        from .blueprints.auth import auth_bp
        app.register_blueprint(auth_bp)
    except Exception:
        app.logger.debug("auth blueprint not registered yet")

    try:
        from .blueprints.main import main_bp
        app.register_blueprint(main_bp)
    except Exception:
        app.logger.debug("main blueprint not registered yet")

    try:
        from .blueprints.api import api_bp
        app.register_blueprint(api_bp, url_prefix="/api")
    except Exception:
        app.logger.debug("api blueprint not registered yet")

    try:
        from .blueprints.admin import admin_bp
        app.register_blueprint(admin_bp, url_prefix="/admin")
    except Exception:
        app.logger.debug("admin blueprint not registered yet")

    return app