"""
app/security.py

init_security(app) を提供:
- Flask-Talisman を初期化（CSP/HSTS）。開発環境では HTTPS 強制を無効にします。
- Flask-Limiter を初期化して返します（戻り値は Limiter オブジェクト）。
- key_func は current_user が利用可能であればユーザ単位、それ以外はリモートIPを使用します。
"""
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def _default_csp():
    return {
        "default-src": ["'self'"],
        "script-src": ["'self'", "https://cdn.tailwindcss.com"],
        "style-src": ["'self'", "https://cdn.tailwindcss.com", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
    }

def init_security(app):
    """
    app を受け取り、Talisman と Limiter を初期化する。
    戻り値: limiter (Flask-Limiter のインスタンス)
    """
    # Talisman: 開発時は force_https=False（ローカルで HTTP を使うため）
    csp = _default_csp()
    if app.debug or app.config.get("DISABLE_FORCE_HTTPS", False):
        Talisman(app, content_security_policy=csp, force_https=False)
    else:
        # 本番: force_https=True にして HSTS 有効化
        Talisman(app, content_security_policy=csp, force_https=True, strict_transport_security=True)

    # key_func を関数で定義しておく（実行時に import することで循環参照を避ける）
    def rate_limit_key():
        # current_user をローカルインポートして参照（import を遅延させる）
        try:
            from flask_login import current_user
            if getattr(current_user, "is_authenticated", False):
                return f"user:{current_user.get_id()}"
        except Exception:
            # 何か問題があれば IP を返す
            pass
        return get_remote_address()

    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=["200 per day", "50 per hour"],
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", None)  # Redis 等を指定する場合
    )

    # limiter.init_app を呼ぶ（ここで app に紐付ける）
    limiter.init_app(app)

    return limiter