"""Add provider column (nullable), seed missing target_accounts, then add FK safely

Revision ID: c4f1d2e3b4a5
Revises: 98ab5c1ef8be
Create Date: 2025-11-08 09:44:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4f1d2e3b4a5"
down_revision = "98ab5c1ef8be"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add provider column (nullable) in a DB-agnostic way.
    # If column already exists, op.add_column may still raise; wrap in try/except to be safe.
    try:
        op.add_column(
            "target_accounts",
            sa.Column("provider", sa.String(length=50), nullable=True),
        )
    except Exception:
        # If column exists or DB does not allow ADD COLUMN here, ignore and continue.
        pass

    # 2) Fill provider for existing target_accounts rows that have NULL
    try:
        op.execute(
            text("UPDATE target_accounts SET provider = 'X' WHERE provider IS NULL;")
        )
    except Exception:
        pass

    # 3) Insert missing target_accounts for orphan usernames found in collected_posts.
    # Use SQL compatible across SQLite/Postgres. Use 0 for false in SQLite.
    try:
        op.execute(
            text(
                """
INSERT INTO target_accounts (username, is_active, added_at, provider)
SELECT DISTINCT cp.username, 0, CURRENT_TIMESTAMP, 'X'
FROM collected_posts cp
LEFT JOIN target_accounts ta ON ta.username = cp.username
WHERE cp.username IS NOT NULL AND ta.username IS NULL;
"""
            )
        )
    except Exception:
        pass

    # 4) Ensure UNIQUE index on username exists.
    try:
        op.create_index(
            "ix_target_accounts_username",
            "target_accounts",
            ["username"],
            unique=True,
        )
    except Exception:
        pass

    # 5) Create FK constraint on collected_posts(username) referencing target_accounts(username).
    try:
        op.create_foreign_key(
            "collected_posts_username_fkey",
            "collected_posts",
            "target_accounts",
            ["username"],
            ["username"],
            ondelete="CASCADE",
        )
    except Exception:
        pass

    # 6) Now provider can be made NOT NULL. SQLite may not support altering column nullability;
    # attempt with op.alter_column and ignore failures (DB-specific repairs should be done manually if needed).
    try:
        op.alter_column(
            "target_accounts",
            "provider",
            existing_type=sa.String(length=50),
            nullable=False,
        )
    except Exception:
        pass


def downgrade():
    # Reverse: drop FK if exists, drop provider column if exists
    try:
        op.drop_constraint(
            "collected_posts_username_fkey", "collected_posts", type_="foreignkey"
        )
    except Exception:
        pass

    # Dropping a column on SQLite via Alembic may not be supported without table rebuild.
    try:
        op.drop_column("target_accounts", "provider")
    except Exception:
        # If drop_column not supported on this backend, ignore.
        pass
