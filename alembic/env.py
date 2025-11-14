import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# プロジェクトルートをパスに追加してプロジェクト内モジュールを import できるようにする
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

# target metadata（models の Base）を安全に取得する
target_metadata = None
MODELS_DATABASE_URL = None
try:
    # models 内で DB_URL を提供している場合に備えて取得を試みる（失敗しても続行）
    from models import Base as _Base  # type: ignore

    target_metadata = _Base.metadata
    try:
        from models import DATABASE_URL as _MODELS_DB_URL  # type: ignore

        MODELS_DATABASE_URL = _MODELS_DB_URL
    except Exception:
        MODELS_DATABASE_URL = None
except Exception:
    target_metadata = None
    MODELS_DATABASE_URL = None

# 環境変数を最優先で使う（Build/Runtime いずれでも明示的に渡せばそれが優先）
env_database_url = os.environ.get("DATABASE_URL")
if env_database_url:
    db_url = env_database_url
else:
    db_url = MODELS_DATABASE_URL

if not db_url:
    raise RuntimeError(
        "DATABASE_URL is not set in environment and models.DATABASE_URL is not available. "
        "Set DATABASE_URL env var for alembic to run migrations."
    )

# alembic の設定に DB URL を注入
config = context.config
config.set_main_option("sqlalchemy.url", db_url)

# ロギング設定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_online():
    connectable = create_engine(db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=db_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
