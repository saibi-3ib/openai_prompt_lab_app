"""add is_admin to users

Revision ID: 20251111_add_is_admin
Revises: <PREV_REVISION_ID>
Create Date: 2025-11-11 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251111_add_is_admin"
down_revision = "9675e53be358"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("users")]
    if "is_admin" not in cols:
        # server_default を用いて既存行に false をセット
        op.add_column(
            "users",
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
        # 必要ならサーバデフォルトを解除（オプション）
        op.alter_column("users", "is_admin", server_default=None)
    else:
        # 既に存在する場合は何もしない（冪等化）
        pass


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("users")]
    if "is_admin" in cols:
        op.drop_column("users", "is_admin")
