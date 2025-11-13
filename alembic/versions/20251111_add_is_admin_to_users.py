"""add is_admin to users

Revision ID: 20251111_add_is_admin
Revises: 9675e53be358
Create Date: 2025-11-11 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251111_add_is_admin"
down_revision = "9675e53be358"
branch_labels = None
depends_on = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    """Return True if column_name exists on table_name for the given connection."""
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade():
    bind = op.get_bind()
    # Only add column if it doesn't already exist (idempotent)
    if not _has_column(bind, "users", "is_admin"):
        op.add_column(
            "users",
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        # Remove server_default after backfilling if you prefer (best-effort; may be ignored on some backends)
        try:
            op.alter_column(
                "users", "is_admin", existing_type=sa.Boolean(), server_default=None
            )
        except Exception:
            # Some backends (or older Alembic/SQLite setups) may not support altering defaults; ignore.
            pass


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "users", "is_admin"):
        try:
            op.drop_column("users", "is_admin")
        except Exception:
            # On SQLite dropping columns may not be supported without a table rebuild; ignore for downgrade safety.
            pass
