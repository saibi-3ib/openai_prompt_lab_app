"""Add is_admin to users

Revision ID: ca92e7b381b0
Revises: 1929cc0687cd
Create Date: 2025-11-12 19:49:49.117656
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "ca92e7b381b0"
down_revision = "1929cc0687cd"
branch_labels = None
depends_on = None


def upgrade():
    # Add is_admin column to users table with a server default of 0 for existing rows.
    # Using server_default ensures existing rows get a value; then we attempt to remove
    # the server_default (some backends may ignore that operation).
    op.add_column(
        "users",
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )
    # try to remove the default so future inserts rely on application logic
    try:
        op.alter_column("users", "is_admin", server_default=None)
    except Exception:
        # Some backends (sqlite via Alembic batch) may not allow altering the default cleanly.
        # It's safe to ignore here; the column will still exist with default applied to existing rows.
        pass


def downgrade():
    # Drop the column on downgrade
    op.drop_column("users", "is_admin")
