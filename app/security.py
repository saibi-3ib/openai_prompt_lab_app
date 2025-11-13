from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman


def init_security(app):
    """
    Initialize Talisman (CSP) and Flask-Limiter.
    This version relaxes CSP for development to allow cdn.jsdelivr.net and inline scripts.
    IMPORTANT: 'unsafe-inline' and allowing external CDNs is for development only.
    Remove or tighten these settings before production.
    """

    csp = {
        "default-src": ["'self'"],
        # Allow Tailwind CDN and jsdelivr (Autolinker) and allow inline scripts in dev
        "script-src": [
            "'self'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "'unsafe-inline'",
        ],
        # Explicit element/attr policies (fallbacks)
        "script-src-elem": [
            "'self'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "'unsafe-inline'",
        ],
        "script-src-attr": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "https://cdn.tailwindcss.com", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
    }

    # force_https: respect app.config flag DISABLE_FORCE_HTTPS (True to disable force)
    force_https = not app.config.get("DISABLE_FORCE_HTTPS", False)
    # strict_transport_security: enable only when force_https True
    strict_transport_security = force_https

    Talisman(
        app,
        content_security_policy=csp,
        force_https=force_https,
        strict_transport_security=strict_transport_security,
    )

    # NOTE: avoid passing `app` positionally — older/newer flask-limiter signatures
    # may interpret the first positional arg as key_func. Use keyword arg to be safe.
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
    )

    return limiter
