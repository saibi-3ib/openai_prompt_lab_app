from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    """Create and configure the Flask application (minimal)."""

    app = Flask(__name__, instance_relative_config=True)

    if config:
        app.config.update(config)

    # initialize extensions if you have app/extensions.py
    try:
        from .extensions import init_extensions

        init_extensions(app)
    except Exception:
        # ignore during incremental refactor
        pass

    # register blueprints
    try:
        from .blueprints.main import main_bp

        app.register_blueprint(main_bp)
    except Exception:
        # ignore if blueprint not yet migrated
        pass

    return app
