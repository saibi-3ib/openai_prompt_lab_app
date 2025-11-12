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

    # Initialize LoginManager and register user_loader
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "このページにアクセスするにはログインが必要です。"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            # import here to avoid circular imports
            from .models import User
            # SQLAlchemy 2.0: use Session.get
            return db.session.get(User, int(user_id))
        except Exception:
            current_app.logger.exception("Failed to load user id=%s", user_id)
            return None

    # Limiter: initialize without storage_uri kwarg (use app.config['RATELIMIT_STORAGE_URI'])
    limiter.init_app(app)

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

    # Blueprint registration hooks: import if present; avoid hard failure
    try:
        from .blueprints.auth import auth_bp
        app.register_blueprint(auth_bp)
    except Exception as e:
        app.logger.exception("auth blueprint import failed: %s", e)

    try:
        from .blueprints.main import main_bp
        app.register_blueprint(main_bp)
    except Exception as e:
        app.logger.exception("main blueprint import failed: %s", e)

    try:
        from .blueprints.api import api_bp
        app.register_blueprint(api_bp, url_prefix="/api")
    except Exception as e:
        app.logger.exception("api blueprint import failed: %s", e)

    try:
        from .blueprints.admin import admin_bp
        app.register_blueprint(admin_bp, url_prefix="/admin")
    except Exception as e:
        app.logger.exception("admin blueprint import failed: %s", e)

    return app