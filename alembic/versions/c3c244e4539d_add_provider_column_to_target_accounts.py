"""Add provider column to target_accounts (idempotent)

Revision ID: c3c244e4539d
Revises: 89abeef2a6d7
Create Date: 2025-11-08 14:31:38.424488
"""

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3c244e4539d"
down_revision = "89abeef2a6d7"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add provider column (nullable) in DB-agnostic way
    try:
        op.add_column(
            "target_accounts",
            sa.Column("provider", sa.String(length=50), nullable=True),
        )
    except Exception:
        # Some DBs / states may raise if column already exists; ignore
        pass

    # 2) Ensure unique index on username (idempotent)
    try:
        op.create_index(
            "ix_target_accounts_username", "target_accounts", ["username"], unique=True
        )
    except Exception:
        pass

    # 3) Seed missing target_accounts for usernames present in collected_posts (idempotent)
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

    # 4) Create FK from collected_posts(username) -> target_accounts(username)
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


def downgrade():
    # Drop FK if exists, drop provider column if supported
    try:
        op.drop_constraint(
            "collected_posts_username_fkey", "collected_posts", type_="foreignkey"
        )
    except Exception:
        pass

    try:
        op.drop_index("ix_target_accounts_username", table_name="target_accounts")
    except Exception:
        pass

    # Dropping a column on SQLite may not be supported; attempt and ignore failures.
    try:
        op.drop_column("target_accounts", "provider")
    except Exception:
        pass
