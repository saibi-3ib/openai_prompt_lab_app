from flask import Blueprint, render_template
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # トップページ（未ログイン時は簡易案内）
    if current_user and getattr(current_user, "is_authenticated", False):
        return render_template("index.html", user=current_user)
    return render_template("index.html", user=None)


@main_bp.route("/manage")
@login_required
def manage():
    # 管理画面のスケルトン（ログイン必須）
    return render_template("manage.html")
