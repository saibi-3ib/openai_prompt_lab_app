import glob
import os
import re
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

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

# 環境変数優先で DB URL を決定（PG_DSN を最優先、次に DATABASE_URL、最後に models の値）
env_db_dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
if env_db_dsn:
    db_url = env_db_dsn
else:
    db_url = MODELS_DATABASE_URL

if not db_url:
    raise RuntimeError(
        "DATABASE_URL/PG_DSN is not set in environment and models.DATABASE_URL is not available. "
        "Set DATABASE_URL or PG_DSN env var for alembic to run migrations."
    )


# 事前チェック: DB に保存されている alembic_version とローカルの alembic/versions を比較して、
# DB に存在するがローカルに該当ファイルがない rev があれば早期にわかりやすくエラーにする。
def _local_revisions(versions_dir=None):
    if versions_dir is None:
        versions_dir = os.path.join(os.path.dirname(__file__), "versions")
    revs = set()
    for path in glob.glob(os.path.join(versions_dir, "*.py")):
        try:
            s = open(path, "r", encoding="utf-8").read()
        except Exception:
            continue
        m = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", s)
        if m:
            revs.add(m.group(1))
    return revs


def _db_revisions(url):
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            # alembic_version テーブルが存在しない場合は空セットを返す
            try:
                rows = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchall()
                return set(r[0] for r in rows if r and r[0])
            except Exception:
                return set()
    except Exception:
        # DB へ接続できない場合は None を返して上位で対処
        return None


_local_revs = _local_revisions()
_db_revs = _db_revisions(db_url)

if _db_revs is None:
    # DB に接続できない（または接続時に問題があった）場合は、詳細を示すエラーにする
    raise RuntimeError(
        "Could not connect to database using the resolved URL. "
        "Ensure the environment variable PG_DSN or DATABASE_URL is set and reachable from this process. "
        "Resolved DB URL (masked) shown via masked printing in your shell for safety."
    )

# DB にあるがローカルに存在しないリビジョンを検出したら、わかりやすく止める
_missing = sorted([r for r in _db_revs if r and r not in _local_revs])
if _missing:
    # ユーザーが次にとるべき代表的な解決法を示す（プレースホルダ作成 or baseline + stamp）
    raise RuntimeError(
        "The database's alembic_version contains revision(s) that are not present in this repository: "
        f"{_missing}\n\n"
        "This typically happens when the database was migrated with a different set of migration files, "
        "or when migration files have been removed from the repo. Choose one of the following remediation steps:\n\n"
        "1) Restore the missing migration files into alembic/versions/ so that Alembic can build the revision map.\n\n"
        "2) If you intentionally want to treat the current DB schema as the canonical baseline and discard old migrations, "
        "create a single baseline revision file (no-op) in alembic/versions and then run on the target environment:\n"
        "   alembic stamp <baseline_revision_id>\n\n"
        "   Example placeholder baseline file contents (create as alembic/versions/<REV>_baseline.py):\n\n"
        '   """baseline: adopt current DB schema as starting point\n\n'
        "   Revision ID: <REV>\n"
        "   Revises:\n"
        "   Create Date: 2025-11-XX XX:XX:XX\n"
        '   """\n'
        "   from alembic import op\n"
        "   import sqlalchemy as sa\n\n"
        "   revision = '<REV>'\n"
        "   down_revision = None\n"
        "   branch_labels = None\n"
        "   depends_on = None\n\n"
        "   def upgrade():\n"
        "       pass\n\n"
        "   def downgrade():\n"
        "       pass\n\n"
        "3) Alternatively create simple placeholder (no-op) migration files named like <MISSING_REV>_placeholder.py "
        "under alembic/versions for each missing revision id (this will satisfy Alembic's revision map). Example of a "
        "placeholder file:\n\n"
        "   revision = '<MISSING_REV>'\n"
        "   down_revision = None\n\n"
        "Perform these fixes in your repository (or create a local branch with the placeholder files), then re-run "
        "the alembic command.\n"
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
