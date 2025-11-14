from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf import CSRFProtect

from flask_session import Session

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
talisman = Talisman()
# Do not pass app positionally; init_app will be used.
limiter = Limiter(key_func=get_remote_address)
server_session = Session()


def init_extensions(app):
    """Initialize Flask extensions and attach them to app."""
    # Initialize core extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    talisman.init_app(app)
    limiter.init_app(app)
    server_session.init_app(app)
    login_manager.init_app(app)

    # Some code expects app.login_manager attribute; set it explicitly.
    app.login_manager = login_manager

    # Optional defaults (adjust as needed)
    login_manager.login_view = "main.login"  # 更新が必要なら変更してください
    login_manager.session_protection = "strong"
