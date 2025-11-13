from flask import abort, current_app, render_template
from flask_login import current_user, login_required

from . import admin_bp


# シンプルな管理チェック補助（実際のロジックに合わせて調整してください）
def require_admin_or_abort():
    if not getattr(current_user, "is_authenticated", False):
        abort(401)
    if getattr(current_user, "is_admin", False):
        return
    admin_users = current_app.config.get("ADMIN_USERS") or current_app.config.get(
        "ADMIN_USERS_LIST"
    )
    if isinstance(admin_users, str):
        admin_users = [s.strip() for s in admin_users.split(",") if s.strip()]
    if not admin_users:
        # フォールバック: ADMIN_USERS が未設定なら許可／拒否の方針を調整してください
        return
    if current_user.username not in admin_users:
        abort(403)


@admin_bp.route("/worker", methods=["GET", "POST"])
@login_required
def worker_settings():
    require_admin_or_abort()
    # ここに元の admin_worker の実装を統合してください。
    # とりあえず最小限のテンプレートを返します。
    return render_template("admin/worker.html")
