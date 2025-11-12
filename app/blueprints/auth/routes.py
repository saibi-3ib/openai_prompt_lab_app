from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, current_user, login_required
from . import auth_bp
from ...extensions import db
# Adjust import path of User to your models location; if using app/models.py:
from ...models import User
from werkzeug.security import check_password_hash

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = db.session.query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("ログインしました。", "success")
            next_page = request.args.get("next") or url_for("main.index")
            return redirect(next_page)
        flash("ユーザー名またはパスワードが無効です。", "error")
    return render_template("auth/login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))