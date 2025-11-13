import os


class Config:
    SECRET_KEY = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or "change-me-locally"
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    DISABLE_FORCE_HTTPS = os.environ.get("DISABLE_FORCE_HTTPS", "0") in (
        "1",
        "true",
        "True",
    )

    # Development CSP relaxed by default; override in production
    CSP = {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "'unsafe-inline'",
        ],
        "style-src": ["'self'", "https://cdn.tailwindcss.com", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    SESSION_TYPE = os.environ.get("SESSION_TYPE", "filesystem")
    SESSION_REDIS_URL = os.environ.get("SESSION_REDIS_URL", "redis://127.0.0.1:6379/1")


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    RATELIMIT_STORAGE_URI = os.environ.get(
        "RATELIMIT_STORAGE_URI", "redis://127.0.0.1:6379/0"
    )
    CSP = {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:"],
    }


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    RATELIMIT_STORAGE_URI = "memory://"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
