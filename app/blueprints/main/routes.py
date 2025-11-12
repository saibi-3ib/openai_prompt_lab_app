from flask import render_template, current_app
from flask_login import login_required
from . import main_bp
from ...extensions import db

@main_bp.route("/")
@login_required
def index():
    # 最小のプレースホルダ実装。実際のロジックは後で移行してください。
    try:
        # もし既に CollectedPost 等のモデルがあるならここで取得できます
        from ...models import CollectedPost
        posts = db.session.query(CollectedPost).order_by(CollectedPost.id.desc()).limit(50).all()
    except Exception:
        current_app.logger.debug("No CollectedPost model or DB access; returning empty list")
        posts = []
    return render_template("index.html", posts=posts)