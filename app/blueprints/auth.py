from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash

from app import extensions as ext

auth_bp = Blueprint("auth", __name__, url_prefix="")


@auth_bp.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("ユーザー名とパスワードを入力してください。", "error")
            return render_template("login.html")

        try:
            # adjust based on your User model fields
            from app.models import User

            user = (
                ext.db.session.query(User)
                .filter(User.username == username)
                .one_or_none()
            )
            if user is None:
                flash("ユーザーが見つかりません。", "error")
                return render_template("login.html")

            # If your model stores hashed password, use check_password_hash
            valid = False
            if getattr(user, "password_hash", None):
                valid = check_password_hash(user.password_hash, password)
            elif getattr(user, "password", None):
                # WARNING: plain password compare only for legacy/dev models
                valid = user.password == password
            else:
                valid = False

            if not valid:
                flash("パスワードが違います。", "error")
                return render_template("login.html")

            login_user(user)
            next_url = request.args.get("next") or url_for("main.index")
            return redirect(next_url)
        except Exception as e:
            ext.db.session.rollback()
            ext.login_manager._get_logger().exception("Login error: %s", e)
            flash("ログイン処理でエラーが発生しました。", "error")
            return render_template("login.html")

    # GET
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))
