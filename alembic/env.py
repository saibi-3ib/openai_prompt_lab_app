# --- ▼▼▼【以下を追加】▼▼▼ ---
import os

# models.py の Base をインポート (パスを調整する必要があるかもしれません)
# Assuming models.py is in the parent directory of 'alembic'
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from alembic import context

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
from app.models import DATABASE_URL, Base  # DATABASE_URL もインポート

# --- ▲▲▲【追加ここまで】▲▲▲ ---

# プロジェクトのルートディレクトリをsys.pathに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


load_dotenv()

# プロジェクトのルートディレクトリへの絶対パスを取得
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# .envファイルからデータベースURLを取得、もしくはデフォルトの'app.db'を使用
DB_NAME = os.environ.get("DB_FILENAME", "app.db")
# 絶対パスのデータベースURLを構築
DYNAMIC_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, DB_NAME)}"
print(
    f"--- [alembic/env.py] Connecting to database at: {DYNAMIC_DATABASE_URL} ---"
)  # デバッグ用出力

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# --- ▼▼▼【ここを修正】▼▼▼ ---
# Read DATABASE_URL directly from the imported models module
# instead of relying solely on alembic.ini's load_dotenv setting.
db_url = DATABASE_URL
if not db_url:
    raise ValueError(
        "DATABASE_URL could not be imported from models.py. Check models.py and .env setup."
    )
# Explicitly set the sqlalchemy.url for Alembic using the imported URL
config.set_main_option("sqlalchemy.url", db_url)
print(
    f"--- [alembic/env.py] Using DATABASE_URL from models: {db_url} ---"
)  # デバッグ用出力追加
# --- ▲▲▲【修正ここまで】▲▲▲ ---

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# for SQLAlchemy 2.0 models, Metadata is available via Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    # ... (docstring) ...
    """
    # url = config.get_main_option("sqlalchemy.url") # <-- 元の行をコメントアウトまたは削除
    context.configure(
        # --- ▼▼▼【ここを修正】▼▼▼ ---
        url=DATABASE_URL,  # <-- インポートした DATABASE_URL を直接使う
        # --- ▲▲▲【修正ここまで】▲▲▲ ---
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    # ... (docstring) ...
    """
    # --- ▼▼▼【ここの engine 作成部分を修正】▼▼▼ ---
    # connectable = engine_from_config(
    #     config.get_section(config.config_ini_section, {}),
    #     prefix="sqlalchemy.",
    #     poolclass=pool.NullPool,
    # ) # <-- 元の engine_from_config をコメントアウトまたは削除

    # --- 代わりに、インポートした DATABASE_URL を使って直接 engine を作成 ---
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    # --- ▲▲▲【修正ここまで】▲▲▲ ---

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
